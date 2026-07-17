# =============================================================================
# xGEOID20B Batch Extraction Script
# NGS Experimental Geoid Model 2020 (B model - with airborne gravity)
# Interpolation: Biquadratic (3x3 stencil)
#
# --- COORDINATE INPUT REQUIREMENTS ---
# Horizontal Reference Frame: IGS14
# Ellipsoid:                  GRS80
# Latitude/Longitude:         Decimal degrees
# Ellipsoidal Height:         Meters
# 
# --- LONGITUDE CONVENTION WARNING ---
# This script expects POSITIVE WEST longitudes as exported by
# OPUS and other NGS tools (e.g., 133.024 for southeastern Alaska).
# The script automatically negates positive longitudes and converts
# to 0-360 east convention internally for grid lookup.
#
# WARNING: Do NOT mix negative-west (-133.024) and positive-west (133.024)
#          longitudes in the same input CSV. The script will detect negative
#          longitudes, flag them in the log file, and skip negation for
#          those rows — but mixed convention inputs likely will produce incorrect
#          results. Ensure all longitudes in the input file use the same
#          convention
#
# NOTE: OPUS-derived coordinates and ellipsoidal heights are in NAD83(2011),
#       which is nominally equivalent to IGS14 at the cm level for most
#       practical geodetic applications. If sub-centimeter accuracy is
#       required, a formal frame transformation should be applied prior
#       to running this script.
#
# Reference Epoch T0:         2005.0
# Processing Epoch:           2020.0 (January 1, 2020)
# Author:                     Nate Murry, NOAA/NOS/CO-OPS, 7/16/2026
# Version:                    2.2.0
#
# --- DEFAULT BEHAVIOR (out-of-the-box) ---
# The tool runs NON-INTERACTIVELY by default:
#   - Reads the single input CSV from the input/ folder.
#   - Writes UTC-timestamped output + log files to the output/ folder.
#   - OVERWRITES without asking (overwrite = always). Timestamps are to
#     the minute, so runs normally produce distinct files.
# All timestamps are UTC (GMT). Behavior is configurable in config.ini.
# =============================================================================


import netCDF4 as nc
import numpy as np
import csv
import os
import sys
import configparser
from datetime import datetime, timezone


__version__ = '2.2.0'


# --- File Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILENAME = 'config.ini'

# The xGEOID20 GGXF grid file (~403 MB) is NOT included in this repository.
# It must be downloaded separately from NGS and placed in the GGXF/ folder:
#     https://geodesy.noaa.gov/research/data/xGEOID20.ggxf
#
# Resolution order (see resolve_ggxf_path):
#   1. XGEOID20_GGXF environment variable (full path override)
#   2. config.ini [paths] ggxf_file (if set)
#   3. <script_dir>/GGXF/xGEOID20.ggxf   (default bundled location)
GGXF_DIR = os.path.join(SCRIPT_DIR, 'GGXF')
GGXF_FILENAME = 'xGEOID20.ggxf'
GGXF_ENV_VAR = 'XGEOID20_GGXF'
GGXF_DOWNLOAD_URL = 'https://geodesy.noaa.gov/research/data/xGEOID20.ggxf'


# --- Defaults (used when config.ini is absent or a value is blank) ---
DEFAULTS = {
    'ggxf_file': '',
    'input_dir': 'input',
    'output_dir': 'output',
    'model': 'xGEOID20B',
    'epoch': 2020.0,
    't0': 2005.0,
    'overwrite': 'always',
}


# --- Constants (populated from config in run_batch; defaults here) ---
MODEL = 'xGEOID20B'
EPOCH = 2020.0
T0 = 2005.0


# --- Region Definitions ---
REGIONS = {
    'xGEOID20A': {
        'CONUSPAC': {
            'var': 'geoidHeightA',
            'lat0': 0.0, 'lon0': 180.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 1
        },
        'Guam and Northern Mariana Islands': {
            'var': 'geoidHeightA',
            'lat0': 11.0, 'lon0': 143.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 2
        },
        'American Samoa': {
            'var': 'geoidHeightA',
            'lat0': -16.0, 'lon0': 186.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 2
        },
    },
    'xGEOID20B': {
        'CONUSPAC': {
            'var': 'geoidHeightB',
            'lat0': 0.0, 'lon0': 180.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 1
        },
        'Guam and Northern Mariana Islands': {
            'var': 'geoidHeightB',
            'lat0': 11.0, 'lon0': 143.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 2
        },
        'American Samoa': {
            'var': 'geoidHeightB',
            'lat0': -16.0, 'lon0': 186.0, 'dlat': 1/60, 'dlon': 1/60,
            'nrows': None, 'ncols': None, 'priority': 2
        },
    },
    'xDGEOID20': {
        'Global': {
            'var': 'geoidVelocity',
            'lat0': -89.75, 'lon0': 0.0, 'dlat': 0.25, 'dlon': 0.25,
            'nrows': None, 'ncols': None, 'priority': 1
        },
    },
}


# =============================================================================
# Utility Functions
# =============================================================================

def load_grid_metadata(ds):
    """Read actual grid dimensions from file at runtime."""
    for model_name, model_grp in ds.groups.items():
        for region_name, region_grp in model_grp.groups.items():
            if model_name in REGIONS and region_name in REGIONS[model_name]:
                var_name = REGIONS[model_name][region_name]['var']
                if var_name in region_grp.variables:
                    shape = region_grp.variables[var_name].shape
                    REGIONS[model_name][region_name]['nrows'] = shape[0]
                    REGIONS[model_name][region_name]['ncols'] = shape[1]


def normalize_lon(lon):
    """Convert any longitude to 0-360 east convention."""
    return lon % 360.0


def correct_ngs_lon(lon, pid='UNKNOWN'):
    """
    Detect and correct positive west longitudes.

    NGS commonly exports west longitudes as positive values
    (e.g., 133.024 instead of -133.024).

    This function negates positive longitudes (NGS convention)
    before normalizing to 0-360 east for internal grid lookup.

    WARNING: Do not mix negative-west and positive-west longitudes
             in the same input file. Negative longitudes are passed
             through unchanged but will be flagged in the log file
             as a potential convention mismatch.

    Parameters
    ----------
    lon : float
        Input longitude value.
    pid : str
        OPUS_PID of the point, used for log warning if needed.

    Returns
    -------
    tuple : (lon360, warning_message or None)
        lon360   : float, longitude normalized to 0-360
        warning  : str or None, warning message if negative lon detected
    """
    warning = None

    if lon < 0:
        # Negative longitude detected — possible convention mismatch
        warning = (
            f"  OPUS_PID: {pid}\n"
            f"  Warning:  Negative longitude ({lon}) detected. "
            f"Script expects NGS positive-west convention.\n"
            f"  Action:   Sign NOT negated — passed through as-is.\n"
            f"  Check:    Verify this point's result is correct.\n"
            f"            Mixed longitude conventions in input may\n"
            f"            produce incorrect grid lookups.\n"
        )
        lon360 = normalize_lon(lon)

    elif lon > 180:
        # Already in 0-360 format — pass through
        lon360 = normalize_lon(lon)

    else:
        # Positive west longitude (NGS convention) — negate and normalize
        lon360 = normalize_lon(-lon)

    return lon360, warning


def point_in_grid(lat, lon360, meta):
    """Check if a lat/lon point falls within a grid's bounds."""
    lat0 = meta['lat0']
    lon0 = meta['lon0']
    dlat = meta['dlat']
    dlon = meta['dlon']
    nrows = meta['nrows']
    ncols = meta['ncols']

    if nrows is None or ncols is None:
        return False

    lat_max = lat0 + dlat * (nrows - 1)
    lon_max = lon0 + dlon * (ncols - 1)

    return (lat0 <= lat <= lat_max) and (lon0 <= lon360 <= lon_max)


def load_config():
    """
    Load configuration from config.ini, falling back to built-in defaults.

    The config file is optional. Missing files, missing sections, missing
    keys, or blank values all fall back to DEFAULTS. This keeps the tool
    working out of the box.

    Returns
    -------
    dict
        Resolved configuration with keys: ggxf_file, input_dir, output_dir,
        model, epoch (float), t0 (float), overwrite.
    """
    cfg = dict(DEFAULTS)
    config_path = os.path.join(SCRIPT_DIR, CONFIG_FILENAME)

    if os.path.isfile(config_path):
        parser = configparser.ConfigParser()
        try:
            parser.read(config_path, encoding='utf-8')
        except configparser.Error as e:
            print(f"WARNING: Could not parse {CONFIG_FILENAME}: {e}")
            print(f"         Falling back to built-in defaults.")
            return cfg

        def get(section, key, default):
            if parser.has_option(section, key):
                val = parser.get(section, key).strip()
                return val if val != '' else default
            return default

        cfg['ggxf_file'] = get('paths', 'ggxf_file', cfg['ggxf_file'])
        cfg['input_dir'] = get('paths', 'input_dir', cfg['input_dir'])
        cfg['output_dir'] = get('paths', 'output_dir', cfg['output_dir'])
        cfg['model'] = get('model', 'model', cfg['model'])
        cfg['overwrite'] = get('options', 'overwrite', cfg['overwrite']).lower()

        # Numeric fields
        for key, section in (('epoch', 'model'), ('t0', 'model')):
            raw = get(section, key, None)
            if raw is not None:
                try:
                    cfg[key] = float(raw)
                except ValueError:
                    print(f"WARNING: config {section}.{key} = '{raw}' is not "
                          f"numeric; using default {DEFAULTS[key]}.")
                    cfg[key] = DEFAULTS[key]

    # Validate overwrite value
    if cfg['overwrite'] not in ('always', 'never', 'prompt'):
        print(f"WARNING: config options.overwrite = '{cfg['overwrite']}' is "
              f"invalid; using 'always'.")
        cfg['overwrite'] = 'always'

    return cfg


def resolve_dir(dir_value):
    """Resolve a directory value: absolute as-is, else relative to SCRIPT_DIR."""
    if os.path.isabs(dir_value):
        return dir_value
    return os.path.join(SCRIPT_DIR, dir_value)


def check_file_overwrite(filepath, mode='always'):
    """
    Decide whether to (over)write a file according to the overwrite policy.

    Parameters
    ----------
    filepath : str
        Full path to the file to check.
    mode : str
        'always' - overwrite without asking (default, non-interactive).
        'never'  - do not overwrite an existing file.
        'prompt' - ask the user y/n (interactive terminals only).

    Returns
    -------
    bool
        True if OK to proceed (file doesn't exist, or overwrite allowed).
        False if the existing file must not be overwritten.
    """
    if not os.path.exists(filepath):
        return True

    name = os.path.basename(filepath)

    if mode == 'always':
        print(f"  [!] Overwriting existing file: {name}")
        return True

    if mode == 'never':
        print(f"  [!] File exists, overwrite=never: {name} (skipping)")
        return False

    # mode == 'prompt' — but fall back to 'always' if stdin isn't interactive
    if not sys.stdin or not sys.stdin.isatty():
        print(f"  [!] File exists: {name} (non-interactive; overwriting)")
        return True

    print(f"\n  [!] File already exists: {name}")
    while True:
        response = input(f"      Overwrite? (y/n): ").strip().lower()
        if response == 'y':
            print(f"      Overwriting {name}...")
            return True
        elif response == 'n':
            print(f"      Skipping - {name} will not be overwritten.")
            return False
        else:
            print("      Please enter 'y' or 'n'.")


def find_input_file(input_dir):
    """
    Find the single input CSV in input_dir (a file whose name contains
    'input' and ends in .csv, case-insensitive).

    Falls back to SCRIPT_DIR if input_dir does not exist (backward
    compatibility with the pre-2.1 layout).

    Returns
    -------
    tuple : (path_or_None, error_message_or_None)
        path : full path to the single input file, or None.
        error: a message if zero or multiple candidates were found.
    """
    search_dir = input_dir if os.path.isdir(input_dir) else SCRIPT_DIR

    candidates = [
        os.path.join(search_dir, f)
        for f in sorted(os.listdir(search_dir))
        if f.lower().endswith('.csv') and 'input' in f.lower()
    ]

    if not candidates:
        return None, (
            f"No input CSV found in: {search_dir}\n"
            f"       A file whose name contains 'input' and ends in .csv "
            f"is required."
        )

    if len(candidates) > 1:
        listing = '\n'.join(f"         - {os.path.basename(c)}"
                            for c in candidates)
        return None, (
            f"Multiple input CSV files found in: {search_dir}\n"
            f"       Please keep only one:\n{listing}"
        )

    return candidates[0], None


def _timestamped_name(input_path, suffix, ext, run_utc):
    """Build '<inputbase>_<suffix>_YYYYMMDDThhmmZ.<ext>' from input name."""
    base = os.path.splitext(os.path.basename(input_path))[0].lower()
    # Drop a trailing '_input' / 'input' token so we don't get 'input_output'
    if base.endswith('_input'):
        base = base[:-len('_input')]
    elif base.endswith('input'):
        base = base[:-len('input')].rstrip('_')
    stamp = run_utc.strftime('%Y%m%dT%H%MZ')
    return f"{base}_{suffix}_{stamp}.{ext}"


def generate_output_filename(input_path, output_dir, run_utc):
    """UTC-timestamped output CSV path in output_dir."""
    return os.path.join(output_dir,
                        _timestamped_name(input_path, 'output', 'csv', run_utc))


def generate_log_filename(input_path, output_dir, run_utc):
    """UTC-timestamped batch log path in output_dir."""
    return os.path.join(output_dir,
                        _timestamped_name(input_path, 'batch_log', 'txt', run_utc))


def resolve_ggxf_path(config_ggxf_file=''):
    """
    Locate the xGEOID20 GGXF grid file.

    The ~403 MB GGXF file is NOT bundled with this tool. The user must
    download it from NGS and place it in the GGXF/ folder (or point the
    XGEOID20_GGXF environment variable / config.ini at it).

    Resolution order
    ----------------
    1. XGEOID20_GGXF environment variable, if set (full path override).
    2. config.ini [paths] ggxf_file, if set (passed in as config_ggxf_file).
    3. <script_dir>/GGXF/xGEOID20.ggxf (default bundled location).

    Parameters
    ----------
    config_ggxf_file : str
        Value of [paths] ggxf_file from config.ini (may be blank).

    Returns
    -------
    str
        Full path to an existing GGXF file.

    Raises
    ------
    FileNotFoundError
        If no GGXF file can be found, with guidance on how to obtain it.
    """
    # 1. Environment variable override
    env_path = os.environ.get(GGXF_ENV_VAR)
    if env_path:
        if os.path.isfile(env_path):
            return env_path
        raise FileNotFoundError(
            f"{GGXF_ENV_VAR} is set to a file that does not exist:\n"
            f"    {env_path}\n"
        )

    # 2. config.ini ggxf_file
    if config_ggxf_file:
        cfg_path = (config_ggxf_file if os.path.isabs(config_ggxf_file)
                    else os.path.join(SCRIPT_DIR, config_ggxf_file))
        if os.path.isfile(cfg_path):
            return cfg_path
        raise FileNotFoundError(
            f"config.ini [paths] ggxf_file points to a file that does not "
            f"exist:\n    {cfg_path}\n"
        )

    # 3. Default bundled location
    default_path = os.path.join(GGXF_DIR, GGXF_FILENAME)
    if os.path.isfile(default_path):
        return default_path

    # Not found anywhere — fail fast with actionable guidance
    raise FileNotFoundError(
        "xGEOID20 GGXF grid file not found.\n\n"
        "  Expected location:\n"
        f"    {default_path}\n\n"
        "  This ~403 MB file is NOT included in the repository and must be\n"
        "  downloaded separately from NGS:\n"
        f"    {GGXF_DOWNLOAD_URL}\n\n"
        f"  Place it in the GGXF folder, or set the {GGXF_ENV_VAR} environment\n"
        "  variable / config.ini ggxf_file to its full path.\n"
    )


# =============================================================================
# Bi-quadratic Interpolation
# =============================================================================

def safe_node_value(var, i, j):
    """
    Fetch a single grid node value as a float, guarding against
    masked / fill / NaN entries.

    netCDF4 returns MaskedArrays by default. If a node is masked
    (a coverage gap or _FillValue) or NaN, using it in interpolation
    would silently poison the result. The current xGEOID20 grids are
    fully populated (no masked/fill nodes), but this guard makes the
    tool fail loudly rather than silently if a future grid revision
    introduces gaps.

    Parameters
    ----------
    var : netCDF4.Variable
        The open grid variable.
    i, j : int
        Node indices.

    Returns
    -------
    float
        The node value.

    Raises
    ------
    ValueError
        If the node is masked or NaN.
    """
    value = var[i, j]
    if np.ma.is_masked(value):
        raise ValueError(
            f"Grid node ({i}, {j}) is masked (coverage gap / fill value)."
        )
    value = float(value)
    if np.isnan(value):
        raise ValueError(f"Grid node ({i}, {j}) is NaN.")
    return value


def biquadratic_interp(grid_data, i_frac, j_frac, nrows, ncols):
    """
    Biquadratic interpolation on a 3x3 stencil.

    Parameters
    ----------
    grid_data : callable
        Function(i, j) -> float that retrieves a grid node value.
    i_frac : float
        Fractional row index of the query point.
    j_frac : float
        Fractional column index of the query point.
    nrows : int
        Total number of rows in the grid.
    ncols : int
        Total number of columns in the grid.

    Returns
    -------
    float
        Interpolated value.

    Notes
    -----
    Biquadratic interpolation fits a 2nd-order polynomial surface through
    a 3x3 neighborhood of grid nodes. The stencil center is chosen as the
    nearest node, with local coordinates (s, t) measured in grid-cell units
    relative to that center (roughly the range [-1, 1] for interior points).

    Basis functions are 1D quadratic Lagrange polynomials:
        L0(x) = x*(x-1)/2   (left/bottom node)
        L1(x) = (1-x^2)     (center node)
        L2(x) = x*(x+1)/2   (right/top node)

    The 2D surface is the tensor product:
        f(s,t) = sum_m sum_n L_m(s) * L_n(t) * f_mn

    If a query point lies within half a cell of a grid edge, the stencil
    center is clamped inward so a full 3x3 neighborhood exists. The result
    is then a (mild) extrapolation. Callers may inspect the returned
    `edge_clamped` flag to warn about such points.
    """

    # --- Choose stencil center (nearest node) ---
    i_center = int(round(i_frac))
    j_center = int(round(j_frac))

    # Clamp center so full 3x3 stencil fits within grid
    i_clamped = max(1, min(i_center, nrows - 2))
    j_clamped = max(1, min(j_center, ncols - 2))
    edge_clamped = (i_clamped != i_center) or (j_clamped != j_center)
    i_center = i_clamped
    j_center = j_clamped

    # --- Local normalized coordinates (grid-cell units) ---
    s = i_frac - i_center
    t = j_frac - j_center

    # --- 1D quadratic Lagrange basis functions ---
    def L(x):
        L0 = x * (x - 1.0) / 2.0
        L1 = 1.0 - x ** 2
        L2 = x * (x + 1.0) / 2.0
        return np.array([L0, L1, L2])

    Ls = L(s)
    Lt = L(t)

    # --- Fetch 3x3 stencil values ---
    F = np.zeros((3, 3))
    for di in range(-1, 2):
        for dj in range(-1, 2):
            F[di + 1, dj + 1] = grid_data(i_center + di, j_center + dj)

    # --- Tensor product interpolation ---
    result = float(Ls @ F @ Lt)

    return result, edge_clamped


# =============================================================================
# Grid Extraction
# =============================================================================

def extract_value(ds, lat, lon, epoch=EPOCH, pid='UNKNOWN'):
    """
    Extract geoid undulation and compute orthometric height.

    Parameters
    ----------
    ds : netCDF4.Dataset
        Open dataset handle.
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees. NGS positive-west convention expected.
    epoch : float
        Decimal year for epoch correction.
    pid : str
        OPUS_PID for longitude warning reporting.

    Returns
    -------
    dict or None
        All extracted and computed values, or None if point not in any grid.
    """

    # --- Correct positive-west longitude convention ---
    lon360, lon_warning = correct_ngs_lon(lon, pid=pid)

    # --- Find highest-priority grid containing this point ---
    candidate_regions = []
    for region_name, meta in REGIONS[MODEL].items():
        if point_in_grid(lat, lon360, meta):
            candidate_regions.append((meta['priority'], region_name, meta))

    if not candidate_regions:
        return None

    candidate_regions.sort(key=lambda x: x[0], reverse=True)
    _, region_name, meta = candidate_regions[0]

    # --- Compute fractional grid indices ---
    i_frac = (lat - meta['lat0']) / meta['dlat']
    j_frac = (lon360 - meta['lon0']) / meta['dlon']

    nrows = meta['nrows']
    ncols = meta['ncols']
    var_name = meta['var']

    # --- Get variable from open dataset ---
    grp = ds.groups[MODEL].groups[region_name]
    var = grp.variables[var_name]

    def grid_data(i, j):
        return safe_node_value(var, i, j)

    # --- Static interpolation ---
    undulation_N, edge_clamped = biquadratic_interp(
        grid_data, i_frac, j_frac, nrows, ncols
    )

    # --- Velocity correction ---
    vel_candidates = []
    for region_name_v, meta_v in REGIONS['xDGEOID20'].items():
        if point_in_grid(lat, lon360, meta_v):
            vel_candidates.append((meta_v['priority'], region_name_v, meta_v))

    undulation_N_corrected = None
    if vel_candidates:
        vel_candidates.sort(key=lambda x: x[0], reverse=True)
        _, vel_region, vel_meta = vel_candidates[0]

        vel_grp = ds.groups['xDGEOID20'].groups[vel_region]
        vel_var = vel_grp.variables['geoidVelocity']

        vel_i_frac = (lat - vel_meta['lat0']) / vel_meta['dlat']
        vel_j_frac = (lon360 - vel_meta['lon0']) / vel_meta['dlon']

        def vel_grid_data(i, j):
            return safe_node_value(vel_var, i, j)

        velocity, _ = biquadratic_interp(
            vel_grid_data, vel_i_frac, vel_j_frac,
            vel_meta['nrows'], vel_meta['ncols']
        )

        undulation_N_corrected = undulation_N + velocity * (epoch - T0)

    return {
        'region': region_name,
        'undulation_N': undulation_N,
        'undulation_N_corrected': undulation_N_corrected,
        'lon360': lon360,
        'lon_warning': lon_warning,
        'edge_clamped': edge_clamped,
    }


# =============================================================================
# Batch Processing
# =============================================================================

def run_batch():
    """Main batch processing function."""
    global MODEL, EPOCH, T0

    # --- Load configuration (config.ini, with fallback to defaults) ---
    config = load_config()
    MODEL = config['model']
    EPOCH = config['epoch']
    T0 = config['t0']
    overwrite_mode = config['overwrite']
    input_dir = resolve_dir(config['input_dir'])
    output_dir = resolve_dir(config['output_dir'])

    # --- Locate input file (single file in input_dir; error on multiple) ---
    input_path, input_error = find_input_file(input_dir)
    if input_error:
        print(f"ERROR: {input_error}")
        sys.exit(1)

    # --- Run timestamp (UTC / GMT) drives output + log filenames ---
    run_start = datetime.now(timezone.utc)

    output_path = generate_output_filename(input_path, output_dir, run_start)
    log_path = generate_log_filename(input_path, output_dir, run_start)

    # --- Ensure output directory exists ---
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        print(f"ERROR: Could not create output directory {output_dir}: {e}")
        sys.exit(1)

    # --- Banner ---
    print(f"\n{'='*60}")
    print(f"  xGEOID20B Batch Extraction  v{__version__}")
    print(f"{'='*60}")

    # --- Overwrite policy for the (rare) timestamp collision ---
    if not check_file_overwrite(output_path, overwrite_mode):
        print(f"\n  Output file will not be overwritten (overwrite=never).")
        print(f"  Exiting.\n")
        sys.exit(0)

    if not check_file_overwrite(log_path, overwrite_mode):
        print(f"\n  Log file will not be overwritten (overwrite=never).")
        print(f"  Exiting.\n")
        sys.exit(0)

    print(f"  Input:    {os.path.basename(input_path)}")
    print(f"  Output:   {os.path.basename(output_path)}")
    print(f"  Log:      {os.path.basename(log_path)}")
    print(f"  Model:    {MODEL}")
    print(f"  Epoch:    {EPOCH}")
    print(f"  Overwrite:{overwrite_mode}")
    print(f"  Started:  {run_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}\n")

    # --- Read input CSV ---
    try:
        with open(input_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            input_columns = reader.fieldnames or []
    except Exception as e:
        print(f"ERROR reading input file: {e}")
        sys.exit(1)

    # --- Validate required columns are present ---
    required_columns = ['OPUS_PID', 'lat', 'lon', 'ellip_h_m']
    missing_columns = [c for c in required_columns if c not in input_columns]
    if missing_columns:
        print(f"ERROR: Input CSV is missing required column(s): "
              f"{', '.join(missing_columns)}")
        print(f"       Required columns: {', '.join(required_columns)}")
        print(f"       Found columns:    "
              f"{', '.join(input_columns) if input_columns else '(none)'}")
        sys.exit(1)

    if not rows:
        print(f"ERROR: Input CSV contains no data rows.")
        sys.exit(1)

    total = len(rows)
    successful = 0
    nan_count = 0
    errors = []
    lon_warnings = []
    edge_warnings = []

    # --- Locate the GGXF grid file (fail fast if missing) ---
    try:
        ggxf_path = resolve_ggxf_path(config['ggxf_file'])
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    # --- Open GGXF file ---
    print(f"  Opening GGXF file...")
    print(f"    {ggxf_path}")
    try:
        ds = nc.Dataset(ggxf_path, 'r')
        load_grid_metadata(ds)
        print(f"  GGXF file opened successfully.\n")
    except Exception as e:
        print(f"ERROR opening GGXF file: {e}")
        sys.exit(1)

    # --- Output CSV setup ---
    output_fieldnames = [
        'OPUS_PID',
        'lat',
        'lon',
        'ellip_h_m',
        'region',
        'undulation_N_m',
        'orthometric_H_m',
        'epoch',
        'undulation_N_epoch_corrected_m',
        'orthometric_H_epoch_corrected_m',
    ]

    # --- Process rows ---
    with open(output_path, 'w', newline='', encoding='utf-8') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=output_fieldnames)
        writer.writeheader()

        for idx, row in enumerate(rows, start=1):
            pid = row.get('OPUS_PID', f'ROW_{idx}').strip()

            print(f"  Processing {pid:<12} ({idx} of {total})...", end=' ')

            try:
                lat = float(row['lat'])
                lon = float(row['lon'])
                ellip_h = float(row['ellip_h_m'])

                result = extract_value(ds, lat, lon, epoch=EPOCH, pid=pid)

                # Capture any longitude convention warning
                if result and result['lon_warning'] is not None:
                    lon_warnings.append((pid, result['lon_warning']))
                    print(f'\n  [!] Longitude warning for {pid} - see log file')

                if result is None:
                    # Point outside all grids
                    writer.writerow({
                        'OPUS_PID': pid,
                        'lat': f"{lat:.8f}",
                        'lon': f"{lon:.8f}",
                        'ellip_h_m': f"{ellip_h:.4f}",
                        'region': 'OUTSIDE GRID',
                        'undulation_N_m': 'NaN',
                        'orthometric_H_m': 'NaN',
                        'epoch': EPOCH,
                        'undulation_N_epoch_corrected_m': 'NaN',
                        'orthometric_H_epoch_corrected_m': 'NaN',
                    })
                    nan_count += 1
                    errors.append((pid, 'Point outside all grid regions'))
                    print('NaN - outside grid')

                else:
                    # Compute orthometric heights
                    N = result['undulation_N']
                    N_corr = result['undulation_N_corrected']
                    H = ellip_h - N
                    H_corr = ellip_h - N_corr if N_corr is not None else None

                    # Note points whose interpolation stencil was clamped
                    # at a grid edge (result is a mild extrapolation).
                    if result.get('edge_clamped'):
                        edge_warnings.append((pid, result['region']))

                    writer.writerow({
                        'OPUS_PID': pid,
                        'lat': f"{lat:.8f}",
                        'lon': f"{lon:.8f}",
                        'ellip_h_m': f"{ellip_h:.4f}",
                        'region': result['region'],
                        'undulation_N_m': f"{N:.4f}",
                        'orthometric_H_m': f"{H:.4f}",
                        'epoch': EPOCH,
                        'undulation_N_epoch_corrected_m': f"{N_corr:.4f}" if N_corr is not None else 'NaN',
                        'orthometric_H_epoch_corrected_m': f"{H_corr:.4f}" if H_corr is not None else 'NaN',
                    })
                    successful += 1
                    print('OK')

            except Exception as e:
                # Unexpected error on this row
                try:
                    # Attempt formatted output if lat/lon parsed successfully
                    writer.writerow({
                        'OPUS_PID': pid,
                        'lat': f"{lat:.8f}",
                        'lon': f"{lon:.8f}",
                        'ellip_h_m': f"{ellip_h:.4f}",
                        'region': 'ERROR',
                        'undulation_N_m': 'NaN',
                        'orthometric_H_m': 'NaN',
                        'epoch': EPOCH,
                        'undulation_N_epoch_corrected_m': 'NaN',
                        'orthometric_H_epoch_corrected_m': 'NaN',
                    })
                except Exception:
                    # Fallback if lat/lon never parsed — write raw strings
                    writer.writerow({
                        'OPUS_PID': pid,
                        'lat': row.get('lat', 'NaN'),
                        'lon': row.get('lon', 'NaN'),
                        'ellip_h_m': row.get('ellip_h_m', 'NaN'),
                        'region': 'ERROR',
                        'undulation_N_m': 'NaN',
                        'orthometric_H_m': 'NaN',
                        'epoch': EPOCH,
                        'undulation_N_epoch_corrected_m': 'NaN',
                        'orthometric_H_epoch_corrected_m': 'NaN',
                    })
                nan_count += 1
                errors.append((pid, str(e)))
                print(f'ERROR - {e}')

    ds.close()

    run_end = datetime.now(timezone.utc)
    duration = run_end - run_start

    # --- Console Summary ---
    print(f"\n{'='*60}")
    print(f"  Batch Complete")
    print(f"{'='*60}")
    print(f"  Total Points:    {total}")
    print(f"  Successful:      {successful}")
    print(f"  NaN / Errors:    {nan_count}")
    if edge_warnings:
        print(f"  Edge-clamped:    {len(edge_warnings)} (see log file)")
    print(f"  Duration:        {duration}")
    print(f"  Output file:     {os.path.basename(output_path)}")
    print(f"  Log file:        {os.path.basename(log_path)}")
    print(f"{'='*60}\n")

    # --- Write Log File ---
    with open(log_path, 'w', encoding='utf-8') as log_f:
        log_f.write('='*60 + '\n')
        log_f.write('  xGEOID20B Batch Extraction Log\n')
        log_f.write('='*60 + '\n')
        log_f.write(f'  Version:         {__version__}\n')
        log_f.write(f'  Run Date/Time:   {run_start.strftime("%Y-%m-%d %H:%M:%S")} UTC\n')
        log_f.write(f'  Input File:      {os.path.basename(input_path)}\n')
        log_f.write(f'  Output File:     {os.path.basename(output_path)}\n')
        log_f.write(f'  Model:           {MODEL}\n')
        log_f.write(f'  Epoch:           {EPOCH}\n')
        log_f.write(f'  Reference T0:    {T0}\n')
        log_f.write(f'  Overwrite Mode:  {overwrite_mode}\n')
        log_f.write(f'  GGXF File:       {ggxf_path}\n')
        log_f.write('='*60 + '\n')
        log_f.write(f'  Total Points:    {total}\n')
        log_f.write(f'  Successful:      {successful}\n')
        log_f.write(f'  NaN / Errors:    {nan_count}\n')
        log_f.write(f'  Duration:        {duration}\n')
        log_f.write('='*60 + '\n')

        if lon_warnings:
            log_f.write('\n  --- Longitude Convention Warnings ---\n\n')
            log_f.write('  WARNING: Negative longitudes were detected in the input.\n')
            log_f.write('  This script expects NGS positive-west convention.\n')
            log_f.write('  Verify results for the following points carefully:\n\n')
            for pid, warning in lon_warnings:
                log_f.write(warning)
                log_f.write('  ' + '-'*40 + '\n')
        else:
            log_f.write('\n  Longitude convention: All inputs positive-west (NGS). OK.\n')

        if edge_warnings:
            log_f.write('\n  --- Grid Edge Warnings ---\n\n')
            log_f.write('  The following points are within half a grid cell of a\n')
            log_f.write('  grid edge. The 3x3 interpolation stencil was clamped\n')
            log_f.write('  inward, so the result is a mild extrapolation rather\n')
            log_f.write('  than a true interpolation. Verify these results:\n\n')
            for pid, region in edge_warnings:
                log_f.write(f'  OPUS_PID: {pid}  (region: {region})\n')
            log_f.write('  ' + '-'*40 + '\n')
        else:
            log_f.write('\n  Grid edges: No points required edge clamping. OK.\n')

        if errors:
            log_f.write('\n  --- NaN / Error Detail ---\n\n')
            for pid, reason in errors:
                log_f.write(f'  OPUS_PID: {pid}\n')
                log_f.write(f'  Reason:   {reason}\n')
                log_f.write('  ' + '-'*40 + '\n')
        else:
            log_f.write('\n  No errors — all points processed successfully.\n')

        log_f.write('\n' + '='*60 + '\n')
        log_f.write(f'  Log closed:  {run_end.strftime("%Y-%m-%d %H:%M:%S")} UTC\n')
        log_f.write('='*60 + '\n')


# =============================================================================
# Entry Point
# =============================================================================
if __name__ == '__main__':
    run_batch()
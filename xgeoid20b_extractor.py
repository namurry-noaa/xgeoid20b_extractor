# =============================================================================
# xGEOID20B Batch Extraction Script
# NGS Experimental Geoid Model 2020 (B model - with airborne gravity)
# Interpolation: Biquadratic (3x3 stencil)
#
# --- COORDINATE INPUT REQUIREMENTS ---
# *** HORIZONTAL REFERENCE FRAME (INPUT) - USER'S RESPONSIBILITY ***
# Input horizontal coordinates MUST be in the correct NAD83(2011) realization
# for their region. The tool does NOT verify or convert the input frame;
# supplying the wrong frame yields silently incorrect results.
#     CONUS (incl. SE Alaska) -> NAD83(2011/CORS96/2007)  [input_frame 2011]
#     Pacific                 -> NAD83(PA11/PACP00)        [input_frame PA11]
#     Marianas                -> NAD83(MA11/MARP00)        [input_frame MA11]
# The tool transforms these to ITRF2014 / IGS14 (via bundled NGS HTDP) and
# reports the transformed lat/lon alongside the xGEOID20B undulation N.
# Set the realization in config.ini [transform] input_frame.
#
# Ellipsoid:                  GRS80
# Latitude/Longitude:         Decimal degrees
# Ellipsoidal Height:         Meters (input only; required for the HTDP
#                             coordinate transform, not reported as output)
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
# NOTE: xGEOID20B is a STATIC geoid model (no time/velocity component), so
#       no geoid epoch is applied. The only epoch used is for the HTDP
#       coordinate transform (nominal 2010.0 for NAD83 -> IGS14).
#
# Author:                     Nate Murry, NOAA/NOS/CO-OPS, 7/16/2026
# Version:                    3.0.1
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
import json
import configparser
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone


__version__ = '3.0.1'


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


# --- HTDP horizontal transform ---
# The bundled NGS HTDP utility performs the NAD83 realization -> IGS14
# transform. It is driven via stdlib subprocess (no third-party deps).
HTDP_DIR = os.path.join(SCRIPT_DIR, 'HTDP')
HTDP_FILENAME = 'htdp360.exe'          # bundled Windows prebuilt
# Native (non-Windows) HTDP binary names to also look for. On Linux/macOS the
# bundled .exe won't run; a native HTDP (built from NGS Fortran, e.g. the sibling
# napgd2022_extractor's htdp/htdp) is used instead. Resolution also honors the
# XGEOID_HTDP environment variable and the config.ini [transform] htdp_exe path.
HTDP_NATIVE_NAMES = ('htdp', 'htdp360')
HTDP_ENV_VAR = 'XGEOID_HTDP'

# HTDP input reference-frame menu codes for the supported NAD83 realizations.
HTDP_INPUT_FRAME_CODES = {
    '2011': '1',   # NAD83(2011/CORS96/2007)  - CONUS
    'PA11': '2',   # NAD83(PA11/PACP00)        - Pacific
    'MA11': '3',   # NAD83(MA11/MARP00)        - Marianas
}
# Output frame is fixed to ITRF2014 / IGS14.
HTDP_OUTPUT_FRAME_CODE = '25'   # ITRF2014 / IGS14 / IGb14
HTDP_OUTPUT_FRAME_NAME = 'ITRF2014/IGS14'


# --- Defaults (used when config.ini is absent or a value is blank) ---
DEFAULTS = {
    'ggxf_file': '',
    'input_dir': 'input',
    'output_dir': 'output',
    'log_dir': 'logs',
    'model': 'xGEOID20B',
    'overwrite': 'always',
    'format': 'csv',
    'input_frame': '2011',
    'input_epoch': '2010.0',
    'output_epoch': '2010.0',
    'htdp_exe': '',
}

# Supported output formats.
SUPPORTED_FORMATS = ('csv', 'json', 'xlsx')


# --- Constants (populated from config in run_batch; default here) ---
MODEL = 'xGEOID20B'


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
        pid of the point, used for log warning if needed.

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
            f"  PID: {pid}\n"
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


def htdp_positive_west_lon(lon):
    """
    Convert an input longitude to the POSITIVE-WEST value HTDP expects.

    HTDP (menu option 4) interprets longitudes as positive-west. The tool's
    geoid path first canonicalizes any input longitude to 0-360 EAST via
    correct_ngs_lon(); positive-west is simply (360 - that east value).
    Reusing the same canonical east longitude keeps the HTDP path and the
    geoid path consistent about what a given input number means, and it fixes
    the case where a raw negative-west longitude would otherwise be misread by
    HTDP as an east longitude (placing the point in the wrong hemisphere and
    corrupting both the longitude and the transformed ellipsoidal height).

    Parameters
    ----------
    lon : float
        Input longitude (same convention as fed to the geoid path).

    Returns
    -------
    float
        Longitude in positive-west convention (0..360) for HTDP.
    """
    lon360_east, _ = correct_ngs_lon(lon)
    return (360.0 - lon360_east) % 360.0


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
        Resolved configuration (paths, model, overwrite, format list, and
        the transform frame/epochs).
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
        cfg['log_dir'] = get('paths', 'log_dir', cfg['log_dir'])
        cfg['model'] = get('model', 'model', cfg['model'])
        cfg['overwrite'] = get('options', 'overwrite', cfg['overwrite']).lower()
        cfg['format'] = get('options', 'format', cfg['format'])

        # Transform section (the transform always runs; there is no on/off)
        cfg['input_frame'] = get('transform', 'input_frame', cfg['input_frame'])
        cfg['input_epoch'] = get('transform', 'input_epoch', cfg['input_epoch'])
        cfg['output_epoch'] = get('transform', 'output_epoch', cfg['output_epoch'])
        cfg['htdp_exe'] = get('transform', 'htdp_exe', cfg['htdp_exe'])

    # Validate overwrite value
    if cfg['overwrite'] not in ('always', 'never', 'prompt'):
        print(f"WARNING: config options.overwrite = '{cfg['overwrite']}' is "
              f"invalid; using 'always'.")
        cfg['overwrite'] = 'always'

    # Validate input_frame
    frame_key = str(cfg['input_frame']).strip().upper()
    if frame_key not in HTDP_INPUT_FRAME_CODES:
        print(f"WARNING: config transform.input_frame = '{cfg['input_frame']}' "
              f"is invalid; expected one of {', '.join(HTDP_INPUT_FRAME_CODES)}. "
              f"Using default '{DEFAULTS['input_frame']}'.")
        frame_key = DEFAULTS['input_frame']
    cfg['input_frame'] = frame_key

    # Parse + validate the output format list (comma-separated).
    raw_formats = str(cfg['format']).split(',')
    fmts = []
    for tok in raw_formats:
        t = tok.strip().lower()
        if t == '':
            continue
        if t not in SUPPORTED_FORMATS:
            print(f"WARNING: config options.format has unsupported value "
                  f"'{tok.strip()}'; ignoring it. Supported: "
                  f"{', '.join(SUPPORTED_FORMATS)}.")
            continue
        if t not in fmts:      # dedupe, preserve order
            fmts.append(t)
    if not fmts:
        print(f"WARNING: no valid output format selected; using 'csv'.")
        fmts = ['csv']
    cfg['formats'] = fmts

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


def generate_output_filename(input_path, output_dir, run_utc, ext='csv'):
    """UTC-timestamped output path in output_dir for a given extension."""
    return os.path.join(output_dir,
                        _timestamped_name(input_path, 'output', ext, run_utc))


def generate_log_filename(input_path, log_dir, run_utc):
    """UTC-timestamped batch log path in log_dir."""
    return os.path.join(log_dir,
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
# Horizontal Coordinate Transform (HTDP -> IGS14)
# =============================================================================

def resolve_htdp_path(config_htdp_exe=''):
    """
    Locate the HTDP executable.

    Order:
      1. config.ini [transform] htdp_exe, if set.
      2. XGEOID_HTDP environment variable, if set.
      3. a NATIVE htdp binary (htdp / htdp360) in the bundled HTDP/ dir
         (for Linux/macOS, where the .exe cannot run).
      4. bundled HTDP/htdp360.exe in the script directory (Windows).

    Returns
    -------
    str
        Full path to an existing HTDP executable.

    Raises
    ------
    FileNotFoundError
        If HTDP cannot be found.
    """
    if config_htdp_exe:
        p = (config_htdp_exe if os.path.isabs(config_htdp_exe)
             else os.path.join(SCRIPT_DIR, config_htdp_exe))
        if os.path.isfile(p):
            return p
        raise FileNotFoundError(
            f"config.ini [transform] htdp_exe points to a file that does not "
            f"exist:\n    {p}\n"
        )

    # environment override (portable; e.g. point at a native Linux HTDP)
    env_htdp = os.environ.get(HTDP_ENV_VAR, '').strip()
    if env_htdp:
        if os.path.isfile(env_htdp):
            return env_htdp
        raise FileNotFoundError(
            f"{HTDP_ENV_VAR} points to a file that does not exist:\n    {env_htdp}\n"
        )

    # native binary in the bundled HTDP dir (Linux/macOS)
    for name in HTDP_NATIVE_NAMES:
        cand = os.path.join(HTDP_DIR, name)
        if os.path.isfile(cand):
            return cand

    bundled = os.path.join(HTDP_DIR, HTDP_FILENAME)
    if os.path.isfile(bundled):
        return bundled

    raise FileNotFoundError(
        "HTDP executable not found.\n\n"
        "  Looked for (in order): config.ini [transform] htdp_exe; "
        f"${HTDP_ENV_VAR}; native {HTDP_NATIVE_NAMES} in {HTDP_DIR}; "
        f"and bundled {HTDP_FILENAME}.\n\n"
        "  Restore HTDP/htdp360.exe (Windows), provide a native htdp binary, "
        f"set ${HTDP_ENV_VAR}, or set htdp_exe in config.ini [transform].\n"
    )


def _epoch_htdp_answers(epoch_value):
    """
    Build the HTDP menu answers for a reference epoch.

    HTDP asks "How do you wish to enter the time?" then:
      option 1 -> month-day-year (free format)
      option 2 -> decimal year

    Accepts either a decimal year ("2010.0") or a calendar date
    ("1 1 2010" or "1/1/2010"). Returns the list of lines to send.
    """
    s = str(epoch_value).strip()
    # Calendar if it contains a separator implying M D Y (space or slash with
    # 3 parts); otherwise treat as decimal year.
    parts = s.replace('/', ' ').split()
    if len(parts) == 3:
        # calendar date -> option 1, then "M D Y"
        return ['1', ' '.join(parts)]
    # decimal year -> option 2, then the value
    return ['2', s]


def htdp_transform_file(htdp_exe, records, input_frame_key,
                        input_epoch, output_epoch):
    """
    Transform a batch of horizontal positions to ITRF2014/IGS14 using HTDP.

    Drives the HTDP interactive CLI via stdlib subprocess (piped stdin).
    No third-party dependencies. Windows-only (HTDP is a Windows exe).

    Parameters
    ----------
    htdp_exe : str
        Path to htdp360.exe.
    records : list of tuple
        (lat, lon, eht, label) per point. lat/lon in decimal degrees using
        the NGS positive-west convention as supplied by the user; eht in
        meters. label is a short identifier (<=24 chars).
    input_frame_key : str
        One of '2011', 'PA11', 'MA11'.
    input_epoch, output_epoch : str
        Decimal year or calendar date (see _epoch_htdp_answers).

    Returns
    -------
    list of tuple
        (lat_igs14, lon_igs14, eht_igs14) per input record, in the same
        order. Values are floats.

    Raises
    ------
    RuntimeError
        If HTDP fails or the output cannot be parsed.
    """
    in_frame_code = HTDP_INPUT_FRAME_CODES[input_frame_key]

    workdir = tempfile.mkdtemp(prefix='xgeoid_htdp_')
    in_file = os.path.join(workdir, 'htdp_in.txt')
    out_file = os.path.join(workdir, 'htdp_out.txt')

    try:
        # Write the delimited input file: lat,lon,eht,label
        with open(in_file, 'w', encoding='ascii') as f:
            for (lat, lon, eht, label) in records:
                safe_label = str(label)[:24]
                f.write(f"{lat},{lon},{eht},{safe_label}\n")

        # Build the keystroke sequence (mirrors the HTDP menu flow).
        answers = ['4', out_file, in_frame_code, HTDP_OUTPUT_FRAME_CODE]
        answers += _epoch_htdp_answers(input_epoch)
        answers += _epoch_htdp_answers(output_epoch)
        answers += ['3', in_file, '0', '']
        keystrokes = '\n'.join(answers)

        proc = subprocess.run(
            [htdp_exe],
            input=keystrokes,
            text=True,
            capture_output=True,
            cwd=workdir,
            timeout=300,
        )

        if not os.path.isfile(out_file):
            raise RuntimeError(
                f"HTDP produced no output file.\n"
                f"  returncode={proc.returncode}\n"
                f"  stderr tail: {proc.stderr[-300:]}"
            )

        results = _parse_htdp_output(out_file)
        if len(results) != len(records):
            raise RuntimeError(
                f"HTDP returned {len(results)} positions for "
                f"{len(records)} inputs (count mismatch)."
            )
        return results

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _parse_htdp_output(out_file):
    """
    Parse an HTDP transform output file.

    The data lines have the form:
        <lat>  <lon>  <eht>  <label>
    preceded by a header/caution block. Data lines are those whose first
    two whitespace-separated tokens parse as floats.

    Returns
    -------
    list of tuple (lat, lon, eht) floats, in file order.
    """
    results = []
    with open(out_file, 'r', encoding='ascii', errors='replace') as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                eht = float(parts[2])
            except ValueError:
                continue  # header / caution / blank line
            results.append((lat, lon, eht))
    return results


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

def extract_value(ds, lat, lon, pid='UNKNOWN'):
    """
    Extract the (static) xGEOID20B geoid undulation at a point.

    Parameters
    ----------
    ds : netCDF4.Dataset
        Open dataset handle.
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees. NGS positive-west convention expected.
    pid : str
        pid for longitude warning reporting.

    Returns
    -------
    dict or None
        Extracted values, or None if the point is not in any grid region.
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

    # --- Static geoid undulation via biquadratic interpolation ---
    undulation_N, edge_clamped = biquadratic_interp(
        grid_data, i_frac, j_frac, nrows, ncols
    )

    return {
        'region': region_name,
        'undulation_N': undulation_N,
        'lon360': lon360,
        'lon_warning': lon_warning,
        'edge_clamped': edge_clamped,
    }


# =============================================================================
# Output Writers (csv / json / xlsx)
# =============================================================================

class MissingDependencyError(Exception):
    """Raised when an optional output format needs a package that isn't installed."""
    pass


def write_csv(path, fieldnames, rows):
    """Write rows to a CSV file (same format as prior versions)."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def write_json(path, run_meta, fieldnames, rows):
    """
    Write a JSON file: a metadata wrapper plus a data array.

    { "metadata": {...run info...},
      "columns": [...],
      "data": [ {col: val, ...}, ... ] }
    """
    doc = {
        'metadata': run_meta,
        'columns': list(fieldnames),
        'data': [dict(r) for r in rows],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2)
        f.write('\n')


def write_xlsx(path, fieldnames, rows):
    """
    Write rows to an .xlsx workbook (single sheet).

    Requires openpyxl. Raises MissingDependencyError (handled gracefully by
    the caller) if openpyxl is not installed, so the other formats and the
    run still complete.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        raise MissingDependencyError(
            "xlsx output requested but the 'openpyxl' package is not "
            "installed. Install it with:\n"
            "        conda install -c conda-forge openpyxl\n"
            "      (or 'pip install openpyxl'). Skipping xlsx output; other "
            "formats were still written."
        )

    wb = Workbook()
    ws = wb.active
    ws.title = 'xGEOID20B'
    ws.append(list(fieldnames))
    for r in rows:
        ws.append([r.get(c, '') for c in fieldnames])
    wb.save(path)


# =============================================================================
# Batch Processing
# =============================================================================

def run_batch():
    """Main batch processing function."""
    global MODEL

    # --- Load configuration (config.ini, with fallback to defaults) ---
    config = load_config()
    MODEL = config['model']
    overwrite_mode = config['overwrite']
    input_dir = resolve_dir(config['input_dir'])
    output_dir = resolve_dir(config['output_dir'])
    log_dir = resolve_dir(config['log_dir'])
    formats = config['formats']

    # --- Locate input file (single file in input_dir; error on multiple) ---
    input_path, input_error = find_input_file(input_dir)
    if input_error:
        print(f"ERROR: {input_error}")
        sys.exit(1)

    # --- Run timestamp (UTC / GMT) drives output + log filenames ---
    run_start = datetime.now(timezone.utc)

    # One output path per requested format; log goes to log_dir.
    output_paths = {
        fmt: generate_output_filename(input_path, output_dir, run_start, ext=fmt)
        for fmt in formats
    }
    log_path = generate_log_filename(input_path, log_dir, run_start)

    # --- Ensure output + log directories exist ---
    for d in (output_dir, log_dir):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            print(f"ERROR: Could not create directory {d}: {e}")
            sys.exit(1)

    # --- Banner ---
    print(f"\n{'='*60}")
    print(f"  xGEOID20B Batch Extraction  v{__version__}")
    print(f"{'='*60}")

    # --- Overwrite policy for the (rare) timestamp collision ---
    for fmt, p in output_paths.items():
        if not check_file_overwrite(p, overwrite_mode):
            print(f"\n  Output file will not be overwritten (overwrite=never).")
            print(f"  Exiting.\n")
            sys.exit(0)

    if not check_file_overwrite(log_path, overwrite_mode):
        print(f"\n  Log file will not be overwritten (overwrite=never).")
        print(f"  Exiting.\n")
        sys.exit(0)

    print(f"  Input:    {os.path.basename(input_path)}")
    print(f"  Output:   {', '.join(os.path.basename(p) for p in output_paths.values())}")
    print(f"  Formats:  {', '.join(formats)}")
    print(f"  Log:      {os.path.basename(log_path)}")
    print(f"  Model:    {MODEL}")
    print(f"  Overwrite:{overwrite_mode}")
    print(f"  Transform:{config['input_frame']} -> {HTDP_OUTPUT_FRAME_NAME} "
          f"(epochs {config['input_epoch']} -> {config['output_epoch']})")
    print(f"  Started:  {run_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}\n")

    # --- Read input CSV ---
    # Required columns: pid, lat, lon, nad83_ellip. Header matching is
    # CASE-INSENSITIVE and tolerant of surrounding whitespace, and column
    # ORDER does not matter. Each header is normalized (trimmed + lowercased)
    # and mapped to its canonical name; extra columns are ignored. Data
    # values (e.g. the pid station labels) are left exactly as-is.
    canonical_columns = ['pid', 'lat', 'lon', 'nad83_ellip']
    canon_by_lower = {c.lower(): c for c in canonical_columns}
    try:
        with open(input_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            raw_fieldnames = reader.fieldnames or []
            # Build: normalized-header -> canonical name (only for recognized cols)
            header_map = {}
            for h in raw_fieldnames:
                if h is None:
                    continue
                key = h.strip().lower()
                if key in canon_by_lower:
                    header_map[h] = canon_by_lower[key]
            # Re-key each row to canonical names (keep unrecognized cols out).
            rows = []
            for raw in reader:
                row = {}
                for orig, val in raw.items():
                    if orig in header_map:
                        row[header_map[orig]] = val
                rows.append(row)
    except Exception as e:
        print(f"ERROR reading input file: {e}")
        sys.exit(1)

    # --- Validate required columns are present (case-insensitive) ---
    found_canon = set(header_map.values())
    missing_columns = [c for c in canonical_columns if c not in found_canon]
    if missing_columns:
        print(f"ERROR: Input CSV is missing required column(s): "
              f"{', '.join(missing_columns)}")
        print(f"       Required columns (case-insensitive, any order): "
              f"{', '.join(canonical_columns)}")
        print(f"       Found columns:    "
              f"{', '.join(h for h in raw_fieldnames if h) if raw_fieldnames else '(none)'}")
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

    # --- Horizontal transform (NAD83 realization -> IGS14) via HTDP ---
    # The transform ALWAYS runs (IGS14 coordinates are core output). HTDP is
    # required; fail fast if it is missing. Computed up front as a single
    # batch (one HTDP invocation for all points), keyed by row index so the
    # results line up with the output rows.
    try:
        htdp_path = resolve_htdp_path(config['htdp_exe'])
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    igs14_by_idx = {}
    # Build records from rows that have parseable coordinates. HTDP expects
    # positive-west longitude; convert from the input convention (consistent
    # with the geoid path) before feeding it.
    recs = []
    rec_idx = []
    for idx, row in enumerate(rows, start=1):
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            eht = float(row['nad83_ellip'])
        except (KeyError, ValueError, TypeError):
            continue
        lon_pw = htdp_positive_west_lon(lon)
        recs.append((lat, lon_pw, eht, f"IDX{idx}"))
        rec_idx.append(idx)

    if recs:
        print(f"  Running HTDP transform "
              f"({config['input_frame']} -> {HTDP_OUTPUT_FRAME_NAME}) "
              f"on {len(recs)} points...")
        try:
            out = htdp_transform_file(
                htdp_path, recs, config['input_frame'],
                config['input_epoch'], config['output_epoch'],
            )
            for k, idx in enumerate(rec_idx):
                igs14_by_idx[idx] = out[k]
            print(f"  HTDP transform complete.\n")
        except Exception as e:
            print(f"\nERROR: HTDP transform failed: {e}")
            sys.exit(1)

    # --- Output columns ---
    output_fieldnames = [
        'pid',
        'lat',
        'lon',
        'lat_igs14',
        'lon_igs14',
        'undulation_N_m',
    ]

    # --- Build all output rows once (then serialize to each format) ---
    out_rows = []
    for idx, row in enumerate(rows, start=1):
        pid = row.get('pid', f'ROW_{idx}').strip()

        print(f"  Processing {pid:<12} ({idx} of {total})...", end=' ')

        # IGS14 transformed coordinates for this row (from HTDP).
        igs14 = igs14_by_idx.get(idx)   # (lat, lon, eht) or None
        if igs14 is not None:
            lat_i, lon_i, _eht_i = igs14
            igs14_cols = {
                'lat_igs14': f"{lat_i:.8f}",
                'lon_igs14': f"{lon_i:.8f}",
            }
        else:
            igs14_cols = {'lat_igs14': '', 'lon_igs14': ''}

        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            # nad83_ellip is required input (fed to HTDP for the transform)
            # but is not part of the output.
            _ellip_h = float(row['nad83_ellip'])

            result = extract_value(ds, lat, lon, pid=pid)

            # Capture any longitude convention warning
            if result and result['lon_warning'] is not None:
                lon_warnings.append((pid, result['lon_warning']))
                print(f'\n  [!] Longitude warning for {pid} - see log file')

            if result is None:
                # Point outside all grids
                out_rows.append({
                    'pid': pid,
                    'lat': f"{lat:.8f}",
                    'lon': f"{lon:.8f}",
                    **igs14_cols,
                    'undulation_N_m': 'NaN',
                })
                nan_count += 1
                errors.append((pid, 'Point outside all grid regions'))
                print('NaN - outside grid')

            else:
                N = result['undulation_N']

                # Note points whose interpolation stencil was clamped
                # at a grid edge (result is a mild extrapolation).
                if result.get('edge_clamped'):
                    edge_warnings.append((pid, result['region']))

                out_rows.append({
                    'pid': pid,
                    'lat': f"{lat:.8f}",
                    'lon': f"{lon:.8f}",
                    **igs14_cols,
                    'undulation_N_m': f"{N:.4f}",
                })
                successful += 1
                print('OK')

        except Exception as e:
            # Unexpected error on this row
            try:
                row_out = {
                    'pid': pid,
                    'lat': f"{lat:.8f}",
                    'lon': f"{lon:.8f}",
                    **igs14_cols,
                    'undulation_N_m': 'NaN',
                }
            except Exception:
                # Fallback if lat/lon never parsed — write raw strings
                row_out = {
                    'pid': pid,
                    'lat': row.get('lat', 'NaN'),
                    'lon': row.get('lon', 'NaN'),
                    'lat_igs14': '',
                    'lon_igs14': '',
                    'undulation_N_m': 'NaN',
                }
            out_rows.append(row_out)
            nan_count += 1
            errors.append((pid, str(e)))
            print(f'ERROR - {e}')

    ds.close()

    run_end = datetime.now(timezone.utc)
    duration = run_end - run_start

    # --- Write each requested output format ---
    written_files = []
    run_meta = {
        'tool': 'xGEOID20B Batch Extraction',
        'version': __version__,
        'run_utc': run_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'input_file': os.path.basename(input_path),
        'model': MODEL,
        'input_frame': config['input_frame'],
        'output_frame': HTDP_OUTPUT_FRAME_NAME,
        'transform_input_epoch': config['input_epoch'],
        'transform_output_epoch': config['output_epoch'],
        'total_points': total,
        'successful': successful,
        'nan_or_errors': nan_count,
    }
    for fmt in formats:
        path = output_paths[fmt]
        try:
            if fmt == 'csv':
                write_csv(path, output_fieldnames, out_rows)
            elif fmt == 'json':
                write_json(path, run_meta, output_fieldnames, out_rows)
            elif fmt == 'xlsx':
                write_xlsx(path, output_fieldnames, out_rows)
            written_files.append(os.path.basename(path))
        except MissingDependencyError as e:
            print(f"  [!] {e}")
        except Exception as e:
            print(f"  [!] Failed to write {fmt} output: {e}")

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
    print(f"  Output file(s):  {', '.join(written_files) if written_files else '(none written)'}")
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
        log_f.write(f'  Output File(s):  {", ".join(written_files) if written_files else "(none)"}\n')
        log_f.write(f'  Formats:         {", ".join(formats)}\n')
        log_f.write(f'  Model:           {MODEL}\n')
        log_f.write(f'  Overwrite Mode:  {overwrite_mode}\n')
        log_f.write(f'  GGXF File:       {ggxf_path}\n')
        log_f.write(f'  Horiz Transform: {config["input_frame"]} -> '
                    f'{HTDP_OUTPUT_FRAME_NAME}\n')
        log_f.write(f'  Transform Epochs: input {config["input_epoch"]} '
                    f'-> output {config["output_epoch"]}\n')
        log_f.write(f'  HTDP Executable: {htdp_path}\n')
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
                log_f.write(f'  PID: {pid}  (region: {region})\n')
            log_f.write('  ' + '-'*40 + '\n')
        else:
            log_f.write('\n  Grid edges: No points required edge clamping. OK.\n')

        if errors:
            log_f.write('\n  --- NaN / Error Detail ---\n\n')
            for pid, reason in errors:
                log_f.write(f'  PID: {pid}\n')
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

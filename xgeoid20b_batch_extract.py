# =============================================================================
# xGEOID20B Batch Extraction Script
# NGS Experimental Geoid Model 2020 (B model - with airborne gravity)
# Interpolation: Biquadratic (3x3 stencil)
#
# --- COORDINATE INPUT REQUIREMENTS ---
# Horizontal Reference Frame: IGS14
# Ellipsoid:                  GRS80
# Latitude/Longitude:         Decimal degrees
# Ellipsoidal Height:         Meters, GRS80 ellipsoid, IGS14 reference frame
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
# Author:                     Nathan Murry, NOAA National Geodetic Survey
# =============================================================================


import netCDF4 as nc
import numpy as np
import csv
import os
import sys
from datetime import datetime


# --- File Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = r"C:\Users\nathan.murry\NOAA\Geodesy\GEOID_Legacy\xGEOID20b\xGEOID20.ggxf"


# --- Constants ---
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


def check_file_overwrite(filepath):
    """
    Check if a file already exists and prompt user for overwrite confirmation.

    Parameters
    ----------
    filepath : str
        Full path to the file to check.

    Returns
    -------
    bool
        True if OK to proceed (file doesn't exist or user confirmed overwrite).
        False if user chose not to overwrite.
    """
    if os.path.exists(filepath):
        print(f"\n  ⚠️  File already exists: {os.path.basename(filepath)}")
        while True:
            response = input(f"      Overwrite? (y/n): ").strip().lower()
            if response == 'y':
                print(f"      Overwriting {os.path.basename(filepath)}...")
                return True
            elif response == 'n':
                print(f"      Skipping — {os.path.basename(filepath)} "
                      f"will not be overwritten.")
                return False
            else:
                print("      Please enter 'y' or 'n'.")
    return True


def find_input_file():
    """Find the first CSV file with 'input' in the name in script directory."""
    for fname in os.listdir(SCRIPT_DIR):
        if fname.lower().endswith('.csv') and 'input' in fname.lower():
            return os.path.join(SCRIPT_DIR, fname)
    return None


def generate_output_filename(input_path):
    """Generate output CSV filename based on input filename."""
    base = os.path.basename(input_path)
    name = base.lower().replace('input', 'output')
    return os.path.join(SCRIPT_DIR, name)


def generate_log_filename(input_path):
    """Generate log filename based on input filename."""
    base = os.path.basename(input_path)
    name = os.path.splitext(base)[0] + '_batch_log.txt'
    return os.path.join(SCRIPT_DIR, name)


# =============================================================================
# Bi-quadratic Interpolation
# =============================================================================

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
    nearest node, with local coordinates (s, t) normalized to [-1, 1].

    Basis functions are 1D quadratic Lagrange polynomials:
        L0(x) = x*(x-1)/2   (left/bottom node)
        L1(x) = (1-x^2)     (center node)
        L2(x) = x*(x+1)/2   (right/top node)

    The 2D surface is the tensor product:
        f(s,t) = sum_m sum_n L_m(s) * L_n(t) * f_mn
    """

    # --- Choose stencil center (nearest node) ---
    i_center = int(round(i_frac))
    j_center = int(round(j_frac))

    # Clamp center so full 3x3 stencil fits within grid
    i_center = max(1, min(i_center, nrows - 2))
    j_center = max(1, min(j_center, ncols - 2))

    # --- Local normalized coordinates in [-1, 1] ---
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

    return result


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
        return float(var[i, j])

    # --- Static interpolation ---
    undulation_N = biquadratic_interp(grid_data, i_frac, j_frac, nrows, ncols)

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
            return float(vel_var[i, j])

        velocity = biquadratic_interp(
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
    }


# =============================================================================
# Batch Processing
# =============================================================================

def run_batch():
    """Main batch processing function."""

    # --- Locate input file ---
    input_path = find_input_file()
    if not input_path:
        print("ERROR: No input CSV file found in script directory.")
        print(f"       Looking in: {SCRIPT_DIR}")
        print("       File must contain 'input' in the filename.")
        sys.exit(1)

    output_path = generate_output_filename(input_path)
    log_path = generate_log_filename(input_path)

    # --- Check for existing output files ---
    print(f"\n{'='*60}")
    print(f"  xGEOID20B Batch Extraction")
    print(f"{'='*60}")

    if not check_file_overwrite(output_path):
        print(f"\n  Output file will not be overwritten.")
        print(f"  Please rename or move the existing output file and rerun.")
        print(f"  Exiting.\n")
        sys.exit(0)

    if not check_file_overwrite(log_path):
        print(f"\n  Log file will not be overwritten.")
        print(f"  Please rename or move the existing log file and rerun.")
        print(f"  Exiting.\n")
        sys.exit(0)

    run_start = datetime.now()

    print(f"  Input:   {os.path.basename(input_path)}")
    print(f"  Output:  {os.path.basename(output_path)}")
    print(f"  Log:     {os.path.basename(log_path)}")
    print(f"  Model:   {MODEL}")
    print(f"  Epoch:   {EPOCH}")
    print(f"  Started: {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # --- Read input CSV ---
    try:
        with open(input_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print(f"ERROR reading input file: {e}")
        sys.exit(1)

    total = len(rows)
    successful = 0
    nan_count = 0
    errors = []
    lon_warnings = []

    # --- Open GGXF file ---
    print(f"  Opening GGXF file...")
    try:
        ds = nc.Dataset(FILE_PATH, 'r')
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
    with open(output_path, 'w', newline='') as out_f:
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
                    print(f'\n  ⚠️  Longitude warning for {pid} — see log file')

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
                    print('✓')

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

    run_end = datetime.now()
    duration = run_end - run_start

    # --- Console Summary ---
    print(f"\n{'='*60}")
    print(f"  Batch Complete")
    print(f"{'='*60}")
    print(f"  Total Points:    {total}")
    print(f"  Successful:      {successful}")
    print(f"  NaN / Errors:    {nan_count}")
    print(f"  Duration:        {duration}")
    print(f"  Output file:     {os.path.basename(output_path)}")
    print(f"  Log file:        {os.path.basename(log_path)}")
    print(f"{'='*60}\n")

    # --- Write Log File ---
    with open(log_path, 'w') as log_f:
        log_f.write('='*60 + '\n')
        log_f.write('  xGEOID20B Batch Extraction Log\n')
        log_f.write('='*60 + '\n')
        log_f.write(f'  Run Date/Time:   {run_start.strftime("%Y-%m-%d %H:%M:%S")}\n')
        log_f.write(f'  Input File:      {os.path.basename(input_path)}\n')
        log_f.write(f'  Output File:     {os.path.basename(output_path)}\n')
        log_f.write(f'  Model:           {MODEL}\n')
        log_f.write(f'  Epoch:           {EPOCH}\n')
        log_f.write(f'  Reference T0:    {T0}\n')
        log_f.write(f'  GGXF File:       {FILE_PATH}\n')
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

        if errors:
            log_f.write('\n  --- NaN / Error Detail ---\n\n')
            for pid, reason in errors:
                log_f.write(f'  OPUS_PID: {pid}\n')
                log_f.write(f'  Reason:   {reason}\n')
                log_f.write('  ' + '-'*40 + '\n')
        else:
            log_f.write('\n  No errors — all points processed successfully.\n')

        log_f.write('\n' + '='*60 + '\n')
        log_f.write(f'  Log closed:  {run_end.strftime("%Y-%m-%d %H:%M:%S")}\n')
        log_f.write('='*60 + '\n')


# =============================================================================
# Entry Point
# =============================================================================
if __name__ == '__main__':
    run_batch()
# xGEOID20B Batch Extraction Tool


## Overview
This tool extracts geoid undulation values (N) from the NGS experimental 
xGEOID20B geoid model and computes orthometric height (H) with supplied GRS80 ellipsoid height (h).

The xGEOID20B model is a deprecated research-grade geoid model and is no longer 
available through NGS online tools.  However, this script provides legacy extraction capability against the xGEOID20 GGXF grid file, to which a link is provided below.


## ⚠️ Default Behavior (read this first)

This tool is designed to run **non-interactively, out of the box**:

- It reads a **single** input CSV from the **`input/`** folder.
- It writes results to the **`output/`** folder using **UTC (GMT)
  timestamped** filenames, to the minute:
  - `<inputbase>_output_YYYYMMDDThhmmZ.csv`
  - `<inputbase>_batch_log_YYYYMMDDThhmmZ.txt`
- **It OVERWRITES without asking** (`overwrite = always`). Because each
  run's filenames carry the run's UTC timestamp, successive runs normally
  produce **distinct** files and do not clobber earlier results. Two runs
  in the *same clock minute* is the only collision case, and the
  `overwrite` policy governs it.

All timestamps are **UTC/GMT** by design (unambiguous; no daylight-saving
shifts). This behavior is configurable in **`config.ini`** — see
[Configuration](#configuration). If you need confirmation before
overwriting, set `overwrite = prompt`; to never overwrite, set
`overwrite = never`.


## Quick Start
1. Create the conda environment: `conda env create -f environment.yml`
2. Obtain the GGXF grid file (see [Data File](#data-file)).
3. Put your input CSV in the `input/` folder.
4. Run: `.\run.ps1`

Results appear in `output/`. See [Running the Tool](#running-the-tool) for
details and configuration.



## Background
The xGEOID20 model consists of two variants:
- **xGEOID20A** — static geoid undulation without airborne gravity
- **xGEOID20B** — static geoid undulation with airborne gravity *(this tool)*

This tool uses the **B model exclusively**, as it incorporates airborne gravity 
data and is considered the more accurate variant for the covered region.

The orthometric height relationship used is:

"H = h - N"

Where:
- `H` = orthometric height (m)
- `h` = ellipsoidal height (m), GRS80, IGS14 frame
- `N` = geoid undulation (m) from xGEOID20B


## Coverage
The xGEOID20B model covers the following regions:

| Region | Notes |
|---|---|
| CONUSPAC | CONUS, Alaska, Hawaii, and Pacific |
| Guam and Northern Mariana Islands | |
| American Samoa | |


## Coordinate Input Requirements

| Parameter | Requirement |
|---|---|
| Horizontal Reference Frame | **NAD83(2011) realization** (see below) |
| Ellipsoid | GRS80 |
| Latitude | Decimal degrees, positive north |
| Longitude | positive-west convention (e.g., 133.024 for SE Alaska) |
| Ellipsoidal Height | Meters, GRS80 ellipsoid |

> ## ⚠️ HORIZONTAL REFERENCE FRAME — INPUT REQUIREMENT (read first)
>
> **Input coordinates MUST be in the correct NAD83(2011) realization for
> their region.** This is the **user's responsibility** — the tool does
> **not** verify or convert the input frame. Supplying the wrong frame
> produces silently incorrect results.
>
> | Region | Required input frame | `input_frame` value |
> |---|---|---|
> | CONUS (incl. SE Alaska) | NAD83(2011/CORS96/2007) | `2011` |
> | Pacific | NAD83(PA11/PACP00) | `PA11` |
> | Marianas | NAD83(MA11/MARP00) | `MA11` |
>
> Declare the region's frame in `config.ini` under `[transform]`
> (`input_frame`). You must set this correctly for your data; there is no
> auto-detection.
>
> **Output:** the tool transforms these coordinates to **ITRF2014 / IGS14**
> (via the bundled NGS HTDP utility) and reports the transformed
> `lat_igs14`, `lon_igs14`, `igs14_ellip_h_m`. The orthometric height is
> then computed as **H = igs14_ellip_h_m − N** (matching the archived NGS
> web tool). The transform always runs and HTDP is required.

> **⚠️ Longitude Convention Warning:**
> This tool expects **positive west** longitudes as exported by OPUS
> and other NGS tools. Do **not** mix positive-west and negative-west longitudes
> in the same input file. The script will detect negative longitudes, flag them
> in the batch log, and skip negation for those rows — but mixed convention
> inputs will likely produce incorrect results.


## Interpolation Method
Biquadratic interpolation on a 3×3 node stencil, consistent with the
interpolation method specified in the xGEOID20 GGXF file metadata.


## Epoch
| Parameter | Value |
|---|---|
| Model Reference Epoch (T0) | 2005.0 |
| Processing Epoch | 2020.0 (January 1, 2020) |

Epoch correction uses the xDGEOID20 dynamic geoid velocity grid:

N(t) = N + velocity * (t - T0)


## Data File
The xGEOID20B GGXF grid file is **not included** in this repository.
It must be obtained separately from NGS and placed in the `GGXF/` folder
included with this tool.


### Obtaining the GGXF File:
Download the file from the following link:
https://geodesy.noaa.gov/research/data/xGEOID20.ggxf


### File Details:
| Property | Value |
|---|---|
| Filename | `xGEOID20.ggxf` |
| Size | ~403 MB |
| Format | GGXF (HDF5/NetCDF4) |
| Source | NOAA National Geodetic Survey |
| Model | xGEOID20 B variant (with airborne gravity) |
| Download URL | https://geodesy.noaa.gov/research/data/xGEOID20.ggxf |


### After Downloading:
Place the downloaded `xGEOID20.ggxf` directly into the `GGXF/` folder so
that the final path is:

    GGXF/xGEOID20.ggxf

The script locates the grid file automatically in this order:

1. The `XGEOID20_GGXF` environment variable, if set — point this at the
   full path of an `xGEOID20.ggxf` stored elsewhere (e.g. a shared or
   production copy). Example (PowerShell):

       $env:XGEOID20_GGXF = "C:\path\to\xGEOID20.ggxf"

2. Otherwise, `GGXF/xGEOID20.ggxf` in the script directory.

If neither is found, the script exits with an error explaining how to
obtain the file. See `GGXF/README.txt` for details. The `.gitignore` is
configured so the downloaded `*.ggxf` file is never committed.


## Requirements
Python 3.10+ and: **netCDF4**, **numpy**, and **openpyxl** (the last only
needed for `xlsx` output).

**Conda is the recommended package manager.** netCDF4 and numpy depend on
compiled binary libraries (HDF5, netCDF-C); conda resolves and installs
those far more reliably than pip. Create the environment from the included
definition:

```
conda env create -f environment.yml      # creates an env named 'xgeoid'
```

(A `requirements.txt` is also provided for pip users, but conda is
preferred for this tool.)


## Running the Tool

The simplest way to run is the included PowerShell launcher, **`run.ps1`**,
which selects the correct conda environment, verifies it, and then runs the
tool:

```powershell
.\run.ps1
```

That's it — drop your input CSV in `input/`, make sure the GGXF grid file
is available (see [Data File](#data-file)), and run `.\run.ps1`. Results
land in `output/` with UTC-timestamped names.

### How the launcher picks the environment
The launcher reads the `[runtime]` section of `config.ini`:

```ini
[runtime]
conda_root =        ; blank = autodetect; else path to your conda install
conda_env  =        ; blank = base env; else a named env (e.g. xgeoid)
```

- **`conda_root`** — leave blank to autodetect conda (first `conda` on
  `PATH`, then common locations like `%USERPROFILE%\Miniconda3`). Set it
  explicitly if conda is **not** on your `PATH`, or you have multiple
  installs and want a specific one. Example:
  `C:\Users\you\Miniconda3`.
- **`conda_env`** — leave blank for the `base` environment, or name the
  env you created (e.g. `xgeoid`).

The launcher fails with a clear message if conda can't be found, the named
environment doesn't exist, or the environment is missing `netCDF4`/`numpy`
(and tells you how to fix each). Once the runtime checks pass, it hands off
to the Python tool, which handles all input/output and data-file issues
itself.

### Running without the launcher
You can also run the Python script directly in any environment that has the
dependencies:

```
conda activate xgeoid
python xgeoid20b_batch_extract.py
```

In this case the `[runtime]` section is ignored (it is only used by
`run.ps1`).


## Input File Format
Place a single input CSV in the **`input/`** folder. The tool looks for a
file whose name contains the word `input` and ends in `.csv`
(e.g., `ak_panhandle_input.csv`). If more than one such file is present,
the tool stops and lists them so you can remove the extras. See
`input/README.txt`.

**Required columns (all four must be present):**

| Column | Meaning |
|---|---|
| `OPUS_PID` | Point identifier / label (any text) |
| `lat` | Latitude, decimal degrees, positive north |
| `lon` | Longitude, decimal degrees, **positive-west** (see below) |
| `ellip_h_m` | Ellipsoidal height, meters (GRS80) |

**Header rules:**
- **Case-insensitive** — `lat`, `LAT`, `Lat` are all accepted (likewise for
  the others).
- **Surrounding whitespace is ignored** — ` lat ` matches `lat`.
- **Column order does not matter** — the tool matches by header name.
- **Extra columns are ignored** — you may keep additional columns in your
  file; the tool only reads the four above.
- The first row **must** be the header row with these column names.

The `OPUS_PID` *values* (your station labels) are used exactly as written;
only the header names are normalized.

Example (any of these header spellings/orders work):

```
OPUS_PID,lat,lon,ellip_h_m
BBFG38,55.03511259,133.0239682,-1.964
BBBW71,55.09597375,131.2221351,-2.312
```

```
LON,LAT,Ellip_H_M,OPUS_PID
133.0239682,55.03511259,-1.964,BBFG38
```

See also the longitude-convention and horizontal-reference-frame
requirements above — they govern the *values*, while the rules here govern
the *headers*.


## Output Files
Result files are written to the **`output/`** folder and the batch log to
the **`logs/`** folder, all with UTC timestamped names (see Default
Behavior above).

### Output data — one or more formats
The `format` option in `config.ini` selects the output format(s). One or
more of `csv`, `json`, `xlsx`, comma-separated (default `csv`):

```ini
format = csv            ; just CSV (default)
format = csv,json       ; CSV and JSON
format = csv,json,xlsx  ; all three
```

All formats contain the **same data**. Files are named
`<inputbase>_output_YYYYMMDDThhmmZ.<ext>`:
- **csv** — comma-separated values (columns below).
- **json** — a `metadata` block (run/config info) plus a `data` array of
  row objects and a `columns` list.
- **xlsx** — Excel workbook (single sheet). Requires the `openpyxl`
  package; if it is not installed the xlsx output is skipped with a
  warning and the other formats still run.

Column description (same for every format):

OPUS_PID -- NGS OPUS Permanent Identifier
lat -- Input latitude (decimal degrees, 8dp)
lon -- Input longitude (decimal degrees, 8dp)
ellip_h_m -- Input ellipsoidal height (m, 4dp; NAD83 realization)
lat_igs14 -- Latitude transformed to ITRF2014/IGS14 (decimal degrees, 8dp)
lon_igs14 -- Longitude transformed to ITRF2014/IGS14 (decimal degrees, 8dp)
igs14_ellip_h_m -- Ellipsoidal height in ITRF2014/IGS14 (m, 4dp)
undulation_N_m -- xGEOID20B geoid undulation N (m, 4dp)
igs14_orthometric_H_m -- Orthometric height H = igs14_ellip_h_m - N (m, 4dp)

### Batch log
Written to `logs/` as `<inputbase>_batch_log_YYYYMMDDThhmmZ.txt`.

Contains:

Run timestamp (UTC) and duration
Input/output file names and formats
Total points processed, successful, and NaN/error counts
Longitude convention warnings (if any)
Grid edge warnings (if any)
Per-point error detail (if any)


## Configuration
Behavior is controlled by **`config.ini`** in the script directory. The
file is **optional** — if it is missing, or any value is blank, the tool
falls back to the built-in defaults shown below, so it still works out of
the box.

```ini
[paths]
ggxf_file  =                 ; blank = use env var, then GGXF/xGEOID20.ggxf
input_dir  = input
output_dir = output
log_dir    = logs

[model]
model = xGEOID20B
epoch = 2020.0
t0    = 2005.0

[options]
overwrite = always           ; always | never | prompt
format    = csv              ; csv | json | xlsx  (comma-separated for multiple)

[transform]
input_frame  = 2011          ; 2011 | PA11 | MA11  (NAD83 realization of INPUT)
input_epoch  = 2010.0        ; decimal year (recommended); calendar "M D Y" also OK
output_epoch = 2010.0        ; decimal year (recommended); calendar "M D Y" also OK
htdp_exe     =               ; blank = bundled HTDP/htdp360.exe
```

Notes:
- `input_dir` / `output_dir` / `log_dir` may be relative (to the script
  directory) or absolute.
- `format` selects one or more output formats (`csv`, `json`, `xlsx`),
  comma-separated. `xlsx` needs the `openpyxl` package; if absent it is
  skipped with a warning and the other formats still run.
- `overwrite` governs the rare case that a timestamped output file already
  exists (same-minute rerun): `always` overwrites silently (default),
  `never` skips and exits, `prompt` asks (interactive terminals only; in a
  non-interactive/piped run `prompt` behaves as `always`).
- `[transform]` controls the horizontal coordinate transform to
  ITRF2014/IGS14 (see the Horizontal Reference Frame requirement above).
  `input_frame` **must** match your data's NAD83 realization. Epochs are
  given as a **decimal year** (recommended, e.g. `2010.0`); a calendar date
  (`1 1 2010`) is also accepted. For the NAD83(2011/PA11/MA11) → IGS14
  transform the nominal reference epoch is **2010.0 for both input and
  output** (the defaults). The transform always runs; the bundled NGS HTDP
  utility is required and the feature is **Windows-only**; see
  `HTDP/README.txt`.

### GGXF file resolution
The GGXF grid file location is resolved in this order:
1. the `XGEOID20_GGXF` environment variable, if set;
2. `config.ini` `[paths] ggxf_file`, if set;
3. `GGXF/xGEOID20.ggxf` in the script directory.

Setting the environment variable or `ggxf_file` lets a shared/production
copy point at a single grid file without editing the script. See the
[Data File](#data-file) section and `GGXF/README.txt`.


## Sample Test
Sample test files `input/ak_example_input.csv` and
`output/ak_example_output.csv` are included in the repository to verify the
tool is working correctly. Run the script; it reads the sample input and
writes a UTC-timestamped output file to `output/`. Confirm the computed
values match `output/ak_example_output.csv` (the reference sample).

These values have been validated against the archived NGS xGEOID20B web tool
output, which is considered the reference standard for this tool.


## Validation
This tool has been validated against archived NGS xGEOID20B web tool output
for benchmark points in the southeastern Alaska panhandle region.  Observed differences are consistently within 0.001—0.004 m, well within the model's stated operational accuracy of ±0.01 m.


## License
See LICENSE for terms of use.


## Notes
The xGEOID20B GGXF file is not included in this repository and must
be obtained via the link above, (see the Data File section).  This tool is for research use and not intended for use in any production environment.  The xGEOID20 model is research-grade and considered deprecated.  Results should be used in accordance with the notes above.
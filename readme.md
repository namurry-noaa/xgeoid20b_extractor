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
| Horizontal Reference Frame | IGS14 |
| Ellipsoid | GRS80 |
| Latitude | Decimal degrees, positive north |
| Longitude | positive-west convention (e.g., 133.024 for SE Alaska) |
| Ellipsoidal Height | Meters, GRS80 ellipsoid, IGS14 reference frame |

> **⚠️ Longitude Convention Warning:**
> This tool expects **positive west** longitudes as exported by OPUS
> and other NGS tools. Do **not** mix positive-west and negative-west longitudes
> in the same input file. The script will detect negative longitudes, flag them
> in the batch log, and skip negation for those rows — but mixed convention
> inputs will likely produce incorrect results.

> **📝 Reference Frame Note:**
> OPUS-derived coordinates are in NAD83(2011), which is nominally equivalent
> to IGS14 at the centimeter level for most practical applications. If
> sub-centimeter accuracy is required, apply a formal frame transformation
> prior to running this tool.


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
Python 3.10+

See requirements.txt for Python dependencies.

Install dependencies with:
pip install -r requirements.txt


## Input File Format
Place a single input CSV in the **`input/`** folder. The tool looks for a
file whose name contains the word `input` and ends in `.csv`
(e.g., `ak_panhandle_input.csv`). If more than one such file is present,
the tool stops and lists them so you can remove the extras. See
`input/README.txt`.

Required columns:

OPUS_PID,lat,lon,ellip_h_m

Example:
OPUS_PID,lat,lon,ellip_h_m
BBFG38,55.03511259,133.0239682,-1.964
BBBW71,55.09597375,131.2221351,-2.312


## Output Files
Both output files are written to the **`output/`** folder with UTC
timestamped names (see Default Behavior above):

1.  Output CSV — `<inputbase>_output_YYYYMMDDThhmmZ.csv`
Column Description:
OPUS_PID -- NGS OPUS Permanent Identifier
lat -- Latitude (decimal degrees, 8dp)
lon -- Longitude (decimal degrees, 8dp)
ellip_h_m -- Ellipsoidal height (m, 4dp)
region -- xGEOID20B grid region used
undulation_N_m -- Static geoid undulation N (m, 4dp)
orthometric_H_m -- Static orthometric height H (m, 4dp)
epoch -- Processing epoch
undulation_N_epoch_corrected_m -- Epoch-corrected undulation N (m, 4dp)
orthometric_H_epoch_corrected_m -- Epoch-corrected orthometric height H (m, 4dp)

2.  Batch Log — `<inputbase>_batch_log_YYYYMMDDThhmmZ.txt`

Contains:

Run timestamp (UTC) and duration
Input/output file names
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

[model]
model = xGEOID20B
epoch = 2020.0
t0    = 2005.0

[options]
overwrite = always           ; always | never | prompt
```

Notes:
- `input_dir` / `output_dir` may be relative (to the script directory) or
  absolute.
- `overwrite` governs the rare case that a timestamped output file already
  exists (same-minute rerun): `always` overwrites silently (default),
  `never` skips and exits, `prompt` asks (interactive terminals only; in a
  non-interactive/piped run `prompt` behaves as `always`).

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
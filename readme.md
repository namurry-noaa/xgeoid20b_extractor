# xGEOID20B Batch Extraction Tool


## Overview
This tool extracts geoid undulation values (N) from the NGS experimental 
xGEOID20B geoid model and computes orthometric heights from GRS80 ellipsoidal 
heights. It is intended for internal NOAA/NGS use only.

The xGEOID20B model is a deprecated research-grade geoid model and is no longer 
available through NGS online tools. This script provides a local extraction 
capability against the raw GGXF grid file.


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
| Longitude | NGS positive-west convention (e.g., 133.024 for SE Alaska) |
| Ellipsoidal Height | Meters, against GRS80 in IGS14 frame |

> **⚠️ Longitude Convention Warning:**
> This tool expects NGS-style **positive west** longitudes as exported by OPUS
> and other NGS tools. Do **not** mix positive-west and negative-west longitudes
> in the same input file. The script will detect negative longitudes, flag them
> in the batch log, and skip negation for those rows — but mixed convention
> inputs may produce incorrect results.

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
It must be obtained separately from the NGS internal data server and
placed in the location specified by the `FILE_PATH` constant in the script.


### Obtaining the GGXF File:
> **⚠️ NOAA Internal Access Only**
> The following URL is accessible from the NOAA internal network only.

Download the file from the NGS internal data server:

https://geodesy.noaa.gov/research/data/xGEOID20.ggxf


### File Details:
| Property | Value |
|---|---|
| Filename | `xGEOID20.ggxf` |
| Size | ~413 MB |
| Format | GGXF (HDF5/NetCDF4) |
| Source | NOAA National Geodetic Survey |
| Model | xGEOID20 B variant (with airborne gravity) |
| Internal URL | https://geodesy.noaa.gov/research/data/xGEOID20.ggxf |


### After Downloading:
Update the `FILE_PATH` constant at the top of `xgeoid20b_batch.py` to
point to your local copy of the file:

FILE_PATH = r"C:\your\local\path\xGEOID20.ggxf"


## Requirements
See requirements.txt for Python dependencies.

Install dependencies with:

bash
Save
Copy
1
pip install -r requirements.txt
Tested with:

Python 3.10+
Spyder 5.5.6
Miniconda3


## Input File Format
The input file must be a standard ASCII CSV with the word input in the
filename (e.g., AK_panhandle_input.csv).

Required columns:

OPUS_PID,lat,lon,ellip_h_m
Example:

OPUS_PID,lat,lon,ellip_h_m
BBFG38,55.03511259,133.0239682,-1.964
BBBW71,55.09597375,131.2221351,-2.312


## Output Files
The script generates two output files in the same directory as the script:

Output CSV
Filename: input filename with input replaced by output
(e.g., AK_panhandle_output.csv)

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


## Batch Log
Filename: input filename with _batch_log.txt appended
(e.g., AK_panhandle_input_batch_log.txt)

Contains:

Run timestamp and duration
Input/output file names
Total points processed, successful, and NaN/error counts
Longitude convention warnings (if any)
Per-point error detail (if any)
Configuration
The following constants at the top of the script may be adjusted as needed:

FILE_PATH = r"C:\your\local\path\xGEOID20.ggxf"   # path to GGXF file
MODEL     = 'xGEOID20B'                             # model variant
EPOCH     = 2020.0                                  # processing epoch
T0        = 2005.0                                  # model reference epoch


##Sample Test
A sample test file sample_test_input.csv is included in the repository.
To verify the script is working correctly, run it against this file and
confirm the following expected output:

Field     Expected Value
OPUS_PID  BBFG38
region    CONUSPAC
undulation_N_m   -4.0193
orthometric_H_m  2.0553
undulation_N_epoch_corrected_m  -4.0208
orthometric_H_epoch_corrected_m  2.0568


These values have been validated against archived NGS xGEOID20B web tool
output and are considered the reference standard for this tool.


## Validation
This tool has been validated against archived NGS xGEOID20B web tool output
for benchmark points in the southeastern Alaska panhandle region and broader
CONUSPAC coverage area. Observed differences are consistently within
0.001—0.004 m, well within the model's stated operational accuracy of ±0.01 m.


## License
See LICENSE for terms of use.


## Notes
The xGEOID20B GGXF file is not included in this repository and must
be obtained from the NGS internal data server (see Data File section).
This tool is for internal NOAA use only and is not intended for public distribution.
The xGEOID20B model is research-grade and deprecated. Results should be used
accordingly and not cited as official NGS products.
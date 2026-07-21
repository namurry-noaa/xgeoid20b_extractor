# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.3.0] - 2026-07-20

### Added
- **Horizontal coordinate transform to ITRF2014 / IGS14.** The tool now
  transforms the input horizontal coordinates from their NAD83 realization
  to ITRF2014/IGS14 using the bundled NGS HTDP utility, and appends the
  transformed position as new output columns: `input_frame`, `lat_igs14`,
  `lon_igs14`, `eht_igs14_m`, `coord_out_epoch`. The geoid/orthometric
  computation is unchanged — it always uses the input coordinates.
- Bundled `HTDP/htdp360.exe` (NGS HTDP v3.6.0) + `HTDP/README.txt`. HTDP is
  driven via the standard-library `subprocess` module (no third-party
  dependencies; **Windows-only** feature).
- `[transform]` section in `config.ini`: `enabled`, `input_frame`
  (`2011` / `PA11` / `MA11`), `input_epoch`, `output_epoch` (decimal year
  recommended; calendar date also accepted), and optional `htdp_exe`
  override. Output frame is fixed to IGS14 (HTDP code 25). For the
  NAD83 → IGS14 transform the nominal reference epoch is 2010.0 for both
  input and output (the defaults).
- README: prominent **Horizontal Reference Frame input-requirement** block
  (the user must supply the correct NAD83 realization; no auto-detection).

### Changed
- Documentation now states the input horizontal frame requirement as
  NAD83(2011/PA11/MA11) rather than implying IGS14 input; IGS14 is the
  transformed **output** frame.
- Pinned the conda environment to Python 3.12 in `environment.yml` (avoids
  bleeding-edge 3.14 build/GIL issues).

### Backward compatibility
- Non-breaking (MINOR). Existing output columns are unchanged; the IGS14
  columns are appended. The transform can be disabled via config. Sample
  geoid results are byte-for-byte identical to v2.2.0.

### Validation status
- Geodetically validated against manual NGS HTDP 3.6.0 runs for all three
  supported realizations: NAD83(2011)→IGS14 (5 CONUS points),
  NAD83(PA11)→IGS14 (5 Pacific points), and NAD83(MA11)→IGS14 (1 Marianas
  point). The tool reproduces every reference coordinate to within 1e-9°
  (~0.1 mm) and 1 mm in ellipsoidal height, at the nominal 2010.0 epoch.

## [2.2.0] - 2026-07-17

### Added
- `run.ps1` PowerShell launcher. It selects the conda environment, verifies
  conda + the environment + required packages (netCDF4, numpy), then runs
  the tool. Data/input/output issues are still handled by the Python tool.
- `environment.yml` conda environment definition (channel: conda-forge;
  creates an env named `xgeoid`). Conda is now the recommended package
  manager, since netCDF4/numpy depend on compiled binaries that conda
  resolves more reliably than pip.
- `[runtime]` section in `config.ini` with `conda_root` and `conda_env`,
  read only by `run.ps1`. Blank `conda_root` autodetects conda (PATH, then
  common user-profile locations); an explicit value overrides autodetect
  entirely. Blank `conda_env` uses the base environment.
- README "Quick Start" and "Running the Tool" sections; Requirements
  section now conda-first.

### Backward compatibility
- Non-breaking (MINOR). The Python tool is unchanged in behavior; the
  launcher and environment definition are additive. You can still run
  `python xgeoid20b_batch_extract.py` directly in any environment that has
  the dependencies.

## [2.1.0] - 2026-07-17

### Added
- `config.ini` (optional) for GGXF path, input/output folders, model,
  epoch, T0, and overwrite policy. Missing file or blank values fall back
  to built-in defaults, so the tool still runs out of the box.
- Dedicated `input/` and `output/` folders (each with a tracked
  `README.txt`). Input CSVs are read from `input/`; results are written to
  `output/`.
- UTC (GMT) timestamped output and log filenames, to the minute
  (`<inputbase>_output_YYYYMMDDThhmmZ.csv` /
  `..._batch_log_YYYYMMDDThhmmZ.txt`). All in-file timestamps are UTC too.
- Error-and-exit if more than one `*input*.csv` is found (lists the
  candidates) instead of silently picking one.
- GGXF resolution now also honors `config.ini [paths] ggxf_file`
  (order: env var, then config, then `GGXF/xGEOID20.ggxf`).

### Changed
- Default run is now non-interactive: `overwrite = always`. Timestamped
  filenames mean runs normally do not collide. `overwrite = prompt` and
  `never` remain available; `prompt` degrades to `always` when stdin is
  not an interactive terminal (prevents hangs in scheduled/piped runs).
- Sample files moved into the new folders: `input/ak_example_input.csv`
  and `output/ak_example_output.csv`.
- README expanded with a prominent "Default Behavior" section and a
  "Configuration" section.

### Backward compatibility
- Non-breaking (MINOR). If `config.ini` is absent the tool uses defaults;
  if the `input/` folder is absent it falls back to scanning the script
  directory as before.

## [2.0.0] - 2026-07-17

### Changed (breaking)
- **GGXF file location is now resolved automatically instead of a
  hardcoded `FILE_PATH` constant.** The `FILE_PATH` constant has been
  removed. The script now looks for the grid file in this order:
  1. the `XGEOID20_GGXF` environment variable, if set;
  2. `GGXF/xGEOID20.ggxf` in the script directory.
  Upgrading users must place the downloaded `xGEOID20.ggxf` in the new
  `GGXF/` folder (or set `XGEOID20_GGXF`) rather than editing the source.

### Added
- `GGXF/` folder (with `README.txt`) as the default drop location for the
  downloaded grid file. The `.gitignore` tracks the README but ignores the
  `*.ggxf` file itself.
- Fail-fast error with download guidance when the GGXF file cannot be
  found.
- `safe_node_value()` guard: interpolation now raises a clear error on
  masked / fill / NaN grid nodes instead of silently producing a bad
  result. (Current xGEOID20 grids are fully populated, so no behavior
  change in practice.)
- Up-front validation that the input CSV contains the required columns
  (`OPUS_PID`, `lat`, `lon`, `ellip_h_m`) and at least one data row, with
  a clear error message instead of a generic per-row failure.
- Grid-edge reporting: points within half a cell of a grid edge (where the
  3x3 interpolation stencil is clamped inward, yielding a mild
  extrapolation) are now counted on the console and listed in the batch
  log under a "Grid Edge Warnings" section.
- `__version__` string; version now printed to the console and written to
  the batch log.

### Fixed
- ASCII-safe console output. Previously the script could crash with
  `UnicodeEncodeError` on legacy Windows (cp1252) terminals due to emoji
  in `print()` statements.
- BOM-safe input CSV reading (`utf-8-sig`), preventing a corrupted
  `OPUS_PID` header when the input is saved from Excel. Output and log
  files are now written with an explicit `utf-8` encoding.
- Renamed sample files to lowercase: `ak_example_input.csv`,
  `ak_example_output.csv`.
- README documentation and minor typo corrections.

## [1.0.1] - 2026-07-16
- Corrected typos in documentation.

## [1.0.0] - 2026-07-16
- Initial release: batch extraction of xGEOID20B geoid undulation and
  orthometric height, with biquadratic interpolation and epoch/velocity
  correction.

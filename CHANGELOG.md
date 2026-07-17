# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

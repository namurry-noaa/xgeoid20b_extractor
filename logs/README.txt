Logs Folder
============================================================

Batch log files are written here.

For each run the tool writes a UTC (GMT) timestamped log:

    <inputbase>_batch_log_YYYYMMDDThhmmZ.txt

  Example (input "ak_example_input.csv", run 2026-07-21 09:30 UTC):
    ak_example_batch_log_20260721T0930Z.txt

The log records the run configuration (version, model, epoch, GGXF file,
transform frames/epochs), point counts, longitude-convention warnings,
grid-edge warnings, and per-point error detail.

NOTE
------------------------------------------------------------
  The .gitignore tracks this README but ignores the generated
  *_batch_log_*.txt files.

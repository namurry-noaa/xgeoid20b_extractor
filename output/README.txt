Output Folder
============================================================

Generated output files are written here.

For each run the tool writes two files, named after the input file
with a UTC (GMT) run timestamp appended to the minute:

    <inputbase>_output_YYYYMMDDThhmmZ.csv
    <inputbase>_batch_log_YYYYMMDDThhmmZ.txt

  Example (input "ak_example_input.csv", run 2026-07-17 09:30 UTC):
    ak_example_output_20260717T0930Z.csv
    ak_example_batch_log_20260717T0930Z.txt

  The trailing "Z" denotes Zulu / UTC time. Timestamps are in UTC by
  design (unambiguous, no daylight-saving shifts).

OVERWRITE BEHAVIOR
------------------------------------------------------------
  Because every run is timestamped to the minute, successive runs
  normally produce distinct files and do NOT overwrite each other.
  Two runs in the same clock minute would collide; the overwrite
  policy for that case is set in config.ini (default: always).

OUTPUT COLUMNS
------------------------------------------------------------
  OPUS_PID, lat, lon, ellip_h_m, region, undulation_N_m,
  orthometric_H_m, epoch, undulation_N_epoch_corrected_m,
  orthometric_H_epoch_corrected_m

NOTE
------------------------------------------------------------
  The .gitignore tracks this README but ignores the generated
  *_output_*.csv and *_batch_log_*.txt files.

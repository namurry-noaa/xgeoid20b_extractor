Input Folder
============================================================

Place your input CSV file(s) here.

The tool looks in this folder for a file whose name contains "input"
and ends in .csv (case-insensitive), e.g.:

    ak_panhandle_input.csv

REQUIRED COLUMNS
------------------------------------------------------------
    OPUS_PID,lat,lon,ellip_h_m

  OPUS_PID   - NGS OPUS Permanent Identifier (any string label)
  lat        - Latitude, decimal degrees, positive north
  lon        - Longitude, decimal degrees, positive-WEST (NGS/OPUS
               convention, e.g. 133.024 for SE Alaska)
  ellip_h_m  - Ellipsoidal height, meters (GRS80, IGS14 frame)

IMPORTANT
------------------------------------------------------------
  * Only ONE input CSV should be present. If more than one file with
    "input" in the name is found, the tool stops and lists them, so
    you can remove the extras.
  * A sample file, ak_example_input.csv, is provided here to verify
    the tool is working.

NOTE
------------------------------------------------------------
  The .gitignore tracks this README but ignores the CSV files you
  place here (except the provided ak_example_input.csv sample).

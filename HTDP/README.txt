NGS HTDP Utility (Horizontal Time-Dependent Positioning)
============================================================

This folder contains the NGS HTDP command-line utility used by the tool's
optional horizontal coordinate transform.


BUNDLED FILE
------------------------------------------------------------
  htdp360.exe   - NGS HTDP version 3.6.0 (Windows executable)

Unlike the large GGXF grid file, HTDP is small and is committed with this
project so the transform works out of the box on Windows.


WHAT IT DOES
------------------------------------------------------------
  The tool transforms the input horizontal coordinates from their NAD83
  realization (NAD83(2011) / NAD83(PA11) / NAD83(MA11)) to ITRF2014 /
  IGS14, and adds the transformed lat/lon (and ellipsoidal height) to the
  output as extra columns. See the "Horizontal Reference Frames" and
  "Configuration" sections of readme.md.


HOW THE TOOL USES IT
------------------------------------------------------------
  The tool drives htdp360.exe via Python's standard-library subprocess
  module (feeding it the menu keystrokes and a temporary input file, then
  reading its output file from a temporary working directory). No extra
  Python packages are required.

  HTDP is a Windows-only executable, so the horizontal transform feature
  is available on Windows only. The rest of the tool (geoid extraction) is
  platform-independent.


OVERRIDE
------------------------------------------------------------
  By default the tool uses this bundled HTDP/htdp360.exe. To use a
  different HTDP executable, set htdp_exe in config.ini under [transform].


SOURCE
------------------------------------------------------------
  NOAA National Geodetic Survey - HTDP (Horizontal Time-Dependent
  Positioning). See the NGS HTDP user guide for full documentation of the
  transformation models and supported reference frames.

xGEOID20 GGXF Grid File - Download Required
============================================================

This folder is where the xGEOID20 GGXF grid file must be placed.

The grid file is NOT included in this repository because of its size
(~403 MB). You must download it yourself from the NGS data server.


REQUIRED FILE
------------------------------------------------------------
  Filename : xGEOID20.ggxf
  Size     : ~403 MB
  Format   : GGXF (HDF5 / NetCDF4)
  Source   : NOAA National Geodetic Survey


DOWNLOAD
------------------------------------------------------------
  https://geodesy.noaa.gov/research/data/xGEOID20.ggxf

  After downloading, place the file directly in this GGXF/ folder so
  that the final path is:

      GGXF/xGEOID20.ggxf


HOW THE SCRIPT FINDS THE FILE
------------------------------------------------------------
  The script resolves the GGXF path in this order:

    1. The XGEOID20_GGXF environment variable, if set. Point this at
       the full path of an xGEOID20.ggxf stored elsewhere (useful for
       a shared/production copy):

         Windows (PowerShell):
           $env:XGEOID20_GGXF = "C:\path\to\xGEOID20.ggxf"

         Windows (cmd):
           set XGEOID20_GGXF=C:\path\to\xGEOID20.ggxf

    2. Otherwise, GGXF/xGEOID20.ggxf in the script directory (this
       folder).

  If neither is found, the script exits with an error explaining how
  to obtain the file.


NOTE
------------------------------------------------------------
  The .gitignore is configured to ignore *.ggxf files, so the grid
  file you download here will never be committed to the repository.
  Only this README.txt is tracked.

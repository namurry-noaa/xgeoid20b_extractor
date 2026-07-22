Validation Folder
============================================================

This folder holds the tool's validation/regression check. It is a
DEVELOPER check and is separate from the "sample test" dataset in the
input/ and output/ folders (which is just example data to confirm the
tool runs).


test_htdp_transform.py
------------------------------------------------------------
  Verifies the HTDP horizontal coordinate transform (NAD83 realizations ->
  ITRF2014 / IGS14) against 11 reference points produced manually with NGS
  HTDP 3.6.0:

     NAD83(2011)  -> IGS14   5 points (CONUS, Key West FL area)
     NAD83(PA11)  -> IGS14   5 points (Pacific, Hawaii)
     NAD83(MA11)  -> IGS14   1 point  (Marianas, Guam)

  The reference vectors are embedded in the script. It feeds the same
  inputs through the tool's HTDP wrapper and confirms the results still
  match to within ~0.1 mm horizontally and 1 mm in height, at the nominal
  2010.0 epoch.


HOW TO RUN
------------------------------------------------------------
  From the repository root, in the tool's environment (Windows; the
  bundled HTDP/htdp360.exe must be present):

     python validation/test_htdp_transform.py

  It prints one line per point and a final:

     RESULT: all 11 points match reference (PASS)

  and exits 0 on success, non-zero if any point fails.


WHY IT EXISTS
------------------------------------------------------------
  The transform involves sign conventions, reference-frame codes, and
  epochs - exactly the kind of details that can break subtly. This check
  preserves the (manually produced) validation vectors so the transform
  can be re-verified in seconds after any code change, without redoing the
  manual HTDP runs.

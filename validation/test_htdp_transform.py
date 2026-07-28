"""
Regression test for the HTDP horizontal transform (NAD83 realizations ->
ITRF2014 / IGS14).

Validates the tool's HTDP wrapper against reference vectors produced
manually with NGS HTDP 3.6.0 (menu option 4, output frame code 25 =
ITRF2014/IGS14) at the nominal reference epoch 2010.0 for both input and
output. Covers all three supported realizations:

    NAD83(2011/CORS96/2007)  - CONUS   (5 points, Key West FL area)
    NAD83(PA11/PACP00)        - Pacific (5 points, Hawaii)
    NAD83(MA11/MARP00)        - Marianas (1 point, Guam)

Run (from the repo root, in an environment with the tool importable and the
bundled HTDP/htdp360.exe present; Windows only):

    python validation/test_htdp_transform.py

Exits non-zero if any transformed coordinate differs from the reference by
more than the tolerance below.
"""

import os
import sys

# Make the tool importable when run from the repo root or the validation/ dir.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, _REPO)

import xgeoid20b_extractor as m  # noqa: E402

# Tolerances: 1e-9 degrees (~0.1 mm horizontally) and 1 mm in height.
TOL_DEG = 1e-9
TOL_M = 0.001

# Nominal reference epoch for NAD83 -> IGS14 (both input and output).
IN_EPOCH = "2010.0"
OUT_EPOCH = "2010.0"

# (input_frame): {input records, expected IGS14 output}
# input record = (lat, lon, eht, label); lat/lon decimal deg (positive-west),
# eht meters. Expected = (lat, lon, eht) in IGS14.
CASES = {
    "2011": {
        "input": [
            (24.57223388, 81.70410173, -21.004, "AA0086"),
            (24.60344171, 81.64300397, -17.879, "AA0112"),
            (24.60587913, 81.63756261, -19.126, "AA0113"),
            (24.61566607, 81.61648438, -18.494, "AA0117"),
            (24.64996333, 81.57263639, -21.505, "AA0130"),
        ],
        "expected": [
            (24.5722385867, 81.7041063343, -22.633),
            (24.6034464289, 81.6430085590, -19.508),
            (24.6058838499, 81.6375671976, -20.755),
            (24.6156707938, 81.6164889622, -20.123),
            (24.6499680656, 81.5726409622, -23.134),
        ],
    },
    "PA11": {
        "input": [
            (21.30517824, 157.8639909, 18.552, "TU0286"),
            (21.30379989, 157.8636224, 18.262, "TU0291"),
            (21.30331458, 157.8645326, 17.839, "TU0292"),
            (21.63019532, 157.9212372, 18.755, "TU0494"),
            (20.89526271, 156.4686445, 19.243, "TU0847"),
        ],
        "expected": [
            (21.3051873688, 157.8640159742, 18.832),
            (21.3038090188, 157.8636474743, 18.542),
            (21.3033237089, 157.8645576743, 18.119),
            (21.6302044346, 157.9212622662, 19.040),
            (20.8952718187, 156.4686695599, 19.469),
        ],
    },
    "MA11": {
        "input": [
            (13.42892181, 144.8012663, 89.422, "DH2989"),
        ],
        "expected": [
            (13.4289259042, 144.8012831166, 89.140),
        ],
    },
}


def main():
    try:
        htdp = m.resolve_htdp_path("")
    except FileNotFoundError as e:
        print(f"SKIP: HTDP executable not found ({e})")
        return 0  # not a failure of the transform logic itself

    failures = 0
    total = 0
    for frame, data in CASES.items():
        results = m.htdp_transform_file(
            htdp, data["input"], frame, IN_EPOCH, OUT_EPOCH
        )
        print(f"=== {frame} -> IGS14 ({len(results)} points) ===")
        for (glat, glon, geht), (elat, elon, eeht) in zip(results, data["expected"]):
            total += 1
            dlat, dlon, deht = abs(glat - elat), abs(glon - elon), abs(geht - eeht)
            ok = dlat < TOL_DEG and dlon < TOL_DEG and deht < TOL_M
            if ok:
                print(f"  OK  ({glat:.10f}, {glon:.10f}, {geht:.3f})")
            else:
                failures += 1
                print(f"  FAIL got ({glat:.10f}, {glon:.10f}, {geht:.3f})")
                print(f"       exp ({elat:.10f}, {elon:.10f}, {eeht:.3f})")
                print(f"       d   dlat={dlat:.2e} dlon={dlon:.2e} deht={deht:.4f}")

    print()
    if failures:
        print(f"RESULT: {failures} of {total} points FAILED")
        return 1
    print(f"RESULT: all {total} points match reference (PASS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

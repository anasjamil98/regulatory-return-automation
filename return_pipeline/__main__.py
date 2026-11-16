"""Command line entry point: python -m return_pipeline --period 2025-06"""

import argparse
import sys
from pathlib import Path

from .build import BLOCKED, ROOT, run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build Form PS-M1 for one month.")
    parser.add_argument("--period", required=True, help="reporting month, e.g. 2025-06")
    parser.add_argument("--db", default=str(ROOT / "data" / "zaffre.db"))
    parser.add_argument("--out", default=str(ROOT / "output"))
    parser.add_argument("--variance-threshold", type=float, default=0.25)
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"No database at {args.db}. Run: python data/generate.py", file=sys.stderr)
        return 2

    manifest = run(args.db, args.period, args.out, args.variance_threshold)

    print(f"Run {manifest['run_id']}")
    for check in manifest["checks"]:
        if check["passed"]:
            mark = "PASS  "
        else:
            mark = "FAIL  " if check["severity"] == "fail" else "REVIEW"
        print(f"  {mark}  {check['name']}: {check['detail']}")
    print(f"Status: {manifest['status']}")
    if manifest["output"]:
        print(f"Wrote {Path(args.out) / manifest['output']['file']}")
    else:
        print("No return written. Fix the failed checks and run again.")
    return 1 if manifest["status"] == BLOCKED else 0


if __name__ == "__main__":
    sys.exit(main())

"""Run Refresh (Component B) over all companies.

  python -m scripts.run_refresh            # FAST profile (2x/day): speed-first
  python -m scripts.run_refresh --deep     # DEEP profile (nightly): completeness-first
  python -m scripts.run_refresh --workers 30   # override worker count
"""
import argparse

from jobbot.refresh import DEEP, FAST, run_refresh


def main():
    ap = argparse.ArgumentParser(description="Poll all companies' ATS APIs and fill listings.")
    ap.add_argument("--deep", action="store_true",
                    help="thorough nightly sweep: patient retries, high trip threshold, "
                         "incremental DB flush")
    ap.add_argument("--workers", type=int, default=None, help="override the profile's worker count")
    args = ap.parse_args()
    run_refresh(policy=DEEP if args.deep else FAST, workers=args.workers)


if __name__ == "__main__":
    main()

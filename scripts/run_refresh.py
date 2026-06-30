"""Run Refresh (Component B) over all companies. Stage 5 schedules this.

  python -m scripts.run_refresh                # 20 concurrent workers
  python -m scripts.run_refresh --workers 10   # dial down if rate-limited (429s)
"""
import argparse

from jobbot.refresh import run_refresh


def main():
    ap = argparse.ArgumentParser(description="Poll all companies' ATS APIs and fill listings.")
    ap.add_argument("--workers", type=int, default=60, help="concurrent polling threads")
    args = ap.parse_args()
    run_refresh(workers=args.workers)


if __name__ == "__main__":
    main()

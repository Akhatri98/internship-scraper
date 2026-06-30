import argparse
from jobbot.refresh import run_refresh


def main():
    ap = argparse.ArgumentParser(description="Poll all companies' ATS APIs and fill listings.")
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between polled companies")
    args = ap.parse_args()
    run_refresh(delay=args.delay)


if __name__ == "__main__":
    main()

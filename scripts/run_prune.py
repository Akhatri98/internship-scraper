import argparse
from jobbot.prune import run_prune


def main():
    ap = argparse.ArgumentParser(description="Remove listings no longer served by a healthy board.")
    ap.add_argument("--dry-run", action="store_true",
                    help="report prune candidates without deleting anything")
    args = ap.parse_args()
    run_prune(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

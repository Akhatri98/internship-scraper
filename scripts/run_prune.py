import argparse
from jobbot.prune import run_prune


def main():
    ap = argparse.ArgumentParser(description="Remove listings no longer served by a healthy board.")
    ap.add_argument("--dry-run", action="store_true",
                    help="report prune candidates without deleting anything")
    ap.add_argument("--force", action="store_true",
                    help="override the safety-fraction abort. OPERATOR USE ONLY — for "
                         "clearing a genuine backlog after confirming with --dry-run. "
                         "Never put this in a workflow.")
    ap.add_argument("--max-delete", type=int, default=None, metavar="N",
                    help="delete at most N listings (most-stale first), then stop")
    args = ap.parse_args()
    run_prune(dry_run=args.dry_run, force=args.force, max_delete=args.max_delete)


if __name__ == "__main__":
    main()

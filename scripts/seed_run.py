import argparse
from jobbot.seed import run


def main():
    ap = argparse.ArgumentParser(description="One-time Serper seed.")
    ap.add_argument("--dry-run", action="store_true", help="run ~5 diverse queries for real")
    ap.add_argument("--go", action="store_true", help="FULL BURN — spends the grant")
    ap.add_argument("--max-pages", type=int, default=10, help="pagination cap per combo")
    ap.add_argument("--budget", type=int, default=2400, help="hard credit cap for the full burn")
    ap.add_argument("--max-queries", type=int, default=None, help="cap total combos (with --go)")
    args = ap.parse_args()

    if args.dry_run and args.go:
        ap.error("pick one of --dry-run / --go, not both")

    if args.dry_run:
        run.dry_run()
    elif args.go:
        run.full_burn(max_pages=args.max_pages, budget=args.budget, max_queries=args.max_queries)
    else:
        run.preview()


if __name__ == "__main__":
    main()

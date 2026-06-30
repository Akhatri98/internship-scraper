import argparse
from jobbot.discover.run import run_discover
from jobbot.seed.domains import SEED_DOMAINS


def main():
    ap = argparse.ArgumentParser(description="Common Crawl company discovery.")
    ap.add_argument("--max-pages", type=int, default=None, help="cap CDX pages per domain")
    ap.add_argument("--only", default=None, help="restrict to one ats_source (e.g. rippling)")
    args = ap.parse_args()

    domains = SEED_DOMAINS
    if args.only:
        domains = [d for d in SEED_DOMAINS if d[1] == args.only]
        if not domains:
            ap.error(f"no domain with ats_source={args.only!r}")

    run_discover(domains=domains, max_pages=args.max_pages)


if __name__ == "__main__":
    main()

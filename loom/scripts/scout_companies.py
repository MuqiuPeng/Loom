"""Discover companies to contact, from a category and an area.

    # job outreach — companies that may hire but don't advertise
    python -m loom.scripts.scout_companies "software development company" \
        --near "Surry Hills, Sydney" --limit 20

    # market research — aggregate only, no detail kept
    python -m loom.scripts.scout_companies "cafe" \
        --near "Marrickville, Sydney" --limit 60 --stats-only

    # write the ToS-clean subset for follow-up
    python -m loom.scripts.scout_companies "digital agency" \
        --near "Sydney CBD" --out leads.json

--out writes only what Candidate.persistable() returns: the place_id plus what
came off the company's own website. Google's name/address/phone stay in the
terminal and are never written to disk — see company_scout.py for why.

Cost: each search page is one billable Places Text Search call, on the
Enterprise SKU because the website field is requested. --stats-only still
needs that field (it's the thing being counted), so it costs the same.
"""

import argparse
import asyncio
import json
import sys

from dotenv import load_dotenv

from loom.services.company_scout import scout, summarise
from loom.services.google import close_http_client
from loom.services.google.client import GoogleAPIError

load_dotenv()


def render(candidates: list) -> None:
    # Best leads first: the more that's wrong, the more there is to pitch.
    for c in sorted(candidates, key=lambda x: -x.opportunity):
        print(f"\n[{c.opportunity:>2}] {c.google_name}")
        print(f"     {c.google_address}")
        if c.google_website:
            print(f"     site     {c.site_url or c.google_website}")
        else:
            print("     site     — none listed")
        for finding in c.audit.findings if c.audit else ():
            print(f"     ⚠ {finding.label} — {finding.detail}")
        if c.careers_url:
            print(f"     careers  {c.careers_url}")
        if c.emails:
            print(f"     email    {', '.join(c.emails[:4])}")
        if c.google_phone:
            print(f"     phone    {c.google_phone}")
        if c.fetch_error:
            print(f"     note     {c.fetch_error}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("query", help='category, e.g. "software development company"')
    parser.add_argument("--near", help='area to bias to, e.g. "Surry Hills, Sydney"')
    parser.add_argument("--radius", type=int, default=5000, help="bias radius in metres")
    parser.add_argument("--limit", type=int, default=20, help="max results")
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="aggregate counts only; skips website fetches and keeps no detail",
    )
    parser.add_argument("--out", help="write the persistable subset to this JSON file")
    args = parser.parse_args()

    try:
        candidates = await scout(
            args.query,
            near=args.near,
            radius_m=args.radius,
            max_results=args.limit,
            enrich=not args.stats_only,
        )
    except GoogleAPIError as e:
        print(f"Places search failed: {e}", file=sys.stderr)
        return 1
    finally:
        await close_http_client()

    stats = summarise(candidates)
    if args.stats_only:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    render(candidates)
    print(
        f"\n{stats['total']} found · {stats['without_website']} without a website "
        f"({stats['pct_without_website']}%) · "
        f"{sum(1 for c in candidates if c.emails)} with a published email"
    )

    if args.out:
        payload = [c.persistable() for c in candidates]
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"wrote {len(payload)} records to {args.out} (place_id + self-sourced only)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

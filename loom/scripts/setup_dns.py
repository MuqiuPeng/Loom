"""Add the mail DNS records for a domain, via the Cloudflare API.

Six records by hand in a web console is three minutes and one typo. The typo
is the problem: a wrong SPF include fails open and silently, and you find out
because mail lands in spam a week later.

Shows what it would do and changes nothing unless you pass --apply. DNS on a
live domain is not a place for a script that acts first.

Never deletes. If a record it wants already exists with a different value it
says so and leaves it alone, because deciding which of two SPF records to
throw away is not a decision to make from a script.

    export CLOUDFLARE_API_TOKEN=...        # Edit zone DNS, scoped to the zone
    python -m loom.scripts.setup_dns robindev.org --lark-verify=ATEeAL...
    python -m loom.scripts.setup_dns robindev.org --lark-verify=ATEeAL... --apply

The token needs one permission: Zone → DNS → Edit, on this zone only. Make it
at Cloudflare → My Profile → API Tokens → Create Token → "Edit zone DNS".

Deliberately not using the official `cloudflare` SDK. This runs once per
domain; a dependency added for a one-off setup task is a dependency to
maintain forever, and httpx is already here.
"""

import argparse
import os
import pathlib
import sys

import httpx

API = "https://api.cloudflare.com/client/v4"

# Lark's own values, taken from its domain-setup panel and verified against
# live DNS: spf.onlarksuite.com really does publish an SPF record, whereas
# spf.larksuite.com is a CDN alias with none.
LARK_SPF = "v=spf1 +include:spf.onlarksuite.com -all"
LARK_MX = [("mx1.larksuite.com", 1), ("mx2.larksuite.com", 5), ("mx3.larksuite.com", 10)]


class SetupError(RuntimeError):
    pass


def call(client: httpx.Client, method: str, path: str, **kw) -> dict:
    response = client.request(method, f"{API}{path}", **kw)
    try:
        body = response.json()
    except ValueError:
        raise SetupError(f"{method} {path}: {response.status_code} {response.text[:200]}")
    if not body.get("success"):
        messages = "; ".join(e.get("message", "") for e in body.get("errors", []))
        raise SetupError(f"{method} {path}: {messages or response.status_code}")
    return body


def zone_id(client: httpx.Client, domain: str) -> str:
    result = call(client, "GET", "/zones", params={"name": domain})["result"]
    if not result:
        raise SetupError(
            f"the token cannot see {domain}. Either it is scoped to a different "
            "zone, or the domain is on another Cloudflare account."
        )
    return result[0]["id"]


def existing(client: httpx.Client, zone: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        body = call(
            client, "GET", f"/zones/{zone}/dns_records",
            params={"page": page, "per_page": 100},
        )
        out.extend(body["result"])
        info = body.get("result_info") or {}
        if page >= (info.get("total_pages") or 1):
            return out
        page += 1


def wanted(
    domain: str, verify: str, dmarc_to: str,
    dkim_name: str = "", dkim_value: str = "",
) -> list[dict]:
    records = [
        {"type": "TXT", "name": domain, "content": LARK_SPF, "_what": "SPF"},
        {
            "type": "TXT",
            "name": f"_dmarc.{domain}",
            # p=none observes without touching delivery. rua is the point of
            # the record: below Postmaster Tools' volume floor, aggregate
            # reports are the only deliverability feedback that exists.
            "content": f"v=DMARC1; p=none; rua=mailto:{dmarc_to}",
            "_what": "DMARC",
        },
    ]
    if verify:
        records.insert(0, {
            "type": "TXT",
            "name": domain,
            "content": f"verification-code-site-App_lark={verify}",
            "_what": "Lark domain verification",
        })
    if dkim_name and dkim_value:
        # The selector is generated per domain — lark2608152149 rather than a
        # fixed one — which is how you can tell Lark signs with your domain
        # rather than its own. A shared selector would mean d=larksuite.com
        # and no alignment however the record was published.
        name = dkim_name if dkim_name.endswith(domain) else f"{dkim_name}.{domain}"
        records.append({
            "type": "TXT", "name": name, "content": dkim_value, "_what": "DKIM",
        })
    for host, priority in LARK_MX:
        records.append({
            "type": "MX", "name": domain, "content": host,
            "priority": priority, "_what": f"MX {priority}",
        })
    return records


def plan(have: list[dict], want: list[dict]) -> tuple[list[dict], list[str]]:
    """What to create, and what to say about everything else."""
    todo: list[dict] = []
    notes: list[str] = []

    for record in want:
        what = record["_what"]
        match = [
            h for h in have
            if h["type"] == record["type"]
            and h["name"] == record["name"]
            and h["content"].strip('"') == record["content"]
        ]
        if match:
            notes.append(f"  = {what:26} already present, unchanged")
            continue
        todo.append(record)
        notes.append(f"  + {what:26} {record['content'][:64]}")

    # Two SPF records is a permerror, and a permerror is treated as no SPF at
    # all — strictly worse than having none. Worth stopping for.
    spf_have = [
        h for h in have
        if h["type"] == "TXT" and h["content"].strip('"').lower().startswith("v=spf1")
    ]
    spf_new = [r for r in todo if r["_what"] == "SPF"]
    if spf_have and spf_new:
        notes.append(
            "\n  ! an SPF record already exists with a different value:\n"
            f"      {spf_have[0]['content']}\n"
            "    Two SPF records are a permanent error, which receivers treat as\n"
            "    no SPF at all. Merge them by hand — this script will not guess\n"
            "    which one you meant."
        )
        todo = [r for r in todo if r["_what"] != "SPF"]

    return todo, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain")
    parser.add_argument("--lark-verify", default="",
                        help="the code from Lark's domain setup panel")
    parser.add_argument("--dmarc-to", default="",
                        help="where DMARC aggregate reports go (default: postmaster@domain)")
    parser.add_argument("--dkim-name", default="",
                        help="selector host, e.g. lark2608152149._domainkey")
    parser.add_argument("--dkim-value", default="",
                        help="the v=DKIM1 record, or @path/to/file to read it")
    parser.add_argument("--apply", action="store_true",
                        help="actually create the records")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("CLOUDFLARE_API_TOKEN is not set.\n"
              "Cloudflare → My Profile → API Tokens → Create Token →\n"
              '"Edit zone DNS" → Zone Resources: Include → Specific zone → '
              f"{args.domain}")
        return 1

    dmarc_to = args.dmarc_to or f"postmaster@{args.domain}"
    dkim_value = args.dkim_value
    if dkim_value.startswith("@"):
        # A DKIM public key is well over the length a shell argument should
        # carry, and it contains + and / — read it from a file instead of
        # trusting quoting.
        dkim_value = pathlib.Path(dkim_value[1:]).read_text().strip()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            call(client, "GET", "/user/tokens/verify")
            zone = zone_id(client, args.domain)
            have = existing(client, zone)
            todo, notes = plan(have, wanted(
                args.domain, args.lark_verify, dmarc_to,
                args.dkim_name, dkim_value,
            ))

            print(f"\n{args.domain}  ({len(have)} existing records)\n")
            for line in notes:
                print(line)

            if not todo:
                print("\nNothing to add.")
                return 0
            if not args.apply:
                print(f"\n{len(todo)} record(s) to add. Re-run with --apply.")
                return 0

            print()
            for record in todo:
                payload = {k: v for k, v in record.items() if not k.startswith("_")}
                payload["ttl"] = 1  # 1 = automatic
                call(client, "POST", f"/zones/{zone}/dns_records", json=payload)
                print(f"  created  {record['_what']}")
    except SetupError as e:
        print(f"\n{e}")
        return 1
    except httpx.HTTPError as e:
        print(f"\nCloudflare unreachable: {e}")
        return 1

    print("\nDone. Now:  python -m loom.scripts.check_mail_setup " + args.domain)
    print("Lark gives no DKIM record in its initial list — add that separately")
    print("from its admin panel once the domain verifies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

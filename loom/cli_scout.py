"""Command line for the scout and outreach half of Loom.

The resume workflow has had a CLI since the beginning; this side never did, so
every look at a lead meant writing a throwaway script — load dotenv, build
storage, iterate, print. Written enough times in one afternoon to shadow the
standard library's `queue` module once and pick the wrong interpreter twice.

WHAT IS NOT HERE, deliberately: sending. A message reaching a stranger goes
through a person marking a row Approved in Notion and then an endpoint, and
that is the whole design. mailer's own note on why the redirect is intercepted
at the single choke point applies exactly as well to this: "A guard one level
up is a guard something will eventually route around." A second way to send is
that route.

Everything here either reads, or recomputes something already computed once and
writes it back under the same guards the endpoints use.
"""

import asyncio
import json
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _run(coro):
    return asyncio.run(coro)


async def _storage():
    from loom.api import get_storage

    return get_storage()


async def _all_leads() -> list[dict]:
    storage = await _storage()
    rows = await storage.list_scout_leads()
    leads = [await storage.get_scout_lead(r["id"]) for r in rows]
    return [lead for lead in leads if lead]


async def _find(needle: str) -> dict:
    """One lead by id, or by any unambiguous part of its name.

    Names are what a person has in their head; ids are what the database has.
    Accepting both, and refusing an ambiguous name rather than picking one, is
    the difference between a convenience and a way to act on the wrong shop.
    """
    leads = await _all_leads()
    exact = [x for x in leads if x["id"] == needle]
    if exact:
        return exact[0]
    hits = [x for x in leads if needle.lower() in (x.get("google_name") or "").lower()]
    if not hits:
        raise click.ClickException(f"no lead matching {needle!r}")
    if len(hits) > 1:
        names = ", ".join(x["google_name"] for x in hits)
        raise click.ClickException(f"{needle!r} matches {len(hits)}: {names}")
    return hits[0]


def _counts(lead: dict) -> tuple[int, int, int]:
    h = lead.get("harvest") or {}
    return (
        len(h.get("pages_read") or []),
        len(h.get("menu") or []),
        len(h.get("images") or []),
    )


@click.group()
def scout():
    """Leads, harvests, audits and drafts. Nothing here sends."""


@scout.command("leads")
@click.option("--status", default=None, help="Only leads with this status.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable.")
def leads(status: str | None, as_json: bool):
    """Every saved lead, with what has been done to it."""

    async def go():
        rows = [x for x in await _all_leads() if not status or x["status"] == status]
        if as_json:
            click.echo(json.dumps(
                [{"id": x["id"], "name": x.get("google_name"), "status": x["status"],
                  "score": x.get("score"), "emails": x.get("emails") or [],
                  "contacted_at": x.get("contacted_at")} for x in rows],
                ensure_ascii=False, indent=2))
            return
        if not rows:
            click.echo("no leads")
            return
        click.echo(f"{'business':30} {'status':9} {'score':>5}  pages menu imgs  contacted")
        for x in rows:
            pages, menu, images = _counts(x)
            click.echo(
                f"{(x.get('google_name') or '?')[:29]:30} {x['status']:9} "
                f"{str(x.get('score') or 0):>5}  {pages:>5} {menu:>4} {images:>4}  "
                f"{(x.get('contacted_at') or '—')[:10]}"
            )
    _run(go())


@scout.command("show")
@click.argument("lead")
def show(lead: str):
    """One lead: what is wrong with it, what was harvested, who to write to."""

    async def go():
        x = await _find(lead)
        click.echo(f"\n{x.get('google_name')}   [{x['status']}]")
        click.echo(f"  {x.get('google_address') or '—'}")
        click.echo(f"  {x.get('site_url') or 'no website'}")

        audit = x.get("audit") or {}
        findings = audit.get("findings") or []
        click.echo(f"\nfindings · score {x.get('score') or 0}")
        for f in sorted(findings, key=lambda f: -f.get("weight", 0)):
            click.echo(f"  [{f.get('weight')}] {f.get('label')}")
            if f.get("detail"):
                click.echo(f"        {f['detail']}")
        if not findings:
            click.echo("  none")

        pages, menu, images = _counts(x)
        h = x.get("harvest") or {}
        click.echo(f"\nharvest   {pages} pages · {menu} menu · {images} images")
        for field in ("hours", "address", "phone", "about"):
            if h.get(field):
                click.echo(f"  {field:8} {str(h[field])[:70]}")
        if h.get("error"):
            click.echo(f"  error    {h['error']}")

        # Who may be written to, and why — the argument, not just the address.
        from loom.services import consent

        sources = x.get("email_sources") or {}
        click.echo("\naddresses")
        for address in x.get("emails") or []:
            verdict = consent.classify(address)
            allowed, why = consent.may_write_to(address, sources.get(address.lower()))
            mark = "send" if allowed else "hold"
            click.echo(f"  {mark}  {address}")
            click.echo(f"        {verdict['role']} ({verdict['tier']})")
            if not allowed:
                click.echo(f"        {why}")
        if not (x.get("emails") or []):
            click.echo("  none found")

        click.echo("\nstages")
        for label, key in (("harvested", "harvested_at"), ("planned", "planned_at"),
                           ("built", "demo_built_at"), ("drafted", "drafted_at"),
                           ("contacted", "contacted_at"), ("followed up", "followed_up_at")):
            click.echo(f"  {label:12} {x.get(key) or '—'}")
        if x.get("demo_slug"):
            shared = "shared" if x.get("demo_public") else "private"
            click.echo(f"  demo         {x['demo_slug']} ({shared})")
    _run(go())


@scout.command("harvest")
@click.argument("lead")
def harvest(lead: str):
    """Re-read the business's own pages. Keeps the richer of old and new."""

    async def go():
        from loom.services.site_harvest import harvest_lead, is_regression

        x = await _find(lead)
        before = _counts(x)
        fresh = await harvest_lead(x)
        why = is_regression(x.get("harvest"), fresh)
        if why:
            click.echo(f"kept the previous harvest — {why}")
            return
        storage = await _storage()
        await storage.update_scout_lead(x["id"], {"harvest": fresh.model_dump(mode="json")})
        after = (len(fresh.pages_read), len(fresh.menu), len(fresh.images))
        click.echo(f"pages {before[0]}→{after[0]}  menu {before[1]}→{after[1]}  "
                   f"images {before[2]}→{after[2]}")
    _run(go())


@scout.command("audit")
@click.argument("lead")
def audit(lead: str):
    """Re-check the site for the problems an email could open on."""

    async def go():
        import httpx

        from loom.services.company_scout import USER_AGENT
        from loom.services.site_audit import audit_response

        x = await _find(lead)
        url = x.get("site_url")
        if not url:
            raise click.ClickException("this lead has no website to audit")
        async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url)
        report = audit_response(url, final_url=str(response.url),
                                status_code=response.status_code, load_ms=0,
                                html=response.text)
        storage = await _storage()
        # score rides along with the audit; the storage layer derives it.
        await storage.update_scout_lead(x["id"], {"audit": report.model_dump(mode="json")})
        click.echo(f"score {report.score}")
        for f in sorted(report.findings, key=lambda f: -f.weight):
            click.echo(f"  [{f.weight}] {f.code:18} {f.label}")
    _run(go())


@scout.command("draft")
@click.argument("lead")
@click.option("--template", default=None, help="Force a template instead of the obvious one.")
def draft(lead: str, template: str | None):
    """Render the email this lead would get. Renders only — nothing is stored."""

    async def go():
        import os

        from loom.services.email_templates import render, suggest_template

        x = await _find(lead)
        key = template or suggest_template(x)
        try:
            message = render(key, x, public_base=os.environ.get("LOOM_PUBLIC_URL", ""))
        except Exception as e:
            # Every one of these refusals is a rule worth reading rather than a
            # failure: no consent basis, nothing wrong worth writing about, a
            # slot with nothing to fill it.
            raise click.ClickException(f"{type(e).__name__}: {e}") from e
        click.echo(f"template  {key}")
        click.echo(f"to        {message['to']}")
        click.echo(f"subject   {message['subject']}\n")
        click.echo(message["body"])
    _run(go())


@scout.command("queue")
def queue():
    """What is waiting to be sent, and what has been."""

    async def go():
        from loom.services import notion_outreach

        if not notion_outreach.enabled():
            click.echo("no outreach table configured")
            return
        waiting = await notion_outreach.approved_rows()
        gone = await notion_outreach.sent_rows()
        click.echo(f"approved  {len(waiting)}")
        for row in waiting[:20]:
            click.echo(f"    {row.get('to')}  {str(row.get('subject'))[:56]}")
        click.echo(f"sent      {len(gone)}")
        for row in gone[:20]:
            click.echo(f"    {row.get('to')}  {str(row.get('subject'))[:56]}")
    _run(go())


@scout.command("doctor")
def doctor():
    """Whether outreach could actually run, and what would happen if it did."""

    async def go():
        from loom.services import inbox, mailer, notion_outreach

        redirect = mailer.redirect_to()
        rows = await _all_leads()
        sendable = [
            x for x in rows
            if x["status"] not in ("dead", "opted_out") and (x.get("emails") or [])
        ]

        click.echo("sending")
        click.echo(f"  transport      {mailer.transport()}")
        click.echo(f"  configured     {mailer.configured()}")
        click.echo(f"  cap per run    {mailer.MAX_PER_RUN}")
        click.echo(
            "  redirect       "
            + (f"{redirect} — nothing reaches a business" if redirect
               else "off — approved mail goes to the business")
        )
        click.echo("\nreading replies")
        click.echo(f"  mailbox        {inbox.enabled()}")
        click.echo(f"  outreach table {notion_outreach.enabled()}")
        if not inbox.enabled():
            click.echo("  ! the opt-out promise has no mechanism without a mailbox")
        click.echo("\nleads")
        click.echo(f"  saved          {len(rows)}")
        click.echo(f"  with an address{len(sendable):>3}")
        click.echo(f"  contacted      {sum(1 for x in rows if x.get('contacted_at'))}")
    _run(go())

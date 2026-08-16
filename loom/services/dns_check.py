"""Ask DNS whether an address's domain can receive mail at all.

Loom's recipient addresses are regex-scraped from page text, so alongside the
real ones it collects the web designer's own address in a footer, addresses
inside schema.org blocks, and typos that were never valid. Writing to a domain
that does not exist produces a hard bounce, and hard bounces are the fastest
route to a sending identity being throttled — faster than complaints, because
they need no human to report anything.

One DNS lookup before sending catches the dead ones for free.

No new dependency: Google's DNS-over-HTTPS endpoint answers JSON over the same
httpx already in use. dnspython would be the obvious alternative but adding a
package to ask one question is not worth it.

Two details that took getting wrong to notice:

  * `Answer` entries must be filtered on their `type` field. A lookup often
    returns a CNAME (type 5) first, and taking Answer[0] blindly reads the
    alias rather than the record asked for.
  * **No MX does not mean no mail.** RFC 5321 §5.1 says a domain with an
    address record and no MX accepts mail at that address — implicit MX. A
    check that required an MX record would reject working small-business
    domains, which is the opposite of the point.
"""

import asyncio
import time

import httpx

DOH_URL = "https://dns.google/resolve"
TIMEOUT = 5.0

TYPE_A = 1
TYPE_AAAA = 28
TYPE_MX = 15

# NXDOMAIN. Status 0 is NOERROR; anything else is inconclusive rather than
# negative, and inconclusive must never block a send.
RCODE_NXDOMAIN = 3

CACHE_TTL = 3600.0
_cache: dict[str, tuple[float, bool | None]] = {}
_lock = asyncio.Lock()


async def _query(client: httpx.AsyncClient, name: str, rtype: int) -> tuple[int, list]:
    response = await client.get(
        DOH_URL, params={"name": name, "type": rtype}, timeout=TIMEOUT
    )
    response.raise_for_status()
    body = response.json()
    answers = [
        entry for entry in (body.get("Answer") or []) if entry.get("type") == rtype
    ]
    return int(body.get("Status", -1)), answers


async def accepts_mail(domain: str, client: httpx.AsyncClient | None = None) -> bool | None:
    """True if the domain can receive mail, False if it certainly cannot.

    None means the question could not be answered — a timeout, a malformed
    response, our own network. Callers must treat None as "proceed": blocking
    a real customer's email because our DNS lookup failed is a worse outcome
    than the bounce this is meant to prevent.
    """
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain or "." not in domain:
        return False

    now = time.monotonic()
    async with _lock:
        cached = _cache.get(domain)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

    verdict: bool | None
    try:
        owned = client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            status, mx = await _query(owned, domain, TYPE_MX)
            if status == RCODE_NXDOMAIN:
                # The domain itself does not exist. Nothing else to check.
                verdict = False
            elif mx:
                verdict = True
            else:
                # No MX. Fall back to implicit MX rather than concluding.
                a_status, a = await _query(owned, domain, TYPE_A)
                if a:
                    verdict = True
                else:
                    aaaa_status, aaaa = await _query(owned, domain, TYPE_AAAA)
                    if aaaa:
                        verdict = True
                    elif a_status == 0 and aaaa_status == 0 and status == 0:
                        # Three clean NOERROR answers with no records at all:
                        # the domain resolves but has nowhere to deliver.
                        verdict = False
                    else:
                        verdict = None
        finally:
            if client is None:
                await owned.aclose()
    except (httpx.HTTPError, ValueError, KeyError):
        verdict = None

    if verdict is not None:
        async with _lock:
            _cache[domain] = (now, verdict)
    return verdict


async def deliverable(address: str, client: httpx.AsyncClient | None = None) -> bool | None:
    """Whether this address's domain can receive mail. None = don't know."""
    _, _, domain = (address or "").partition("@")
    if not domain:
        return False
    return await accepts_mail(domain, client=client)

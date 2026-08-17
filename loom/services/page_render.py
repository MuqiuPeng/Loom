"""Fetch a page the way a browser would, when fetching it as a file gets nothing.

The harvest reads HTML over httpx, which is right for most of the web and
wrong for a lot of small-business sites. Of the six leads in the database when
this was written, four returned under 300 characters of text: Espresso! Coffee
Bar returned exactly none — a 48KB document whose `<body>` is 539 characters of
scaffolding and whose entire content sits in a `__NEXT_DATA__` blob — and Pura
Vida and Gundog returned 73 and 35. The extractor was not losing that text.
There was no text; there was a program that would have produced text if
anything had run it.

The consequence is not one missing field. `_pick_pages` reads links out of the
same document, so a shell page yields no menu page, no about page, nothing to
crawl — which is why those three leads each show exactly one page read. The
audit judges the same shell. A JavaScript-rendered site does not degrade the
harvest; it empties it.

A FALLBACK, NOT A FETCHER. Chromium is slow and the two Shopify sites in that
same set returned five and six thousand characters without it. So the browser
starts only when a page comes back thin, and once started is reused for the
rest of that harvest rather than relaunched per page.

WHAT IT DOES NOT DO. It does not execute anything a normal visit would not: no
clicking, no scrolling, no dismissing of overlays, and no waiting past a fixed
budget. If a site hides its menu behind an interaction, this returns the same
shell the crawler got and the harvest is honestly empty rather than
half-invented.

Fails open at every step — no Playwright, no browser, a timeout, a crash — by
returning the empty string, which leaves the caller with the HTML it already
had. Harvesting a shell is a poor result; failing to harvest is a worse one.
"""

import logging

log = logging.getLogger(__name__)

# Below this many characters of visible text, a page is a shell rather than a
# page. The working sites in the sample cleared it by a factor of ten and the
# broken ones came in under 300, so the exact number is not load-bearing.
THIN_TEXT = 500

# A page that has not painted its content within this has something wrong with
# it that a longer wait will not fix.
LOAD_TIMEOUT_MS = 15_000

# How long to keep waiting for a client-rendered page to put words on itself.
# Generous, because the cost is paid only by pages that arrived empty, and the
# alternative to waiting is harvesting nothing from them at all.
SETTLE_TIMEOUT_MS = 20_000
POLL_INTERVAL_MS = 500
# Consecutive identical measurements before the page is called finished. Two
# rather than one because a render can pause mid-flight — a font loading, a
# lazy section resolving — and a single flat sample is not evidence of an end.
STEADY_SAMPLES = 2

# Chromium refuses to start as root without this, which is exactly how it runs
# in the container. Verified against production rather than assumed: the first
# attempt there failed with a bare TargetClosedError that says nothing about
# sandboxing.
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]


def is_thin(text: str) -> bool:
    """Whether this much visible text means the document is a shell."""
    return len(text.strip()) < THIN_TEXT


async def _wait_for_text(page) -> None:
    """Wait until the page has words on it, or until the budget runs out.

    `networkidle` was the obvious wait and the wrong one. It is a proxy for
    "finished", and the things it actually measures — open sockets — are held
    by analytics and chat widgets long after the content has painted, and
    released by some sites well before it has. pvgrinds.com returned
    "Loading... (480) 600-7528" under it: the socket count settled while the
    page was still showing its spinner.

    So wait for the thing being waited for — and wait for it to stop, not to
    start. The page is polled for text and ends when the count has held still
    across consecutive samples, because a page that is filling in progressively
    crosses any fixed threshold long before it is finished. A page that never
    settles returns whatever it has, and the caller keeps the HTML it already
    fetched.
    """
    waited = 0
    previous = -1
    steady = 0
    while waited < SETTLE_TIMEOUT_MS:
        try:
            length = await page.evaluate(
                "() => (document.body && document.body.innerText || '').trim().length"
            )
        except Exception:
            return
        # Growth, not a threshold. Returning at the first sample above the
        # shell floor is what an earlier version did, and it stopped the moment
        # the page started filling rather than when it had finished: the same
        # square.site page measured 710, 864 and 2471 characters on three
        # consecutive runs of identical code. A harvest built on the first of
        # those has a third of the menu and no way to know it.
        if length >= THIN_TEXT and length == previous:
            steady += 1
            if steady >= STEADY_SAMPLES:
                return
        else:
            steady = 0
        previous = length
        await page.wait_for_timeout(POLL_INTERVAL_MS)
        waited += POLL_INTERVAL_MS


class Renderer:
    """One browser, started on first need, shared for the rest of a harvest.

    Used as an async context manager. Every method returns "" rather than
    raising, so a caller can treat rendering as an optional improvement on the
    HTML it already holds.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._failed = False

    async def __aenter__(self) -> "Renderer":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _browser_or_none(self):
        if self._browser is not None or self._failed:
            return self._browser
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(args=LAUNCH_ARGS)
        except Exception as e:
            # Once, not once per page: a machine without a browser will not
            # grow one partway through a crawl.
            self._failed = True
            log.info("no browser for rendering (%s) — using the HTML as fetched", e)
            await self.close()
        return self._browser

    async def html_of(self, url: str) -> str:
        """The page's DOM after scripts have run, or "" if that cannot be had."""
        browser = await self._browser_or_none()
        if browser is None:
            return ""
        page = None
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
            await _wait_for_text(page)
            return await page.content()
        except Exception as e:
            log.info("could not render %s (%s)", url, str(e)[:120])
            return ""
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    async def close(self) -> None:
        for closer in (
            getattr(self._browser, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:
                pass
        self._browser = None
        self._playwright = None

"""Load a generated page in a real browser and see whether it actually works.

Everything else in the agent reads the HTML as text. That catches invented
prices and stray script tags, but it cannot tell you the layout blows out
sideways on a phone — and "your site doesn't work on a phone" is the single
most common thing we pitch to these businesses. Shipping a demo with that
exact fault would be self-defeating.

So the page gets rendered at a phone width and asked three questions a person
would ask by looking at it:

  * does it scroll sideways
  * did any picture fail to load
  * is the text too small to read

Rendering is optional at runtime: if Playwright or its browser is missing the
check reports itself as skipped rather than failing the build, so a machine
without a browser can still generate demos.
"""

import asyncio
from typing import Any

# Phone width first — that's where these pages get opened and where the
# failure we care about shows up.
PHONE = (375, 812)
DESKTOP = (1440, 900)
MIN_BODY_PX = 13.0
RENDER_TIMEOUT_MS = 15_000

PROBE = """() => {
  const d = document.documentElement;
  const over = [...document.querySelectorAll('*')]
    .filter(e => e.getBoundingClientRect().right > d.clientWidth + 2)
    .map(e => (e.tagName + (e.className ? '.' + String(e.className).slice(0, 30) : '')));
  return {
    viewport: d.clientWidth,
    scrollWidth: d.scrollWidth,
    overflow: d.scrollWidth > d.clientWidth + 2,
    offenders: over.slice(0, 4),
    // Only images the visitor can actually see. A lazy-loaded photo below
    // the fold legitimately has naturalWidth 0 until it scrolls into view,
    // and counting those would put "5 broken images" in a sales email about
    // a site that is fine.
    brokenImages: [...document.images].filter(i => {
      if (i.naturalWidth !== 0) return false;
      const r = i.getBoundingClientRect();
      const onScreen = r.top < window.innerHeight * 1.5 && r.bottom > 0
        && r.width > 24 && r.height > 24;
      return onScreen;
    }).length,
    imageCount: document.images.length,
    bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize),
    textLength: (document.body.innerText || '').trim().length,
  };
}"""


class RenderReport(dict):
    """Plain dict with a couple of conveniences."""

    @property
    def skipped(self) -> bool:
        return bool(self.get("skipped"))

    @property
    def problems(self) -> list[dict[str, str]]:
        return self.get("problems", [])


async def render_check(html: str) -> RenderReport:
    """Render `html` at phone and desktop widths; report what's broken."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return RenderReport(skipped="playwright not installed", problems=[])

    problems: list[dict[str, str]] = []
    measurements: dict[str, Any] = {}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                for label, (width, height) in (
                    ("phone", PHONE),
                    ("desktop", DESKTOP),
                ):
                    page = await browser.new_page(
                        viewport={"width": width, "height": height}
                    )
                    # The page loads images from the business's own CDN, so
                    # wait for network rather than DOM alone.
                    await page.set_content(html, wait_until="networkidle",
                                           timeout=RENDER_TIMEOUT_MS)
                    result = await page.evaluate(PROBE)
                    measurements[label] = result
                    await page.close()

                    if result["overflow"]:
                        offenders = ", ".join(result["offenders"]) or "unknown element"
                        problems.append({
                            "code": "horizontal_overflow",
                            "detail": (
                                f"at {width}px the page scrolls sideways "
                                f"({result['scrollWidth']}px wide) — offending: {offenders}"
                            ),
                        })
                    if result["brokenImages"]:
                        problems.append({
                            "code": "broken_image",
                            "detail": (
                                f"{result['brokenImages']} of {result['imageCount']} "
                                f"images failed to load at {width}px"
                            ),
                        })
                    if result["bodyFontPx"] and result["bodyFontPx"] < MIN_BODY_PX:
                        problems.append({
                            "code": "text_too_small",
                            "detail": (
                                f"body text is {result['bodyFontPx']}px; "
                                f"use at least {MIN_BODY_PX}px"
                            ),
                        })
            finally:
                await browser.close()
    except Exception as e:  # browser missing, launch failure, timeout
        return RenderReport(skipped=str(e).splitlines()[0][:160], problems=[])

    # Deduplicate: the same fault at both widths is one fault.
    seen: list[dict[str, str]] = []
    for problem in problems:
        if not any(s["code"] == problem["code"] for s in seen):
            seen.append(problem)

    return RenderReport(skipped=None, problems=seen, measurements=measurements)


async def render_audit(urls: list[str], concurrency: int = 4) -> dict[str, list[dict]]:
    """Open each prospect's site in a phone-sized browser and see what breaks.

    Static analysis cannot find the failure that actually sells this work: a
    site that renders fine on a desktop and is unusable on a phone. The
    canonical case is a Wix site with a perfectly good viewport tag whose
    layout still blows out — the owner believes they have a website, and every
    passer-by searching "restaurant near me" gets a broken page.

    One browser for the whole batch; launching per URL costs more than the
    page loads do.
    """
    if not urls:
        return {}
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {}

    results: dict[str, list[dict]] = {}
    gate = asyncio.Semaphore(concurrency)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:

                async def one(url: str) -> None:
                    async with gate:
                        page = None
                        try:
                            page = await browser.new_page(
                                viewport={"width": PHONE[0], "height": PHONE[1]},
                                user_agent=(
                                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                                    "Mobile/15E148 Safari/604.1"
                                ),
                            )
                            await page.goto(
                                url, wait_until="domcontentloaded",
                                timeout=RENDER_TIMEOUT_MS,
                            )
                            # Give lazy-loaded layout a moment to settle.
                            await page.wait_for_timeout(1200)
                            probe = await page.evaluate(PROBE)
                        except Exception:
                            return
                        finally:
                            if page:
                                await page.close()

                        found: list[dict] = []
                        if probe["overflow"]:
                            found.append({
                                "code": "mobile_broken",
                                "weight": 5,
                                "label": "Unusable on a phone",
                                "detail": (
                                    f"the page is {probe['scrollWidth']}px wide in a "
                                    f"{probe['viewport']}px window — it scrolls sideways "
                                    "and text runs off the screen"
                                ),
                            })
                        if probe["brokenImages"]:
                            found.append({
                                "code": "broken_images",
                                "weight": 3,
                                "label": f"{probe['brokenImages']} images don't load",
                                "detail": "visitors see empty boxes where photos should be",
                            })
                        if probe["bodyFontPx"] and probe["bodyFontPx"] < MIN_BODY_PX:
                            found.append({
                                "code": "tiny_text",
                                "weight": 2,
                                "label": "Text too small to read",
                                "detail": f"body text renders at {probe['bodyFontPx']}px on a phone",
                            })
                        if probe["textLength"] < 200:
                            found.append({
                                "code": "renders_empty",
                                "weight": 4,
                                "label": "Renders almost nothing",
                                "detail": "the page loads but shows barely any content",
                            })
                        results[url] = found

                await asyncio.gather(*(one(u) for u in urls))
            finally:
                await browser.close()
    except Exception:
        return {}

    return results


async def screenshot(
    html: str, *, width: int = 420, height: int = 760, quality: int = 80
) -> bytes | None:
    """A phone-shaped JPEG of the page, or None if no browser is available.

    This is the hook for the approach email. A cold link from an unknown
    sender often goes unclicked; an image in the body gets looked at, and the
    look is what earns the click. The working page still does the persuading —
    the picture just gets someone to open it.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(
                    viewport={"width": width, "height": height},
                    # Retina-sharp when embedded, but JPEG rather than PNG —
                    # the same shot as PNG is over a megabyte, which mail
                    # clients throttle or strip.
                    device_scale_factor=2,
                )
                await page.set_content(
                    html, wait_until="networkidle", timeout=RENDER_TIMEOUT_MS
                )
                return await page.screenshot(type="jpeg", quality=quality)
            finally:
                await browser.close()
    except Exception:
        return None


if __name__ == "__main__":  # pragma: no cover - manual probe
    import sys

    page = open(sys.argv[1], encoding="utf-8").read()
    report = asyncio.run(render_check(page))
    print(report.get("skipped") or report.get("measurements"))
    for problem in report.problems:
        print(f"  [{problem['code']}] {problem['detail']}")

"""Render the plain-text body as HTML, laid out rather than merely converted.

Deliberately a renderer, not a second template. The wording lives once, in
config/email_templates.json; a parallel HTML copy of every template is two
things to keep in step and one of them will drift, which for a legal opt-out
line is not a cosmetic problem.

WHAT LARK ALLOWS. Probed by running candidate markup through `mail
+lint-html` and reading what came back, because designing against a
sanitiser's documentation rather than its behaviour is guesswork:

    survives   border, border-radius, padding, border-left, <hr>, <table>,
               font-family (serif included), font-size, font-weight, color,
               text-transform
    stripped   background / background-color — every tint is silently dropped
               letter-spacing
               font-variant: small-caps
    forced     link colour, overridden to Lark's brand blue with a
               class="not-doclink" of its own

So the two most obvious devices — a tinted panel and a wide-tracked eyebrow —
are both unavailable, and link colour is not ours to choose. What is left is
rules, type contrast and whitespace.

THE BRIEF, which is narrow. This is one person writing to a shop owner, not a
campaign. No logo, no button, no columns, no footer. One link.

Exactly one image is allowed, and only one: a screenshot of the rebuilt site.
It earns its place because it *is* the pitch — a cold link from an unknown
sender often goes unclicked, and the look is what earns the click. The spam
rules people cite against images are narrower than they sound: SpamAssassin
scores image-ONLY mail, and a tracking pixel is a 1x1 remote request. One
inline screenshot among a hundred words of text is neither. It is attached by
content-id rather than fetched from a server, so it survives the
image-blocking that would leave a remote <img> as an empty box, and it looks
nothing like a beacon.

Boldness is spent exactly once, on the demo panel — that link is the only
thing the message exists to deliver, and a bare URL underplays it. Everything
else stays quiet: a serif line to separate the evidence from the pitch, a
hairline above the sign-off, and air.
"""

import html
import re

_URL_LINE_RE = re.compile(r"^\s*(https?://\S+)\s*$")
_SIGNATURE_MARK = "—"

SANS = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
    "Helvetica,Arial,sans-serif"
)
SERIF = "Georgia,'Iowan Old Style','Times New Roman',serif"

INK = "#1f2328"
MUTED = "#57606a"
FAINT = "#8c959f"
RULE = "#d8dee4"


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _linkify(text: str) -> str:
    out: list[str] = []
    last = 0
    for match in re.finditer(r"https?://[^\s<>\"]+", text):
        out.append(_escape(text[last:match.start()]))
        url = match.group(0)
        out.append(f'<a href="{html.escape(url, quote=True)}">{_escape(url)}</a>')
        last = match.end()
    out.append(_escape(text[last:]))
    return "".join(out)


def _paragraph(inner: str, *, first: bool = False) -> str:
    top = "0" if first else "0"
    return f'<div style="margin:{top} 0 20px">{inner}</div>'


def _evidence(inner: str) -> str:
    """The line naming what is wrong with their site.

    Given a left rule and a serif face because it is the one claim in the
    message the owner can check for themselves in ten seconds, and everything
    after it rests on their believing it. Setting it apart is structural, not
    decorative.
    """
    return (
        f'<div style="border-left:2px solid {RULE};padding-left:16px;'
        f'margin:0 0 24px;font-family:{SERIF};font-size:16px;'
        f'line-height:1.55;color:{INK}">{inner}</div>'
    )


def _demo_panel(url: str, lead_in: str, image_cid: str = "", alt: str = "") -> str:
    """The demo link, as the one thing the eye should land on.

    A bordered block rather than a button: a button is the shape of a
    campaign, and this has to read as a person sending you something they
    made. The URL stays visible underneath — an unfamiliar sender asking for
    a click should show where the click goes.

    Order inside the panel is explanation, then evidence, then action: the
    sentence says what you are looking at, the screenshot shows it, the link
    lets you open it. The image carries real alt text because a reader whose
    client blocks images should still be told what was there.

    How the link is presented depends on whether the screenshot is there.

    Without an image the full address is the only thing to click, so it stays
    whole and becomes the largest type in the message.

    With one, the picture is the link and nothing is printed beneath it. A
    long machine-made slug repeated under the image is the ugliest thing in
    the message, and caf-calibre-zqetdk reads as generated, which costs more
    trust than it buys.

    The cost of that, and it is a real one: a client that blocks images
    leaves this message with nothing to click at all. Nothing in HTML can
    conditionally restore a link in that case, so the address goes into the
    alt text instead — invisible while the picture loads, and the one thing
    a blocked reader sees. It is not clickable, but it can be read and typed,
    which beats a dead end.
    """
    safe = html.escape(url, quote=True)
    picture = ""
    if image_cid:
        # The address rides in the alt text: unseen when the picture loads,
        # and the only thing left when a client blocks it.
        host = re.sub(r"^https?://", "", url)
        described = f'{alt or "The rebuilt page"} — {host}'
        picture = (
            f'<a href="{safe}" style="display:block">'
            f'<img src="cid:{html.escape(image_cid, quote=True)}" '
            f'alt="{html.escape(described, quote=True)}" '
            f'width="100%" style="display:block;width:100%;max-width:100%;'
            f'height:auto;border:1px solid {RULE};border-radius:6px"></a>'
        )
    if image_cid:
        # The picture is the link. Nothing printed underneath it.
        action = ""
    else:
        # No picture: the address is the only thing to click, so it stays
        # whole and becomes the largest type in the message.
        action = (
            f'<div style="font-size:17px;line-height:1.4;word-break:break-word">'
            f'<a href="{safe}">{_escape(url)}</a></div>'
        )

    return (
        f'<div style="border:1px solid {RULE};border-radius:8px;'
        'padding:20px;margin:0 0 26px">'
        f'<div style="font-size:14px;line-height:1.5;color:{MUTED};'
        f'margin:0 0 14px">{lead_in}</div>'
        + picture
        + action
        + "</div>"
    )


def to_html(body: str, *, image_cid: str = "", image_alt: str = "") -> str:
    """One plain-text body as HTML. Same words, same order, nothing added."""
    blocks = [b.strip("\n") for b in re.split(r"\n\s*\n", body.strip()) if b.strip()]
    parts: list[str] = []
    in_signature = False
    # The first paragraph after the greeting is the finding — the sentence the
    # whole approach rests on.
    evidence_used = False
    seen_greeting = False

    index = 0
    while index < len(blocks):
        block = blocks[index]

        lines_all = block.split("\n")
        if lines_all[0].strip() == _SIGNATURE_MARK:
            # The sign-off separator becomes the rule itself; keeping the dash
            # as well would draw the same divider twice.
            in_signature = True
            parts.append(
                f'<hr style="border:0;border-top:1px solid {RULE};'
                'margin:32px 0 18px">'
            )
            rest = "\n".join(lines_all[1:]).strip()
            if not rest:
                index += 1
                continue
            block = rest

        url_only = _URL_LINE_RE.match(block)
        lines = block.split("\n")
        trailing_url = _URL_LINE_RE.match(lines[-1]) if len(lines) > 1 else None

        if not in_signature and (url_only or trailing_url):
            # "I rebuilt it as it could be — …:" followed by the address.
            url = (url_only or trailing_url).group(1)
            lead_in = "<br>".join(_linkify(ln) for ln in lines[:-1]) if trailing_url else ""
            parts.append(_demo_panel(url, lead_in or "See it rebuilt:",
                                     image_cid=image_cid, alt=image_alt))
            index += 1
            continue

        inner = "<br>".join(_linkify(ln) for ln in lines)

        if in_signature:
            size = "13px"
            colour = FAINT if "unsubscribe" in block.lower() else MUTED
            parts.append(
                f'<div style="margin:0 0 8px;font-size:{size};'
                f'line-height:1.5;color:{colour}">{inner}</div>'
            )
        elif not seen_greeting:
            seen_greeting = True
            parts.append(_paragraph(inner, first=True))
        elif not evidence_used:
            evidence_used = True
            parts.append(_evidence(inner))
        else:
            parts.append(_paragraph(inner))
        index += 1

    return (
        f'<div style="font-family:{SANS};font-size:15px;line-height:1.65;'
        f'color:{INK};max-width:36rem">'
        + "".join(parts)
        + "</div>"
    )

import { describe, expect, it } from "vitest";

import { previewNotice, withPreviewNotice } from "./demo-banner";

const PAGE =
  '<!doctype html><html><head><title>Café Calibre</title></head>' +
  '<body class="warm"><h1>Café Calibre</h1></body></html>';

describe("withPreviewNotice", () => {
  it("puts the notice inside body, not before it", () => {
    const out = withPreviewNotice(PAGE, "Café Calibre");
    const body = out.indexOf('<body class="warm">');
    const notice = out.indexOf("loom-preview-notice");
    const heading = out.indexOf("<h1>");
    expect(body).toBeGreaterThan(-1);
    expect(notice).toBeGreaterThan(body);
    expect(notice).toBeLessThan(heading);
  });

  // The body padding rule only applies to what is inside body. A notice
  // landing above <html> would render, and would overlap the page.
  it("keeps the whole original document", () => {
    const out = withPreviewNotice(PAGE, "Café Calibre");
    expect(out).toContain("<title>Café Calibre</title>");
    expect(out).toContain("<h1>Café Calibre</h1>");
    expect(out).toContain("</html>");
  });

  // A generated document occasionally has no body tag at all. Rendering the
  // notice above <html> is wrong but recoverable; dropping it is not.
  it("still shows the notice when there is no body tag", () => {
    const out = withPreviewNotice("<h1>Shop</h1>", "Shop");
    expect(out).toContain("loom-preview-notice");
    expect(out).toContain("<h1>Shop</h1>");
  });

  it("survives a body tag with no attributes", () => {
    const out = withPreviewNotice("<html><body><p>x</p></body></html>", "X");
    expect(out.indexOf("loom-preview-notice")).toBeGreaterThan(
      out.indexOf("<body>")
    );
  });
});

describe("previewNotice", () => {
  it("names the business, because an unnamed disclaimer disclaims nothing", () => {
    expect(previewNotice("Café Calibre")).toContain(
      "not the official website of Café Calibre"
    );
  });

  it("falls back to a generic subject rather than an empty sentence", () => {
    for (const missing of [null, undefined, "", "   "]) {
      expect(previewNotice(missing)).toContain(
        "not the official website of this business"
      );
    }
  });

  // The name comes from Google Places and lands in markup unescaped otherwise.
  it("escapes a business name that contains markup", () => {
    const out = previewNotice('Bob & Sons <script>alert(1)</script>');
    expect(out).not.toContain("<script>");
    expect(out).toContain("Bob &amp; Sons");
  });

  // The CSP on this response allows no JavaScript, so a dismissable banner
  // could not work — and should not. The notice is not the reader's to close.
  it("needs no javascript", () => {
    const out = previewNotice("X");
    expect(out).not.toMatch(/<script|onclick=|javascript:/i);
  });

  // It has to win against whatever the art direction does at the top of the
  // page — including a fixed header of the page's own.
  it("outranks the page it is stamped onto", () => {
    const out = previewNotice("X");
    expect(out).toContain("position:fixed");
    expect(out).toContain("z-index:2147483647");
    expect(out).toContain("padding-top:2.5rem !important");
  });
});

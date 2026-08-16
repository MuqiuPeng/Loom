# The API, with the two things it cannot do without: a TeX toolchain and a
# browser. Both were the reason it had to run on a laptop; neither is hard to
# put in an image, which is why moving the whole service is less work than
# splitting the 50 endpoints that need neither away from the 8 that do.
#
# Image size is the one thing worth caring about here — a slow cold start is
# a user-visible cost. texlive-full is ~5GB; this set lands around 2.3GB
# because it installs the packages the two templates actually \usepackage and
# nothing else. If a new template pulls in a package, the compile fails with
# "File x.sty not found" and the fix is one line in this list — which is
# exactly how texlive-lang-chinese came to be here.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # Where playwright puts browsers; pinned so the runtime stage can copy it.
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    # Heiti SC is macOS-only. The container has Noto; see pdf_generator.py.
    LOOM_CJK_FONT="Noto Sans CJK SC"

# ── TeX, fonts, and the libraries Chromium links against ─────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
      # xelatex + the packages the resume templates use
      texlive-xetex \
      texlive-latex-recommended \
      texlive-latex-extra \
      texlive-fonts-recommended \
      # xeCJK.sty lives here, not in texlive-xetex. Without it every Chinese
      # resume dies at \setCJKmainfont with "File `xeCJK.sty' not found".
      texlive-lang-chinese \
      lmodern \
      # Chinese resumes: xeCJK needs a CJK font that actually exists here
      fonts-noto-cjk \
      # Chromium's runtime deps (playwright install-deps pulls far more)
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
      ca-certificates fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a source edit does not re-resolve or re-download
# ~700MB of TeX and a browser.
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
      "fastapi>=0.110.0" "uvicorn[standard]>=0.27.0" "pydantic>=2.0.0" \
      "anthropic>=0.18.0" "httpx>=0.27.0" "click>=8.1.0" \
      "python-dotenv>=1.0.0" "jinja2>=3.1.0" \
      "asyncpg>=0.29.0" "sqlalchemy[asyncio]>=2.0.0" "alembic>=1.13.0" \
      "playwright>=1.44.0" \
 && playwright install chromium

COPY loom ./loom
COPY config ./config
COPY alembic.ini ./

# Compiled PDFs and built demos land here. Deliberately not a volume: both
# are derived — a PDF recompiles from content_tex on request, and demo_html
# is served from Postgres — so losing them on redeploy costs nothing.
RUN mkdir -p output/resumes output/loom-demos

EXPOSE 8001

# One worker. The app keeps in-process state that does not survive being
# forked across workers: the chat session store, and the daily scheduler and
# reply poller started in the lifespan hook, which must not run twice.
CMD ["uvicorn", "loom.api:app", "--host", "0.0.0.0", "--port", "8001", \
     "--timeout-keep-alive", "300"]

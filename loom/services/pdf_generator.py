"""PDF generation service - compiles LaTeX to PDF via pdflatex."""

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Output directory for compiled PDFs
OUTPUT_DIR = Path("output/resumes")



# The Chinese template asks for "Heiti SC", which exists on macOS and nowhere
# else. xelatex does not fall back — it fails the whole compile — so the font
# has to be whatever the machine actually has. LOOM_CJK_FONT names it; the
# default matches the font installed in the container image.
DEFAULT_CJK_FONT = "Noto Sans CJK SC"
_CJK_FONT_RE = re.compile(r"\\setCJKmainfont\{[^}]*\}")


def _with_local_cjk_font(content_tex: str) -> str:
    """Point \\setCJKmainfont at a font this machine has."""
    font = os.environ.get("LOOM_CJK_FONT")
    if not font:
        # macOS keeps the template's own choice; anything else needs the
        # container's font, because Heiti SC will not be there.
        font = "Heiti SC" if sys.platform == "darwin" else DEFAULT_CJK_FONT
    return _CJK_FONT_RE.sub(f"\\\\setCJKmainfont{{{font}}}", content_tex)


class PDFGenerator:
    """Compile LaTeX content to PDF using pdflatex."""

    async def generate(self, content_tex: str, output_path: str | None = None) -> str:
        """Compile LaTeX content to PDF.

        Args:
            content_tex: Full LaTeX document source.
            output_path: Optional destination path for the PDF.
                         If None, generates a path under output/resumes/.

        Returns:
            Absolute path to the compiled PDF file.

        Raises:
            FileNotFoundError: If pdflatex/xelatex is not installed.
            RuntimeError: If compilation fails.
        """
        # Detect if Chinese template (uses xeCJK) → needs xelatex
        use_xelatex = "xeCJK" in content_tex or "\\setCJKmainfont" in content_tex
        compiler = "xelatex" if use_xelatex else "pdflatex"
        if use_xelatex:
            content_tex = _with_local_cjk_font(content_tex)

        # PM2/launchd processes often lack /Library/TeX/texbin in PATH,
        # so fall back to the standard MacTeX install location.
        compiler_path = shutil.which(compiler)
        if not compiler_path:
            for candidate in (f"/Library/TeX/texbin/{compiler}", f"/usr/local/texlive/bin/{compiler}"):
                if os.path.exists(candidate):
                    compiler_path = candidate
                    break
        if not compiler_path:
            raise FileNotFoundError(
                f"{compiler} not found. Install with: brew install --cask mactex-no-gui"
            )
        compiler = compiler_path

        # Create temp directory for compilation
        tmp_dir = tempfile.mkdtemp(prefix="loom_resumes_")
        tex_file = os.path.join(tmp_dir, "resume.tex")

        try:
            from loom.services.logger import logger as loom_log
        except ImportError:
            loom_log = None

        try:
            if loom_log:
                import asyncio as _aio
                _aio.create_task(loom_log.info("system", "pdf.compile.start",
                    f"Starting PDF compilation ({len(content_tex)} chars LaTeX)"))

            # Write .tex file
            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(content_tex)

            # Run compiler twice (resolve cross-references)
            for pass_num in range(2):
                proc = await asyncio.create_subprocess_exec(
                    compiler,
                    "-interaction=nonstopmode",
                    f"-output-directory={tmp_dir}",
                    tex_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0 and pass_num == 1:
                    log_file = os.path.join(tmp_dir, "resume.log")
                    error_lines = ""
                    if os.path.exists(log_file):
                        with open(log_file, "r", errors="replace") as f:
                            all_lines = f.readlines()
                            error_lines = "".join(all_lines[-20:])
                    if loom_log:
                        import asyncio as _aio
                        _aio.create_task(loom_log.error("system", "pdf.compile.failed",
                            f"{compiler} failed (pass {pass_num + 1})",
                            error_tail=error_lines[:500]))
                    raise RuntimeError(
                        f"{compiler} compilation failed (pass {pass_num + 1}):\n{error_lines}"
                    )

            # Verify PDF was created
            pdf_source = os.path.join(tmp_dir, "resume.pdf")
            if not os.path.exists(pdf_source):
                raise RuntimeError(f"{compiler} completed but no PDF was generated")

            # Determine output path
            if not output_path:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                import uuid
                output_path = str(OUTPUT_DIR / f"resume_{uuid.uuid4().hex[:8]}.pdf")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            shutil.copy2(pdf_source, output_path)
            pdf_size = os.path.getsize(output_path)
            logger.info("PDF generated: %s (%d bytes)", output_path, pdf_size)
            if loom_log:
                import asyncio as _aio
                _aio.create_task(loom_log.info("system", "pdf.compile.complete",
                    f"PDF compiled: {pdf_size} bytes",
                    file_size=pdf_size, output_path=output_path))
            return os.path.abspath(output_path)

        finally:
            # Clean up temp files
            shutil.rmtree(tmp_dir, ignore_errors=True)

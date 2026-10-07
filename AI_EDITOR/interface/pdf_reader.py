"""PDF script reader for AI EDITOR.

Extracts text from user-provided editing-script PDFs.
"""

from __future__ import annotations

from pathlib import Path


class PDFReaderError(RuntimeError):
    """Raised when a PDF cannot be read."""


class PDFScriptReader:
    """Read text from an editing-script PDF."""

    def read(self, pdf_path: str | Path) -> str:
        """Extract all available text from a PDF."""

        path = Path(pdf_path).expanduser()

        if not path.exists():
            raise PDFReaderError(
                f"PDF file does not exist: {path}"
            )

        if not path.is_file():
            raise PDFReaderError(
                f"PDF path is not a file: {path}"
            )

        if path.suffix.lower() != ".pdf":
            raise PDFReaderError(
                f"Expected a PDF file: {path}"
            )

        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise PDFReaderError(
                "The 'pypdf' package is required to read PDF scripts."
            ) from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise PDFReaderError(
                f"Unable to open PDF: {exc}"
            ) from exc

        pages: list[str] = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise PDFReaderError(
                    f"Unable to extract text from PDF page "
                    f"{page_number}: {exc}"
                ) from exc

            text = text.strip()

            if text:
                pages.append(text)

        return "\n\n".join(pages)
"""Replaceable document processing pipeline (validation, OCR, extraction).

The API depends on the DocumentProcessor protocol rather than an OCR vendor, so a
managed OCR or LLM-backed extractor can be substituted without changing routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Protocol


@dataclass
class ProcessorResult:
    extracted_text: str
    fields: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    readable: bool = True


class DocumentProcessor(Protocol):
    def process(self, path: str, media_type: str) -> ProcessorResult: ...


class TesseractPyMuPDFProcessor:
    """Extract embedded PDF text and use Tesseract OCR for scans and images."""

    def process(self, path: str, media_type: str) -> ProcessorResult:
        text = ""
        warnings: list[str] = []
        try:
            if media_type == "application/pdf":
                import fitz  # PyMuPDF

                with fitz.open(path) as document:
                    pages = list(document)[:10]
                    text = "\n".join(page.get_text("text") for page in pages).strip()
                    if len(text) < 25:
                        text = self._ocr_pages(pages)
            else:
                from PIL import Image
                import pytesseract

                with Image.open(path) as image:
                    text = pytesseract.image_to_string(image, timeout=30).strip()
        except ImportError:
            warnings.append("OCR dependencies are not installed; text could not be checked.")
        except Exception as exc:
            # OCR absence and unreadable scans are validation warnings, not upload failures.
            warnings.append(f"Text extraction was unavailable: {type(exc).__name__}.")
        text = text[:200_000]
        fields = extract_fields(text)
        return ProcessorResult(
            extracted_text=text,
            fields=fields,
            warnings=warnings,
            readable=len(text.strip()) >= 8,
        )

    @staticmethod
    def _ocr_pages(pages: list) -> str:
        from PIL import Image
        import pytesseract

        blocks = []
        for page in pages:
            import fitz

            max_dimension = max(page.rect.width, page.rect.height, 1)
            scale = min(1.7, 1800 / max_dimension)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            blocks.append(pytesseract.image_to_string(image, timeout=30))
        return "\n".join(blocks).strip()


def extract_fields(text: str) -> dict[str, str]:
    normalized = text.upper()
    patterns = {
        "pan": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        "gstin": r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
        "cin": r"\b[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b",
        "udyam_number": r"\bUDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}\b",
    }
    fields = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, normalized)
        if match:
            fields[name] = match.group(0)

    dates = re.findall(
        r"(?:VALID\s*(?:UP\s*TO|UNTIL|TILL|THROUGH)|EXPIRES?\s*(?:ON|:)?|EXPIRY\s*DATE\s*:?)\s*([0-3]?\d[/-][01]?\d[/-](?:19|20)\d{2})",
        normalized,
    )
    if dates:
        parsed = _parse_date(dates[0])
        if parsed:
            fields["expiry_date"] = parsed.isoformat()
    return fields


def _parse_date(value: str) -> date | None:
    for pattern in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def get_document_processor() -> DocumentProcessor:
    return TesseractPyMuPDFProcessor()

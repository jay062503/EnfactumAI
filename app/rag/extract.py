"""Text extraction for uploads, with OCR for images and scanned PDF pages.

OCR engines (OCR_PROVIDER):
  auto      -> vision LLM if the model can read images, else Tesseract if installed
  llm       -> vision LLM (OCR_MODEL / OCR_BASE_URL / OCR_API_KEY can point to a different model)
  tesseract -> local Tesseract binary + pytesseract (offline)
  none      -> no OCR
"""
import asyncio
import io
import logging
import shutil
from pathlib import Path

from ..config import Settings
from .parsers import IMAGE_TYPES, UnsupportedDocument, parse_document

log = logging.getLogger(__name__)
MIN_PAGE_TEXT = 25


def _tesseract_available() -> bool:
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


class Extractor:
    def __init__(self, settings: Settings, vision=None):
        self.s = settings
        self.vision = vision
        provider = settings.ocr_provider.lower()
        has_tess = provider in ("auto", "tesseract") and _tesseract_available()
        has_llm = provider in ("auto", "llm") and vision is not None and vision.available
        if provider == "tesseract":
            self.engine = "tesseract" if has_tess else None
        elif provider == "llm":
            self.engine = "llm" if has_llm else None
        elif provider == "auto":
            self.engine = "llm" if has_llm else "tesseract" if has_tess else None
        else:
            self.engine = None
        self._sem = asyncio.Semaphore(4)
        log.info("OCR engine: %s", self.engine or "disabled")

    @property
    def ocr_available(self) -> bool:
        return self.engine is not None

    async def ocr(self, data: bytes, mime: str) -> str:
        if not self.engine:
            raise UnsupportedDocument("Reading text from images needs OCR. Use a vision-capable model "
                                      "(LLM_SUPPORTS_VISION=true) or install Tesseract (OCR_PROVIDER=tesseract).")
        async with self._sem:
            if self.engine == "tesseract":
                return await asyncio.to_thread(self._tesseract, data)
            return await self.vision.read(data, mime)

    @staticmethod
    def _tesseract(data: bytes) -> str:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(data)))

    async def extract(self, filename: str, data: bytes) -> tuple[list[tuple[str, int | None]], bool]:
        """Returns ([(text, page)], used_ocr)."""
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_TYPES:
            text = (await self.ocr(data, IMAGE_TYPES[ext])).strip()
            if not text:
                raise UnsupportedDocument("No text could be read from this image.")
            return [(text, None)], True
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
            except ImportError:
                return await asyncio.to_thread(parse_document, filename, data), False
            return await self._pdf(fitz, data)
        return await asyncio.to_thread(parse_document, filename, data), False

    async def _pdf(self, fitz, data: bytes) -> tuple[list[tuple[str, int | None]], bool]:
        def read():
            doc = fitz.open(stream=data, filetype="pdf")
            pages, scans = [], []
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                if len(text.strip()) < MIN_PAGE_TEXT and self.engine and len(scans) < self.s.ocr_max_pages:
                    scans.append((i, page.get_pixmap(dpi=160).tobytes("png")))
                pages.append([text, i])
            return pages, scans

        pages, scans = await asyncio.to_thread(read)
        if scans:
            results = await asyncio.gather(*(self.ocr(png, "image/png") for _, png in scans), return_exceptions=True)
            for (page_no, _), text in zip(scans, results):
                if isinstance(text, str) and text.strip():
                    pages[page_no - 1][0] = text
        sections = [(t.strip(), p) for t, p in pages if t and t.strip()]
        if not sections:
            raise UnsupportedDocument("No text found in this PDF (scanned PDF and OCR unavailable).")
        return sections, bool(scans)

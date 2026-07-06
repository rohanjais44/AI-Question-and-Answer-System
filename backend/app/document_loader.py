
import os
from pathlib import Path
from typing import List

import PyPDF2

try:
    import pytesseract
    from pdf2image import convert_from_path

    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# Below this average extracted-characters-per-page, assume the PDF is
# scanned/image-only and worth trying OCR on.
MIN_CHARS_PER_PAGE = 20


class DocumentLoader:
    @staticmethod
    def load_from_file(file_path: str) -> str:
        ext = Path(file_path).suffix.lower()

        if ext == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        if ext == ".pdf":
            return DocumentLoader._extract_pdf_text(file_path)

        raise ValueError(f"Unsupported format: {ext}")

    @staticmethod
    def _extract_pdf_text(pdf_path: str) -> str:
        text = []
        page_count = 0
        try:
            with open(pdf_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                page_count = len(reader.pages)
                for page in reader.pages:
                    extracted = page.extract_text() or ""
                    text.append(extracted)
        except Exception as e:
            raise Exception(f"Error reading PDF: {str(e)}")

        joined = "\n".join(text)

        looks_scanned = page_count > 0 and (len(joined.strip()) / page_count) < MIN_CHARS_PER_PAGE
        if looks_scanned and _OCR_AVAILABLE:
            ocr_text = DocumentLoader._ocr_pdf(pdf_path)
            if len(ocr_text.strip()) > len(joined.strip()):
                return ocr_text

        return joined

    @staticmethod
    def _ocr_pdf(pdf_path: str) -> str:
        try:
            pages = convert_from_path(pdf_path, dpi=200)
            return "\n".join(pytesseract.image_to_string(p) for p in pages)
        except Exception:
            # Missing tesseract/poppler binaries, or a page that fails to
            # rasterize — degrade gracefully rather than failing the upload.
            return ""

    @staticmethod
    def split_into_chunks(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        chunks = []
        step = max(chunk_size - overlap, 1)
        for i in range(0, len(text), step):
            chunk = text[i:i + chunk_size]
            if len(chunk.strip()) > 50:
                chunks.append(chunk.strip())
        return chunks

    @staticmethod
    def load_documents(file_paths: List[str]) -> List[dict]:
        """Returns list of {source, text} chunk records for a set of file paths."""
        records = []
        for full_path in file_paths:
            file = os.path.basename(full_path)
            if not file.lower().endswith((".txt", ".pdf")):
                continue
            try:
                text = DocumentLoader.load_from_file(full_path)
                chunks = DocumentLoader.split_into_chunks(text)
                for chunk in chunks:
                    records.append({"source": file, "text": chunk})
            except Exception as e:
                print(f"Error loading {file}: {str(e)}")
        return records

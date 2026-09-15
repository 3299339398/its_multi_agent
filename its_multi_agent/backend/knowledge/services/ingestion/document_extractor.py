import logging
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Iterable, List
from zipfile import ZipFile

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.config.settings import settings


logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Extract text and OCR content from supported knowledge-base documents."""

    _ocr_engine = None
    _ocr_lock = Lock()

    @classmethod
    def load(cls, file_path: str) -> List[Document]:
        extension = Path(file_path).suffix.lower()
        if extension in {".md", ".txt"}:
            return TextLoader(file_path=file_path, encoding="utf-8", autodetect_encoding=True).load()
        if extension == ".pdf":
            return cls._load_pdf(file_path)
        if extension == ".docx":
            return cls._load_docx(file_path)
        if extension == ".xlsx":
            return cls._load_xlsx(file_path)
        raise ValueError(f"不支持的文档格式: {extension}")

    @classmethod
    def _load_pdf(cls, file_path: str) -> List[Document]:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        pdfium_document = None
        documents = []
        try:
            for page_index, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                ocr_text = ""
                if settings.OCR_ENABLED and len(text) < settings.OCR_PDF_TEXT_THRESHOLD:
                    if pdfium_document is None:
                        import pypdfium2 as pdfium
                        pdfium_document = pdfium.PdfDocument(file_path)
                    scale = settings.OCR_PDF_DPI / 72
                    image = pdfium_document[page_index].render(scale=scale).to_pil()
                    ocr_text = cls._recognize_image(image)
                page_content = cls._join_unique_text(text, ocr_text)
                documents.append(Document(
                    page_content=page_content,
                    metadata={"page": page_index + 1, "ocr_applied": bool(ocr_text)},
                ))
        finally:
            if pdfium_document is not None:
                pdfium_document.close()
        return documents

    @classmethod
    def _load_docx(cls, file_path: str) -> List[Document]:
        from docx import Document as WordDocument

        source = WordDocument(file_path)
        blocks = [paragraph.text.strip() for paragraph in source.paragraphs if paragraph.text.strip()]
        for table_index, table in enumerate(source.tables, start=1):
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            table_text = "\n".join(row for row in rows if row.strip())
            if table_text:
                blocks.append(f"表格 {table_index}:\n{table_text}")

        if settings.OCR_ENABLED:
            for image_index, image_bytes in enumerate(cls._docx_images(file_path), start=1):
                ocr_text = cls._recognize_image(image_bytes)
                if ocr_text:
                    blocks.append(f"图片 {image_index} OCR:\n{ocr_text}")
        return [Document(page_content="\n\n".join(blocks))]

    @staticmethod
    def _load_xlsx(file_path: str) -> List[Document]:
        from openpyxl import load_workbook

        workbook = load_workbook(file_path, read_only=True, data_only=True)
        documents = []
        try:
            for sheet in workbook.worksheets:
                rows = []
                for row in sheet.iter_rows(values_only=True):
                    values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                    if values:
                        rows.append(" | ".join(values))
                if rows:
                    documents.append(Document(
                        page_content=f"工作表: {sheet.title}\n" + "\n".join(rows),
                        metadata={"sheet": sheet.title},
                    ))
        finally:
            workbook.close()
        return documents

    @staticmethod
    def _docx_images(file_path: str) -> Iterable[bytes]:
        with ZipFile(file_path) as archive:
            for name in sorted(archive.namelist()):
                if name.startswith("word/media/") and not name.endswith("/"):
                    yield archive.read(name)

    @classmethod
    def _recognize_image(cls, image) -> str:
        try:
            from PIL import Image
            import numpy as np

            if isinstance(image, bytes):
                image = Image.open(BytesIO(image)).convert("RGB")
            else:
                image = image.convert("RGB")
            result, _ = cls._get_ocr_engine()(np.asarray(image))
            if not result:
                return ""
            lines = [str(item[1]).strip() for item in result if len(item) > 1 and str(item[1]).strip()]
            return "\n".join(lines)
        except Exception as error:
            logger.warning("图片 OCR 失败: %s", error)
            return ""

    @classmethod
    def _get_ocr_engine(cls):
        if cls._ocr_engine is None:
            with cls._ocr_lock:
                if cls._ocr_engine is None:
                    from rapidocr_onnxruntime import RapidOCR
                    cls._ocr_engine = RapidOCR()
        return cls._ocr_engine

    @staticmethod
    def _join_unique_text(text: str, ocr_text: str) -> str:
        if not text:
            return ocr_text
        if not ocr_text or ocr_text in text:
            return text
        return f"{text}\n\nOCR 提取内容:\n{ocr_text}"

"""Draft file import: UTF-8 .txt and text-based PDF, validated by content.

The browser's filename extension and MIME type are hints only. A file is
classified by its bytes: PDF files must start with the PDF signature, and
plain-text files must decode as UTF-8 without NUL bytes. Imported text is
never executed and never written to the database; it becomes editable draft
text only after the guest confirms the extracted preview.

Limits (documented on the workspace page):
  * one file per import,
  * 5 MiB upload,
  * 10 PDF pages,
  * the same draft-text limit as the editor (``MAX_DRAFT_LENGTH``).
"""
import io
import os
import re

from .checker import MAX_DRAFT_LENGTH

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_FILENAME_LENGTH = 200
SUPPORTED_EXTENSIONS = (".txt", ".pdf")

PDF_SIGNATURE = b"%PDF-"
NO_TEXT_MESSAGE = (
    "We couldn’t extract usable text. Paste the content manually or choose a "
    "text-based PDF. Scanned-document OCR is not supported."
)
ENCODING_MESSAGE = (
    "This file is not UTF-8 text. Save it as UTF-8 (or choose a UTF-8 .txt "
    "file) and try again."
)

_UTF16_32_BOMS = (
    b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff",  # UTF-32 LE / BE
    b"\xff\xfe", b"\xfe\xff",                  # UTF-16 LE / BE
)


class FileImportError(ValueError):
    """A user-facing reason the file could not be turned into draft text."""


def _filename(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FileImportError("Choose a .txt or PDF file to import.")
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        raise FileImportError("Choose a .txt or PDF file to import.")
    if len(name) > MAX_FILENAME_LENGTH:
        raise FileImportError("That filename is too long to import.")
    return name


def _extension(name: str) -> str:
    return os.path.splitext(name)[1].casefold()


def _is_pdf(data: bytes) -> bool:
    """Recognise the PDF signature, tolerating a leading BOM or whitespace."""
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    return head.startswith(PDF_SIGNATURE)


def _check_length(text: str, *, source: str) -> str:
    if len(text) > MAX_DRAFT_LENGTH:
        raise FileImportError(
            f"The {source} is {len(text):,} characters; drafts are limited to "
            f"{MAX_DRAFT_LENGTH:,} characters. Shorten the file and try again."
        )
    return text


def _normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_text_file(name: str, data: bytes) -> dict:
    if data.startswith(_UTF16_32_BOMS):
        raise FileImportError(ENCODING_MESSAGE)
    if b"\x00" in data:
        raise FileImportError(
            "This file looks like a binary document, not plain text. Choose a "
            "UTF-8 .txt file or a text-based PDF."
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileImportError(ENCODING_MESSAGE) from exc
    text = _normalise_newlines(text)
    if not text.strip():
        raise FileImportError("This file contains no readable text.")
    _check_length(text, source="text in this file")
    return {"kind": "txt", "filename": name, "text": text, "pages": None}


def _extract_pdf(name: str, data: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - deployment guard
        raise FileImportError(
            "PDF import is not available in this build. Use a UTF-8 .txt file "
            "or paste the text instead."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            # Some PDFs carry an empty user password and open without one;
            # a real password must be reported, never guessed at.
            try:
                opened = reader.decrypt("")
            except Exception as exc:
                raise FileImportError(
                    "This PDF is password-protected. Remove the password and "
                    "try again."
                ) from exc
            if not opened:
                raise FileImportError(
                    "This PDF is password-protected. Remove the password and "
                    "try again."
                )
        page_count = len(reader.pages)
        if page_count == 0:
            raise FileImportError("This PDF has no pages to extract.")
        if page_count > MAX_PDF_PAGES:
            raise FileImportError(
                f"This PDF has {page_count} pages. PDFs are limited to "
                f"{MAX_PDF_PAGES} pages; split the document and try again."
            )
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # a single unreadable page must not fake text
                pages.append("")
        text = _normalise_newlines("\n\n".join(pages))
    except FileImportError:
        raise
    except Exception as exc:
        raise FileImportError(
            "This PDF could not be read. It may be malformed or damaged. "
            "Choose a text-based PDF or paste the content manually."
        ) from exc

    # Strip trailing whitespace per line and collapse blank runs, without
    # inventing text that was not extracted.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise FileImportError(NO_TEXT_MESSAGE)
    _check_length(text, source="extracted PDF text")
    return {"kind": "pdf", "filename": name, "text": text, "pages": page_count}


def validate_and_extract(filename, data) -> dict:
    """Validate one uploaded file and return its extracted draft text.

    Raises :class:`FileImportError` with a message safe to show to a guest.
    Nothing is written anywhere; the caller decides whether to use the text.
    """
    name = _filename(filename)
    extension = _extension(name)
    if extension not in SUPPORTED_EXTENSIONS:
        raise FileImportError(
            "Only UTF-8 .txt files and text-based PDFs are supported. "
            "Choose a different file."
        )
    if not isinstance(data, (bytes, bytearray)):
        raise FileImportError("The uploaded file could not be read.")
    data = bytes(data)
    if not data:
        raise FileImportError("This file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileImportError(
            f"Files are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            "Choose a smaller file."
        )

    if _is_pdf(data):
        return _extract_pdf(name, data)
    if extension == ".pdf":
        raise FileImportError(
            "This file does not look like a PDF. Choose a text-based PDF or a "
            "UTF-8 .txt file."
        )
    return _extract_text_file(name, data)

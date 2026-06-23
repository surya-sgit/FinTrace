"""Parser Factory for FinTrace ingestion pipeline.

Based on the uploaded file's MIME type (or content detection) it returns an
instance of a concrete parser implementing :class:`BaseParser`.
"""

from typing import Optional
from fastapi import UploadFile

from .base import BaseParser, IngestionValidationError
from .parsers.csv_parser import BrokerCSVParser
from .parsers.pdf_parser import CasPDFParser


class ParserFactory:
    """Factory that selects the appropriate parser for a given upload.

    The factory inspects ``UploadFile.content_type`` to decide between the CSV
    and PDF parsers.  For unknown MIME types a ``ValueError`` is raised – the
    caller translates this into a 400 response.
    """

    @staticmethod
    def get_parser(file: UploadFile, password: Optional[str] = None) -> BaseParser:
        mime = file.content_type.lower()
        if mime == "text/csv":
            return BrokerCSVParser()
        if mime == "application/pdf":
            return CasPDFParser(password=password)
        raise ValueError(f"Unsupported file type: {mime}")

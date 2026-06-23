from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from domain import schemas


class IngestionValidationError(Exception):
    """Raised when any row fails validation during parsing.

    Attributes
    ----------
    errors: List[dict]
        List of error dicts containing row information and validation errors.
    """

    def __init__(self, errors: List[dict]):
        self.errors = errors
        super().__init__("Ingestion validation failed")


class BaseParser(ABC):
    """Abstract parser interface for all ingestion pipelines.

    Sub‑classes must implement :py:meth:`parse` and return a list of
    :class:`domain.schemas.TransactionCreate` instances.
    """

    @abstractmethod
    def parse(self, file_content: bytes, password: Optional[str] = None) -> List[schemas.TransactionCreate]:
        """Parse the raw file content.

        Parameters
        ----------
        file_content: bytes
            The uploaded file bytes.
        password: Optional[str]
            Password for encrypted PDFs (only relevant for PDF parsers).
        """
        raise NotImplementedError

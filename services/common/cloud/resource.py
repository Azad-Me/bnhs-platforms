from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


ClientT = TypeVar("ClientT")


class CloudResource(ABC, Generic[ClientT]):
    """Base for lazily initialized cloud SDK clients."""

    def __init__(self) -> None:
        self._client: ClientT | None = None

    @property
    def client(self) -> ClientT:
        if self._client is None:
            self._client = self.create_client()
        return self._client

    @abstractmethod
    def create_client(self) -> ClientT:
        """Create and return the provider-specific SDK client."""

    def close(self) -> None:
        """Close the client if its SDK exposes a synchronous close method."""
        if self._client is None:
            return

        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None

# from common import S3Resource

# s3 = S3Resource()
# s3.client.upload_file("document.pdf", "journal-qc", "incoming/document.pdf")
# s3.close()
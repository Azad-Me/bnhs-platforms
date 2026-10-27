from __future__ import annotations

from typing import TYPE_CHECKING

from ..env import load_environment
from .resource import CloudResource

if TYPE_CHECKING:
    from botocore.client import BaseClient


class S3Resource(CloudResource["BaseClient"]):
    """Lazily created boto3 S3 client for direct programmatic operations."""

    def __init__(
        self,
        *,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
    ) -> None:
        super().__init__()
        env = load_environment()
        self.region_name = region_name or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
        self.endpoint_url = endpoint_url or env.get("AWS_S3_ENDPOINT_URL")
        self.aws_access_key_id = aws_access_key_id or env.get("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or env.get("AWS_SECRET_ACCESS_KEY")
        self.aws_session_token = aws_session_token or env.get("AWS_SESSION_TOKEN")

    def create_client(self) -> BaseClient:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "S3 access requires boto3. Install it with `pip install boto3`."
            ) from exc

        client_options = {
            "endpoint_url": self.endpoint_url,
            "region_name": self.region_name,
            "aws_access_key_id": self.aws_access_key_id,
            "aws_secret_access_key": self.aws_secret_access_key,
            "aws_session_token": self.aws_session_token,
        }
        return boto3.client(
            "s3",
            **{key: value for key, value in client_options.items() if value is not None},
        )

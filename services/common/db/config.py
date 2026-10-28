from dataclasses import dataclass

from common import params


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = params.get("DB_HOST", "localhost")
    port: int = int(params.get("DB_PORT", "5432"))
    username: str = params.get("DB_USERNAME", "postgres")
    password: str = params.get("DB_PASSWORD", "12345")
    database: str = params.get("DB_NAME", "journal_qc")
    min_size: int = int(params.get("DB_POOL_MIN_SIZE", "5"))
    max_size: int = int(params.get("DB_POOL_MAX_SIZE", "20"))
    max_overflow: int = int(params.get("DB_POOL_MAX_OVERFLOW", "10"))
    pool_timeout: float = float(params.get("DB_POOL_TIMEOUT", "30"))
    echo: bool = params.get("DB_ECHO", "false").lower() == "true"

    @property
    def async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/"
            f"{self.database}"
        )

    @property
    def sync_url(self) -> str:
        return (
            f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/"
            f"{self.database}"
        )

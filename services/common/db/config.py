from dataclasses import dataclass, field

from ..env import load_environment


def _environment_value(name: str, default: str) -> str:
    return load_environment().get(name, default)


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = field(default_factory=lambda: _environment_value("DB_HOST", "localhost"))
    port: int = field(
        default_factory=lambda: int(_environment_value("DB_PORT", "5432"))
    )
    username: str = field(
        default_factory=lambda: _environment_value("DB_USERNAME", "postgres")
    )
    password: str = field(
        default_factory=lambda: _environment_value("DB_PASSWORD", "12345")
    )
    database: str = field(
        default_factory=lambda: _environment_value("DB_NAME", "journal_qc")
    )
    min_size: int = field(
        default_factory=lambda: int(_environment_value("DB_POOL_MIN_SIZE", "5"))
    )
    max_size: int = field(
        default_factory=lambda: int(_environment_value("DB_POOL_MAX_SIZE", "20"))
    )
    max_overflow: int = field(
        default_factory=lambda: int(_environment_value("DB_POOL_MAX_OVERFLOW", "10"))
    )
    pool_timeout: float = field(
        default_factory=lambda: float(_environment_value("DB_POOL_TIMEOUT", "30"))
    )
    echo: bool = field(
        default_factory=lambda: _environment_value("DB_ECHO", "false").lower()
        == "true"
    )

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

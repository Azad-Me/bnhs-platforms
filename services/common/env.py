from os import environ

from dotenv import load_dotenv


load_dotenv()


def load_environment() -> dict[str, str]:
    """Return a snapshot of the process environment variables."""
    return dict(environ)

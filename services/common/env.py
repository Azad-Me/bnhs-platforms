from os import environ


def load_environment() -> dict[str, str]:
    """Return a snapshot of the process environment variables."""
    return dict(environ)

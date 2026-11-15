from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RedactingFormatter(logging.Formatter):
    def __init__(self, secret: str):
        super().__init__(LOG_FORMAT)
        self.secret = secret

    def format(self, record: logging.LogRecord) -> str:
        return super().format(record).replace(self.secret, "[redacted]")


def configure_logging(level: str = "INFO", *, secret: str | None = None) -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format=LOG_FORMAT, force=True)
    if secret:
        for handler in logging.getLogger().handlers:
            handler.setFormatter(RedactingFormatter(secret))

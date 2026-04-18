from __future__ import annotations

from chromantis.config import AppConfig
from chromantis.source.adapters import ArchiveSource, FtpArchiveSource, LocalArchiveSource


def build_archive_source(config: AppConfig) -> ArchiveSource:
    if config.source_type == "ftp":
        return FtpArchiveSource(
            host=config.ftp_host,
            port=config.ftp_port,
            user=config.ftp_user,
            password=config.ftp_password,
            source_root=config.source_root,
        )
    if config.source_type == "local":
        return LocalArchiveSource(source_root=config.source_root)
    raise ValueError(f"Unsupported SOURCE_TYPE: {config.source_type}")

from chromantis.source.adapters import (
    MAX_SCAN_DEPTH,
    ArchiveEntry as FTPEntry,
    ArchiveSource as FTPClient,
    FtpArchiveSource as StdlibFTPClient,
    LocalArchiveSource as LocalPathFTPClient,
)

__all__ = [
    "FTPEntry",
    "FTPClient",
    "StdlibFTPClient",
    "LocalPathFTPClient",
    "MAX_SCAN_DEPTH",
]

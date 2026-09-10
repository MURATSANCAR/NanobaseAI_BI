"""Driver dispatch. Every scanner is imported only when its driver is the one in use.

A SQL Server deployment was unable to scan at all because importing this package pulled in the
postgres scanner, and with it psycopg2: an interpreter that has the driver for the database the
customer actually runs failed on the driver for one they do not.
"""

from __future__ import annotations

__all__ = ["scan_metadata", "apply_controlled_profiling"]


def scan_metadata(cfg):
    """Dispatch on the datasource driver (postgres default, mssql via mssql-ro map)."""
    if cfg.driver == "mssql":
        from scanner.mssql import scan_metadata_mssql

        return scan_metadata_mssql(cfg)
    from scanner.metadata import scan_metadata as scan_postgres

    return scan_postgres(cfg)


def apply_controlled_profiling(cfg, tables):
    if cfg.driver == "mssql":
        from scanner.mssql import profile_mssql

        return profile_mssql(cfg, tables)
    from scanner.profiler import apply_controlled_profiling as profile_postgres

    return profile_postgres(cfg, tables)

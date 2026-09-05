from __future__ import annotations

from scanner.metadata import scan_metadata as _scan_postgres
from scanner.profiler import apply_controlled_profiling as _profile_postgres

__all__ = ["scan_metadata", "apply_controlled_profiling"]


def scan_metadata(cfg):
    """Dispatch on the datasource driver (postgres default, mssql via mssql-ro map)."""
    if cfg.driver == "mssql":
        from scanner.mssql import scan_metadata_mssql

        return scan_metadata_mssql(cfg)
    return _scan_postgres(cfg)


def apply_controlled_profiling(cfg, tables):
    if cfg.driver == "mssql":
        from scanner.mssql import profile_mssql

        return profile_mssql(cfg, tables)
    return _profile_postgres(cfg, tables)

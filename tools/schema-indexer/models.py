from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DocumentType = Literal["TABLE", "COLUMN", "RELATIONSHIP"]


@dataclass
class ForeignKey:
    column: str
    target_schema: str
    target_table: str
    target_column: str

    def as_doc(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "target_table": self.target_table,
            "target_column": self.target_column,
            "target_schema": self.target_schema,
        }


@dataclass
class ColumnMeta:
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    nullable: bool
    ordinal: int
    is_pk: bool = False
    description: str = ""
    samples: list[str] = field(default_factory=list)
    udt_name: str | None = None
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    type_display: str = ""


@dataclass
class TableMeta:
    schema_name: str
    table_name: str
    table_type: str  # BASE TABLE | VIEW
    description: str = ""
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    columns: list[ColumnMeta] = field(default_factory=list)
    row_count: int | None = None
    date_min: str | None = None
    date_max: str | None = None
    status_dist: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RelationshipMeta:
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    relationship_type: str = "many-to-one"


@dataclass
class SchemaDocument:
    """Normalized document ready for fingerprint + embed + upsert."""

    document_type: DocumentType
    datasource_id: str
    document_key: str
    fingerprint: str
    text: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanReport:
    datasource_id: str
    collection: str
    schemas: list[str]
    tables_scanned: int
    documents_total: int
    embedded: int
    skipped_unchanged: int
    upserted: int
    soft_deleted: int
    elapsed_s: float
    points_count: int | None = None
    sample_docs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

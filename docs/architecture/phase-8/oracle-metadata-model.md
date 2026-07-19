# Oracle Metadata Model

Scanner sources (no `DBA_*`):

`ALL_OBJECTS`, `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_TAB_COMMENTS`, `ALL_COL_COMMENTS`,
`ALL_CONSTRAINTS`, `ALL_CONS_COLUMNS`, `ALL_INDEXES`, `ALL_IND_COLUMNS`,
`ALL_VIEWS`, `ALL_MVIEWS`, `ALL_SYNONYMS`, `ALL_POLICIES`.

Synonym policy: public rejected by default; private allowlisted; resolve chain;
target must be TABLE/VIEW in allowed owners; remote/circular rejected.

Qdrant payload requires: `tenant_id`, `datasource_id`, `database_type=ORACLE`,
`owner`, `schema_version`, `semantic_version`, `status=ACTIVE`.

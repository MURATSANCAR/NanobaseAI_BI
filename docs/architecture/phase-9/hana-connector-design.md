# HANA Connector Design

## Driver

`hdbcli` (`from hdbcli import dbapi`), version pinned. TLS + certificate verify required.
Autocommit off, read-only user, statement timeout required.

## Policy

SELECT / WITH / UNION only. No DML/DDL/SQLScript/procedure/remote source/virtual table.
Function allowlist in `hana-functions.yaml`. Unparsed SQL is rejected.

## Workload

Class `NANOBASE_INTERACTIVE_QUERY`: statement timeout ~15s, memory/concurrency per DBA profile.
Missing workload policy → `HANA_WORKLOAD_POLICY_MISSING` (no execute).

## Plan Guard

`EXPLAIN PLAN` rejects full scans, cartesian joins, remote/virtual access, excessive memory
against datasource size profile (SMALL…VERY_LARGE).

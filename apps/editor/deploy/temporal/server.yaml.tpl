# Rendered by editorctl into $EDITOR_ROOT/temporal/server.yaml (password filled in).
# Based on temporalio/temporal v1.32.0 config/development-postgres12.yaml.
log:
  stdout: true
  level: warn

persistence:
  defaultStore: postgres-default
  visibilityStore: postgres-visibility
  numHistoryShards: 4
  datastores:
    postgres-default:
      sql:
        pluginName: "postgres12"
        databaseName: "temporal"
        connectAddr: "editor-postgres:5432"
        connectProtocol: "tcp"
        user: "temporal"
        password: "${TEMPORAL_DB_PASSWORD}"
        maxConns: 20
        maxIdleConns: 20
        maxConnLifetime: "1h"
    postgres-visibility:
      sql:
        pluginName: "postgres12"
        databaseName: "temporal_visibility"
        connectAddr: "editor-postgres:5432"
        connectProtocol: "tcp"
        user: "temporal"
        password: "${TEMPORAL_DB_PASSWORD}"
        maxConns: 4
        maxIdleConns: 4
        maxConnLifetime: "1h"

global:
  membership:
    maxJoinDuration: 30s
    broadcastAddress: "127.0.0.1"

services:
  frontend:
    rpc: {grpcPort: 7233, membershipPort: 6933, bindOnIP: "0.0.0.0", httpPort: 7243}
  matching:
    rpc: {grpcPort: 7235, membershipPort: 6935, bindOnLocalHost: true}
  history:
    rpc: {grpcPort: 7234, membershipPort: 6934, bindOnLocalHost: true}
  worker:
    rpc: {grpcPort: 7239, membershipPort: 6939, bindOnLocalHost: true}

clusterMetadata:
  enableGlobalNamespace: false
  failoverVersionIncrement: 10
  masterClusterName: "active"
  currentClusterName: "active"
  clusterInformation:
    active:
      enabled: true
      initialFailoverVersion: 1
      rpcName: "frontend"
      rpcAddress: "127.0.0.1:7233"

dcRedirectionPolicy:
  policy: "noop"

dynamicConfigClient:
  filepath: "/etc/temporal/config/dynamicconfig.yaml"
  pollInterval: "60s"

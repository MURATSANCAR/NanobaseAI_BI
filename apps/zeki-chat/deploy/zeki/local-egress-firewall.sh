#!/usr/bin/env bash
# Only this stack's fixed bridge is affected. Keep replies to host-initiated requests.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { printf '%s\n' 'Run as root' >&2; exit 1; }
for firewall in iptables ip6tables; do
  if ! "$firewall" -w -S ZEKI-LOCAL-HOST >/dev/null 2>&1; then
    "$firewall" -w -N ZEKI-LOCAL-HOST
  fi
  "$firewall" -w -C ZEKI-LOCAL-HOST -m conntrack --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN 2>/dev/null ||
    "$firewall" -w -I ZEKI-LOCAL-HOST 1 -m conntrack --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN
  # Remove the former broad rule: pre-existing outbound flows must not survive policy application.
  while "$firewall" -w -C ZEKI-LOCAL-HOST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN 2>/dev/null; do
    "$firewall" -w -D ZEKI-LOCAL-HOST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  done
  "$firewall" -w -C ZEKI-LOCAL-HOST -j REJECT 2>/dev/null ||
    "$firewall" -w -A ZEKI-LOCAL-HOST -j REJECT
  for bridge in zeki-local0 zeki-ingress0; do
    "$firewall" -w -C INPUT -i "$bridge" -j ZEKI-LOCAL-HOST 2>/dev/null ||
      "$firewall" -w -I INPUT 1 -i "$bridge" -j ZEKI-LOCAL-HOST
  done
  if ! "$firewall" -w -S ZEKI-LOCAL-EGRESS >/dev/null 2>&1; then
    "$firewall" -w -N ZEKI-LOCAL-EGRESS
  fi
  "$firewall" -w -C ZEKI-LOCAL-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN 2>/dev/null ||
    "$firewall" -w -I ZEKI-LOCAL-EGRESS 1 -m conntrack --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN
  # Remove the former broad rule: pre-existing outbound flows must not survive policy application.
  while "$firewall" -w -C ZEKI-LOCAL-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN 2>/dev/null; do
    "$firewall" -w -D ZEKI-LOCAL-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  done
  "$firewall" -w -C ZEKI-LOCAL-EGRESS -j REJECT 2>/dev/null ||
    "$firewall" -w -A ZEKI-LOCAL-EGRESS -j REJECT
  # Docker preserves this user chain and invokes it before its own forwarding rules.
  if ! "$firewall" -w -S DOCKER-USER >/dev/null 2>&1; then
    "$firewall" -w -N DOCKER-USER
  fi
  "$firewall" -w -C DOCKER-USER -i zeki-ingress0 -j ZEKI-LOCAL-EGRESS 2>/dev/null ||
    "$firewall" -w -I DOCKER-USER 1 -i zeki-ingress0 -j ZEKI-LOCAL-EGRESS
  # Also cover the pre-Docker interval; Docker's own jump takes over after startup.
  "$firewall" -w -C FORWARD -i zeki-ingress0 -j ZEKI-LOCAL-EGRESS 2>/dev/null ||
    "$firewall" -w -I FORWARD 1 -i zeki-ingress0 -j ZEKI-LOCAL-EGRESS
done

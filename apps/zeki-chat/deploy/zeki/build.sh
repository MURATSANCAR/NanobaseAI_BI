#!/usr/bin/env bash
# ZEKI AI CHAT chat: packages -> Meteor bundle -> Docker image -> restart container.
# Run on the build server from the BI repository apps/zeki-chat directory. Writes progress to ~/zeki-build.status.
set -euo pipefail

CHAT_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO="${REPO:-$CHAT_SOURCE_ROOT}"
DIST="${DIST:-/tmp/zeki-ai-chat-dist}"
STATUS="$HOME/zeki-build.status"
export PATH="$HOME/.local/bin:$HOME/.meteor:$HOME/.deno/bin:$PATH"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

step() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }
trap 'step "FAILED at line $LINENO"' ERR

: > "$STATUS"
cd "$REPO"

step "packages"
NODE_OPTIONS=--max-old-space-size=16384 yarn build > "$HOME/yarn-build.log" 2>&1

step "meteor bundle"
rm -rf "$DIST"
(cd apps/meteor && TOOL_NODE_FLAGS=--max-old-space-size=32768 METEOR_DEBUG_BUILD=1 METEOR_DISABLE_OPTIMISTIC_CACHING=1 meteor build --verbose --server-only --directory "$DIST" > "$HOME/meteor-build.log" 2>&1)
if grep -q "Errors prevented bundling" "$HOME/meteor-build.log"; then
	step "FAILED meteor bundle (see ~/meteor-build.log)"
	exit 1
fi

# IMAGE: tag to build (default the one compose runs). SKIP_RESTART=1 builds only; the running
# container keeps its image until it is recreated.
IMAGE="${IMAGE:-zeki-ai-chat:8.5.3}"

step "docker image $IMAGE"
cp deploy/zeki/Dockerfile "$DIST/Dockerfile"
cp deploy/zeki/clean-vendor-notices.cjs "$DIST/clean-vendor-notices.cjs"
docker build --build-arg ZEKI_CODE_VERSION="${ZEKI_CODE_VERSION:-unknown}" -t "$IMAGE" "$DIST" > "$HOME/zeki-docker-build.log" 2>&1

if [ "${SKIP_RESTART:-0}" = "1" ]; then
	step "DONE (no restart)"
	exit 0
fi

# The host-input guard complements Docker internal networking: no host proxy detour.
sudo -n /usr/local/sbin/zeki-local-egress && systemctl is-active --quiet zeki-local-egress.service || {
	step "FAILED: install and start deploy/zeki/zeki-local-egress.service before restart"
	exit 1
}
step "restart"
(cd deploy/zeki && ZEKI_CHAT_IMAGE="$IMAGE" docker compose --env-file .env -p zeki up -d --force-recreate zeki-chat zeki-ingress > "$HOME/zeki-compose.log" 2>&1)

bash deploy/zeki/clear-external-ice.sh

step "DONE"

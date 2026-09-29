# ZEKI AI CHAT image (glibc base — the bundle is built on Ubuntu, so native modules like sharp need glibc).
# Build context is the Meteor bundle produced by `yarn build:ci` in apps/meteor (output dir contains ./bundle).
ARG DENO_VERSION="2.3.1"

FROM denoland/deno:bin-${DENO_VERSION} AS deno

FROM node:22.22.3-bookworm-slim

ARG ZEKI_CODE_VERSION=unknown
ENV ZEKI_CODE_VERSION=${ZEKI_CODE_VERSION}

RUN groupadd -g 65533 -r zeki \
    && useradd -u 65533 -r -g zeki zeki \
    && mkdir -p /app/uploads \
    && chown zeki:zeki /app/uploads \
    && apt-get update \
    && apt-get install -y --no-install-recommends fontconfig fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deno /deno /bin/deno

ADD --chown=zeki:zeki bundle /app/bundle
COPY clean-vendor-notices.cjs /tmp/clean-vendor-notices.cjs

ENV DEPLOY_METHOD=docker \
    NODE_ENV=production \
    MONGO_URL=mongodb://mongo:27017/zeki \
    HOME=/tmp \
    PORT=3000 \
    ROOT_URL=http://localhost:3000 \
    Accounts_AvatarStorePath=/app/uploads

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ make python3 \
    && su zeki -s /bin/sh -c 'export HOME=/tmp && cd /app/bundle/programs/server \
        && npm install --omit=dev \
        && cd npm/node_modules/isolated-vm && npm install --omit=dev \
        && npm cache clean --force' \
    && find /app/bundle/programs/server/npm/node_modules -type f -name "*.map" -delete \
    && find /app/bundle/programs/web.browser -type f -name "*.map" -delete \
    && node /tmp/clean-vendor-notices.cjs /app/bundle \
    && rm /tmp/clean-vendor-notices.cjs \
    && apt-get purge -y --auto-remove g++ make python3 \
    && rm -rf /var/lib/apt/lists/*

USER zeki

VOLUME /app/uploads

WORKDIR /app/bundle

EXPOSE 3000

CMD ["node", "main.js"]

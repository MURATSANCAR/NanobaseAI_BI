# NanobaseAI BI — web arayüzü (statik build + nginx ters vekil)
FROM node:20-alpine AS build
ARG VITE_BASE=/
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json tailwind.config.js postcss.config.js ./
COPY src ./src
ENV VITE_BASE=${VITE_BASE}
RUN npm run build

FROM nginx:1.27-alpine
ARG VITE_BASE=/
COPY deploy/compose/web/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV WEB_BASE_PATH=${VITE_BASE}
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80

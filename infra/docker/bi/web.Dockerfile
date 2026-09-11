# Portal (kanvas arayüz): node ile derle, nginx:alpine ile sun.
# İki aşama — imajda node kalmaz.
#
# Tek frontend kök dizindeki kanvas uygulamasıdır (src/). Bizim sunucudaki gibi /timas/ altında
# sunulur; motor /timas/api/. VITE_ENGINE_BASE boşsa arayüz veri çağrılarını tamamen kapatır.
FROM node:20-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js ./
COPY src ./src
RUN VITE_ENGINE_BASE=/timas npx vite build --base=/timas/

FROM nginx:alpine
# default.conf.template: nginx:alpine açılışta envsubst ile ${CALLER_TOKEN}'ı yazar.
# Ortam değişkeni olmayan $host/$uri gibi nginx değişkenlerine dokunmaz (sadece env'de tanımlı olanları değiştirir).
COPY infra/docker/bi/web.default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80

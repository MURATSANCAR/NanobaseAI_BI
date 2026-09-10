# Kokpit: node ile derle, nginx:alpine ile sun. İki aşama — imajda node kalmaz.
FROM node:20-slim AS build
WORKDIR /src
COPY apps/cockpit/package.json apps/cockpit/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/cockpit ./
# Kök yoldan sunulur (VM IP / müşteri alan adı): base '/'.
RUN npm run build

FROM nginx:alpine
# default.conf.template: nginx:alpine açılışta envsubst ile ${CALLER_TOKEN}'ı yazar.
# Ortam değişkeni olmayan $host/$uri gibi nginx değişkenlerine dokunmaz (sadece env'de tanımlı olanları değiştirir).
COPY infra/docker/bi/web.default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80

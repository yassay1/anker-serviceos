ARG NODE_IMAGE=node:24-alpine
ARG NGINX_IMAGE=nginx:1.28-alpine
FROM ${NODE_IMAGE} AS build

# Official registry by default; a reviewed mirror may be passed for local builds only.
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}"
COPY frontend ./
RUN npm run build

FROM ${NGINX_IMAGE} AS runtime
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/proxy.conf /etc/nginx/serviceos-proxy.conf
COPY deploy/nginx/security.conf /etc/nginx/serviceos-security.conf
COPY deploy/nginx/local.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
# The official entrypoint renders only the production hostname template.
# TLS keys are runtime mounts; no application secrets enter this build.
RUN chown -R nginx:nginx /etc/nginx/conf.d
USER nginx
EXPOSE 8080 8443
CMD ["nginx", "-g", "daemon off;"]

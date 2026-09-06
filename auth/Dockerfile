FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
WORKDIR /app
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci --no-fund
COPY src ./src
COPY test ./test
RUN npm test && npm prune --omit=dev --ignore-scripts --no-fund

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
ENV NODE_ENV=production \
    AUTH_HOST=0.0.0.0 \
    AUTH_PORT=3219 \
    AUTH_DATA_DIR=/data \
    AUTH_ISSUER=https://kcanakdag.com:8443/auth
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist/src ./dist/src
COPY package.json package-lock.json ./
RUN mkdir -p /data && chown node:node /data
USER node
VOLUME ["/data"]
EXPOSE 3219
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 CMD ["node", "--input-type=module", "-e", "fetch('http://127.0.0.1:' + (process.env.AUTH_PORT || '3219') + '/auth/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "dist/src/main.js"]

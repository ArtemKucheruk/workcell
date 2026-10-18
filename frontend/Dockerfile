# docs/MVP.md §4.6: the frontend image. server.js uses Node built-ins only, so the runtime has no node_modules.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-slim
WORKDIR /app
# package.json: its "type": "module" makes server.js load as ESM
COPY package.json server.js ./
COPY --from=build /app/dist ./dist
USER node
CMD ["node", "server.js"]

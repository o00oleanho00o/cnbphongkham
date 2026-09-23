# Build context is the repo root: the viewer bundles the sibling canvas folder as its public dir.
FROM node:24-slim AS build
WORKDIR /repo/design-viewer
COPY design-viewer/package.json design-viewer/package-lock.json ./
RUN npm ci
COPY design-viewer/ ./
COPY ["Pema App redesign canvas", "/repo/Pema App redesign canvas"]
RUN npm run build

FROM nginx:stable-alpine
COPY design-viewer/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/design-viewer/dist /usr/share/nginx/html
EXPOSE 80

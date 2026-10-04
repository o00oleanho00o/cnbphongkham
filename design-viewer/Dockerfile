# Build context is the repo root: the viewer bundles the sibling canvas folder as its public dir.
# CANVAS_DIR picks the canvas folder (default: the app canvas); the web canvas uses --build-arg CANVAS_DIR="Pema Web redesign canvas".
ARG CANVAS_DIR="Pema App redesign canvas"
FROM node:24-slim AS build
WORKDIR /repo/design-viewer
COPY design-viewer/package.json design-viewer/package-lock.json ./
RUN npm ci
COPY design-viewer/ ./
ARG CANVAS_DIR
COPY ["${CANVAS_DIR}", "/repo/canvas"]
ENV DC_CANVAS_DIR=../canvas
RUN npm run build

FROM nginx:stable-alpine
COPY design-viewer/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/design-viewer/dist /usr/share/nginx/html
EXPOSE 80

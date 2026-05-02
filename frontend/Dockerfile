# Multi-stage build: Node for vite build, nginx for serving.
FROM node:22-alpine AS build
WORKDIR /app

# Cache deps separately so source changes don't bust the npm install layer.
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Signal handling for clean container shutdown.
STOPSIGNAL SIGTERM
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]

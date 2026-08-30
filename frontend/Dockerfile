# ---- Stage 1: Build ----
FROM node:20-slim AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite inlines `import.meta.env.VITE_*` at build time, reading them from the process
# environment — so a bare ARG is not enough, it has to be re-exported as ENV before the
# build runs. docker-compose.yml has always passed these two as build args; without the
# declarations below Docker discarded them silently and the bundle fell back to the
# localhost defaults in src/api/client.ts.
ARG VITE_API_URL
ARG VITE_WS_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# ---- Stage 2: Serve ----
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

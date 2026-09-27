# ==============================================================================
# Stage 1: Build React Frontend SPA
# ==============================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Build WhatsApp Baileys Microservice
# ==============================================================================
FROM node:22-alpine AS whatsapp-builder
WORKDIR /app/whatsapp-service

COPY whatsapp-service/package*.json whatsapp-service/tsconfig.json ./
RUN npm ci

COPY whatsapp-service/src/ ./src/
RUN npm run build

# ==============================================================================
# Stage 3: All-in-One Production Runtime (Python + Node.js + Supervisor)
# ==============================================================================
FROM python:3.12-slim-bookworm AS runner
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NODE_ENV=production

# Install Supervisor, Curl (for healthcheck), and CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Node.js binary and npm from official Node 22 Debian Bookworm image
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/include/node /usr/local/include/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Install Backend Python Dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Install WhatsApp Service Production Dependencies
COPY whatsapp-service/package*.json ./whatsapp-service/
RUN cd ./whatsapp-service && npm ci --omit=dev

# Copy Built Artifacts & Application Source Code
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY --from=whatsapp-builder /app/whatsapp-service/dist ./whatsapp-service/dist
COPY backend/ ./backend/

# Setup Configuration & Entrypoint
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /app/data/whatsapp_auth

# Port 8000 serves both the FastAPI API and the React frontend SPA
EXPOSE 8000

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

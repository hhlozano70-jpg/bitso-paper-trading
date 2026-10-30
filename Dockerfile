# ============================================================================
# Etapa 1: Compilar el Frontend en React + Vite
# ============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ============================================================================
# Etapa 2: Servidor Unificado Python (FastAPI + Bot 24/7 + React SPA)
# Compatible con Hugging Face Spaces (puerto 7860), Render, Koyeb y Railway
# ============================================================================
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTO_START_BOT=true \
    PORT=7860

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Permisos de escritura para portfolio_state.json en contenedores no-root (ej. Hugging Face Spaces)
RUN chmod -R 777 /app/backend

EXPOSE 7860 8000

CMD ["sh", "-c", "cd /app/backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]

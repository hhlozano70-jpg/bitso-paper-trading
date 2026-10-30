---
title: Bitso Paper Trader 24/7
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Bitso Paper Trading & AI Multi-Asset Scanner (24/7 Cloud Ready)

Plataforma completa de **Paper Trading (Trading Simulado)** conectada en tiempo real a la **API Pública v3 de Bitso**, con escáner cuantitativo de **24 monedas y activos** (Cripto MXN, Oro Físico PAXG, RWA ONDO, Divisas USD/EUR, Layer-1/DeFi y Arbitraje Triangular) y un **Bot de Trading Automático 24/7**.

---

## ☁️ Cómo Subirlo a un Servidor Gratis 24/7

El proyecto ya está empaquetado en un **Servidor Unificado** ([`Dockerfile`](./Dockerfile), [`render.yaml`](./render.yaml) y [`railway.json`](./railway.json)) donde **FastAPI sirve tanto el Backend + Bot 24/7 como el Frontend de React compilado** en un solo puerto, con el Bot activado automáticamente al iniciar (`AUTO_START_BOT=true`) y un endpoint de vigilancia [`/api/health`](./backend/main.py).

### Opción A: Hugging Face Spaces (Recomendado — 100% Gratis, 16 GB RAM, Sin Tarjeta)
1. Crea una cuenta gratuita en [huggingface.co](https://huggingface.co) y ve a **Spaces -> Create new Space**.
2. Ponle un nombre (ej. `bitso-paper-trader`), elige **Docker** como SDK (plantilla *Blank*) y visibilidad **Public**.
3. Sube los archivos de esta carpeta `bitso-paper-trading` (puedes arrastrarlos desde el navegador en *Files -> Add file -> Upload files* o hacer `git push`).
4. Hugging Face construirá automáticamente el [`Dockerfile`](./Dockerfile) y tu bot quedará trabajando en vivo en tu URL pública.
5. Para mantenerlo despierto 24/7 sin pausas por inactividad, registra la URL `https://tu-espacio.hf.space/api/health` en [cron-job.org](https://cron-job.org) o [UptimeRobot](https://uptimerobot.com) cada 5 minutos (gratis).

### Opción B: Render.com (Plan Free con `render.yaml`)
1. Sube esta carpeta a un repositorio en tu cuenta de **GitHub**.
2. Entra a [render.com](https://render.com) -> **New + -> Blueprint** (o **Web Service**) y conecta tu repositorio.
3. Render detectará automáticamente el archivo [`render.yaml`](./render.yaml) y el [`Dockerfile`](./Dockerfile) en el plan **Free**.
4. **Truco para 24/7 sin suspensión en Render Free:**
   - En las variables de entorno de Render agrega `RENDER_EXTERNAL_URL` con la URL que te asigne Render (`https://tu-app.onrender.com`), lo cual activa el bucle [`keep_alive_loop`](./backend/main.py) integrado en `backend/main.py`.
   - Adicionalmente, añade `https://tu-app.onrender.com/api/health` en [cron-job.org](https://cron-job.org) (cada 5 minutos) para garantizar actividad externa 24/7.

---

## 💻 Ejecución Local

Ejecuta [`start.ps1`](./start.ps1) o inicia manualmente:

```powershell
# Backend (FastAPI en puerto 8000)
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Frontend (React + Vite en puerto 5173)
cd frontend
npm run dev
```

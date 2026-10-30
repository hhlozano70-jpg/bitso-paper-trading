# Script para iniciar el Backend (FastAPI) y el Frontend (React + Vite)
Write-Host "Iniciando Bitso Paper Trading Backend (puerto 8000) y Frontend (puerto 5173)..." -ForegroundColor Green

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\backend'; uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev"

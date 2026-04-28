#!/bin/bash

# Iniciar Celery Worker en segundo plano (con el & al final)
echo "Iniciando Celery Worker..."
celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2 &

# Iniciar FastAPI en primer plano (esto mantendrá el puerto abierto para Render)
echo "Iniciando FastAPI..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT

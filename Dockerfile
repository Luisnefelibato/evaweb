FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Asegúrate de que se cumplan las dependencias para edge-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Exponer el puerto en el que correrá la aplicación
EXPOSE $PORT

# Ejecutar la aplicación con gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT app:app

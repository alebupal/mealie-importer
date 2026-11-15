# Imagen oficial de Docker Hub servida desde el espejo de AWS: no gasta el límite de descargas de Docker Hub
FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8094 \
    BIND_ADDRESS=0.0.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -sL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY alimentos_sinonimos.json ./alimentos_sinonimos.json
COPY README.md ./README.md

VOLUME ["/app/data"]
EXPOSE 8094

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8094'), timeout=4)" || exit 1

CMD ["sh", "-c", "exec python3 -m uvicorn app.main:app --host ${BIND_ADDRESS:-0.0.0.0} --port ${PORT:-8094} --no-access-log"]

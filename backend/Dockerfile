FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libmagic1 \
      fonts-noto-core fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd -r app && useradd -r -g app -d /app app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN pip install --no-deps -e . && mkdir -p /data/files && chown -R app:app /app /data
USER app
EXPOSE 8000
ENV WEB_CONCURRENCY=2
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health/live',timeout=5).status==200 else 1)"
# Worker processes: WEB_CONCURRENCY (about one per CPU core). The worker/beat containers override CMD.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --workers ${WEB_CONCURRENCY}"]

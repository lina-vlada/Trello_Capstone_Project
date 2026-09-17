FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN groupadd -r --gid 1001 app && useradd -r --uid 1001 --gid app --no-create-home -s /sbin/nologin appuser
COPY --from=builder /install /usr/local
WORKDIR /app/src
COPY --chown=appuser:app ./src .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=2 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz'); urllib.request.urlopen('http://127.0.0.1:8000/readyz')" || exit 1
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
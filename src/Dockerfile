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
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
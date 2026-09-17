FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.txt

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN groupadd -r --gid 1001 app && useradd -r --uid 1001 --gid app --no-create-home -s /sbin/nologin appuser
COPY --from=builder /install /usr/local
WORKDIR /app/src
COPY --chown=appuser:app ./src .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=2 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz'); urllib.request.urlopen('http://127.0.0.1:8000/readyz')" || exit 1
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
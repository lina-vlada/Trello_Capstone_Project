FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN groupadd -r --gid 1001 app && useradd -r --uid 1001 --gid app --no-create-home -s /sbin/nologin appuser
COPY --from=builder /install /usr/local
WORKDIR /app/src
COPY --chown=appuser:app ./src .
USER appuser
EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
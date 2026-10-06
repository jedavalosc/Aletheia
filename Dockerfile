FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    SITE_DIR=/app/build/site PORT=8080 TZ=America/Sao_Paulo

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY docs ./docs
COPY evals ./evals

RUN useradd --create-home --uid 10001 aletheia && mkdir -p /app/build && chown -R aletheia /app/build
USER aletheia

EXPOSE 8080
CMD ["./scripts/start.sh"]

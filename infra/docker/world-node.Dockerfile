FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs openssl \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["python3", "/workspace/silicium"]
CMD ["node", "start", "--help"]

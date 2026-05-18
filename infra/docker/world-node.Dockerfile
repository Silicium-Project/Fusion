FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm openssl \
    && rm -rf /var/lib/apt/lists/*

COPY infra/docker/world-node-entrypoint.sh /usr/local/bin/world-node-entrypoint.sh
RUN chmod +x /usr/local/bin/world-node-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/world-node-entrypoint.sh"]
CMD ["node", "start", "--help"]

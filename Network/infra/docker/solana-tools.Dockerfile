FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/share/solana/install/active_release/bin:$PATH

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSfL https://release.anza.xyz/stable/install | sh

ENTRYPOINT ["/bin/sh", "-lc"]
CMD ["sleep infinity"]

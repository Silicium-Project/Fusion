FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       build-essential \
       pkg-config \
       libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash solana \
    && mkdir -p /usr/local/solana \
    && chown solana:solana /usr/local/solana

COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint

USER solana
WORKDIR /home/solana

RUN curl -sSfL https://release.solana.com/stable/install | sh -s stable --data-dir /usr/local/solana

ENV PATH="/home/solana/.local/share/solana/install/active_release/bin:${PATH}"

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]

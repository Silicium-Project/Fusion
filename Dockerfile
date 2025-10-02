FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       git \
       build-essential \
       pkg-config \
       libssl-dev \
       libudev-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash solana \
    && mkdir -p /usr/local/solana \
    && chown solana:solana /usr/local/solana

COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint

USER solana
WORKDIR /home/solana

RUN curl -sSfL https://release.solana.com/stable/install -o /tmp/solana-install.sh \
    && bash /tmp/solana-install.sh stable --data-dir /usr/local/solana \
    && rm /tmp/solana-install.sh \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup component add rustfmt clippy \
    && rustup target add wasm32-unknown-unknown \
    && cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked \
    && /home/solana/.local/share/solana/install/active_release/bin/solana --version

USER root

RUN ln -sf /home/solana/.local/share/solana/install/active_release/bin/solana /usr/local/bin/solana

USER solana

ENV PATH="/home/solana/.local/share/solana/install/active_release/bin:/home/solana/.cargo/bin:${PATH}"

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]

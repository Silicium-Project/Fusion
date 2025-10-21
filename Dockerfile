FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    RUSTUP_HOME=/home/solana/.rustup \
    CARGO_HOME=/home/solana/.cargo

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        build-essential \
        pkg-config \
        libssl-dev \
        libudev-dev \
        libusb-1.0-0-dev \
        libhidapi-dev \
        python3 \
        python3-pip \
        perl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash solana \
    && mkdir -p /usr/local/solana \
    && chown -R solana:solana /home/solana /usr/local/solana

COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint

USER solana
WORKDIR /home/solana
SHELL ["/bin/bash", "-lc"]

ENV OPENSSL_NO_VENDOR=1

RUN curl -sSfL https://release.solana.com/stable/install | bash -s stable --data-dir /usr/local/solana \
    && curl https://sh.rustup.rs -sSf | bash -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup component add rustfmt clippy \
    && rustup target add wasm32-unknown-unknown \
    && OPENSSL_NO_VENDOR=1 cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked

ENV PATH="/home/solana/.local/share/solana/install/active_release/bin:/home/solana/.cargo/bin:${PATH}"

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]

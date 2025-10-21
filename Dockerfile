FROM alpine:3.19

ENV RUSTUP_HOME=/home/solana/.rustup \
    CARGO_HOME=/home/solana/.cargo

RUN apk add --no-cache \
        bash \
        ca-certificates \
        curl \
        git \
        build-base \
        pkgconf \
        openssl-dev \
        eudev-dev \
        python3 \
        py3-pip \
    && update-ca-certificates

RUN addgroup -S solana \
    && adduser -S -G solana -h /home/solana solana \
    && mkdir -p /usr/local/solana \
    && chown -R solana:solana /home/solana /usr/local/solana

COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint

USER solana
WORKDIR /home/solana
SHELL ["/bin/bash", "-lc"]

RUN curl -sSfL https://release.solana.com/stable/install | bash -s stable --data-dir /usr/local/solana \
    && curl https://sh.rustup.rs -sSf | bash -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup component add rustfmt clippy \
    && rustup target add wasm32-unknown-unknown \
    && cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked

ENV PATH="/home/solana/.local/share/solana/install/active_release/bin:/home/solana/.cargo/bin:${PATH}"

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]

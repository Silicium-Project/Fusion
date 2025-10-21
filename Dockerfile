FROM alpine:3.19 AS builder

ENV RUSTUP_HOME=/home/solana/.rustup \
    CARGO_HOME=/home/solana/.cargo

RUN apk add --no-cache \
        bash \
        ca-certificates \
        curl \
        git \
        gcompat \
        build-base \
        linux-headers \
        pkgconf \
        openssl-dev \
        openssl-libs-static \
        eudev-dev \
        zlib-dev \
        zlib-static \
        python3 \
        py3-pip \
    && update-ca-certificates

RUN addgroup -S solana \
    && adduser -S -G solana -h /home/solana solana \
    && mkdir -p /usr/local/solana \
    && chown -R solana:solana /home/solana /usr/local/solana

USER solana
WORKDIR /home/solana
SHELL ["/bin/bash", "-lc"]

RUN curl -sSfL https://release.solana.com/stable/install | bash -s stable --data-dir /usr/local/solana \
    && curl https://sh.rustup.rs -sSf | bash -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup component add rustfmt clippy \
    && rustup target add wasm32-unknown-unknown \
    && OPENSSL_NO_VENDOR=1 cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked

FROM alpine:3.19

RUN apk add --no-cache \
        bash \
        ca-certificates \
        curl \
        git \
        gcompat \
        openssl \
        eudev-libs \
        zlib \
    && update-ca-certificates

RUN addgroup -S solana \
    && adduser -S -G solana -h /home/solana solana \
    && mkdir -p /usr/local/solana \
    && chown -R solana:solana /home/solana /usr/local/solana

COPY docker/solana-entrypoint.sh /usr/local/bin/solana-entrypoint
RUN chmod +x /usr/local/bin/solana-entrypoint

COPY --from=builder --chown=solana:solana /usr/local/solana /usr/local/solana
COPY --from=builder --chown=solana:solana /home/solana/.cargo/bin /home/solana/.cargo/bin

ENV PATH="/usr/local/solana/active_release/bin:/home/solana/.cargo/bin:${PATH}"

USER solana
WORKDIR /home/solana
SHELL ["/bin/bash", "-lc"]

ENTRYPOINT ["/usr/local/bin/solana-entrypoint"]
CMD ["--help"]

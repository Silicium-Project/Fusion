# syntax=docker/dockerfile:1.7

FROM rust:1.94-bookworm AS builder

WORKDIR /work
COPY node-core/Cargo.toml ./node-core/Cargo.toml
COPY node-core/src ./node-core/src
COPY p2p-node/Cargo.toml p2p-node/Cargo.lock ./p2p-node/
COPY p2p-node/src ./p2p-node/src

RUN cargo fetch --locked --manifest-path /work/p2p-node/Cargo.toml

WORKDIR /work/p2p-node
RUN cargo build --release --locked

FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium
WORKDIR /app

COPY --from=builder /work/p2p-node/target/release/p2p_node /usr/local/bin/p2p_node

EXPOSE 4001/tcp
EXPOSE 4001/udp
EXPOSE 9092/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9092/health || exit 1

USER silicium
ENTRYPOINT ["/usr/local/bin/p2p_node"]

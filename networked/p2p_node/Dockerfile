# syntax=docker/dockerfile:1.7

FROM rust:1.89-bookworm AS builder

WORKDIR /work
COPY silicium_node_core/Cargo.toml ./silicium_node_core/Cargo.toml
COPY p2p_node/Cargo.toml p2p_node/Cargo.lock ./p2p_node/

RUN cargo fetch --locked --manifest-path /work/p2p_node/Cargo.toml

COPY silicium_node_core ./silicium_node_core
COPY p2p_node ./p2p_node

WORKDIR /work/p2p_node
RUN cargo build --release --locked

FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium
WORKDIR /app

COPY --from=builder /work/p2p_node/target/release/p2p_node /usr/local/bin/p2p_node

EXPOSE 4001/tcp
EXPOSE 4001/udp
EXPOSE 9092/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9092/health || exit 1

USER silicium
ENTRYPOINT ["/usr/local/bin/p2p_node"]

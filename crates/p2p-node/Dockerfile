# syntax=docker/dockerfile:1.7

FROM rust:1.94-bookworm AS builder

# Build context = Network/ (workspace root). See Dockerfile.dockerignore.
WORKDIR /work
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates

RUN cargo fetch --locked
RUN cargo build --release --locked -p p2p_node

FROM debian:bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium
WORKDIR /app

COPY --from=builder /work/target/release/p2p_node /usr/local/bin/p2p_node

EXPOSE 4001/tcp
EXPOSE 4001/udp
EXPOSE 9092/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9092/health || exit 1

USER silicium
ENTRYPOINT ["/usr/local/bin/p2p_node"]

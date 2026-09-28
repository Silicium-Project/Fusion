FROM rust:1.94-bookworm AS builder

WORKDIR /work

RUN apt-get update \
    && apt-get install -y --no-install-recommends pkg-config libssl-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Build context = Network/ (workspace root). See Dockerfile.dockerignore.
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates

RUN cargo build --release --locked -p reputation_bridge

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium

WORKDIR /app

COPY --from=builder /work/target/release/reputation_bridge /usr/local/bin/reputation_bridge

EXPOSE 9091/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9091/health || exit 1

USER silicium
ENTRYPOINT ["/usr/local/bin/reputation_bridge"]

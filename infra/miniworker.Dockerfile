# Small, unprivileged dev worker image. Build context is the Network workspace.
FROM rust:1.94-bookworm AS builder

WORKDIR /work
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
ARG CARGO_BUILD_JOBS=2
RUN cargo fetch --locked \
    && CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS} cargo build --release --locked -p p2p_node -p compute_daemon -p silicium-raytracer

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium \
    && install -d -o 65532 -g 65532 /data /data/work

COPY --from=builder /work/target/release/p2p_node /usr/local/bin/p2p_node
COPY --from=builder /work/target/release/compute_daemon /usr/local/bin/compute_daemon
COPY --from=builder /work/target/release/silicium-raytracer /usr/local/bin/silicium-raytracer
COPY --from=builder /work/target/release/solana_worker_wallet /usr/local/bin/solana-worker-wallet
COPY infra/miniworker-entrypoint.sh /usr/local/bin/miniworker-entrypoint
RUN chmod 0555 /usr/local/bin/miniworker-entrypoint

ENV SILICIUM_DATA_DIR=/data \
    SILICIUM_COMPUTE_ROOT=/data/work \
    SILICIUM_RAYTRACER_BIN=/usr/local/bin/silicium-raytracer \
    SILICIUM_API_BIND=127.0.0.1 \
    SILICIUM_COMPUTE_BIND=127.0.0.1:9090

VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9092/health && curl -fsS http://127.0.0.1:9090/health || exit 1

USER silicium
ENTRYPOINT ["/usr/local/bin/miniworker-entrypoint"]

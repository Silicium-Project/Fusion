FROM rust:1.94-alpine AS builder

WORKDIR /work
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN apk add --no-cache musl-dev
ARG CARGO_BUILD_JOBS=2
RUN CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS} cargo build \
    --release --locked -p p2p_node --target-dir /work/target/node-alpine

FROM scratch AS artifact
COPY --from=builder /work/target/node-alpine/release/p2p_node /p2p_node

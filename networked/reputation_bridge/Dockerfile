FROM rust:1.77-slim AS builder

WORKDIR /usr/src/app

# Install OpenSSL development headers (reqwest/rustls might need some basic certs or gcc for build)
RUN apt-get update && apt-get install -y pkg-config libssl-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy the whole Network repository so that Cargo can resolve paths if there's a workspace
# But we will focus on reputation_bridge. We assume the context is Network.
COPY . .

# Build the reputation bridge in release mode
WORKDIR /usr/src/app/networked/reputation_bridge
RUN cargo build --release

FROM debian:bookworm-slim

# Install CA certificates to allow HTTPS requests (reqwest)
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/src/app/networked/reputation_bridge/target/release/reputation_bridge /app/reputation_bridge

# Reputation Bridge listens on 9091 by default
EXPOSE 9091

CMD ["./reputation_bridge"]

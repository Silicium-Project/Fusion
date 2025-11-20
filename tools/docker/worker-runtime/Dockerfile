FROM luis1454/worker-builder:1.0 AS builder

WORKDIR /workspace
COPY . .

RUN make -C tools/worker worker

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libjansson4 \
        libstdc++6 \
        libgcc-s1 \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /workspace/tools/worker/worker /usr/local/bin/worker

ENTRYPOINT ["/usr/local/bin/worker"]

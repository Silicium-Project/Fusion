# Node dependencies and runtime are assembled on GitHub from qualified binaries.
FROM node:22.23.4-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node-deps
WORKDIR /opt/worker-solana
COPY .artifacts/build/network/runtime-src/worker-solana/package.json .artifacts/build/network/runtime-src/worker-solana/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY .artifacts/build/network/runtime-src/solana-worker-settlement.mjs ./solana-worker-settlement.mjs
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 65532 --create-home --shell /usr/sbin/nologin silicium \
    && install -d -o 65532 -g 65532 /data /data/work
COPY --from=node-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=node-deps /opt/worker-solana /opt/worker-solana
COPY --chmod=0555 .artifacts/build/network/ /usr/local/bin/
COPY .artifacts/build/network/runtime-src/miniworker-entrypoint.sh /usr/local/bin/miniworker-entrypoint
RUN chmod 0555 /usr/local/bin/miniworker-entrypoint
ENV SILICIUM_DATA_DIR=/data SILICIUM_COMPUTE_ROOT=/data/work SILICIUM_RAYTRACER_BIN=/usr/local/bin/silicium-raytracer
USER 65532:65532
EXPOSE 9092 9090
ENTRYPOINT ["/usr/local/bin/miniworker-entrypoint"]

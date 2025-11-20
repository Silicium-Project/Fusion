FROM luis1454/worker-builder:1.0 AS builder

WORKDIR /workspace
COPY . .
RUN make -C tools/worker worker

FROM luis1454/worker-runtime:1.0
COPY --from=builder /workspace/tools/worker/worker /usr/local/bin/worker
ENTRYPOINT ["/usr/local/bin/worker"]

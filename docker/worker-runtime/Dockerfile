FROM luis1454/worker:builder AS builder

WORKDIR /workspace
COPY . .
RUN make -C worker worker

FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=builder /workspace/worker/worker /usr/local/bin/worker
COPY --from=builder /usr/lib/x86_64-linux-gnu/libjansson.so.* /usr/lib/x86_64-linux-gnu/

ENTRYPOINT ["/usr/local/bin/worker"]

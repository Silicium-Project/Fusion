FROM luis1454/worker:builder AS builder

WORKDIR /workspace
COPY . .
RUN make -C executor && make -C worker worker

FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=builder /workspace/worker/worker /usr/local/bin/worker
COPY --from=builder /workspace/executor/libfragment_emulator.so /usr/local/executor/libfragment_emulator.so
COPY --from=builder /workspace/executor/libfragment_executor.so /usr/local/executor/libfragment_executor.so
COPY --from=builder /usr/lib/x86_64-linux-gnu/libjansson.so.* /usr/lib/x86_64-linux-gnu/
ENV LD_LIBRARY_PATH=/usr/local/executor:$LD_LIBRARY_PATH

ENTRYPOINT ["/usr/local/bin/worker"]

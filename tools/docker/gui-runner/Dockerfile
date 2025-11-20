FROM luis1454/worker-builder:1.0 AS builder

WORKDIR /workspace
COPY . .
RUN make -C tools/fragment/executor

FROM luis1454/gui-runner:1.0 AS runtime
COPY --from=builder /workspace/tools/fragment/executor/fragment_executor /usr/local/bin/fragment_executor
COPY tools/docker/gui-runner/entrypoint.sh /opt/gui-runner/entrypoint.sh
RUN chmod +x /opt/gui-runner/entrypoint.sh

EXPOSE 5900

ENTRYPOINT ["/opt/gui-runner/entrypoint.sh"]

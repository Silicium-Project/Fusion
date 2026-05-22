FROM debian:bookworm-slim AS runtime-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        libavcodec59 \
        libavformat59 \
        libavutil57 \
        libswscale6 \
        libcsfml-graphics2.5 \
        libcsfml-window2.5 \
        libcsfml-system2.5 \
        libjansson4 \
        libgl1-mesa-glx \
        libglu1-mesa \
        libxrender1 \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

FROM luis1454/worker:builder AS builder

WORKDIR /workspace
COPY . .
RUN make -C executor

FROM runtime-base AS runtime
ENV DISPLAY=:99 \
    VNC_DISPLAY=99 \
    VNC_PORT=5900 \
    VNC_SCREEN=1280x720x24
COPY --from=builder /workspace/executor/fragment_executor /usr/local/bin/fragment_executor
COPY docker/gui-runner/entrypoint.sh /opt/gui-runner/entrypoint.sh
RUN chmod +x /opt/gui-runner/entrypoint.sh

EXPOSE 5900

ENTRYPOINT ["/opt/gui-runner/entrypoint.sh"]

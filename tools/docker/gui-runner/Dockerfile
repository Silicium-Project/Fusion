ARG DEBIAN_SUITE=bookworm
ARG APT_MIRROR=http://deb.debian.org/debian
ARG SECURITY_MIRROR=http://security.debian.org/debian-security

FROM debian:${DEBIAN_SUITE}-slim AS base
ARG DEBIAN_SUITE
ARG APT_MIRROR
ARG SECURITY_MIRROR

ENV DEBIAN_FRONTEND=noninteractive

# Runtime X/VNC + CSFML libs only (no devel)
RUN printf "deb ${APT_MIRROR} ${DEBIAN_SUITE} main\n" > /etc/apt/sources.list \
 && printf "deb ${APT_MIRROR} ${DEBIAN_SUITE}-updates main\n" >> /etc/apt/sources.list \
 && printf "deb ${SECURITY_MIRROR} ${DEBIAN_SUITE}-security main\n" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        libcsfml-graphics2.5 \
        libcsfml-window2.5 \
        libcsfml-system2.5 \
        libjansson4 \
        libgl1-mesa-glx \
        libglu1-mesa \
        libxrender1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM debian:${DEBIAN_SUITE}-slim AS builder
ARG DEBIAN_SUITE
ARG APT_MIRROR
ARG SECURITY_MIRROR

ENV DEBIAN_FRONTEND=noninteractive

RUN printf "deb ${APT_MIRROR} ${DEBIAN_SUITE} main\n" > /etc/apt/sources.list \
 && printf "deb ${APT_MIRROR} ${DEBIAN_SUITE}-updates main\n" >> /etc/apt/sources.list \
 && printf "deb ${SECURITY_MIRROR} ${DEBIAN_SUITE}-security main\n" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        pkg-config \
        libcsfml-dev \
        libjansson-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . .
RUN make -C tools/fragment/executor

FROM base AS runtime
COPY --from=builder /workspace/tools/fragment/executor/fragment_executor /usr/local/bin/fragment_executor
COPY tools/docker/gui-runner/entrypoint.sh /opt/gui-runner/entrypoint.sh
RUN chmod +x /opt/gui-runner/entrypoint.sh

EXPOSE 5900

ENTRYPOINT ["/opt/gui-runner/entrypoint.sh"]

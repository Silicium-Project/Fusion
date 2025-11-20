ARG DEBIAN_SUITE=bookworm
ARG APT_MIRROR=http://deb.debian.org/debian
ARG SECURITY_MIRROR=http://security.debian.org/debian-security

FROM debian:${DEBIAN_SUITE}-slim AS builder
ARG DEBIAN_SUITE
ARG APT_MIRROR
ARG SECURITY_MIRROR

ENV DEBIAN_FRONTEND=noninteractive

# Pin mirrors to allow custom caches/proxies.
RUN printf "deb ${APT_MIRROR} ${DEBIAN_SUITE} main\n" > /etc/apt/sources.list \
 && printf "deb ${APT_MIRROR} ${DEBIAN_SUITE}-updates main\n" >> /etc/apt/sources.list \
 && printf "deb ${SECURITY_MIRROR} ${DEBIAN_SUITE}-security main\n" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        pkg-config \
        libjansson-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . .

# Build the native runner and the worker binaries.
RUN make -C tools/fragment/executor \
 && make -C tools/worker worker dynamo_fragment_runner


FROM debian:${DEBIAN_SUITE}-slim AS runtime
ARG DEBIAN_SUITE
ARG APT_MIRROR
ARG SECURITY_MIRROR

ENV DEBIAN_FRONTEND=noninteractive

RUN printf "deb ${APT_MIRROR} ${DEBIAN_SUITE} main\n" > /etc/apt/sources.list \
 && printf "deb ${APT_MIRROR} ${DEBIAN_SUITE}-updates main\n" >> /etc/apt/sources.list \
 && printf "deb ${SECURITY_MIRROR} ${DEBIAN_SUITE}-security main\n" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        libjansson4 \
        ca-certificates \
        libstdc++6 \
        libgcc-s1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /workspace/tools/fragment/executor/fragment_executor /usr/local/bin/fragment_executor
COPY --from=builder /workspace/tools/worker/worker /usr/local/bin/worker
COPY --from=builder /workspace/tools/worker/dynamo_fragment_runner /usr/local/bin/dynamo_fragment_runner

ENTRYPOINT ["/usr/local/bin/worker"]

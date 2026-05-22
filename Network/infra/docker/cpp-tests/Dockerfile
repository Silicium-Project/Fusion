FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libjansson-dev \
        libgtest-dev \
        lcov \
        ccache \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN cmake -S /usr/src/googletest -B /tmp/gtest \
    && cmake --build /tmp/gtest \
    && cmake --install /tmp/gtest \
    && rm -rf /tmp/gtest

WORKDIR /workspace

ENV CCACHE_DIR=/ccache

CMD ["/bin/bash"]

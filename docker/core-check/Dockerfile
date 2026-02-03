FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3 \
        python3-venv \
        python3-pip \
        libjansson-dev \
        binutils \
        pkg-config \
        cmake \
        libgtest-dev \
        ca-certificates \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install -r /tmp/requirements-dev.txt \
    && rm /tmp/requirements-dev.txt

ENV PATH=/opt/venv/bin:$PATH

RUN cmake -S /usr/src/googletest -B /tmp/gtest \
    && cmake --build /tmp/gtest \
    && cmake --install /tmp/gtest \
    && rm -rf /tmp/gtest

CMD ["/bin/bash"]

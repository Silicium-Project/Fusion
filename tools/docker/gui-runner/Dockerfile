FROM registry.fedoraproject.org/fedora:42 AS builder

RUN dnf -y install make gcc gcc-c++ git \
    && dnf clean all

WORKDIR /workspace
COPY . .
RUN make -C tools/experiments/fragment-executor

FROM registry.fedoraproject.org/fedora:42

RUN dnf -y install \
        xorg-x11-server-Xvfb \
        x11vnc \
        CSFML-devel \
        mesa-dri-drivers \
        libXrender \
        which \
        && dnf clean all

COPY --from=builder /workspace/tools/experiments/fragment-executor/fragment_executor /usr/local/bin/fragment_executor
COPY tools/docker/gui-runner/entrypoint.sh /opt/gui-runner/entrypoint.sh
RUN chmod +x /opt/gui-runner/entrypoint.sh

EXPOSE 5900

ENTRYPOINT ["/opt/gui-runner/entrypoint.sh"]

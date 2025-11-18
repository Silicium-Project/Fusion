FROM fedora:40

ENV LANG=C.UTF-8

RUN dnf -y update && \
    dnf -y install \
        xorg-x11-server-Xvfb \
        x11vnc \
        csfml-devel \
        mesa-dri-drivers \
        libXrender \
        glibc-langpack-en && \
    dnf clean all

COPY entrypoint.sh /opt/gui-runner/entrypoint.sh
RUN chmod +x /opt/gui-runner/entrypoint.sh

EXPOSE 5900

ENTRYPOINT ["/opt/gui-runner/entrypoint.sh"]

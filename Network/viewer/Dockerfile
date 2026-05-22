FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    qtbase5-dev \
    qtbase5-dev-tools \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Copier uniquement le viewer pour construire l'UI.
COPY viewer /src/viewer

# Construire dans un répertoire neutre pour éviter tout cache local
RUN cmake -S /src/viewer -B /tmp/build && cmake --build /tmp/build

# Binaire résultat : /tmp/build/fragment_viewer
CMD ["/bin/bash"]

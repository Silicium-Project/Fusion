FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential make libjansson-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY executor /src/executor
COPY worker /src/worker

RUN cd worker \
 && make clean \
 && make dynamo_fragment_runner

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    DYNAMORIO_VERSION=10.0.0 \
    DYNAMORIO_HOME=/opt/dynamorio \
    DYNAMO_RUNNER_HOME=/opt/dynamo-runner
ARG DYNAMORIO_SHA256=""

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates wget tar libstdc++6 libgcc-s1 libjansson4 \
 && wget -q https://github.com/DynamoRIO/dynamorio/releases/download/release_${DYNAMORIO_VERSION}/DynamoRIO-Linux-${DYNAMORIO_VERSION}.tar.gz -O /tmp/dynamorio.tar.gz \
 && test -n "$DYNAMORIO_SHA256" \
 && echo "${DYNAMORIO_SHA256}  /tmp/dynamorio.tar.gz" | sha256sum -c - \
 && mkdir -p /opt \
 && tar -C /opt -xf /tmp/dynamorio.tar.gz \
 && mv /opt/DynamoRIO-Linux-${DYNAMORIO_VERSION} ${DYNAMORIO_HOME} \
 && rm -rf /tmp/dynamorio.tar.gz /var/lib/apt/lists/*

RUN mkdir -p ${DYNAMO_RUNNER_HOME}

COPY --from=builder /src/worker/dynamo_fragment_runner ${DYNAMO_RUNNER_HOME}/dynamo_fragment_runner

ENV PATH="${DYNAMORIO_HOME}/bin64:${PATH}"

ENTRYPOINT ["/opt/dynamorio/bin64/drrun"]
CMD ["--help"]

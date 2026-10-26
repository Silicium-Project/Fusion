# Uses the exact statically linked binary already produced by qualification.
FROM alpine:3.22@sha256:2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -g 101 -S silicium \
    && adduser -u 100 -S -G silicium -h /app silicium
WORKDIR /app
COPY --chmod=0555 .artifacts/build/api/silicium-api ./silicium-api
COPY contracts/http/api.openapi.yaml ./docs/openapi.yaml
USER 100:101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
CMD ["./silicium-api"]

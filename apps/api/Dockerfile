# Build context: Fusion root. Release publication uses api-runtime.Dockerfile.
FROM golang:1.27.3-bookworm AS build
WORKDIR /src
COPY apps/api/go.mod apps/api/go.sum ./
RUN go mod download
COPY apps/api/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/silicium-api ./cmd
FROM alpine:3.22@sha256:2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f AS runtime
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -g 101 -S silicium \
    && adduser -u 100 -S -G silicium -h /app silicium
WORKDIR /app
COPY --from=build /out/silicium-api ./silicium-api
COPY contracts/http/api.openapi.yaml ./docs/openapi.yaml
USER 100:101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
CMD ["./silicium-api"]

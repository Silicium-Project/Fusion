FROM golang:1.22.4-alpine3.20 AS build
WORKDIR /src
RUN apk add --no-cache ca-certificates git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/silicium-api ./cmd

FROM alpine:3.20 AS runtime
WORKDIR /app
RUN apk add --no-cache ca-certificates tzdata python3 openssl \
    && addgroup -S silicium \
    && adduser -S -G silicium -h /app silicium
COPY --from=build --chown=silicium:silicium /out/silicium-api ./silicium-api
COPY --from=build --chown=silicium:silicium /src/docs ./docs
USER silicium
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
CMD ["./silicium-api"]

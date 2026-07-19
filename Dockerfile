FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache gcc musl-dev python3 py3-pip
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir aioice==0.10.2
ENV PATH="/opt/venv/bin:$PATH"

COPY go.mod ./
RUN go mod download

COPY . ./

RUN go build -o main ./cmd/main.go

FROM alpine:latest

WORKDIR /app

RUN apk add --no-cache openssl python3 libstdc++
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/main .

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8080

CMD ["./main"]

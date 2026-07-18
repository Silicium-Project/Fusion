FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache gcc musl-dev python3 py3-pip
RUN pip install --no-cache-dir aioice==0.10.2

COPY go.mod ./
RUN go mod download

COPY . ./

RUN go build -o main ./cmd/main.go

FROM alpine:latest

WORKDIR /app

COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]

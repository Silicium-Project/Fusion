# Silicium Backend

Go HTTP API used by Fusion for user, job, and network operations.

## About

This repository contains the backend server for the Silicium network. It is
deployed with the Fusion stack and exposes the current dashboard, job
orchestration, and network-related endpoints.

## Getting Started

To get started with the backend, refer to the documentation in the `/doc`
directory:

- [Installation and Setup](./doc/install.md): how to install Docker and launch the backend server and database locally.
- [Environment Variables](./doc/env-variables.md): required `.env` variables.
- [Accessing the Services](./doc/access.md): exposed ports and access paths.

## Current Surface

- HTTP API on `127.0.0.1:8080`
- Health endpoints: `GET /health` and `GET /healthz`
- Auth endpoints: `/register`, `/login`, `/refresh`, `/user`
- Job endpoints: `/jobs` and `/jobs/network/*`
- OpenAPI docs: `/docs/`

## Deployment

The backend is started by the Fusion deployment workflow and by the local
Docker Compose stack in `deploy/`.

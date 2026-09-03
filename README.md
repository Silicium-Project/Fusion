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

## Authentication fix — fix/auth_site

This branch only changes registration/login validation, their error responses,
and explicit password hashing. Routes, JWT format, token lifetimes, middleware,
database schema, deployment and job handling are unchanged.

- Registration normalizes email whitespace/case and reports conflicts with 409.
- Login accepts `identifier` (email or username); the legacy `email` field still works.
  Emails ignore case/outer whitespace. Usernames use their stored case, matching
  the existing unique constraint. Surrounding input whitespace is ignored.
  Email takes priority if it matches another account's username; ambiguous legacy
  emails are rejected. No account or username migration is introduced.
- Invalid credentials return 401; database failures return 503, not "wrong password".
  Auth errors are JSON `{ "message": "..." }`; SQL details stay server-side.
- `User.SetPassword` replaces the length-based hashing hook, including for password
  changes. A 60-byte plaintext password is now hashed correctly. Profile saves
  never hash an existing hash. Empty and over-72-byte passwords are rejected;
  the existing allowance for shorter passwords is preserved.
- No account migration or automatic password repair is performed. A legacy account
  containing plaintext from the old 60-byte bug needs an authorized password reset.

Run `go test ./...` and `go vet ./...`. To run the API outside Docker, provide
DATABASE_URL for an existing PostgreSQL database and JWT_SECRET_KEY in the process
environment, then `go run ./cmd`. The binary does not load a .env file itself.
Use HOST=127.0.0.1, PORT=8080 and CORS_ALLOWED_ORIGINS=http://localhost:3000 locally.
Do not change the production secret for testing or delete an existing database.

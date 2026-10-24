# Contributing to Silicium

Thank you for your interest in contributing to Silicium! This guide explains how
to set up your environment, propose changes, and get them merged.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
  - [Windows](#windows)
  - [Linux / macOS](#linux--macos)
- [Development Workflow](#development-workflow)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Running Tests](#running-tests)
- [Reporting Issues](#reporting-issues)
- [Code of Conduct](#code-of-conduct)

---

## Project Structure

Silicium is a **monorepo of submodules**. The `Fusion` repository is the
composition layer; it pins exact commits of each component so that every
build, rollback, and deployment is fully reproducible.

```
Fusion/                      ← you are here (composition root)
├── Network/                 ← P2P runtime & node core (Rust)   [submodule]
├── BackEnd/                 ← REST API & orchestrator (Go)      [submodule]
├── FrontEnd/                ← Public website (Nuxt)             [submodule]
├── apps/
│   └── silicium-node/       ← Desktop app (Tauri + Node.js)
├── deploy/                  ← VPS deployment scripts & Docker Compose
└── docs/                    ← Architecture & CI/CD documentation
```

Each component lives in its own repository. **Open a PR in the relevant
submodule repo**, not in Fusion, unless the change is about deployment,
CI/CD configuration, or documentation that belongs to the composition layer.

---

## Prerequisites

| Tool | Minimum version | Used by |
|---|---|---|
| Git | 2.40+ | All |
| Node.js | 20 LTS | FrontEnd, silicium-node |
| Rust (stable) | 1.78+ | Network, silicium-node (Tauri) |
| Go | 1.22+ | BackEnd |
| Docker & Compose v2 | Latest stable | Integration tests, deploy |
| Python | 3.11+ | Developer tooling and deploy scripts (not the runtime) |

> **Tauri prerequisites:** On Linux you additionally need WebKitGTK 4.1 and
> its development headers. See the
> [Tauri 2 prerequisites guide](https://tauri.app/start/prerequisites/)
> for the exact package list for your distribution.

---

## Local Setup

### Clone with submodules

Always clone with `--recurse-submodules` to initialize all components:

```bash
git clone --recurse-submodules https://github.com/Silicium-Project/Fusion.git
cd Fusion
```

If you already cloned without the flag, run:

```bash
git submodule update --init --recursive
```

---

### Windows

Run the installer script from the repository root (PowerShell, no admin required
unless you pass `-InstallSystemDeps`):

```powershell
.\install-silicium-windows.cmd -InstallSystemDeps
```

Start all services locally:

```powershell
.\start-silicium-local.cmd
```

Useful flags:

| Flag | Effect |
|---|---|
| `-Visible` | Opens a terminal window per service |
| `-DryRun` | Prints commands without executing them |
| `-SkipDatabase` | Skips the local SQLite setup |
| `-SkipBackend` | Skips the Go backend |

Logs are written to `.silicium\logs\local-start`.

---

### Linux / macOS

Install the WebKitGTK prerequisites for Tauri (Debian/Ubuntu example):

```bash
sudo apt install libwebkit2gtk-4.1-dev libssl-dev libayatana-appindicator3-dev \
  librsvg2-dev patchelf curl build-essential
```

Install language toolchains if not already present:

```bash
# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Go (replace version as needed)
wget https://go.dev/dl/go1.22.4.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.22.4.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin
```

Start each service manually in separate terminals:

```bash
# Network (Rust P2P node)
cd Network && cargo run

# BackEnd (Go API)
cd BackEnd && go run ./cmd/server

# FrontEnd (Nuxt dev server)
cd FrontEnd && npm ci && npm run dev

# Desktop app (Tauri)
cd apps/silicium-node && npm ci && npm run prepare:runtime:linux && npm run tauri:dev
```

The local services default to:

| Service | URL |
|---|---|
| FrontEnd | `http://localhost:3000` |
| BackEnd API | `http://localhost:8080` |

---

### Environment variables

Copy and edit the example environment files before starting:

```bash
cp deploy/env/backend.example.env .env.backend
cp deploy/env/frontend.example.env .env.frontend
```

Key variables used by the backend:

| Variable | Default (local) | Description |
|---|---|---|
| `DATABASE_DRIVER` | `sqlite` | Use `postgres` for a real DB |
| `DATABASE_URL` | — | Required when `DATABASE_DRIVER=postgres` |
| `SQLITE_PATH` | `.silicium/site/silicium.db` | SQLite file path |
| `JWT_SECRET_KEY` | auto-generated | Auth signing key |
| `SILICIUM_NODE_API_URL` | `http://127.0.0.1:46100` (local stack) | API of the orchestrator node (`p2p_node`) |
| `SILICIUM_NODE_CONTROL_TOKEN` | local value | Bearer token of that API |

> **Never commit real secrets.** The `.gitignore` already excludes `.env*`
> files at the root level.

---

## Development Workflow

1. **Fork** the relevant repository (Fusion, BackEnd, FrontEnd, or Network).
2. Create a **feature branch** from `dev`:
   ```bash
   git checkout -b feat/my-feature dev
   ```
3. Make your changes. Keep commits focused and atomic.
4. Push your branch and open a **Pull Request targeting `dev`**, not `main`.
5. Ensure all CI checks pass before requesting review.
6. A maintainer will review and merge once approved.

> **`main` is production-protected.** All contributions flow through `dev`
> and are promoted to `main` via a reviewed merge. Direct pushes to `main`
> are not allowed for external contributors.

---

## Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

Common types:

| Type | When to use |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or fixing tests |
| `chore` | Build process, CI, dependencies |
| `perf` | Performance improvement |

Examples:

```
feat(network): add peer reconnection backoff
fix(backend): return 404 when job not found
docs(deploy): clarify VPS Nginx setup steps
```

---

## Pull Request Process

- Fill in the [PR template](.github/pull_request_template.md) completely.
- Link the issue your PR addresses with `Refs https://github.com/Silicium-Project/REPO/issues/<number>`.
- Keep PRs **small and focused** — one logical change per PR.
- Add or update tests for every changed behavior.
- Update documentation if your change affects the public API or user-facing
  behavior.
- At least **one maintainer approval** is required before merging.

---

## Running Tests

### Unit & integration tests (per component)

```bash
# Network (Rust)
cd Network && cargo test

# BackEnd (Go)
cd BackEnd && go test ./...

# FrontEnd (Nuxt)
cd FrontEnd && npm run test
```

### Network end-to-end test

Starts an orchestrator and workers (release binaries) on loopback and runs a
raytracer job with one then two workers, and a sha256 job (Linux/WSL, no
Docker needed):

```bash
cd Network && make e2e
```

### CI smoke test (local)

The `ci-fast.yml` workflow runs on every PR. You can reproduce it locally with
[`act`](https://github.com/nektos/act):

```bash
act pull_request --job fast-check
```

---

## Reporting Issues

- **Bugs:** Use the [Bug Report](.github/ISSUE_TEMPLATE/01-bug.yml) template.
- **Feature requests:** Use the [Feature Request](.github/ISSUE_TEMPLATE/02-feature.yml) template.
- **Security vulnerabilities:** **Do not open a public issue.** Please report
  security issues by emailing the maintainers directly (see the repository
  contact information). We aim to respond within 72 hours.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you agree to uphold this standard. Please report unacceptable
behavior to the maintainers.


## Issue management and repository metadata

Use the shared [Project](https://github.com/orgs/Silicium-Project/projects/12) and
[issue workflow](docs/development/issue-workflow.md) for roadmap, backlog,
readiness, ownership, review and acceptance. Link PRs with `Refs` and the full
issue URL while qualification remains outstanding. A merged PR moves to
Validation; close the issue after its acceptance criteria are evidenced.

GitHub reads issue forms from the default branch. A metadata-only PR based on
that branch may target it directly after maintainer review; its diff must be
limited to issue forms, PR templates and contributor/process documentation.
This exception does not promote application commits from dev or bypass checks.

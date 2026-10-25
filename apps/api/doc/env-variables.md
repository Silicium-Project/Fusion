# Environment Variables

For local development the API defaults to SQLite when no database URL is
provided. Production should select PostgreSQL explicitly. Create a `.env`
file in the root of the project with the relevant configuration:

```
# Local database (the Fusion launcher sets these values automatically).
DATABASE_DRIVER=sqlite
SQLITE_PATH=.silicium/site/silicium.db

# Production database alternative.
DATABASE_DRIVER=postgres
DATABASE_URL=postgres://user:password@127.0.0.1:5432/silicium?sslmode=disable

# JWT configuration
JWT_SECRET_KEY=your_jwt_secret_key
```

## Variable Descriptions

-   `DATABASE_DRIVER`: `sqlite` for local development or `postgres` for production. If omitted, the API chooses SQLite unless `DATABASE_URL` is present.
-   `SQLITE_PATH`: SQLite database path; defaults to `.silicium/site/silicium.db`.
-   `DATABASE_URL`: PostgreSQL DSN, required when `DATABASE_DRIVER=postgres`.
-   `JWT_SECRET_KEY`: A secret key for signing JWT (JSON Web Tokens). This should be a long, random string (32 characters or more). Required in production (`SILICIUM_RELEASE_CHANNEL=prod`): the API refuses to start without it. Elsewhere a missing key is replaced by a random one per process (sessions end when the API restarts).

## Blockchain trace of jobs

-   `SILICIUM_DEVNET_TRACE`: `1` anchors every completed job on Solana (package `internal/chainproof`): one Memo transaction carrying the Merkle root of the job's signed task traces, its task count and the SHA-256 of the final result. `0` (default) disables it. Anchoring runs after the job is saved and never makes it fail; the dashboard shows the reason when it does not succeed.
-   `SILICIUM_SOLANA_WALLET`: Solana CLI keypair file (JSON array of 64 bytes) that signs and pays the transaction. One job costs one transaction fee (5 000 lamports on devnet).
-   `SILICIUM_SOLANA_RPC`: RPC endpoint; defaults to `https://api.devnet.solana.com`. Only its scheme and host are shown on the site, so an API key in the URL stays private.
-   `SILICIUM_DEVNET_CONFIRM_TIMEOUT_S`: how long to wait for the transaction to be confirmed (default 90).

The trace is written as `devnet-trace.json` next to the job summary; its path and the transaction signature are stored in `jobs.devnet_trace_path` and `jobs.devnet_job`.

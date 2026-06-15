# Environment Variables

The following environment variables are required to run the application. Create a `.env` file in the root of the project with the following content:

```
# Database configuration
POSTGRES_DB=your_database_name
POSTGRES_USER=your_database_user
POSTGRES_PASSWORD=your_database_password
HOST=silicium_database

# JWT configuration
JWT_SECRET_KEY=your_jwt_secret_key

# Silicium network bridge
SILICIUM_NETWORK_ROOT=../../Network
SILICIUM_SEED_PEERS=http://127.0.0.1:46101,http://127.0.0.1:46102
SILICIUM_MESH_KEY=demo-mesh
SILICIUM_ORCHESTRATOR_HOST=127.0.0.1
SILICIUM_DASHBOARD_URL=http://localhost:5174/
SILICIUM_DEVNET_TRACE=1
SILICIUM_DEVNET_TX_DELAY_MS=2500
```

## Variable Descriptions

-   `POSTGRES_DB`: The name of the database to be created.
-   `POSTGRES_USER`: The username for the PostgreSQL database.
-   `POSTGRES_PASSWORD`: The password for the PostgreSQL database.
-   `HOST`: The hostname of the database. When running with `docker-compose`, this should be the name of the database service (`silicium_database`).
-   `JWT_SECRET_KEY`: A secret key for signing JWT (JSON Web Tokens). This should be a long, random string.
-   `SILICIUM_NETWORK_ROOT`: Path to the `Network` repository that contains the P2P node, render demo, and Solana trace scripts.
-   `SILICIUM_SEED_PEERS`: Comma-separated worker/verifier peer URLs used by the orchestrator.
-   `SILICIUM_MESH_KEY`: Shared demo mesh key used by the nodes.
-   `SILICIUM_ORCHESTRATOR_HOST`: Host advertised by the temporary orchestrator started by the backend.
-   `SILICIUM_DASHBOARD_URL`: Read-only Devnet dashboard URL shown to the client.
-   `SILICIUM_DEVNET_TRACE`: Set to `1` to write job/fragment/vote/finalize traces to Devnet.
-   `SILICIUM_DEVNET_TX_DELAY_MS`: Delay between Devnet transactions.

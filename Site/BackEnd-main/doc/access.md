# Accessing the Services

This document provides information on how to access the services once they are running.

## Ports

The services are exposed on the following ports:

-   **Backend Server:** `8080`
-   **Database (PostgreSQL):** `5432`

## Accessing the Backend Server

The backend server is accessible at `http://localhost:8080`. You can use a tool like `curl` or Postman to interact with the API endpoints.

Example using `curl`:

```bash
curl http://localhost:8080/
```

## Accessing the Database

The database is accessible on port `5432`. You can use a database client like `psql` or a graphical tool like DBeaver to connect to the database.

-   **Host:** `localhost`
-   **Port:** `5432`
-   **User:** The value of `POSTGRES_USER` in your `.env` file.
-   **Password:** The value of `POSTGRES_PASSWORD` in your `.env` file.
-   **Database:** The value of `POSTGRES_DB` in your `.env` file.

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
-   `JWT_SECRET_KEY`: A secret key for signing JWT (JSON Web Tokens). This should be a long, random string.

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
```

## Variable Descriptions

-   `POSTGRES_DB`: The name of the database to be created.
-   `POSTGRES_USER`: The username for the PostgreSQL database.
-   `POSTGRES_PASSWORD`: The password for the PostgreSQL database.
-   `HOST`: The hostname of the database. When running with `docker-compose`, this should be the name of the database service (`silicium_database`).
-   `JWT_SECRET_KEY`: A secret key for signing JWT (JSON Web Tokens). This should be a long, random string.

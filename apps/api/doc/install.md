# Installation and Setup

This document provides instructions on how to set up the environment and run the backend server and database using Docker.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create a `.env` file:**

    Create a `.env` file in the root of the project and add the necessary environment variables. See [env-variables.md](env-variables.md) for more details.

3.  **Build and run the services:**

    ```bash
    docker compose up --build
    ```

    This command will build the Docker images for the backend server and the database, and then start the services. The `-d` flag can be used to run the services in detached mode.

    ```bash
    docker compose up --build -d
    ```

## Stopping the services

To stop the services, run the following command:

```bash
docker compose down
```

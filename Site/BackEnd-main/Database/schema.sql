-- This schema is designed for PostgreSQL, but is easily adaptable to other SQL databases.

-- The 'users' table stores traditional Web2-style account information.
-- This allows users to register with an email and password.
CREATE TABLE IF NOT EXISTS users (
    -- Unique identifier for the user account.
    id BIGSERIAL PRIMARY KEY,

    -- User's email, used for login and notifications.
    email VARCHAR(255) UNIQUE NOT NULL,

    -- First and last name of the user, optional.
    first_name VARCHAR(50),
    last_name VARCHAR(50),

    -- A secure hash of the user's password.
    -- IMPORTANT: Never store plain-text passwords. Use a strong hashing algorithm like bcrypt.
    password_hash VARCHAR(255) NOT NULL,
    
    -- An optional, user-chosen display name.
    username VARCHAR(50) UNIQUE,

    -- The user's associated wallet address, must be unique.
    wallet_address TEXT UNIQUE,

    -- The user's role, e.g., 'user' or 'admin'.
    role VARCHAR(20) NOT NULL DEFAULT 'user',

    -- Timestamps for tracking account creation and updates.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    description TEXT,
    workload VARCHAR(80) NOT NULL DEFAULT 'raytracer',
    priority VARCHAR(20) NOT NULL DEFAULT 'high',
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    silicium_job_id VARCHAR(128) UNIQUE NOT NULL,
    input_path TEXT NOT NULL,
    result_path TEXT,
    summary_path TEXT,
    devnet_trace_path TEXT,
    devnet_job VARCHAR(128),
    dashboard_url TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

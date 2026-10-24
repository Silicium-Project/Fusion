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

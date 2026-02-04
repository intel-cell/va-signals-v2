-- Authentication Schema for VA Signals Command Dashboard
-- ECHO COMMAND - Phase 1 & 2

-- Users table for role-based access control
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_by TEXT,  -- user_id of who created this user
    CONSTRAINT valid_role CHECK (role IN ('commander', 'leadership', 'analyst', 'viewer'))
);

-- Sessions table for cookie-based authentication
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    is_valid BOOLEAN DEFAULT TRUE,
    invalidated_at TIMESTAMP,
    invalidated_reason TEXT
);

-- Audit log table for comprehensive request tracking
CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    user_email TEXT,
    action TEXT NOT NULL,
    resource TEXT,
    resource_id TEXT,
    request_method TEXT,
    request_path TEXT,
    request_body TEXT,
    response_status INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    duration_ms INTEGER,
    success BOOLEAN
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

-- Seed commander account (Xavier Aguiar - Chief in Command)
-- Use a placeholder user_id that will be linked on first Firebase login
INSERT OR IGNORE INTO users (user_id, email, display_name, role, is_active)
VALUES ('pending-commander', 'x_aguiar@yahoo.com', 'Xavier Aguiar', 'commander', TRUE);

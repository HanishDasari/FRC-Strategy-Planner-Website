-- PostgreSQL Schema for FRC Strategy Planner

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    team_number INTEGER UNIQUE NOT NULL,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    google_id TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    is_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    match_number INTEGER NOT NULL,
    match_type TEXT NOT NULL, -- 'Qualification', 'Elimination'
    creator_team_id INTEGER NOT NULL REFERENCES teams(id),
    creator_user_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS match_alliances (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    user_id INTEGER REFERENCES users(id),
    alliance_color TEXT NOT NULL, -- 'Red', 'Blue'
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invites (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    from_team_id INTEGER NOT NULL REFERENCES teams(id),
    to_team_id INTEGER NOT NULL REFERENCES teams(id),
    from_user_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'Pending', -- 'Pending', 'Accepted', 'Declined', 'Expired'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '20 minutes')
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    sender_team_id INTEGER NOT NULL REFERENCES teams(id),
    sender_user_id INTEGER REFERENCES users(id),
    content TEXT,
    message_type TEXT DEFAULT 'text', -- 'text', 'image', 'video'
    media_url TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    phase TEXT NOT NULL, -- 'Autonomous', 'Teleop', 'Endgame'
    text_content TEXT DEFAULT '',
    UNIQUE(match_id, phase)
);

CREATE TABLE IF NOT EXISTS drawings (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    drawing_data_json TEXT DEFAULT '[]',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, phase)
);

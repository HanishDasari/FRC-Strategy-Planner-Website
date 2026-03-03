-- PostgreSQL Schema for FRC Strategy Planner

DROP TABLE IF EXISTS drawings CASCADE;
DROP TABLE IF EXISTS strategies CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS invites CASCADE;
DROP TABLE IF EXISTS password_resets CASCADE;
DROP TABLE IF EXISTS email_verifications CASCADE;
DROP TABLE IF EXISTS match_alliances CASCADE;
DROP TABLE IF EXISTS matches CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS teams CASCADE;

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    team_number INTEGER UNIQUE NOT NULL,
    team_name TEXT NOT NULL
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    google_id TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    is_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE email_verifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    match_number INTEGER NOT NULL,
    match_type TEXT NOT NULL, -- 'Qualification', 'Elimination'
    creator_team_id INTEGER NOT NULL REFERENCES teams(id)
);

CREATE TABLE match_alliances (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    alliance_color TEXT NOT NULL, -- 'Red', 'Blue'
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invites (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    from_team_id INTEGER NOT NULL REFERENCES teams(id),
    to_team_id INTEGER NOT NULL REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'Pending', -- 'Pending', 'Accepted', 'Declined'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    sender_team_id INTEGER NOT NULL REFERENCES teams(id),
    sender_user_id INTEGER REFERENCES users(id),
    content TEXT,
    message_type TEXT DEFAULT 'text', -- 'text', 'image', 'video'
    media_url TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    phase TEXT NOT NULL, -- 'Autonomous', 'Teleop', 'Endgame'
    text_content TEXT DEFAULT '',
    UNIQUE(match_id, phase)
);

CREATE TABLE drawings (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    drawing_data_json TEXT DEFAULT '[]',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, phase)
);

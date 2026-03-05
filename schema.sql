DROP TABLE IF EXISTS drawings;
DROP TABLE IF EXISTS strategies;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS invites;
DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS email_verifications;
DROP TABLE IF EXISTS match_alliances;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS teams;

CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_number INTEGER UNIQUE NOT NULL,
    team_name TEXT NOT NULL
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    team_id INTEGER NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (team_id) REFERENCES teams (id)
);

CREATE TABLE email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_number INTEGER NOT NULL,
    match_type TEXT NOT NULL, -- 'Qualification', 'Elimination'
    creator_team_id INTEGER NOT NULL,
    FOREIGN KEY (creator_team_id) REFERENCES teams (id)
);

CREATE TABLE match_alliances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    alliance_color TEXT NOT NULL, -- 'Red', 'Blue'
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (team_id) REFERENCES teams (id)
);

CREATE TABLE invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    from_team_id INTEGER NOT NULL,
    to_team_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending', -- 'Pending', 'Accepted', 'Declined'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (from_team_id) REFERENCES teams (id),
    FOREIGN KEY (to_team_id) REFERENCES teams (id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    sender_team_id INTEGER NOT NULL,
    sender_user_id INTEGER,
    content TEXT,
    message_type TEXT DEFAULT 'text', -- 'text', 'image', 'video'
    media_url TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (sender_team_id) REFERENCES teams (id),
    FOREIGN KEY (sender_user_id) REFERENCES users (id)
);

CREATE TABLE strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    phase TEXT NOT NULL, -- 'Autonomous', 'Teleop', 'Endgame'
    text_content TEXT DEFAULT '',
    FOREIGN KEY (match_id) REFERENCES matches (id),
    UNIQUE(match_id, phase)
);

CREATE TABLE drawings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    phase TEXT NOT NULL, -- 'Field' (can differ if needed, but usually one map per match)
    drawing_data_json TEXT DEFAULT '[]',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    UNIQUE(match_id, phase)
);

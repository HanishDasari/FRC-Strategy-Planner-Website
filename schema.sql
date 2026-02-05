DROP TABLE IF EXISTS drawings;
DROP TABLE IF EXISTS strategies;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS invites;
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
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams (id)
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
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (team_id) REFERENCES teams (id)
);

CREATE TABLE invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    from_team_id INTEGER NOT NULL,
    to_team_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending', -- 'Pending', 'Accepted', 'Declined'
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (from_team_id) REFERENCES teams (id),
    FOREIGN KEY (to_team_id) REFERENCES teams (id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    sender_team_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    FOREIGN KEY (sender_team_id) REFERENCES teams (id)
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
    drawing_data_json TEXT DEFAULT '{}',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches (id),
    UNIQUE(match_id, phase)
);

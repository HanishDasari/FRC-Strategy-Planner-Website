-- TiDB (MySQL) Schema for FRC Strategy Planner

CREATE TABLE IF NOT EXISTS teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_number INTEGER UNIQUE NOT NULL,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT,
    team_id INTEGER NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    INDEX (team_id),
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_number INTEGER NOT NULL,
    match_type TEXT NOT NULL, -- 'Qualification', 'Elimination'
    creator_team_id INTEGER NOT NULL,
    creator_user_id INTEGER,
    INDEX (creator_team_id),
    INDEX (creator_user_id),
    FOREIGN KEY (creator_team_id) REFERENCES teams(id),
    FOREIGN KEY (creator_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS match_alliances (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    user_id INTEGER,
    alliance_color TEXT NOT NULL, -- 'Red', 'Blue'
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (match_id),
    INDEX (team_id),
    INDEX (user_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS invites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    from_team_id INTEGER NOT NULL,
    to_team_id INTEGER NOT NULL,
    from_user_id INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending', -- 'Pending', 'Accepted', 'Declined', 'Expired'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    INDEX (match_id),
    INDEX (from_team_id),
    INDEX (to_team_id),
    INDEX (from_user_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (from_team_id) REFERENCES teams(id),
    FOREIGN KEY (to_team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    sender_team_id INTEGER NOT NULL,
    sender_user_id INTEGER,
    content TEXT,
    message_type VARCHAR(50) DEFAULT 'text', -- 'text', 'image', 'video'
    media_url TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (match_id),
    INDEX (sender_team_id),
    INDEX (sender_user_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS strategies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    phase VARCHAR(50) NOT NULL, -- 'Autonomous', 'Teleop', 'Endgame'
    text_content TEXT,
    UNIQUE(match_id, phase),
    INDEX (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drawings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    phase VARCHAR(50) NOT NULL,
    drawing_data_json LONGTEXT,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, phase),
    INDEX (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

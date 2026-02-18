# FRC Strategy Platform 🤖

A full-stack web-based collaboration platform for FIRST Robotics Competition (FRC) teams to plan match strategies efficiently.

## Features

### 🔐 Authentication
- Team-based registration and login
- Secure password hashing
- Session management

### 📊 Dashboard
- Create and manage matches
- View all team matches
- Send and receive team invites
- Real-time invite notifications

### 🎯 Match Collaboration Room
- **Strategy Planning**: Separate tabs for Autonomous, Teleop, and Endgame phases
- **Field Drawing**: Interactive canvas with multi-color drawing tools
- **Real-time Chat**: Team communication with timestamps
- **Auto-sync**: All changes sync automatically across team members

## Tech Stack

- **Backend**: Python (Flask)
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Canvas API**: HTML5 Canvas for field drawing

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
flask --app app init-db

# Run server
flask --app app run
```

Open `http://127.0.0.1:5000` in your browser.

## Project Structure

```
FRC-Flask/
├── app.py                 # Main Flask application
├── db.py                  # Database utilities
├── schema.sql             # Database schema
├── requirements.txt       # Python dependencies
├── templates/
│   ├── index.html        # Login/Register page
│   ├── dashboard.html    # Match dashboard
│   └── match.html        # Collaboration room
└── static/
    ├── css/
    │   └── style.css     # Dark mode styling
    └── js/
        ├── main.js       # Auth & dashboard logic
        └── match.js      # Match room & canvas logic
```

## Database Schema

- **teams**: Team information
- **users**: User accounts linked to teams
- **matches**: Match metadata
- **match_alliances**: Team-match relationships
- **invites**: Team invitation system
- **messages**: Match chat messages
- **strategies**: Phase-specific strategy text
- **drawings**: Canvas drawing data (JSON)

## API Endpoints

### Authentication
- `POST /auth/register` - Create new user/team
- `POST /auth/login` - User login
- `POST /auth/logout` - User logout
- `GET /auth/me` - Get current user info

### Matches
- `GET /api/matches` - List user's matches
- `POST /api/matches` - Create new match
- `GET /api/matches/<id>/data` - Get match data (messages, strategies, drawings)

### Collaboration
- `POST /api/matches/<id>/messages` - Send chat message
- `POST /api/matches/<id>/strategy` - Update strategy text
- `POST /api/matches/<id>/drawing` - Save drawing data

### Invites
- `POST /api/invites` - Send team invite
- `GET /api/invites/pending` - Get pending invites
- `POST /api/invites/<id>/respond` - Accept/decline invite

## Verification

Run automated backend tests:
```bash
python verify_backend.py
```

## Design Philosophy

- **Competition-ready**: Fast, simple, and reliable
- **Dark Mode**: Professional FRC-themed interface
- **Real-time**: 2-second polling for live updates
- **Portable**: SQLite database for easy deployment

## License

MIT License - Built for FRC teams

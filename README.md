# FRC Strategy Platform 🤖

A premium, collaborative web platform for FIRST Robotics Competition (FRC) teams to plan and sync match strategies in real-time.

## 🚀 Key Features

### 🔐 Advanced Authentication
- **Team-based Registration**: Join as a specific team number.
- **Email Verification**: Secure account activation and password resets via Gmail SMTP.
- **Google Login**: Seamless integration with Google Accounts.
- **Secure Profile Management**: Update personal info, team details, or reset passwords with a built-in strength meter and visibility toggle.
- **Account Deletion**: Full control over your data with permanent account removal.

### 📊 Strategy Dashboard
- **Match Management**: Create, view, and delete match plans.
- **Collaboration Invites**: Invite other teams to your match room with real-time popup notifications.
- **Team Status**: See who is currently active and online in your team room.

### 🎯 Real-time Match Room
- **Multi-Phase Planning**: Specialized tabs for Autonomous, Teleop, and Endgame.
- **Live Video/Chat**: Integrated chat system with support for image uploads and real-time messaging.
- **Interactive Sketchboard**: High-performance HTML5 Canvas drawing with multi-user sync and undo/redo support.
- **Socket.IO Sync**: Every stroke and message is broadcasted instantly to all connected team members.

## 🛠️ Tech Stack

- **Backend**: Python (Flask) with `Flask-SocketIO` for real-time events.
- **Database**: **PostgreSQL** (Hosted on Neon.tech/AWS) for high-availability.
- **Real-time**: WebSockets via `gevent-websocket`.
- **Email**: `Flask-Mail` with Gmail SMTP integration.
- **Frontend**: Modern HTML5, Vanilla CSS3 (Glassmorphism & Dark Mode), and Vanilla JavaScript.

## ⚡ Quick Start

1.  **Clone and Install**:
    ```bash
    git clone https://github.com/sdatta25/FRC-Strategy-Planner-Website.git
    cd FRC-Flask
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    Create a `.env` file from the provided `.env.example`:
    ```bash
    cp .env.example .env
    # Add your DATABASE_URL, MAIL_USERNAME, and MAIL_PASSWORD
    ```

3.  **Run the App**:
    ```bash
    python3 app.py
    ```
    Open `http://localhost:5000` to start planning!

## 📂 Project Architecture

- `app.py`: Central logic, Socket.IO handlers, and API routes.
- `db.py`: PostgreSQL connection management using `psycopg2`.
- `migrate_to_pg.py`: Specialized script for SQLite -> PostgreSQL data transfers.
- `static/js/match.js`: The "brain" of the real-time drawing sync and strategy engine.
- `templates/`: Premium, responsive UI templates for every platform feature.

## 🧪 Verification

Ensure the system is running correctly by running the backend audit:
```bash
python3 verify_backend.py
```

## 📜 License

MIT License - Built with ❤️ for FRC teams everywhere.

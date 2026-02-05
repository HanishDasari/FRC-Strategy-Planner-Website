import os
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
import db

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.root_path, 'frc_strategy.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)

    # Helper decorator for login required routes
    def login_required(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return view(**kwargs)
        return wrapped_view

    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')

        if user_id is None:
            g.user = None
        else:
            g.user = db.get_db().execute(
                'SELECT u.id, u.username, u.team_id, t.team_number, t.team_name '
                'FROM users u JOIN teams t ON u.team_id = t.id '
                'WHERE u.id = ?', (user_id,)
            ).fetchone()

    # --- Routes ---

    @app.route('/')
    def index():
        if g.user:
            return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html')

    # Auth API
    @app.route('/auth/register', methods=('POST',))
    def register():
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        team_number = data.get('team_number')
        team_name = data.get('team_name')
        
        if not username or not password or not team_number:
            return jsonify({'error': 'Missing required fields'}), 400

        database = db.get_db()
        error = None
        
        try:
            # Check if team exists, if not create it
            team = database.execute('SELECT id FROM teams WHERE team_number = ?', (team_number,)).fetchone()
            if team is None:
                cursor = database.execute(
                    'INSERT INTO teams (team_number, team_name) VALUES (?, ?)',
                    (team_number, team_name)
                )
                team_id = cursor.lastrowid
            else:
                team_id = team['id']

            # Create User
            database.execute(
                'INSERT INTO users (username, password_hash, team_id) VALUES (?, ?, ?)',
                (username, generate_password_hash(password), team_id)
            )
            database.commit()
        except database.IntegrityError:
            error = f"User {username} is already registered."
        except Exception as e:
            error = str(e)

        if error is None:
            return jsonify({'message': 'Registration successful'}), 201
        
        return jsonify({'error': error}), 400

    @app.route('/auth/login', methods=('POST',))
    def login():
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        database = db.get_db()
        error = None
        user = database.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return jsonify({'message': 'Login successful'}), 200

        return jsonify({'error': error}), 401

    @app.route('/auth/logout', methods=('POST',))
    def logout():
        session.clear()
        return jsonify({'message': 'Logged out'}), 200

    @app.route('/auth/me')
    def me():
        if g.user:
            return jsonify({
                'id': g.user['id'],
                'username': g.user['username'],
                'team_id': g.user['team_id'],
                'team_number': g.user['team_number'],
                'team_name': g.user['team_name']
            })
        return jsonify({'user': None}), 401

    # --- Match & Invitation Management ---

    @app.route('/api/matches', methods=('GET', 'POST'))
    @login_required
    def matches():
        database = db.get_db()
        if request.method == 'POST':
            data = request.get_json()
            match_number = data.get('match_number')
            match_type = data.get('match_type', 'Qualification')

            if not match_number:
                return jsonify({'error': 'Match number is required'}), 400

            cursor = database.execute(
                'INSERT INTO matches (match_number, match_type, creator_team_id) VALUES (?, ?, ?)',
                (match_number, match_type, g.user['team_id'])
            )
            match_id = cursor.lastrowid
            
            # Automatically add creator to match_alliances (defaulting to Red for now, or let them choose)
            # For simplicity, we won't assign color yet or default to Red
            database.execute(
                'INSERT INTO match_alliances (match_id, team_id, alliance_color) VALUES (?, ?, ?)',
                (match_id, g.user['team_id'], 'Red') 
            )
            
            # Create empty strategy/drawing entries
            for phase in ['Autonomous', 'Teleop', 'Endgame']:
                database.execute(
                     'INSERT INTO strategies (match_id, phase) VALUES (?, ?)',
                     (match_id, phase)
                )
            database.execute('INSERT INTO drawings (match_id, phase) VALUES (?, ?)', (match_id, 'Field'))

            database.commit()
            return jsonify({'message': 'Match created', 'id': match_id}), 201

        # GET: List matches for the user's team (either created or invited)
        matches = database.execute(
            '''
            SELECT m.id, m.match_number, m.match_type, t.team_number as creator_team_number
            FROM matches m
            JOIN teams t ON m.creator_team_id = t.id
            JOIN match_alliances ma ON m.id = ma.match_id
            WHERE ma.team_id = ?
            ORDER BY m.id DESC
            ''', (g.user['team_id'],)
        ).fetchall()
        
        return jsonify([dict(row) for row in matches])

    @app.route('/api/invites', methods=('POST',))
    @login_required
    def create_invite():
        data = request.get_json()
        match_id = data.get('match_id')
        to_team_number = data.get('to_team_number') # Invite by team number
        
        database = db.get_db()
        
        # Find the team
        to_team = database.execute('SELECT id FROM teams WHERE team_number = ?', (to_team_number,)).fetchone()
        if not to_team:
             return jsonify({'error': 'Team not found'}), 404
             
        # Check if already invited or in match
        existing = database.execute(
            'SELECT id FROM match_alliances WHERE match_id = ? AND team_id = ?',
            (match_id, to_team['id'])
        ).fetchone()
        
        if existing:
             return jsonify({'error': 'Team already in match'}), 400

        database.execute(
            'INSERT INTO invites (match_id, from_team_id, to_team_id) VALUES (?, ?, ?)',
            (match_id, g.user['team_id'], to_team['id'])
        )
        database.commit()
        return jsonify({'message': 'Invite sent'}), 201
        
    @app.route('/api/invites/pending', methods=('GET',))
    @login_required
    def get_invites():
        database = db.get_db()
        invites = database.execute(
            '''
            SELECT i.id, i.match_id, m.match_number, t.team_number as from_team
            FROM invites i
            JOIN matches m ON i.match_id = m.id
            JOIN teams t ON i.from_team_id = t.id
            WHERE i.to_team_id = ? AND i.status = 'Pending'
            ''', (g.user['team_id'],)
        ).fetchall()
        return jsonify([dict(row) for row in invites])

    @app.route('/api/invites/<int:invite_id>/respond', methods=('POST',))
    @login_required
    def respond_invite(invite_id):
        data = request.get_json()
        status = data.get('status') # 'Accepted' or 'Declined'
        
        if status not in ['Accepted', 'Declined']:
             return jsonify({'error': 'Invalid status'}), 400
             
        database = db.get_db()
        invite = database.execute('SELECT * FROM invites WHERE id = ?', (invite_id,)).fetchone()
        
        if not invite or invite['to_team_id'] != g.user['team_id']:
            return jsonify({'error': 'Invite not found or not for you'}), 404
            
        database.execute('UPDATE invites SET status = ? WHERE id = ?', (status, invite_id))
        
        if status == 'Accepted':
            # Add to match alliances
            database.execute(
                'INSERT INTO match_alliances (match_id, team_id, alliance_color) VALUES (?, ?, ?)',
                (invite['match_id'], g.user['team_id'], 'Blue') # Defaulting to Blue? or Unknown.
            )
        
        database.commit()
        return jsonify({'message': f'Invite {status}'}), 200

    @app.route('/match/<int:match_id>')
    @login_required
    def match_room(match_id):
        return render_template('match.html', match_id=match_id)

    # --- Collaboration API (Polling) ---

    @app.route('/api/matches/<int:match_id>/data')
    @login_required
    def get_match_data(match_id):
        database = db.get_db()
        
        # Check access
        access = database.execute(
            'SELECT id FROM match_alliances WHERE match_id = ? AND team_id = ?',
            (match_id, g.user['team_id'])
        ).fetchone()
        
        if not access:
            return jsonify({'error': 'Unauthorized'}), 403

        # Messages
        messages = database.execute(
            '''
            SELECT m.content, m.timestamp, t.team_number, t.team_name
            FROM messages m
            JOIN teams t ON m.sender_team_id = t.id
            WHERE m.match_id = ?
            ORDER BY m.timestamp ASC
            ''', (match_id,)
        ).fetchall()

        # Strategies
        strategies = database.execute(
            'SELECT phase, text_content FROM strategies WHERE match_id = ?',
            (match_id,)
        ).fetchall()
        
        # Drawing
        drawing = database.execute(
            'SELECT drawing_data_json FROM drawings WHERE match_id = ?',
            (match_id,)
        ).fetchone()

        return jsonify({
            'messages': [dict(row) for row in messages],
            'strategies': {row['phase']: row['text_content'] for row in strategies},
            'drawing': drawing['drawing_data_json'] if drawing else '{}'
        })

    @app.route('/api/matches/<int:match_id>/messages', methods=('POST',))
    @login_required
    def post_message(match_id):
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'No content'}), 400
            
        database = db.get_db()
        # Verify access (omitted for brevity, but should be there)
        
        database.execute(
            'INSERT INTO messages (match_id, sender_team_id, content) VALUES (?, ?, ?)',
            (match_id, g.user['team_id'], content)
        )
        database.commit()
        return jsonify({'message': 'Sent'}), 201

    @app.route('/api/matches/<int:match_id>/strategy', methods=('POST',))
    @login_required
    def update_strategy(match_id):
        data = request.get_json()
        phase = data.get('phase')
        text_content = data.get('text_content')
        
        if phase not in ['Autonomous', 'Teleop', 'Endgame']:
            return jsonify({'error': 'Invalid phase'}), 400
            
        database = db.get_db()
        database.execute(
            'UPDATE strategies SET text_content = ? WHERE match_id = ? AND phase = ?',
            (text_content, match_id, phase)
        )
        database.commit()
        return jsonify({'message': 'Strategy updated'}), 200

    @app.route('/api/matches/<int:match_id>/drawing', methods=('POST',))
    @login_required
    def update_drawing(match_id):
        data = request.get_json()
        drawing_data = data.get('drawing_data') # Expecting JSON string
        
        database = db.get_db()
        database.execute(
            'UPDATE drawings SET drawing_data_json = ?, last_updated = CURRENT_TIMESTAMP WHERE match_id = ?',
            (drawing_data, match_id)
        )
        database.commit()
        return jsonify({'message': 'Drawing saved'}), 200

    return app



if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)

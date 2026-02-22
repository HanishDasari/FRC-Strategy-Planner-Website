import os
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify, current_app
from authlib.integrations.flask_client import OAuth
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import db
import uuid
import random
import string
from datetime import datetime, timedelta

socketio = SocketIO()
mail = Mail()

def create_app(test_config=None):
    # Allow OAuth over HTTP for development (required for WiFi access/nip.io)
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.root_path, 'frc_strategy.sqlite'),
        GOOGLE_CLIENT_ID=os.environ.get('GOOGLE_CLIENT_ID'),
        GOOGLE_CLIENT_SECRET=os.environ.get('GOOGLE_CLIENT_SECRET'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    if not app.config['GOOGLE_CLIENT_ID'] or not app.config['GOOGLE_CLIENT_SECRET']:
        print("WARNING: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set. Google Login will fail.")

    oauth = OAuth(app)
    oauth.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    mail.init_app(app)

    import traceback
    @app.errorhandler(500)
    def handle_500(e):
        print("\n--- SERVER ERROR 500 ---")
        traceback.print_exc()
        print("------------------------\n")
        return jsonify(error="Internal Server Error"), 500

    def get_db_for_socket():
        # Socket handlers don't have 'g', so we create a temporary connection
        import sqlite3
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        return conn

    # Helper decorator for login required routes
    def login_required(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                return redirect(url_for('index'))
            return view(**kwargs)
        return wrapped_view

    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')

        if user_id is None:
            g.user = None
        else:
            g.user = db.get_db().execute(
                'SELECT u.id, u.email, u.name, u.team_id, t.team_number, t.team_name '
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

    def send_email(subject, recipient, body):
        msg = Message(subject, recipients=[recipient])
        msg.body = body
        try:
            mail.send(msg)
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    # Auth API
    # Auth API
    # Auth API
    @app.route('/login/google')
    def login_google():
        if not app.config['GOOGLE_CLIENT_ID'] or not app.config['GOOGLE_CLIENT_SECRET']:
            flash("Configuration Error: Google Credentials missing on server.")
            return redirect(url_for('index'))
            
        redirect_uri = url_for('auth_callback', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route('/register')
    def register_page():
        return render_template('register.html')

    @app.route('/auth/register', methods=('POST',))
    def auth_register():
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        team_number = request.form.get('team_number')
        team_name = request.form.get('team_name')

        if not all([name, email, password, team_number, team_name]):
            flash("All fields are required.")
            return redirect(url_for('register_page'))

        database = db.get_db()
        user = database.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if user:
            flash("Email already registered. Please login.")
            return redirect(url_for('index'))

        # Team logic
        team = database.execute('SELECT id FROM teams WHERE team_number = ?', (team_number,)).fetchone()
        if not team:
            cursor = database.execute(
                'INSERT INTO teams (team_number, team_name) VALUES (?, ?)',
                (team_number, team_name)
            )
            team_id = cursor.lastrowid
        else:
            team_id = team['id']

        # Create User
        cursor = database.execute(
            'INSERT INTO users (email, name, password_hash, team_id, is_verified) VALUES (?, ?, ?, ?, ?)',
            (email, name, generate_password_hash(password), team_id, 0)
        )
        user_id = cursor.lastrowid

        # Generate Verification Code
        code = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.now() + timedelta(minutes=15)
        database.execute(
            'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (?, ?, ?)',
            (user_id, code, expires_at)
        )
        database.commit()

        # "Send" Email
        email_body = f"Hello {name},\n\nYour verification code is: {code}\n\nThis code will expire in 15 minutes."
        if send_email("Verify Your Email", email, email_body):
            flash("Registration successful. Please enter the verification code sent to your email.")
        else:
            flash("Registration successful, but there was an error sending the verification email. Please check the server console for the code.")
            print(f"\n--- EMAIL VERIFICATION DEBUG ---\nUser: {email}\nCode: {code}\n--------------------------------\n")
        
        session['pending_verification_user_id'] = user_id
        flash("Registration successful. Please enter the verification code sent to your email (check server console).")
        return redirect(url_for('verify_email_page'))

    @app.route('/verify-email')
    def verify_email_page():
        if 'pending_verification_user_id' not in session:
            return redirect(url_for('index'))
        return render_template('verify_email.html')

    @app.route('/auth/verify-email', methods=('POST',))
    def auth_verify_email():
        user_id = session.get('pending_verification_user_id')
        code = request.form.get('code')

        if not user_id or not code:
            flash("Missing information.")
            return redirect(url_for('verify_email_page'))

        database = db.get_db()
        verification = database.execute(
            'SELECT * FROM email_verifications WHERE user_id = ? AND code = ? AND expires_at > ?',
            (user_id, code, datetime.now())
        ).fetchone()

        if verification:
            database.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user_id,))
            database.execute('DELETE FROM email_verifications WHERE user_id = ?', (user_id,))
            database.commit()
            session.pop('pending_verification_user_id', None)
            session['user_id'] = user_id
            flash("Email verified successfully!")
            return redirect(url_for('dashboard'))
        
        flash("Invalid or expired verification code.")
        return redirect(url_for('verify_email_page'))

    @app.route('/auth/resend-verification')
    def resend_verification():
        user_id = session.get('pending_verification_user_id')
        if not user_id:
            return redirect(url_for('index'))

        database = db.get_db()
        user = database.execute('SELECT email FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if user:
            code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.now() + timedelta(minutes=15)
            database.execute('DELETE FROM email_verifications WHERE user_id = ?', (user_id,))
            database.execute(
                'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (?, ?, ?)',
                (user_id, code, expires_at)
            )
            database.commit()
            email_body = f"Your new verification code is: {code}\n\nThis code will expire in 15 minutes."
            if send_email("New Verification Code", user['email'], email_body):
                flash("A new verification code has been sent.")
            else:
                flash("There was an error sending the verification email. Please check the server console.")
                print(f"\n--- EMAIL VERIFICATION DEBUG (RESEND) ---\nUser: {user['email']}\nCode: {code}\n-----------------------------------------\n")
            flash("A new verification code has been sent.")
        
        return redirect(url_for('verify_email_page'))

    @app.route('/auth/login', methods=('POST',))
    def auth_login():
        email = request.form.get('email')
        password = request.form.get('password')

        database = db.get_db()
        user = database.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()

        if user and user['password_hash'] and check_password_hash(user['password_hash'], password):
            if not user['is_verified']:
                session['pending_verification_user_id'] = user['id']
                
                # Generate and send verification code to cyborg email
                code = ''.join(random.choices(string.digits, k=6))
                expires_at = datetime.now() + timedelta(minutes=15)
                
                database.execute('DELETE FROM email_verifications WHERE user_id = ?', (user['id'],))
                database.execute(
                    'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (?, ?, ?)',
                    (user['id'], code, expires_at)
                )
                database.commit()
                
                cyborg_email = current_app.config.get('MAIL_USERNAME', 'cyborg.13747@gmail.com')
                email_body = f"User {user['email']} requested login. Verification code: {code}"
                send_email("Login Verification Code", cyborg_email, email_body)
                
                flash("Please enter the verification code sent to the administrator email.")
                return redirect(url_for('verify_email_page'))
                
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        
        flash("Invalid email or password.")
        return redirect(url_for('index'))

    @app.route('/forgot-password')
    def forgot_password_page():
        return render_template('forgot_password.html')

    @app.route('/auth/forgot-password', methods=('POST',))
    def auth_forgot_password():
        email = request.form.get('email')
        database = db.get_db()
        user = database.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()

        if user:
            token = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(hours=1)
            database.execute(
                'INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)',
                (user['id'], token, expires_at)
            )
            database.commit()
            
            reset_link = url_for('reset_password_page', token=token, _external=True)
            email_body = f"Hi,\n\nYou requested a password reset. Click the link below to reset your password:\n{reset_link}\n\nIf you did not request this, please ignore this email."
            if send_email("Password Reset Request", email, email_body):
                flash("If that email is registered, a reset link has been sent.")
            else:
                flash("If that email is registered, a reset link has been sent (check server console).")
                print(f"\n--- PASSWORD RESET DEBUG ---\nUser: {email}\nLink: {reset_link}\n----------------------------\n")
        else:
            flash("If that email is registered, a reset link has been sent.")
            
        return redirect(url_for('index'))

    @app.route('/reset-password/<token>')
    def reset_password_page(token):
        return render_template('reset_password.html', token=token)

    @app.route('/auth/reset-password', methods=('POST',))
    def auth_reset_password():
        token = request.form.get('token')
        password = request.form.get('password')

        database = db.get_db()
        reset = database.execute(
            'SELECT * FROM password_resets WHERE token = ? AND expires_at > ?',
            (token, datetime.now())
        ).fetchone()

        if reset:
            database.execute(
                'UPDATE users SET password_hash = ? WHERE id = ?',
                (generate_password_hash(password), reset['user_id'])
            )
            database.execute('DELETE FROM password_resets WHERE id = ?', (reset['id'],))
            database.commit()
            flash("Password reset successful. Please login.")
            return redirect(url_for('index'))
        
        flash("Invalid or expired reset token.")
        return redirect(url_for('index'))

    @app.route('/auth/callback')
    def auth_callback():
        try:
            token = oauth.google.authorize_access_token()
        except Exception as e:
            flash(f"Authentication failed: {str(e)}")
            return redirect(url_for('index'))
            
        user_info = token.get('userinfo')
        if not user_info:
             user_info = oauth.google.userinfo()
             
        # Check if user exists by google_id
        database = db.get_db()
        user = database.execute(
            'SELECT * FROM users WHERE google_id = ?', (user_info['sub'],)
        ).fetchone()

        if not user:
            # Check by email for potential account linking
            user = database.execute(
                'SELECT * FROM users WHERE email = ?', (user_info['email'],)
            ).fetchone()
            
            if user:
                # Link account!
                database.execute(
                    'UPDATE users SET google_id = ? WHERE id = ?',
                    (user_info['sub'], user['id'])
                )
                database.commit()

        if user:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        else:
            # New user - temporary store info and redirect to finish registration
            session['google_user_info'] = user_info
            return redirect(url_for('register_finish_page'))

    @app.route('/register/google')
    def register_finish_page():
        user_info = session.get('google_user_info')
        if not user_info:
            return redirect(url_for('index'))
            
        return render_template('register_finish.html', 
                             email=user_info['email'], 
                             name=user_info.get('name'))

    @app.route('/auth/register-finish', methods=('POST',))
    def register_finish():
        user_info = session.get('google_user_info')
        if not user_info:
            return redirect(url_for('index'))
            
        team_number = request.form['team_number']
        team_name = request.form['team_name']
        
        database = db.get_db()
        try:
            # Check/Create Team
            team = database.execute('SELECT id FROM teams WHERE team_number = ?', (team_number,)).fetchone()
            if team is None:
                cursor = database.execute(
                    'INSERT INTO teams (team_number, team_name) VALUES (?, ?)',
                    (team_number, team_name)
                )
                team_id = cursor.lastrowid
            else:
                team_id = team['id']

            # Create User (Initially Unverified)
            cursor = database.execute(
                'INSERT INTO users (google_id, email, name, team_id, is_verified) VALUES (?, ?, ?, ?, ?)',
                (user_info['sub'], user_info['email'], user_info.get('name'), team_id, 0)
            )
            user_id = cursor.lastrowid
            
            # Generate and Send Verification Code
            code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.now() + timedelta(minutes=15)
            database.execute(
                'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (?, ?, ?)',
                (user_id, code, expires_at)
            )
            database.commit()
            
            email_body = f"Hello {user_info.get('name')},\n\nYour Google account registration is almost complete. Your verification code is: {code}"
            send_email("Verify Your Email", user_info['email'], email_body)

            session.pop('google_user_info', None)
            session['pending_verification_user_id'] = user_id
            flash("Registration successful. Please enter the verification code sent to your email.")
            return redirect(url_for('verify_email_page'))

        except database.IntegrityError:
            flash("User already registered or invalid data.")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Registration error: {str(e)}")
            return redirect(url_for('index'))

    @app.route('/auth/logout') 
    def logout():
        session.clear()
        return redirect(url_for('index'))

    @app.route('/auth/me')
    def me():
        if g.user:
            return jsonify({
                'id': g.user['id'],
                'email': g.user['email'],
                'name': g.user['name'],
                'team_id': g.user['team_id'],
                'team_number': g.user['team_number'],
                'team_name': g.user['team_name']
            })
        return jsonify({'user': None}), 401

    @app.route('/auth/delete-account')
    @login_required
    def auth_delete_account():
        user_id = g.user['id']
        database = db.get_db()
        try:
            # Delete associated records (manual cascade for safety)
            database.execute('DELETE FROM email_verifications WHERE user_id = ?', (user_id,))
            database.execute('DELETE FROM password_resets WHERE user_id = ?', (user_id,))
            database.execute('DELETE FROM users WHERE id = ?', (user_id,))
            database.commit()
            session.clear()
            flash("Your account has been successfully deleted.")
            return redirect(url_for('index'))
        except Exception as e:
            database.rollback()
            flash(f"Error deleting account: {str(e)}")
            return redirect(url_for('profile_page'))

    @app.route('/profile')
    @login_required
    def profile_page():
        return render_template('profile.html')

    @app.route('/auth/profile/update', methods=('POST',))
    @login_required
    def auth_profile_update():
        name = request.form.get('name')
        team_number = request.form.get('team_number')
        team_name = request.form.get('team_name')
        new_password = request.form.get('password')

        if not all([name, team_number, team_name]):
            flash("Name and Team info are required.")
            return redirect(url_for('profile_page'))

        database = db.get_db()
        
        # Team logic
        team = database.execute('SELECT id FROM teams WHERE team_number = ?', (team_number,)).fetchone()
        if not team:
            cursor = database.execute(
                'INSERT INTO teams (team_number, team_name) VALUES (?, ?)',
                (team_number, team_name)
            )
            team_id = cursor.lastrowid
        else:
            team_id = team['id']
            # Update team name if it already exists (allows fixing typos)
            database.execute('UPDATE teams SET team_name = ? WHERE id = ?', (team_name, team_id))
        
        # Update User
        database.execute(
            'UPDATE users SET name = ?, team_id = ? WHERE id = ?',
            (name, team_id, g.user['id'])
        )

        # Password update
        if new_password:
            database.execute(
                'UPDATE users SET password_hash = ?, is_verified = 0 WHERE id = ?',
                (generate_password_hash(new_password), g.user['id'])
            )

        database.commit()
        flash("Profile updated successfully!")
        return redirect(url_for('profile_page'))

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
            # Creator is always Red for now
            database.execute(
                'INSERT INTO match_alliances (match_id, team_id, alliance_color, last_seen) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (match_id, g.user['team_id'], 'Red') 
            )
            
            # Create empty strategy/drawing entries
            for phase in ['Autonomous', 'Teleop', 'Endgame']:
                database.execute(
                     'INSERT INTO strategies (match_id, phase) VALUES (?, ?)',
                     (match_id, phase)
                )
                database.execute(
                     'INSERT INTO drawings (match_id, phase) VALUES (?, ?)',
                     (match_id, phase)
                )

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

    @app.route('/api/matches/<int:match_id>', methods=('DELETE',))
    @login_required
    def delete_match(match_id):
        database = db.get_db()
        
        # Check if the user's team is the creator or part of the match
        match = database.execute(
            'SELECT creator_team_id FROM matches WHERE id = ?', (match_id,)
        ).fetchone()
        
        if not match:
            return jsonify({'error': 'Match not found'}), 404
            
        if match['creator_team_id'] != g.user['team_id']:
            return jsonify({'error': 'Only the creator team can delete this match'}), 403

        try:
            # Cascading deletion
            database.execute('DELETE FROM messages WHERE match_id = ?', (match_id,))
            database.execute('DELETE FROM strategies WHERE match_id = ?', (match_id,))
            database.execute('DELETE FROM drawings WHERE match_id = ?', (match_id,))
            database.execute('DELETE FROM invites WHERE match_id = ?', (match_id,))
            database.execute('DELETE FROM match_alliances WHERE match_id = ?', (match_id,))
            database.execute('DELETE FROM matches WHERE id = ?', (match_id,))
            
            database.commit()
            return jsonify({'message': 'Match deleted successfully'}), 200
        except Exception as e:
            database.rollback()
            return jsonify({'error': f'Failed to delete match: {str(e)}'}), 500

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
                'INSERT INTO match_alliances (match_id, team_id, alliance_color, last_seen) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                (invite['match_id'], g.user['team_id'], 'Blue') # Defaulting to Blue? or Unknown.
            )
        
        database.commit()
        return jsonify({'message': f'Invite {status}'}), 200

    @app.route('/match/<int:match_id>')
    @login_required
    def match_room(match_id):
        # Pass current user info to template for JS
        return render_template('match.html', 
                             match_id=match_id, 
                             current_team_number=g.user['team_number'],
                             current_user_id=g.user['id'])

    # --- Collaboration API (Polling) ---

    @app.route('/api/matches/<int:match_id>/data')
    @login_required
    def get_match_data(match_id):
        database = db.get_db()
        
        # Check access and update Last Seen
        print(f"DEBUG: Getting match data for {match_id}")
        if not g.user:
            return jsonify({'error': 'Not logged in'}), 401
            
        access = database.execute(
            'SELECT id FROM match_alliances WHERE match_id = ? AND team_id = ?',
            (match_id, g.user['team_id'])
        ).fetchone()
        
        print(f"DEBUG: Access found? {access is not None}")
        if not access:
            print(f"DEBUG: Unauthorized match access for match {match_id}")
            return jsonify({'error': 'Unauthorized'}), 403

        # Update last_seen
        database.execute(
            'UPDATE match_alliances SET last_seen = CURRENT_TIMESTAMP WHERE id = ?',
            (access['id'],)
        )
        database.commit()

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
        
        # Drawings - Return all phases
        drawings = database.execute(
            'SELECT phase, drawing_data_json FROM drawings WHERE match_id = ?',
            (match_id,)
        ).fetchall()
        
        # Teams in this match with Active Status
        # Active if seen in last 30 seconds
        teams = database.execute(
            '''
            SELECT t.team_number, t.team_name, ma.alliance_color, ma.last_seen,
                   (CASE WHEN ma.last_seen IS NOT NULL 
                         THEN (CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', ma.last_seen) AS INTEGER)) < 30 
                         ELSE 0 END) as is_active
            FROM match_alliances ma
            JOIN teams t ON ma.team_id = t.id
            WHERE ma.match_id = ?
            ''', (match_id,)
        ).fetchall()

        # Invites
        invites = database.execute(
            '''
            SELECT i.*, t.team_number as from_team_number, t2.team_number as to_team_number
            FROM invites i
            JOIN teams t ON i.from_team_id = t.id
            JOIN teams t2 ON i.to_team_id = t2.id
            WHERE i.match_id = ?
            ''', (match_id,)
        ).fetchall()
        
        # Format messages with string timestamps
        messages_list = []
        for m in messages:
            msg_dict = dict(m)
            if msg_dict.get('timestamp'):
                msg_dict['timestamp'] = str(msg_dict['timestamp'])
            messages_list.append(msg_dict)

        return jsonify({
            'match_id': match_id,
            'messages': messages_list,
            'strategies': {s['phase']: s['text_content'] for s in strategies},
            'drawings': {d['phase']: d['drawing_data_json'] for d in drawings},
            'teams': [dict(a) for a in teams],
            'invites': [dict(i) for i in invites]
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
        phase = data.get('phase', 'Autonomous') # Default if missing
        
        if phase not in ['Autonomous', 'Teleop', 'Endgame']:
            return jsonify({'error': 'Invalid phase'}), 400

        database = db.get_db()
        database.execute(
            'UPDATE drawings SET drawing_data_json = ?, last_updated = CURRENT_TIMESTAMP WHERE match_id = ? AND phase = ?',
            (drawing_data, match_id, phase)
        )
        database.commit()
        return jsonify({'message': 'Drawing saved'}), 200

    # --- Socket.IO Events ---

    @socketio.on('join')
    def on_join(data):
        room = str(data['match_id'])
        join_room(room)
        print(f"User joined room: {room}")

    @socketio.on('chat_message')
    def handle_chat(data):
        room = str(data['match_id'])
        database = get_db_for_socket()
        try:
            database.execute(
                'INSERT INTO messages (match_id, sender_team_id, content) VALUES (?, ?, ?)',
                (data['match_id'], data['team_id'], data['content'])
            )
            database.commit()
            emit('message', data, room=room)
        finally:
            database.close()

    @socketio.on('update_drawing')
    def handle_drawing(data):
        room = str(data['match_id'])
        database = get_db_for_socket()
        try:
            database.execute(
                'UPDATE drawings SET drawing_data_json = ?, last_updated = CURRENT_TIMESTAMP WHERE match_id = ? AND phase = ?',
                (data['drawing_data'], data['match_id'], data['phase'])
            )
            database.commit()
            emit('drawing_update', data, room=room, include_self=False)
        finally:
            database.close()

    @socketio.on('update_strategy')
    def handle_strategy(data):
        room = str(data['match_id'])
        database = get_db_for_socket()
        try:
            database.execute(
                'UPDATE strategies SET text_content = ? WHERE match_id = ? AND phase = ?',
                (data['text_content'], data['match_id'], data['phase'])
            )
            database.commit()
            emit('strategy_update', data, room=room, include_self=False)
        finally:
            database.close()

    return app



if __name__ == '__main__':
    app = create_app()
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)

import os
import functools
from dotenv import load_dotenv
load_dotenv(override=True)
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify, current_app
from flask_socketio import SocketIO, emit, join_room, leave_room
import resend
from werkzeug.security import generate_password_hash, check_password_hash
import db
import uuid
import random
import string
from datetime import datetime, timedelta
import socket
import threading

socketio = SocketIO()


def create_app(test_config=None):
    # Allow OAuth over HTTP for development (required for WiFi access/nip.io)
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE_URL=os.environ.get('DATABASE_URL'),
        UPLOAD_FOLDER=os.path.join(app.root_path, 'static', 'uploads'),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024, # 16MB limit
        # MAIL_* configs removed for Resend API
        MAIL_DEFAULT_SENDER=os.environ.get('MAIL_USERNAME'),
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False, # Required for HTTP
    )
    
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)


    # ensure the instance and upload folders exist
    try:
        os.makedirs(app.instance_path)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except OSError:
        pass

    db.init_app(app)
    socketio.init_app(app)
    
    # --- Background cleanup thread: expire old invites every 5 minutes ---
    def cleanup_expired_invites():
        import psycopg2
        import psycopg2.extras
        import time
        while True:
            time.sleep(300)  # 5 minutes
            try:
                db_url = app.config.get('DATABASE_URL') or os.environ.get('DATABASE_URL')
                conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)
                cur = conn.cursor()
                cur.execute(
                    "UPDATE invites SET status = 'Expired' WHERE status = 'Pending' AND expires_at IS NOT NULL AND expires_at < NOW()"
                )
                conn.commit()
                conn.close()
                print("[CLEANUP] Expired invite cleanup ran successfully.")
            except Exception as e:
                print(f"[CLEANUP] Error expiring invites: {e}")

    cleanup_thread = threading.Thread(target=cleanup_expired_invites, daemon=True)
    cleanup_thread.start()
    
    # --- Database Initialization ---
    with app.app_context():
        try:
            database = db.get_db()
            cur = database.cursor()
            # Check if users table exists
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'users'")
            if not cur.fetchone():
                print("[APP INIT] Tables missing. Please run 'flask init-db' if this is a new setup.")
                # Removed dangerous auto-init that was wiping data on slow connections
                # db.init_db() 
            
            # Match alliances migrations
            try:
                cur.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS creator_user_id INTEGER REFERENCES users(id)")
                cur.execute("ALTER TABLE match_alliances ADD COLUMN IF NOT EXISTS creator_user_id INTEGER REFERENCES users(id)")
                cur.execute("ALTER TABLE match_alliances ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
                # Invites table migrations
                cur.execute("ALTER TABLE invites ADD COLUMN IF NOT EXISTS from_user_id INTEGER REFERENCES users(id)")
                cur.execute("ALTER TABLE invites ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '20 minutes')")
                database.commit()
                print("Database migrations (matches, match_alliances & invites) applied successfully.")
            except Exception as inner_e:
                database.rollback()
                print(f"Migration notice (already applied or minor error): {inner_e}")

        except Exception as e:
            print(f"[APP INIT] Error checking/initializing database: {e}")

    # Brevo API Setup
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = os.environ.get('BREVO_API_KEY')
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

    import traceback
    @app.errorhandler(500)
    def handle_500(e):
        print("\n--- SERVER ERROR 500 ---")
        traceback.print_exc()
        print("------------------------\n")
        return jsonify(error="Internal Server Error"), 500

    def get_db_for_socket():
        # Socket handlers don't have 'g', so we create a temporary connection
        import psycopg2
        import psycopg2.extras
        db_url = app.config.get('DATABASE_URL') or os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)
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
        print(f"[AUTH DEBUG] Loaded user_id from session: {user_id}")

        if user_id is None:
            g.user = None
        else:
            cur = db.get_db().cursor()
            cur.execute(
                'SELECT u.id, u.email, u.name, u.team_id, u.is_verified, t.team_number, t.team_name '
                'FROM users u JOIN teams t ON u.team_id = t.id '
                'WHERE u.id = %s', (user_id,)
            )
            g.user = cur.fetchone()

    # --- Routes ---

    @app.route('/')
    def index():
        if g.user:
            return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html', 
                               current_user_id=g.user['id'],
                               current_team_id=g.user['team_id'],
                               current_team_number=g.user['team_number'])

    def send_email(subject, recipient, body):
        sender_email = os.environ.get('MAIL_USERNAME') or "hanishdasari007@gmail.com"
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": recipient}],
            sender={"name": "FRC Strategy Planner", "email": sender_email},
            subject=subject,
            text_content=body
        )
        try:
            api_instance.send_transac_email(send_smtp_email)
            return True
        except ApiException as e:
            print(f"Exception when calling TransactionalEmailsApi->send_transac_email: {e}")
            return False

    # Auth Utilities
    def validate_password(password):
        """
        Enforces password requirements:
        - Minimum 10 characters
        - At least one uppercase letter
        - At least one digit
        - At least one special character
        """
        if len(password) < 10 or len(password) > 128:
            return False, "Password must be between 10 and 128 characters."
        
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter."
            
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one number."
            
        import re
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "Password must contain at least one special character."
            
        return True, ""

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

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg)
            return redirect(url_for('register_page'))

        database = db.get_db()
        cur = database.cursor()
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        # Team logic
        cur.execute('SELECT id FROM teams WHERE team_number = %s', (team_number,))
        team = cur.fetchone()
        if not team:
            cur.execute(
                'INSERT INTO teams (team_number, team_name) VALUES (%s, %s) RETURNING id',
                (team_number, team_name)
            )
            team_id = cur.fetchone()['id']
        else:
            team_id = team['id']

        if user:
            if user['is_verified']:
                flash("Email already registered. Please login.")
                return redirect(url_for('index'))
            else:
                # Update existing unverified user
                cur.execute(
                    'UPDATE users SET name = %s, password_hash = %s, team_id = %s WHERE id = %s',
                    (name, generate_password_hash(password), team_id, user['id'])
                )
                user_id = user['id']
        else:
            # Create New User
            cur.execute(
                'INSERT INTO users (email, name, password_hash, team_id, is_verified) VALUES (%s, %s, %s, %s, %s) RETURNING id',
                (email, name, generate_password_hash(password), team_id, 0)
            )
            user_id = cur.fetchone()['id']
        
        database.commit()

        # Generate Verification Code
        cur.execute('DELETE FROM email_verifications WHERE user_id = %s', (user_id,))
        code = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        cur.execute(
            'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (%s, %s, %s)',
            (user_id, code, expires_at)
        )
        database.commit()

        # "Send" Email
        email_body = f"Hello {name},\n\nYour verification code is: {code}\n\nThis code will expire in 15 minutes."
        if send_email("Verify Your Email", email, email_body):
            flash("Registration successful. Please enter the verification code sent to your email.")
        else:
            flash("Registration successful, but there was an error sending the verification email. Our team is looking into it.")
            print(f"\n--- EMAIL VERIFICATION ERROR ---\nUser: {email}\nCode: {code}\n--------------------------------\n")
        
        session['pending_verification_user_id'] = user_id
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
        cur = database.cursor()
        cur.execute(
            'SELECT * FROM email_verifications WHERE user_id = %s AND code = %s AND expires_at > %s',
            (user_id, code, datetime.utcnow())
        )
        verification = cur.fetchone()

        if verification:
            cur.execute('UPDATE users SET is_verified = 1 WHERE id = %s', (user_id,))
            cur.execute('DELETE FROM email_verifications WHERE user_id = %s', (user_id,))
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
        cur = database.cursor()
        cur.execute('SELECT email FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        if user:
            code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.utcnow() + timedelta(minutes=15)
            cur.execute('DELETE FROM email_verifications WHERE user_id = %s', (user_id,))
            cur.execute(
                'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (%s, %s, %s)',
                (user_id, code, expires_at)
            )
            database.commit()
            email_body = f"Your new verification code is: {code}\n\nThis code will expire in 15 minutes."
            if send_email("New Verification Code", user['email'], email_body):
                flash("A new verification code has been sent.")
            else:
                flash("There was an error sending the verification email. Please try again later.")
        
        return redirect(url_for('verify_email_page'))

    @app.route('/auth/login', methods=('POST',))
    def auth_login():
        print(f"\n[LOGIN DEBUG] Received POST request to /auth/login from {request.remote_addr}")
        print(f"[LOGIN DEBUG] Headers: {dict(request.headers)}")
        email = request.form.get('email')
        password = request.form.get('password')
        print(f"[LOGIN DEBUG] Attempting login for email: {email}")

        database = db.get_db()
        cur = database.cursor()
        cur.execute(
            'SELECT * FROM users WHERE email = %s', (email,)
        )
        user = cur.fetchone()

        if user and user['password_hash'] and check_password_hash(user['password_hash'], password):
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
        cur = database.cursor()
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()

        if user:
            token = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=1)
            cur.execute(
                'INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)',
                (user['id'], token, expires_at)
            )
            database.commit()
            
            reset_link = url_for('reset_password_page', token=token, _external=True)
            email_body = f"Hi,\n\nYou requested a password reset. Click the link below to reset your password:\n{reset_link}\n\nIf you did not request this, please ignore this email."
            if send_email("Password Reset Request", email, email_body):
                flash("If that email is registered, a reset link has been sent.")
            else:
                flash("If that email is registered, a reset link has been sent. Please contact support if you don't receive it.")
                print(f"Password reset link for {email}: {reset_link}")
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

        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg)
            return redirect(url_for('reset_password_page', token=token))

        database = db.get_db()
        cur = database.cursor()
        cur.execute(
            'SELECT * FROM password_resets WHERE token = %s AND expires_at > %s',
            (token, datetime.utcnow())
        )
        reset = cur.fetchone()

        if reset:
            cur.execute(
                'UPDATE users SET password_hash = %s, is_verified = 0 WHERE id = %s',
                (generate_password_hash(password), reset['user_id'])
            )
            cur.execute('DELETE FROM password_resets WHERE id = %s', (reset['id'],))
            database.commit()
            flash("Password reset successful. Please verify your email again.")
            session['pending_verification_user_id'] = reset['user_id']
            
            # Send new OTP
            code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.utcnow() + timedelta(minutes=15)
            cur.execute('INSERT INTO email_verifications (user_id, code, expires_at) VALUES (%s, %s, %s)', (reset['user_id'], code, expires_at))
            database.commit()
            
            cur.execute('SELECT email FROM users WHERE id = %s', (reset['user_id'],))
            user_email = cur.fetchone()['email']
            send_email("New Verification Code", user_email, f"Your verification code is: {code}")
            
            return redirect(url_for('verify_email_page'))
        
        flash("Invalid or expired reset token.")
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
        cur = database.cursor()
        try:
            # Delete associated records (manual cascade for safety)
            cur.execute('DELETE FROM email_verifications WHERE user_id = %s', (user_id,))
            cur.execute('DELETE FROM password_resets WHERE user_id = %s', (user_id,))
            cur.execute('DELETE FROM users WHERE id = %s', (user_id,))
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
        cur = database.cursor()
        
        # Team logic
        cur.execute('SELECT id FROM teams WHERE team_number = %s', (team_number,))
        team = cur.fetchone()
        if not team:
            cur.execute(
                'INSERT INTO teams (team_number, team_name) VALUES (%s, %s) RETURNING id',
                (team_number, team_name)
            )
            team_id = cur.fetchone()['id']
        else:
            team_id = team['id']
            # Update team name if it already exists (allows fixing typos)
            cur.execute('UPDATE teams SET team_name = %s WHERE id = %s', (team_name, team_id))
        
        # Update User
        cur.execute(
            'UPDATE users SET name = %s, team_id = %s WHERE id = %s',
            (name, team_id, g.user['id'])
        )

        # Password update
        if new_password:
            is_valid, error_msg = validate_password(new_password)
            if not is_valid:
                flash(error_msg)
                return redirect(url_for('profile_page'))

            # Record user ID and email before clearing session
            user_id = g.user['id']
            user_email = g.user['email']

            cur.execute(
                'UPDATE users SET password_hash = %s, is_verified = 0 WHERE id = %s',
                (generate_password_hash(new_password), user_id)
            )
            
            # Generate and send verification code immediately
            code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.utcnow() + timedelta(minutes=15)
            cur.execute('DELETE FROM email_verifications WHERE user_id = %s', (user_id,))
            cur.execute(
                'INSERT INTO email_verifications (user_id, code, expires_at) VALUES (%s, %s, %s)',
                (user_id, code, expires_at)
            )
            database.commit()
            
            email_body = f"You updated your password. Your verification code is: {code}\n\nThis code will expire in 15 minutes."
            if send_email("Password Updated - Verify Email", user_email, email_body):
                flash("Password updated! A verification code has been sent to your email.")
            else:
                flash("Password updated! There was an error sending the verification email, but a code has been generated. Our team is looking into it.")
                print(f"\n--- EMAIL VERIFICATION ERROR (Profile Update) ---\nUser: {user_email}\nCode: {code}\n----------------------------------------------\n")

            session.clear() # Force re-login and verification
            session['pending_verification_user_id'] = user_id
            return redirect(url_for('verify_email_page'))

        database.commit()
        flash("Profile updated successfully!")
        return redirect(url_for('profile_page'))

    # --- Match & Invitation Management ---

    @app.route('/api/matches', methods=('GET', 'POST'))
    @login_required
    def matches():
        database = db.get_db()
        cur = database.cursor()
        if request.method == 'POST':
            data = request.get_json()
            match_number = data.get('match_number')
            match_type = data.get('match_type', 'Qualification')

            if not match_number:
                return jsonify({'error': 'Match number is required'}), 400

            cur.execute(
                'INSERT INTO matches (match_number, match_type, creator_team_id, creator_user_id) VALUES (%s, %s, %s, %s) RETURNING id',
                (match_number, match_type, g.user['team_id'], g.user['id'])
            )
            match_id = cur.fetchone()['id']
            
            # Creator is always Red for now
            cur.execute(
                'INSERT INTO match_alliances (match_id, team_id, user_id, alliance_color, last_seen, joined_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)',
                (match_id, g.user['team_id'], g.user['id'], 'Red') 
            )
            
            # Create empty strategy/drawing entries
            for phase in ['Autonomous', 'Teleop', 'Endgame']:
                cur.execute(
                     'INSERT INTO strategies (match_id, phase) VALUES (%s, %s)',
                     (match_id, phase)
                )
                cur.execute(
                     'INSERT INTO drawings (match_id, phase) VALUES (%s, %s)',
                     (match_id, phase)
                )

            database.commit()
            return jsonify({'message': 'Match created', 'id': match_id}), 201

        # GET: List matches for the user's team
        cur.execute(
            '''
            SELECT m.id, m.match_number, m.match_type, t.team_number as creator_team_number, m.creator_team_id
            FROM matches m
            JOIN teams t ON m.creator_team_id = t.id
            JOIN match_alliances ma ON m.id = ma.match_id
            WHERE ma.user_id = %s
            ORDER BY m.id DESC
            ''', (g.user['id'],)
        )
        matches = cur.fetchall()
        
        return jsonify([dict(row) for row in matches])

    @app.route('/api/matches/<int:match_id>', methods=('DELETE',))
    @login_required
    def delete_match(match_id):
        database = db.get_db()
        cur = database.cursor()
        
        # Check if the user's team is the creator or part of the match
        cur.execute(
            'SELECT creator_team_id FROM matches WHERE id = %s', (match_id,)
        )
        match = cur.fetchone()
        
        if not match:
            return jsonify({'error': 'Match not found'}), 404
            
        # Relaxed check: as long as match exists and user is logged in (handled by decorator), allow deletion.
        # User requested the delete button/ability to be available to everyone at all times.

        try:
            # Broadcast deletion to all users in the match room BEFORE deleting the match
            # so they receive the event before the room is destroyed or invalid
            socketio.emit('match_deleted', {'match_id': match_id}, room=str(match_id))
            
            # Find all teams involved (alliances and invites) to broadcast to their dashboards
            cur.execute('''
                SELECT DISTINCT team_id FROM match_alliances WHERE match_id = %s
                UNION
                SELECT DISTINCT to_team_id FROM invites WHERE match_id = %s
            ''', (match_id, match_id))
            involved_teams = cur.fetchall()
            
            for team in involved_teams:
                team_room_name = f"team_{team['team_id']}"
                socketio.emit('match_deleted', {'match_id': match_id}, room=team_room_name)
            
            # Cascading deletion
            cur.execute('DELETE FROM messages WHERE match_id = %s', (match_id,))
            cur.execute('DELETE FROM strategies WHERE match_id = %s', (match_id,))
            cur.execute('DELETE FROM drawings WHERE match_id = %s', (match_id,))
            cur.execute('DELETE FROM invites WHERE match_id = %s', (match_id,))
            cur.execute('DELETE FROM match_alliances WHERE match_id = %s', (match_id,))
            cur.execute('DELETE FROM matches WHERE id = %s', (match_id,))
            
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
        cur = database.cursor()
        
        # Find the team
        cur.execute('SELECT id FROM teams WHERE team_number = %s', (to_team_number,))
        to_team = cur.fetchone()
        if not to_team:
             return jsonify({'error': 'Team not found'}), 404
             
        # Check if already in match (but allow inviting own team for notifications)
        cur.execute(
            'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
            (match_id, to_team['id'])
        )
        existing = cur.fetchone()
        
        if existing and to_team['id'] != g.user['team_id']:
             return jsonify({'error': 'Team already in match'}), 400

        # Set expiry 20 minutes from now
        expires_at = datetime.utcnow() + timedelta(minutes=20)

        cur.execute(
            'INSERT INTO invites (match_id, from_team_id, to_team_id, from_user_id, expires_at) VALUES (%s, %s, %s, %s, %s) RETURNING id',
            (match_id, g.user['team_id'], to_team['id'], g.user['id'], expires_at)
        )
        invite_id = cur.fetchone()['id']
        database.commit()
        
        # Emit real-time invite via Socket.IO
        cur.execute('SELECT match_number FROM matches WHERE id = %s', (match_id,))
        match_info = cur.fetchone()
        
        # Get from team name
        cur.execute('SELECT team_name FROM teams WHERE id = %s', (g.user['team_id'],))
        from_team_name = cur.fetchone()['team_name']

        socketio.emit('new_invite', {
            'id': invite_id,
            'match_id': match_id,
            'match_number': match_info['match_number'],
            'from_team_number': g.user['team_number'],
            'from_team_name': from_team_name,
            'from_user_name': g.user['name'],
            'from_user_id': g.user['id'],
            'expires_at': expires_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'is_same_team': (to_team['id'] == g.user['team_id'])
        }, room=f"team_{to_team['id']}")
        
        # Also notify everyone in the match room to refresh their invite lists
        socketio.emit('refresh_data', {'match_id': int(match_id)}, room=str(match_id))

        return jsonify({'message': 'Invite sent'}), 201
        
    @app.route('/api/invites/pending', methods=('GET',))
    @login_required
    def get_invites():
        database = db.get_db()
        cur = database.cursor()
        
        # Aggressively delete any Pending invites older than 20 minutes
        # PostgreSQL syntax: NOW() - INTERVAL '20 minutes'
        cur.execute('''
            DELETE FROM invites 
            WHERE status = 'Pending' 
            AND created_at <= NOW() - INTERVAL '20 minutes'
        ''')
        database.commit()
        
        cur.execute(
            '''
            SELECT i.id, i.match_id, m.match_number, t.team_number as from_team,
                   u.name as from_user_name, t.team_name as from_team_name,
                   i.from_user_id,
                   (i.from_team_id = i.to_team_id) as is_same_team
            FROM invites i
            JOIN matches m ON i.match_id = m.id
            JOIN teams t ON i.from_team_id = t.id
            LEFT JOIN users u ON i.from_user_id = u.id
            WHERE i.to_team_id = %s AND i.status = 'Pending'
            AND (i.from_user_id IS NULL OR i.from_user_id != %s)
            ''', (g.user['team_id'], g.user['id'])
        )
        invites = cur.fetchall()
        return jsonify([dict(row) for row in invites])

    @app.route('/api/invites/<int:invite_id>/respond', methods=('POST',))
    @login_required
    def respond_invite(invite_id):
        data = request.get_json()
        status = data.get('status') # 'Accepted' or 'Declined'
        
        if status not in ['Accepted', 'Declined']:
             return jsonify({'error': 'Invalid status'}), 400
             
        database = db.get_db()
        cur = database.cursor()
        cur.execute('SELECT * FROM invites WHERE id = %s', (invite_id,))
        invite = cur.fetchone()
        
        if not invite or invite['to_team_id'] != g.user['team_id']:
            return jsonify({'error': 'Invite not found or not for you'}), 404

        # Block responses to expired invites
        if invite['status'] == 'Expired' or (invite.get('expires_at') and datetime.utcnow() > invite['expires_at']):
            return jsonify({'error': 'This invite has expired and can no longer be accepted or declined.'}), 410
            
        cur.execute('UPDATE invites SET status = %s WHERE id = %s', (status, invite_id))
        
        if status == 'Accepted':
            # Add to match alliances, preventing duplicates for the SPECIFIC user
            cur.execute(
                '''
                INSERT INTO match_alliances (match_id, team_id, user_id, alliance_color, last_seen, joined_at) 
                SELECT %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM match_alliances WHERE match_id = %s AND user_id = %s
                )
                ''',
                (invite['match_id'], g.user['team_id'], g.user['id'], 'Blue', invite['match_id'], g.user['id'])
            )
        
        database.commit()
        
        # Notify both teams via socket to refresh their views
        socketio.emit('refresh_data', {'match_id': invite['match_id']}, room=str(invite['match_id']))
        
        return jsonify({'message': f'Invite {status}', 'match_id': invite['match_id'], 'match_url': f'/match/{invite["match_id"]}'}), 200

    @app.route('/match/<int:match_id>')
    @login_required
    def match_room(match_id):
        database = db.get_db()
        cur = database.cursor()
        # Verify access
        cur.execute(
            'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
            (match_id, g.user['team_id'])
        )
        access = cur.fetchone()

        if not access:
            flash("You do not have access to this match.")
            return redirect(url_for('dashboard'))

        # Pass current user info to template for JS
        return render_template('match.html', 
                             match_id=match_id, 
                             current_team_number=g.user['team_number'],
                             current_user_id=g.user['id'],
                             current_team_id=g.user['team_id'])

    # --- Collaboration API (Polling) ---

    @app.route('/api/matches/<int:match_id>/data')
    @login_required
    def get_match_data(match_id):
        database = db.get_db()
        cur = database.cursor()
        
        # Check access and update Last Seen
        print(f"DEBUG: Getting match data for {match_id}")
        if not g.user:
            return jsonify({'error': 'Not logged in'}), 401
            
        cur.execute(
            'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
            (match_id, g.user['team_id'])
        )
        access = cur.fetchone()
        
        print(f"DEBUG: Access found? {access is not None}")
        if not access:
            print(f"DEBUG: Unauthorized match access for match {match_id}")
            return jsonify({'error': 'Unauthorized'}), 403

        # Update last_seen
        cur.execute(
            'UPDATE match_alliances SET last_seen = CURRENT_TIMESTAMP WHERE id = %s',
            (access['id'],)
        )
        database.commit()

        # Strategies
        cur.execute(
            'SELECT phase, text_content FROM strategies WHERE match_id = %s',
            (match_id,)
        )
        strategies = cur.fetchall()
        
        # Drawings - Return all phases
        cur.execute(
            'SELECT phase, drawing_data_json FROM drawings WHERE match_id = %s',
            (match_id,)
        )
        drawings = cur.fetchall()
        
        # Teams in this match with Active Status
        # Active if seen in last 30 seconds
        cur.execute(
            '''
            SELECT t.team_number, t.team_name, ma.alliance_color, ma.last_seen,
                   (CASE WHEN ma.last_seen IS NOT NULL 
                         THEN (EXTRACT(EPOCH FROM (NOW() - ma.last_seen))) < 30 
                         ELSE FALSE END) as is_active
            FROM match_alliances ma
            JOIN teams t ON ma.team_id = t.id
            WHERE ma.match_id = %s
            ''', (match_id,)
        )
        teams = cur.fetchall()

        # Invites — only return non-expired pending invites
        cur.execute(
            '''
            SELECT i.*, t.team_number as from_team_number, t2.team_number as to_team_number
            FROM invites i
            JOIN teams t ON i.from_team_id = t.id
            JOIN teams t2 ON i.to_team_id = t2.id
            WHERE i.match_id = %s
            AND (i.status != 'Pending' OR (i.expires_at IS NULL OR i.expires_at > NOW()))
            ''', (match_id,)
        )
        invites = cur.fetchall()
        
        # Ensure all phases are present in the dictionaries
        strategies_dict = {phase: '' for phase in ['Autonomous', 'Teleop', 'Endgame']}
        for s in strategies:
            strategies_dict[s['phase']] = s['text_content'] or ''
            
        drawings_dict = {phase: [] for phase in ['Autonomous', 'Teleop', 'Endgame']}
        for d in drawings:
            # psycopg2 automatically converts jsonb to Python objects
            val = d['drawing_data_json']
            if isinstance(val, str):
                try:
                    import json
                    val = json.loads(val)
                except:
                    val = []
            drawings_dict[d['phase']] = val if val is not None else []

        def serialize_row(row):
            """Convert a psycopg2 row to a JSON-safe dict."""
            d = dict(row)
            for k, v in d.items():
                if hasattr(v, 'isoformat'):
                    d[k] = v.strftime('%Y-%m-%dT%H:%M:%SZ')
            return d

        print(f"DEBUG: Match {match_id} data - Strategies: {len(strategies)}, Drawings: {len(drawings)}, Teams: {len(teams)}, Invites: {len(invites)}")
        return jsonify({
            'match_id': match_id,
            'strategies': strategies_dict,
            'drawings': drawings_dict,
            'teams': [serialize_row(a) for a in teams],
            'invites': [serialize_row(i) for i in invites]
        })

    @app.route('/api/matches/<int:match_id>/strategy', methods=('POST',))
    @login_required
    def update_strategy(match_id):
        data = request.get_json()
        phase = data.get('phase')
        text_content = data.get('text_content')
        
        if phase not in ['Autonomous', 'Teleop', 'Endgame']:
            return jsonify({'error': 'Invalid phase'}), 400
            
        database = db.get_db()
        cur = database.cursor()
        cur.execute(
            'UPDATE strategies SET text_content = %s WHERE match_id = %s AND phase = %s',
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
        cur = database.cursor()
        cur.execute(
            'UPDATE drawings SET drawing_data_json = %s, last_updated = CURRENT_TIMESTAMP WHERE match_id = %s AND phase = %s',
            (drawing_data, match_id, phase)
        )
        database.commit()
        return jsonify({'message': 'Drawing saved'}), 200

    @app.route('/api/teams/<int:team_number>/status')
    @login_required
    def team_status(team_number):
        database = db.get_db()
        cur = database.cursor()
        # Check if team exists and if any user from that team has been seen recently
        cur.execute('SELECT id FROM teams WHERE team_number = %s', (team_number,))
        team = cur.fetchone()
        if not team:
            return jsonify({'active': False, 'exists': False})
        
        # Check if any alliance record for this team has been updated in the last 60 seconds
        cur.execute(
            '''
            SELECT 1 FROM match_alliances 
            WHERE team_id = %s AND (EXTRACT(EPOCH FROM (NOW() - last_seen)) < 60)
            LIMIT 1
            ''', (team['id'],)
        )
        active = cur.fetchone()
        
        return jsonify({'active': bool(active), 'exists': True})

    # --- Socket.IO Events ---

    @socketio.on('join')
    def on_join(data):
        match_id = data.get('match_id')
        user_id = session.get('user_id')
        
        if not user_id:
            return

        with app.app_context():
            # Get user's team_id
            database = db.get_db()
            cur = database.cursor()
            cur.execute('SELECT team_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if not user:
                return
            
            # Join personal team room for invites ALWAYS
            join_room(f"team_{user['team_id']}")
            print(f"User {user_id} joined team_room: team_{user['team_id']}")
            
            # Verify match access if match_id provided
            if match_id:
                cur.execute(
                    'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
                    (match_id, user['team_id'])
                )
                access = cur.fetchone()

                if access:
                    room = str(match_id)
                    join_room(room)
                    print(f"User {user_id} joined match room: {room}")
                else:
                    print(f"User {user_id} denied access to match room: {match_id}")

    @socketio.on('update_drawing')
    def handle_drawing(data):
        match_id = data.get('match_id')
        user_id = session.get('user_id')
        if not match_id or not user_id: return

        room = str(match_id)
        database = get_db_for_socket()
        cur = database.cursor()
        try:
            # Verify access
            cur.execute('SELECT team_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if not user: return
            
            cur.execute(
                'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
                (match_id, user['team_id'])
            )
            access = cur.fetchone()

            if not access: return

            # New: Support both full state overwrite (legacy/undo) and incremental updates
            phase = data.get('phase', 'Autonomous')
            drawing_data = data.get('drawing_data')

            cur.execute(
                '''
                INSERT INTO drawings (match_id, phase, drawing_data_json) 
                VALUES (%s, %s, %s)
                ON CONFLICT (match_id, phase) 
                DO UPDATE SET drawing_data_json = EXCLUDED.drawing_data_json, last_updated = CURRENT_TIMESTAMP
                ''',
                (match_id, phase, drawing_data)
            )
            print(f"DEBUG: Successfully persisted drawing for match {match_id}, phase {phase}")
            database.commit()
            emit('drawing_update', data, room=room, include_self=False)
        finally:
            database.close()

    @socketio.on('start_path')
    def handle_start_path(data):
        match_id = data.get('match_id')
        emit('path_started', data, room=str(match_id), include_self=False)

    @socketio.on('add_points')
    def handle_add_points(data):
        match_id = data.get('match_id')
        emit('points_added', data, room=str(match_id), include_self=False)

    @socketio.on('finish_path')
    def handle_finish_path(data):
        match_id = data.get('match_id')
        user_id = session.get('user_id')
        if not match_id or not user_id: return
        handle_drawing(data)

    @socketio.on('update_strategy')
    def handle_strategy(data):
        match_id = data.get('match_id')
        user_id = session.get('user_id')
        if not match_id or not user_id: return

        room = str(match_id)
        database = get_db_for_socket()
        cur = database.cursor()
        try:
            # Verify access
            cur.execute('SELECT team_id FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
            if not user: return
            
            cur.execute(
                'SELECT id FROM match_alliances WHERE match_id = %s AND team_id = %s',
                (match_id, user['team_id'])
            )
            access = cur.fetchone()

            if not access: return

            cur.execute(
                '''
                INSERT INTO strategies (match_id, phase, text_content) 
                VALUES (%s, %s, %s)
                ON CONFLICT (match_id, phase) 
                DO UPDATE SET text_content = EXCLUDED.text_content
                ''',
                (match_id, data['phase'], data['strategy_text'])
            )
            database.commit()
            emit('strategy_update', data, room=room, include_self=False)
        finally:
            database.close()

    return app



if __name__ == '__main__':
    def get_local_ip():
        try:
            # Create a dummy socket to find the primary interface IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    local_ip = get_local_ip()
    print("\n" + "="*50)
    print("FRC STRATEGY PLATFORM - NETWORK ACCESS INFO")
    print(f"Server is running and accessible on your Wi-Fi!")
    print(f"Teammates can join at: http://{local_ip}:5000")
    print("="*50 + "\n")

    app = create_app()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

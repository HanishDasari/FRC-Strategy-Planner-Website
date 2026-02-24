
import unittest
import os
import json
from app import create_app
import db

class FRCFlaskTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = 'test_backend.sqlite'
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'GOOGLE_CLIENT_ID': 'test',
            'GOOGLE_CLIENT_SECRET': 'test'
        })
        self.client = self.app.test_client()
        self.runner = self.app.test_cli_runner()

        with self.app.app_context():
            db.init_db()
            # Create a dummy team and user
            database = db.get_db()
            database.execute('INSERT INTO teams (team_number, team_name) VALUES (254, "Cheesy Poofs")')
            database.execute('INSERT INTO teams (team_number, team_name) VALUES (1678, "Citrus Circuits")')
            database.execute('INSERT INTO users (google_id, email, name, team_id) VALUES ("g123", "test@example.com", "Test User", 1)')
            database.commit()

    def tearDown(self):
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            os.remove(self.db_path)

    def login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1

    def test_match_creation_and_drawings(self):
        self.login()
        # Create Match
        res = self.client.post('/api/matches', json={
            'match_number': 1,
            'match_type': 'Qualification'
        })
        self.assertEqual(res.status_code, 201)
        match_id = res.json['id']

        # Verify 3 drawing rows created
        with self.app.app_context():
            database = db.get_db()
            drawings = database.execute('SELECT phase FROM drawings WHERE match_id = ?', (match_id,)).fetchall()
            phases = [row['phase'] for row in drawings]
            self.assertIn('Autonomous', phases)
            self.assertIn('Teleop', phases)
            self.assertIn('Endgame', phases)
            self.assertEqual(len(phases), 3)

        # Verify API returns them correctly
        res = self.client.get(f'/api/matches/{match_id}/data')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertIn('drawings', data)
        self.assertIn('Autonomous', data['drawings'])

        # Test Last Seen / Active Status
        # The GET request above should have updated last_seen
        with self.app.app_context():
            database = db.get_db()
            alliance = database.execute('SELECT last_seen FROM match_alliances WHERE match_id = ? AND team_id = 1', (match_id,)).fetchone()
            self.assertIsNotNone(alliance['last_seen'])

        # Test Updating Drawing
        drawing_data = json.dumps([{'color': 'red', 'points': [{'x': 10, 'y': 10}]}])
        res = self.client.post(f'/api/matches/{match_id}/drawing', json={
            'phase': 'Autonomous',
            'drawing_data': drawing_data
        })
        self.assertEqual(res.status_code, 200)

        # Verify only Autonomous updated
        with self.app.app_context():
             database = db.get_db()
             auto = database.execute("SELECT drawing_data_json FROM drawings WHERE match_id = ? AND phase = 'Autonomous'", (match_id,)).fetchone()
             teleop = database.execute("SELECT drawing_data_json FROM drawings WHERE match_id = ? AND phase = 'Teleop'", (match_id,)).fetchone()
             
             self.assertEqual(auto['drawing_data_json'], drawing_data)
             self.assertEqual(teleop['drawing_data_json'], '[]')

    def test_invites(self):
        self.login()
        # Create Match
        res = self.client.post('/api/matches', json={'match_number': 2, 'match_type': 'Qualification'})
        match_id = res.json['id']

        # Invite Team 1678 (id 2)
        res = self.client.post('/api/invites', json={
            'match_id': match_id,
            'to_team_number': 1678
        })
        self.assertEqual(res.status_code, 201)

        # Verify Invite
        with self.app.app_context():
            database = db.get_db()
            invite = database.execute('SELECT * FROM invites WHERE match_id = ?', (match_id,)).fetchone()
            self.assertEqual(invite['to_team_id'], 2)
            self.assertEqual(invite['status'], 'Pending')

if __name__ == '__main__':
    unittest.main()

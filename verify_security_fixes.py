import unittest
import os
import json
from app import create_app
import db

class SecurityFixesTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = 'test_security.sqlite'
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'GOOGLE_CLIENT_ID': 'test',
            'GOOGLE_CLIENT_SECRET': 'test'
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.init_db()
            database = db.get_db()
            # Team 1: Creator
            database.execute('INSERT INTO teams (team_number, team_name) VALUES (111, "Team One")')
            # Team 2: Invited
            database.execute('INSERT INTO teams (team_number, team_name) VALUES (222, "Team Two")')
            # Users
            database.execute('INSERT INTO users (email, team_id, is_verified) VALUES ("u1@test.com", 1, 1)')
            database.execute('INSERT INTO users (email, team_id, is_verified) VALUES ("u2@test.com", 2, 1)')
            database.commit()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def login(self, user_id):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id

    def test_security_and_creation(self):
        # 1. Login as User 1 (Team 1)
        self.login(1)
        
        # 2. Create Match
        res = self.client.post('/api/matches', json={
            'match_number': 100,
            'match_type': 'Qualification'
        })
        self.assertEqual(res.status_code, 201)
        match_id = res.json['id']
        
        # 3. Invite Team 222 (Team 2)
        res = self.client.post('/api/invites', json={
            'match_id': match_id,
            'to_team_number': 222
        })
        self.assertEqual(res.status_code, 201)
        
        # 4. Verify Match List for User 1 includes creator_team_id
        res = self.client.get('/api/matches')
        self.assertEqual(res.status_code, 200)
        matches = res.json
        self.assertEqual(matches[0]['creator_team_id'], 1)
        
        # 5. Login as User 2 (Team 2)
        self.login(2)
        
        # 6. Accept Invite
        # We need the invite ID. Let's get it.
        with self.app.app_context():
            invite = db.get_db().execute('SELECT id FROM invites WHERE to_team_id = 2').fetchone()
            invite_id = invite['id']
            
        res = self.client.post(f'/api/invites/{invite_id}/respond', json={'status': 'Accepted'})
        self.assertEqual(res.status_code, 200)
        
        # 7. Attempt to Delete Match as User 2 (Team 2)
        res = self.client.delete(f'/api/matches/{match_id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['message'], 'Match deleted successfully')
        
if __name__ == '__main__':
    unittest.main()

import requests

BASE_URL = 'http://127.0.0.1:5000'
SESSION = requests.Session()

def test_auth():
    print("Testing Auth...")
    # Register
    res = SESSION.post(f'{BASE_URL}/auth/register', json={
        'username': 'testuser',
        'password': 'password',
        'team_number': 254,
        'team_name': 'Cheesy Poofs'
    })
    if res.status_code == 201:
        print("Registration successful")
    elif res.status_code == 400 and 'already registered' in res.text:
         print("User already registered (expected on re-run)")
    else:
        print(f"Registration failed: {res.text}")
        return False

    # Login
    res = SESSION.post(f'{BASE_URL}/auth/login', json={
        'username': 'testuser',
        'password': 'password'
    })
    if res.status_code == 200:
        print("Login successful")
    else:
        print(f"Login failed: {res.text}")
        return False
    return True

def test_match_flow():
    print("\nTesting Match Flow...")
    # Create Match
    res = SESSION.post(f'{BASE_URL}/api/matches', json={
        'match_number': 1,
        'match_type': 'Qualification'
    })
    
    match_id = None
    if res.status_code == 201:
        data = res.json()
        match_id = data['id']
        print(f"Match created: ID {match_id}")
    else:
        print(f"Match creation failed: {res.text}")
        return False

    # Get Match Data
    res = SESSION.get(f'{BASE_URL}/api/matches/{match_id}/data')
    if res.status_code == 200:
        print("Got match data")
    else:
        print(f"Failed to get match data: {res.text}")
        return False

    # Send Message
    res = SESSION.post(f'{BASE_URL}/api/matches/{match_id}/messages', json={
        'content': 'Hello Alliance!'
    })
    if res.status_code == 201:
        print("Message sent")
    else:
        print(f"Message send failed: {res.text}")
        return False
        
    # Update Strategy
    res = SESSION.post(f'{BASE_URL}/api/matches/{match_id}/strategy', json={
        'phase': 'Autonomous',
        'text_content': 'Score 4 coral on L4'
    })
    if res.status_code == 200:
        print("Strategy updated")
    else:
        print(f"Strategy update failed: {res.text}")
        return False
    
    return True

if __name__ == '__main__':
    try:
        if test_auth():
            test_match_flow()
    except requests.exceptions.ConnectionError:
        print("Error: Flask server is not running. Please run 'flask --app app run' in a separate terminal.")

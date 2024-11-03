import json
from flask import Flask, render_template, jsonify, request, redirect, url_for, make_response
import math
import os
import redis
from redis.connection import SSLConnection
import uuid
import random
import string

app = Flask(__name__)

# Set up Redis connection with SSL parameters
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
if redis_url.startswith('redis://'):
    redis_url = redis_url.replace('redis://', 'rediss://', 1)

redis_client = redis.Redis.from_url(
    redis_url,
    connection_class=SSLConnection,
    ssl_cert_reqs=None
)

# Horizon calculation parameters
VIEWER_HEIGHT_FT = 6
SQUARE_SIZE_MILES = 0.1

# Calculate visibility range
def get_visibility_range():
    horizon_distance_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT)
    visibility_range_squares = int(horizon_distance_miles / SQUARE_SIZE_MILES)
    return visibility_range_squares

# Session management functions
def get_session_id():
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id

def get_session_data(session_id):
    session_data_json = redis_client.get(f'session:{session_id}')
    if session_data_json:
        return json.loads(session_data_json)
    else:
        return {}

def save_session_data(session_id, session_data, expire_seconds=3600):
    redis_client.set(f'session:{session_id}', json.dumps(session_data), ex=expire_seconds)

def generate_lobby_code():
    """Generates a unique 6-character lobby code."""
    while True:
        lobby_code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        if not redis_client.exists(lobby_code):
            return lobby_code

@app.route('/')
def index():
    session_id = get_session_id()
    # Always render index.html
    response = make_response(render_template('index.html'))
    response.set_cookie('session_id', session_id)
    return response

@app.route('/start_game', methods=['POST'])
def start_game():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    player_name = data.get('player_name', 'Player1')
    # Generate a unique lobby code
    lobby_code = generate_lobby_code()
    session_data = {'lobby_code': lobby_code, 'player_name': player_name}

    # Initialize game state in Redis
    game_state = {
        'players': {player_name: {'x': 0, 'y': 0}},
        'previous_positions': [],
        'max_players': 4,  # You can adjust this as needed
        'player_names': [player_name],
        'ready_statuses': [False],
        'game_started': False
    }
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)  # Expires in 1 hour

    # Save session data
    save_session_data(session_id, session_data)

    response = jsonify({
        'message': 'Lobby created',
        'lobby_code': lobby_code,
        'player_names': game_state['player_names'],
        'ready_statuses': game_state['ready_statuses'],
        'max_players': game_state['max_players']
    })
    response.set_cookie('session_id', session_id)
    return response

@app.route('/join_game', methods=['POST'])
def join_game():
    session_id = get_session_id()
    data = request.get_json()
    lobby_code = data.get('lobby_code')
    player_name = data.get('player_name', f'Player{uuid.uuid4().hex[:4]}')
    if not lobby_code:
        return jsonify({'status': 'error', 'message': 'No lobby code provided'}), 400

    game_state_json = redis_client.get(lobby_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Invalid lobby code'}), 400

    game_state = json.loads(game_state_json)

    if game_state.get('game_started'):
        return jsonify({'status': 'error', 'message': 'Game has already started'}), 400

    if len(game_state['player_names']) >= game_state['max_players']:
        return jsonify({'status': 'error', 'message': 'Lobby is full'}), 400

    # Add player to the game state
    game_state['players'][player_name] = {'x': 0, 'y': 0}
    game_state['player_names'].append(player_name)
    game_state['ready_statuses'].append(False)
    # Update game state in Redis
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)  # Reset expiration time

    # Update session data
    session_data = {'lobby_code': lobby_code, 'player_name': player_name}
    save_session_data(session_id, session_data)

    response = jsonify({
        'message': f'Joined lobby {lobby_code}',
        'lobby_code': lobby_code,
        'player_names': game_state['player_names'],
        'ready_statuses': game_state['ready_statuses'],
        'max_players': game_state['max_players']
    })
    response.set_cookie('session_id', session_id)
    return response

# ... rest of your code remains the same, ensure you add 'ex=3600' where you set the game state in Redis

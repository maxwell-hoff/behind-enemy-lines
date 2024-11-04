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
def get_visibility_range(x, y):
    VIEWER_HEIGHT_FT = 6  # Viewer height
    SQUARE_SIZE_MILES = 0.1  # Size of each square in miles

    # Compute tilt angle at the current position
    theta = tilt_angle(x, y)
    sin_theta = math.sin(theta)

    # Compute horizon distances in downhill and uphill directions
    d_downhill_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT * (1 + sin_theta))
    d_uphill_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT * (1 - sin_theta))

    # Convert distances to squares
    a_squares = int(d_downhill_miles / SQUARE_SIZE_MILES)
    b_squares = int(d_uphill_miles / SQUARE_SIZE_MILES)

    # Return visibility ranges and tilt direction
    phi = tilt_direction(x, y)
    return a_squares, b_squares, phi

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

def terrain_height(x, y):
    # Amplitude of the hills (in feet)
    A = 30  # Maximum height variation
    # Wavelength of the hills (in squares)
    wavelength = 50  # Adjust as needed
    # Convert x and y to radians for the sine function
    k = (2 * math.pi) / wavelength
    # Terrain height function
    return A * math.sin(k * x) * math.sin(k * y)

def terrain_gradient(x, y):
    A = 30
    wavelength = 50
    k = (2 * math.pi) / wavelength
    # Partial derivatives (slopes in x and y)
    dh_dx = A * k * math.cos(k * x) * math.sin(k * y)
    dh_dy = A * k * math.sin(k * x) * math.cos(k * y)
    return dh_dx, dh_dy

def tilt_angle(x, y):
    dh_dx, dh_dy = terrain_gradient(x, y)
    # Gradient magnitude
    gradient_magnitude = math.sqrt(dh_dx**2 + dh_dy**2)
    # Tilt angle in radians
    theta = math.atan(gradient_magnitude)
    return theta

def tilt_direction(x, y):
    dh_dx, dh_dy = terrain_gradient(x, y)
    # Direction angle in radians (0 = east, pi/2 = north)
    phi = math.atan2(dh_dy, dh_dx)
    return phi

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
        'position': {'x': 0, 'y': 0},
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

@app.route('/game')
def game():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    if 'lobby_code' not in session_data:
        return redirect(url_for('index'))
    response = make_response(render_template('game.html'))
    response.set_cookie('session_id', session_id)
    return response

@app.route('/visible_cells')
def visible_cells():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    if 'lobby_code' not in session_data:
        return jsonify({'status': 'error', 'message': 'Not in a game'}), 400

    lobby_code = session_data['lobby_code']

    # Load game state from Redis
    game_state_json = redis_client.get(lobby_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)

    position = game_state['position']
    center_x = position['x']
    center_y = position['y']

    # Get the adjusted visibility ranges
    a_squares, b_squares, phi = get_visibility_range(center_x, center_y)

    # Rotate the ellipse to align with the tilt direction
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    # Prepare visible cells
    visible_cells = []

    # Determine the grid boundaries
    max_range = max(a_squares, b_squares)
    for y in range(center_y - max_range, center_y + max_range + 1):
        for x in range(center_x - max_range, center_x + max_range + 1):
            dx = x - center_x
            dy = y - center_y

            # Rotate coordinates to align with the ellipse axes
            x_rot = dx * cos_phi + dy * sin_phi
            y_rot = -dx * sin_phi + dy * cos_phi

            # Check if the point is within the ellipse
            if (x_rot / a_squares) ** 2 + (y_rot / b_squares) ** 2 <= 1:
                visible_cells.append({'x': dx, 'y': dy})

    # Prepare previous positions relative to the current position
    relative_previous_positions = []
    for pos in game_state.get('previous_positions', []):
        rel_x = pos['x'] - center_x
        rel_y = pos['y'] - center_y
        relative_previous_positions.append({'x': rel_x, 'y': rel_y})

    response = jsonify({
        'visible_cells': visible_cells,
        'previous_positions': relative_previous_positions,
        'lobby_code': lobby_code
    })
    response.set_cookie('session_id', session_id)
    return response

@app.route('/move', methods=['POST'])
def move():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    if 'lobby_code' not in session_data:
        return jsonify({'status': 'error', 'message': 'Not in a game'}), 400

    lobby_code = session_data['lobby_code']

    direction = request.json.get('direction')
    if not direction:
        return jsonify({'status': 'error', 'message': 'No direction provided'}), 400

    # Load game state from Redis
    game_state_json = redis_client.get(lobby_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)

    position = game_state['position']

    # Update previous positions
    game_state.setdefault('previous_positions', []).append({'x': position['x'], 'y': position['y']})

    # Update position based on direction
    if direction == 'up':
        position['y'] -= 1
    elif direction == 'down':
        position['y'] += 1
    elif direction == 'left':
        position['x'] -= 1
    elif direction == 'right':
        position['x'] += 1
    else:
        return jsonify({'status': 'error', 'message': 'Invalid direction'}), 400

    # Limit the length of previous positions to avoid too much data
    if len(game_state['previous_positions']) > 100:
        game_state['previous_positions'] = game_state['previous_positions'][-100:]

    # Update game state in Redis
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)  # Reset expiration time

    response = jsonify({'status': 'success'})
    response.set_cookie('session_id', session_id)
    return response

@app.route('/leave_game', methods=['POST'])
def leave_game():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    # Remove 'lobby_code' and 'player_name' from session data
    session_data.pop('lobby_code', None)
    session_data.pop('player_name', None)
    save_session_data(session_id, session_data)
    response = jsonify({'status': 'success'})
    response.set_cookie('session_id', session_id)
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use the PORT environment variable if available
    app.run(debug=False, host='0.0.0.0', port=port)  # Listen on all interfaces
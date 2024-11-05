import json
from flask import Flask, render_template, jsonify, request, redirect, url_for, make_response
import math
import os
import redis
from redis.connection import SSLConnection
import uuid
import random
import string
import noise  # Import the noise library

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

# Terrain types
TERRAIN_SINE = 'sine'
TERRAIN_PERLIN = 'perlin'
TERRAIN_MOUNTAINS = 'mountains' 

# Define the scale for Perlin noise
PERLIN_SCALE = 0.05  # Adjust as needed

# Define parameters for the mountain terrain
MOUNTAIN_PEAK_HEIGHT = 500  # Increased height of the mountain peaks
MOUNTAIN_SCALE = 0.01  # Controls the size of the mountains

def terrain_height_sine(x, y):
    A = 500
    wavelength = 200
    k = (2 * math.pi) / wavelength
    terrain_elevation = A * math.sin(k * x) * math.sin(k * y) + 500  # Add 500 ft offset
    return terrain_elevation

def terrain_height_perlin(x, y):
    A = 500
    scale = PERLIN_SCALE
    noise_value = noise.pnoise2(x * scale, y * scale)
    terrain_elevation = A * noise_value + 500  # Add 500 ft offset
    return terrain_elevation

def terrain_height_mountains(x, y):
    A = MOUNTAIN_PEAK_HEIGHT
    scale = MOUNTAIN_SCALE
    base_height = noise.pnoise2(x * scale, y * scale)
    peaks = [
        {'x': 100, 'y': 100, 'height': A},
        {'x': -150, 'y': 50, 'height': A * 0.8},
        {'x': 200, 'y': -200, 'height': A * 1.2},
    ]
    peak_height = 0
    for peak in peaks:
        distance_sq = (x - peak['x'])**2 + (y - peak['y'])**2
        peak_height += peak['height'] * math.exp(-distance_sq / (2 * (50**2)))
    terrain_elevation = base_height * 500 + peak_height + 500  # Add 500 ft offset
    return terrain_elevation

def terrain_gradient_perlin(x, y):
    A = 500
    scale = PERLIN_SCALE
    delta = 0.01
    h_center = noise.pnoise2(x * scale, y * scale)
    h_x1 = noise.pnoise2((x + delta) * scale, y * scale)
    h_y1 = noise.pnoise2(x * scale, (y + delta) * scale)
    dh_dx = A * (h_x1 - h_center) / delta
    dh_dy = A * (h_y1 - h_center) / delta
    return dh_dx, dh_dy

def terrain_gradient_mountains(x, y):
    scale = MOUNTAIN_SCALE
    delta = 0.01
    h_center = terrain_height_mountains(x, y)
    h_x1 = terrain_height_mountains(x + delta, y)
    h_y1 = terrain_height_mountains(x, y + delta)
    dh_dx = (h_x1 - h_center) / delta
    dh_dy = (h_y1 - h_center) / delta
    return dh_dx, dh_dy

def terrain_height(x, y, terrain_type):
    if terrain_type == TERRAIN_PERLIN:
        return terrain_height_perlin(x, y)
    elif terrain_type == TERRAIN_MOUNTAINS:
        return terrain_height_mountains(x, y)
    else:
        return terrain_height_sine(x, y)

def terrain_gradient(x, y, terrain_type):
    if terrain_type == TERRAIN_PERLIN:
        return terrain_gradient_perlin(x, y)
    elif terrain_type == TERRAIN_MOUNTAINS:
        return terrain_gradient_mountains(x, y)
    else:
        return terrain_gradient_sine(x, y)

def horizon_distance(viewer_elevation_ft):
    # Set minimum viewer elevation to VIEWER_HEIGHT_FT (6 ft)
    viewer_elevation_ft = max(viewer_elevation_ft, VIEWER_HEIGHT_FT)
    # Calculate the standard horizon distance
    calculated_distance = 1.22 * math.sqrt(viewer_elevation_ft)
    # Limit the horizon distance to a maximum of 15 miles
    max_horizon_distance = 15  # in miles
    return min(calculated_distance, max_horizon_distance)

def line_of_sight_visibility(center_x, center_y, terrain_type):
    VERTICAL_SCALE = 1  # Adjust vertical exaggeration

    visible_cells = []

    # Get viewer elevation in feet
    viewer_elevation = terrain_height(center_x, center_y, terrain_type) + VIEWER_HEIGHT_FT

    # Calculate horizon distance in miles
    max_view_distance_miles = horizon_distance(viewer_elevation)
    max_view_distance_squares = int(max_view_distance_miles / SQUARE_SIZE_MILES)

    # Ensure we have at least one square to look at
    if max_view_distance_squares < 1:
        max_view_distance_squares = 1

    # Cast rays in all directions
    for angle_deg in range(0, 360, 2):
        angle_rad = math.radians(angle_deg)
        sin_theta = math.sin(angle_rad)
        cos_theta = math.cos(angle_rad)

        prev_max_angle = -math.inf

        for d in range(0, max_view_distance_squares + 1):
            x = center_x + d * cos_theta
            y = center_y + d * sin_theta

            x_int = int(round(x))
            y_int = int(round(y))

            target_elevation = terrain_height(x, y, terrain_type)
            delta_h = (target_elevation - viewer_elevation) * VERTICAL_SCALE
            distance_ft = max(d * SQUARE_SIZE_MILES * 5280, 1)  # Convert miles to feet

            elevation_angle = math.degrees(math.atan2(delta_h, distance_ft))

            if elevation_angle > prev_max_angle:
                # Point is visible
                cell_elevation = target_elevation
                visible_cells.append({
                    'x': x_int - center_x,
                    'y': y_int - center_y,
                    'elevation': cell_elevation
                })
                prev_max_angle = elevation_angle

    return visible_cells

def tilt_angle(x, y, terrain_type):
    if terrain_type == TERRAIN_PERLIN:
        dh_dx, dh_dy = terrain_gradient_perlin(x, y)
    else:
        dh_dx, dh_dy = terrain_gradient_sine(x, y)
    gradient_magnitude = math.sqrt(dh_dx**2 + dh_dy**2)
    theta = math.atan(gradient_magnitude)
    max_tilt_radians = math.radians(15)
    if theta > max_tilt_radians:
        theta = max_tilt_radians
    return theta

def tilt_direction(x, y, terrain_type):
    if terrain_type == TERRAIN_PERLIN:
        dh_dx, dh_dy = terrain_gradient_perlin(x, y)
    else:
        dh_dx, dh_dy = terrain_gradient_sine(x, y)
    phi = math.atan2(dh_dy, dh_dx)
    return phi

# Calculate visibility range
def get_visibility_range(x, y, terrain_type):
    theta = tilt_angle(x, y, terrain_type)
    sin_theta = math.sin(theta)
    d_downhill_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT * (1 + sin_theta))
    d_uphill_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT * (1 - sin_theta))
    a_squares = int(d_downhill_miles / SQUARE_SIZE_MILES)
    b_squares = int(d_uphill_miles / SQUARE_SIZE_MILES)
    phi = tilt_direction(x, y, terrain_type)
    return a_squares, b_squares, phi

# Session management functions (unchanged)
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

# Routes
@app.route('/')
def index():
    session_id = get_session_id()
    response = make_response(render_template('index.html'))
    response.set_cookie('session_id', session_id)
    return response

@app.route('/start_game', methods=['POST'])
def start_game():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    player_name = data.get('player_name', 'Player1')
    terrain_type = data.get('terrain_type', TERRAIN_SINE)
    lobby_code = generate_lobby_code()
    session_data = {'lobby_code': lobby_code, 'player_name': player_name}

    game_state = {
        'position': {'x': 0, 'y': 0},
        'previous_positions': [],
        'max_players': 4,
        'player_names': [player_name],
        'ready_statuses': [False],
        'game_started': False,
        'terrain_type': terrain_type
    }
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)

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

    game_state['player_names'].append(player_name)
    game_state['ready_statuses'].append(False)
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)

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

    game_state_json = redis_client.get(lobby_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)
    terrain_type = game_state.get('terrain_type', TERRAIN_SINE)

    position = game_state['position']
    center_x = position['x']
    center_y = position['y']

    # Use LOS visibility for "mountains" terrain
    if terrain_type == TERRAIN_MOUNTAINS:
        visible_cells = line_of_sight_visibility(center_x, center_y, terrain_type)
    else:
        # Existing visibility calculation
        a_squares, b_squares, phi = get_visibility_range(center_x, center_y, terrain_type)

        # Rotate the ellipse to align with the tilt direction
        cos_phi = math.cos(phi)
        sin_phi = math.sin(phi)

        # Prepare visible cells
        visible_cells = []

        # Determine the grid boundaries
        max_range = max(a_squares, b_squares, 10)
        for y in range(center_y - max_range, center_y + max_range + 1):
            for x in range(center_x - max_range, center_x + max_range + 1):
                dx = x - center_x
                dy = y - center_y

                x_rot = dx * cos_phi + dy * sin_phi
                y_rot = -dx * sin_phi + dy * cos_phi

                if (x_rot / a_squares) ** 2 + (y_rot / b_squares) ** 2 <= 1:
                    cell_elevation = terrain_height(x, y, terrain_type)
                    visible_cells.append({
                        'x': dx,
                        'y': dy,
                        'elevation': cell_elevation
                    })

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

# Modify the /move route
@app.route('/move', methods=['POST'])
def move():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    if 'lobby_code' not in session_data:
        return jsonify({'status': 'error', 'message': 'Not in a game'}), 400

    lobby_code = session_data['lobby_code']

    data = request.get_json()
    direction = data.get('direction')
    if not direction:
        return jsonify({'status': 'error', 'message': 'No direction provided'}), 400

    scale = data.get('scale', 1)
    try:
        scale = int(scale)
    except (ValueError, TypeError):
        scale = 1

    game_state_json = redis_client.get(lobby_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)

    position = game_state['position']
    previous_positions = game_state.setdefault('previous_positions', [])

    # Determine the movement direction
    dx, dy = 0, 0
    if direction == 'up':
        dx, dy = 0, -1
    elif direction == 'down':
        dx, dy = 0, 1
    elif direction == 'left':
        dx, dy = -1, 0
    elif direction == 'right':
        dx, dy = 1, 0
    else:
        return jsonify({'status': 'error', 'message': 'Invalid direction'}), 400

    # Record the starting position
    x0, y0 = position['x'], position['y']

    # Generate the positions along the path (excluding the starting position)
    path_positions = [{'x': x0 + dx * step, 'y': y0 + dy * step} for step in range(1, scale + 1)]

    # Append the path positions to previous_positions
    previous_positions.extend(path_positions)

    # Update the current position to the final position
    position['x'] = x0 + dx * scale
    position['y'] = y0 + dy * scale

    # Limit the length of previous_positions to avoid too much data
    if len(previous_positions) > 100:
        previous_positions = previous_positions[-100:]
        game_state['previous_positions'] = previous_positions

    # Update game state in Redis
    redis_client.set(lobby_code, json.dumps(game_state), ex=3600)

    response = jsonify({'status': 'success'})
    response.set_cookie('session_id', session_id)
    return response

@app.route('/leave_game', methods=['POST'])
def leave_game():
    session_id = get_session_id()
    session_data = get_session_data(session_id)
    session_data.pop('lobby_code', None)
    session_data.pop('player_name', None)
    save_session_data(session_id, session_data)
    response = jsonify({'status': 'success'})
    response.set_cookie('session_id', session_id)
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

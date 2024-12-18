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
TERRAIN_MOUNTAINS = 'mountains' 

# Define the scale for Perlin noise
PERLIN_SCALE = 0.05  # Adjust as needed

# Define parameters for the mountain terrain
MOUNTAIN_PEAK_HEIGHT = 500  # Increased height of the mountain peaks
MOUNTAIN_SCALE = 0.01  # Controls the size of the mountains

# River parameters
RIVER_WIDTH = 10  # Increased width of the river in cells
RIVER_CENTER_X = 0  # X-coordinate for the center of the river path
RIVER_FLOW_DIRECTION = 'south'  # Direction the river flows ('south' for this example)

# Vegetation parameters
MAX_VEG_HEIGHT = 50  # Maximum vegetation height in feet
VEG_SCALE = 0.05  # Controls the size of vegetation patches
MIN_VEG_DENSITY = 0.0  # Minimum vegetation density (0 to 1)
MAX_VEG_DENSITY = 0.1  # Maximum vegetation density (0 to 1)
VEG_DISTRIBUTION_COEF = 1.5  # Coefficient to control distribution skewness
ELEVATION_VEG_COEF = 2000  # Elevation coefficient to adjust vegetation with elevation

# Sound ranges for river
RIVER_SOUND_RANGE_NEAR = 20  # Cells
RIVER_SOUND_RANGE_FAR = 50   # Cells

# Sound ranges for vegetation
VEG_SOUND_RANGE_NEAR = 10    # Cells
VEG_SOUND_RANGE_FAR = 30     # Cells

# Enemy sound ranges
ENEMY_SOUND_RANGE_MIN = 50  # Minimum range in cells
ENEMY_SOUND_RANGE_MAX = 65  # Maximum range in cells

def is_river(x, y):
    """
    Determines if the cell at (x, y) is part of the river.
    For simplicity, the river flows south along the x=0 axis with a sinusoidal meander.
    """
    meander_amplitude = 20  # Controls how much the river meanders
    meander_frequency = 0.05  # Controls the frequency of meanders

    # Calculate the river's central y-coordinate based on x
    central_y = int(meander_amplitude * math.sin(meander_frequency * x))

    # Check if the cell is within the river's width around the central path
    return abs(y - central_y) < (RIVER_WIDTH // 2)

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

def terrain_gradient_mountains(x, y):
    delta = 0.01
    h_center = terrain_height_mountains(x, y)
    h_x1 = terrain_height_mountains(x + delta, y)
    h_y1 = terrain_height_mountains(x, y + delta)
    dh_dx = (h_x1 - h_center) / delta
    dh_dy = (h_y1 - h_center) / delta
    return dh_dx, dh_dy

def terrain_height(x, y, terrain_type):
    if terrain_type == TERRAIN_MOUNTAINS:
        return terrain_height_mountains(x, y)
    else:
        # Default to mountains if unknown terrain type
        return terrain_height_mountains(x, y)

def terrain_gradient(x, y, terrain_type):
    if terrain_type == TERRAIN_MOUNTAINS:
        return terrain_gradient_mountains(x, y)
    else:
        # Default to mountains gradient if unknown terrain type
        return terrain_gradient_mountains(x, y)

def horizon_distance(viewer_elevation_ft):
    # Set minimum viewer elevation to VIEWER_HEIGHT_FT (6 ft)
    viewer_elevation_ft = max(viewer_elevation_ft, VIEWER_HEIGHT_FT)
    # Calculate the standard horizon distance
    calculated_distance = 1.22 * math.sqrt(viewer_elevation_ft)
    # Limit the horizon distance to a maximum of 20 miles
    max_horizon_distance = 20  # in miles
    return min(calculated_distance, max_horizon_distance)

def compute_sound_levels(x, y, center_x, center_y):
    """
    Computes the sound levels for different sound sources at a given cell.
    Returns a dictionary of sound sources and their levels.
    """
    sound_sources = {}

    # Sound from river
    if is_river(x, y):
        dx = x - center_x
        dy = y - center_y
        distance_to_player = math.sqrt(dx**2 + dy**2)
        if distance_to_player <= RIVER_SOUND_RANGE_NEAR:
            sound_sources['river'] = 2  # Near level
        elif distance_to_player <= RIVER_SOUND_RANGE_FAR:
            sound_sources['river'] = 1  # Far level

    return sound_sources

def line_of_sight_visibility(center_x, center_y, terrain_type):
    VERTICAL_SCALE = 1  # Adjust vertical exaggeration

    visible_cells = []

    # Get viewer elevation in feet (include vegetation at viewer's location)
    viewer_terrain_elevation = terrain_height(center_x, center_y, terrain_type)
    viewer_veg_height = vegetation_height(center_x, center_y, viewer_terrain_elevation)
    viewer_elevation = viewer_terrain_elevation + viewer_veg_height + VIEWER_HEIGHT_FT

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

            target_terrain_elevation = terrain_height(x, y, terrain_type)
            target_veg_height = vegetation_height(x, y, target_terrain_elevation)
            target_total_elevation = target_terrain_elevation + target_veg_height

            # Determine if the cell is part of the river
            target_water = is_river(x_int, y_int) if terrain_type == TERRAIN_MOUNTAINS else False

            delta_h = (target_total_elevation - viewer_elevation) * VERTICAL_SCALE
            distance_ft = max(d * SQUARE_SIZE_MILES * 5280, 1)  # Convert miles to feet

            elevation_angle = math.degrees(math.atan2(delta_h, distance_ft))

            if elevation_angle > prev_max_angle:
                # Point is visible
                cell_elevation = target_terrain_elevation
                cell_vegetation_height = target_veg_height

                # Compute sound levels for the cell
                sound_sources = compute_sound_levels(x_int, y_int, center_x, center_y)

                visible_cells.append({
                    'x': x_int - center_x,
                    'y': y_int - center_y,
                    'elevation': cell_elevation,
                    'vegetation_height': cell_vegetation_height,
                    'water': target_water,
                    'sound_sources': sound_sources  # Include sound sources
                })
                prev_max_angle = elevation_angle
            else:
                break

    return visible_cells

def tilt_angle(x, y, terrain_type):
    dh_dx, dh_dy = terrain_gradient(x, y, terrain_type)
    gradient_magnitude = math.sqrt(dh_dx**2 + dh_dy**2)
    theta = math.atan(gradient_magnitude)
    max_tilt_radians = math.radians(15)
    if theta > max_tilt_radians:
        theta = max_tilt_radians
    return theta

def tilt_direction(x, y, terrain_type):
    dh_dx, dh_dy = terrain_gradient(x, y, terrain_type)
    phi = math.atan2(dh_dy, dh_dx)
    return phi

def vegetation_height(x, y, elevation):
    # Generate base vegetation density using Perlin noise
    base_density = noise.pnoise2(x * VEG_SCALE, y * VEG_SCALE, repeatx=1000, repeaty=1000)
    
    # Shift range from [-0.5, 0.5] to [0, 1]
    base_density += 0.5
    
    # Clamp base_density to [0, 1] to avoid negative or zero values
    base_density = max(0.0, min(base_density, 1.0))
    
    # Apply distribution coefficient
    base_density = base_density ** VEG_DISTRIBUTION_COEF  # Raises to power, safe now
    
    # Adjust vegetation density based on elevation
    elevation_factor = max(0.0, min(1.0, 1 - (elevation - 500) / ELEVATION_VEG_COEF))
    
    vegetation_density = base_density * elevation_factor
    
    # Clamp vegetation density to min and max values
    vegetation_density = max(MIN_VEG_DENSITY, min(vegetation_density, MAX_VEG_DENSITY))
    
    # Calculate vegetation height
    veg_height = vegetation_density * MAX_VEG_HEIGHT
    return veg_height

def compute_sounds(center_x, center_y, terrain_type, previous_positions):
    """
    Computes the sounds to be displayed on the client.
    """
    sounds = []

    # 1. River Sounds
    # Define the range within which river sounds are heard
    RIVER_SOUND_RANGE = 50  # in cells

    # Sample river cells every 10 cells within range
    for dx in range(-RIVER_SOUND_RANGE, RIVER_SOUND_RANGE + 1, 10):
        for dy in range(-RIVER_SOUND_RANGE, RIVER_SOUND_RANGE + 1, 10):
            x = center_x + dx
            y = center_y + dy
            if is_river(x, y):
                distance = math.sqrt(dx**2 + dy**2)
                if distance <= RIVER_SOUND_RANGE:
                    sounds.append({
                        'x': dx,
                        'y': dy,
                        'color': 'blue'
                    })

    # 2. Center Dot Sound (Player's Position)
    sounds.append({
        'x': 0,
        'y': 0,
        'color': 'red'
    })

    # 3. Previous Movements Sounds
    # Limit to last 10 movements to avoid clutter
    recent_positions = previous_positions[-10:]
    for pos in recent_positions:
        dx = pos['x'] - center_x
        dy = pos['y'] - center_y
        sounds.append({
            'x': dx,
            'y': dy,
            'color': 'yellow'
        })

    # 4. Random Sounds Based on Vegetation Density
    # Use the same distribution as vegetation
    RANDOM_SOUND_RANGE = 100  # in cells
    for dx in range(-RANDOM_SOUND_RANGE, RANDOM_SOUND_RANGE + 1, 5):
        for dy in range(-RANDOM_SOUND_RANGE, RANDOM_SOUND_RANGE + 1, 5):
            x = center_x + dx
            y = center_y + dy
            # Probability based on vegetation density
            veg_height = vegetation_height(x, y, terrain_height(x, y, terrain_type))
            veg_density = veg_height / MAX_VEG_HEIGHT  # Normalize to [0,1]
            if random.random() < veg_density * 0.05:  # 5% base probability
                sounds.append({
                    'x': dx,
                    'y': dy,
                    'color': 'green'
                })

    # 5. Enemy Sounds
    for enemy in enemies:
        dx = enemy['x'] - center_x
        dy = enemy['y'] - center_y
        distance = math.sqrt(dx**2 + dy**2)
        if distance <= ENEMY_SOUND_RANGE_MAX:
            # Compute intensity based on distance
            if distance <= ENEMY_SOUND_RANGE_MIN:
                intensity = 1.0  # Maximum intensity
            else:
                intensity = (ENEMY_SOUND_RANGE_MAX - distance) / (ENEMY_SOUND_RANGE_MAX - ENEMY_SOUND_RANGE_MIN)
            # Convert intensity to color (red with varying opacity)
            color = f'rgba(255, 0, 0, {intensity})'
            sounds.append({
                'x': dx,
                'y': dy,
                'color': color
            })

    return sounds

def compute_enemy_fov(enemy_x, enemy_y, enemy_direction, fov_angle=60, fov_range=25):
    """
    Computes the cells within the enemy's field of vision cone.
    Returns a set of (dx, dy) tuples relative to the enemy's position.
    """
    fov_cells = set()
    half_angle = fov_angle / 2
    start_angle = enemy_direction - half_angle
    end_angle = enemy_direction + half_angle

    for angle in range(int(start_angle), int(end_angle) + 1):
        angle_rad = math.radians(angle % 360)
        for d in range(1, fov_range + 1):
            dx = int(round(d * math.cos(angle_rad)))
            dy = int(round(d * math.sin(angle_rad)))
            fov_cells.add((dx, dy))
    return fov_cells

def compute_enemy_hearing(enemy_x, enemy_y, hearing_range=15):
    """
    Computes the cells within the enemy's hearing circle.
    Returns a set of (dx, dy) tuples relative to the enemy's position.
    """
    hearing_cells = set()
    for dx in range(-hearing_range, hearing_range + 1):
        for dy in range(-hearing_range, hearing_range + 1):
            if dx**2 + dy**2 <= hearing_range**2:
                hearing_cells.add((dx, dy))
    return hearing_cells

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
    terrain_type = TERRAIN_MOUNTAINS  # Fixed to mountains
    lobby_code = generate_lobby_code()
    session_data = {'lobby_code': lobby_code, 'player_name': player_name}

    # Ensure starting position is on land (not on the river)
    start_x, start_y = 0, 0  # Starting at the center
    while is_river(start_x, start_y):
        start_y += 10  # Move south until landing on land
        # Optional: Add bounds checking here to prevent infinite loop

    # Initialize enemies
    enemies = []
    num_enemies = 2

    for _ in range(num_enemies):
        while True:
            # Generate random positions for enemies
            enemy_x = random.randint(-50, 50)
            enemy_y = random.randint(-50, 50)
            if not is_river(enemy_x, enemy_y):
                break
        # Assign random direction for enemy's field of vision (in degrees)
        enemy_direction = random.uniform(0, 360)
        enemies.append({
            'x': enemy_x,
            'y': enemy_y,
            'direction': enemy_direction
        })

    game_state = {
        'position': {'x': start_x, 'y': start_y},
        'previous_positions': [],
        'max_players': 4,
        'player_names': [player_name],
        'ready_statuses': [False],
        'game_started': False,
        'terrain_type': terrain_type,
        'enemies': enemies  # Add enemies to game state
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
    terrain_type = game_state.get('terrain_type', TERRAIN_MOUNTAINS)

    position = game_state['position']
    center_x = position['x']
    center_y = position['y']

    # Use LOS visibility for "mountains" terrain
    visible_cells = line_of_sight_visibility(center_x, center_y, terrain_type)

    # Prepare previous positions relative to the current position
    relative_previous_positions = []
    for pos in game_state.get('previous_positions', []):
        rel_x = pos['x'] - center_x
        rel_y = pos['y'] - center_y
        relative_previous_positions.append({'x': rel_x, 'y': rel_y})

    # Create a set of visible positions for quick lookup
    visible_positions = set((cell['x'], cell['y']) for cell in visible_cells)

    # Get enemies from game state
    enemies = game_state.get('enemies', [])

    for enemy in enemies:
        enemy_x = enemy['x']
        enemy_y = enemy['y']
        enemy_direction = enemy['direction']

        # Compute relative position of enemy
        enemy_rel_x = enemy_x - center_x
        enemy_rel_y = enemy_y - center_y

        enemy_visible = (enemy_rel_x, enemy_rel_y) in visible_positions

        if enemy_visible:
            # Mark the enemy's position
            for cell in visible_cells:
                if cell['x'] == enemy_rel_x and cell['y'] == enemy_rel_y:
                    cell['enemy'] = True

            # Compute FOV and hearing ranges
            fov_cells = compute_enemy_fov(enemy_x, enemy_y, enemy_direction)
            hearing_cells = compute_enemy_hearing(enemy_x, enemy_y)

            # Mark cells in visible_cells
            for cell in visible_cells:
                cell_x_global = cell['x'] + center_x
                cell_y_global = cell['y'] + center_y

                dx_enemy = cell_x_global - enemy_x
                dy_enemy = cell_y_global - enemy_y

                if (dx_enemy, dy_enemy) in fov_cells:
                    cell['enemy_fov'] = True
                elif (dx_enemy, dy_enemy) in hearing_cells:
                    cell['enemy_hearing'] = True
        else:
            # Enemy not visible, do not include FOV and hearing ranges
            continue

    # Get enemies from game state
    enemies = game_state.get('enemies', [])

    # Compute sounds, including enemies
    sounds = compute_sounds(center_x, center_y, terrain_type, game_state.get('previous_positions', []), enemies)

    response = jsonify({
        'visible_cells': visible_cells,
        'previous_positions': relative_previous_positions,
        'lobby_code': lobby_code,
        'sounds': sounds  # Include sounds in the response
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

    # Generate the new position(s) based on scale
    new_positions = []
    for step in range(1, scale + 1):
        new_x = position['x'] + dx * step
        new_y = position['y'] + dy * step
        if is_river(new_x, new_y):
            return jsonify({'status': 'error', 'message': 'Cannot move into the river!'}), 400
        new_positions.append({'x': new_x, 'y': new_y})

    # Append the new positions to previous_positions
    previous_positions.extend(new_positions)

    # Update the current position to the final position
    position['x'] += dx * scale
    position['y'] += dy * scale

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
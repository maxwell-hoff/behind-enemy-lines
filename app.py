import json
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import math
import os
import redis
import uuid
import ssl

app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Replace with a secure secret key

# Get the Redis URL from the environment variables
REDIS_URL = os.environ.get('REDIS_TLS_URL') or os.environ.get('REDIS_URL')

if not REDIS_URL:
    raise Exception("Redis URL not found. Make sure the REDIS_URL or REDIS_TLS_URL environment variable is set.")

# Configure Redis client with SSL if necessary
if REDIS_URL.startswith('rediss://'):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    redis_client = redis.Redis.from_url(REDIS_URL, ssl=True, ssl_cert_reqs=None, ssl_context=ssl_context)
else:
    redis_client = redis.Redis.from_url(REDIS_URL)

# Horizon calculation parameters
VIEWER_HEIGHT_FT = 6
SQUARE_SIZE_MILES = 0.1

# Calculate visibility range
def get_visibility_range():
    horizon_distance_miles = 1.22 * math.sqrt(VIEWER_HEIGHT_FT)
    visibility_range_squares = int(horizon_distance_miles / SQUARE_SIZE_MILES)
    return visibility_range_squares

@app.route('/')
def index():
    if 'team_code' in session:
        # Player is already in a game
        return redirect(url_for('game'))
    return render_template('index.html')

@app.route('/start_game', methods=['POST'])
def start_game():
    # Generate a unique team code
    team_code = str(uuid.uuid4())[:8]  # Shorten UUID to 8 characters
    session['team_code'] = team_code

    # Initialize game state in Redis
    game_state = {
        'players': {},
        'previous_positions': []
    }
    redis_client.set(team_code, json.dumps(game_state))

    return jsonify({'team_code': team_code})

@app.route('/join_game', methods=['POST'])
def join_game():
    team_code = request.json.get('team_code')
    if not team_code:
        return jsonify({'status': 'error', 'message': 'No team code provided'}), 400

    if not redis_client.exists(team_code):
        return jsonify({'status': 'error', 'message': 'Invalid team code'}), 400

    session['team_code'] = team_code
    return jsonify({'status': 'success'})

@app.route('/game')
def game():
    if 'team_code' not in session:
        return redirect(url_for('index'))
    return render_template('game.html')

@app.route('/visible_cells')
def visible_cells():
    if 'team_code' not in session:
        return jsonify({'status': 'error', 'message': 'Not in a game'}), 400

    team_code = session['team_code']
    player_id = session.get('player_id')

    # Load game state from Redis
    game_state_json = redis_client.get(team_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)

    # Get player's position
    if not player_id or player_id not in game_state['players']:
        # Assign a new player ID and position
        player_id = str(uuid.uuid4())
        session['player_id'] = player_id
        game_state['players'][player_id] = {'x': 0, 'y': 0}
        # Update game state in Redis
        redis_client.set(team_code, json.dumps(game_state))

    player_position = game_state['players'][player_id]
    center_x = player_position['x']
    center_y = player_position['y']

    visibility_range_squares = get_visibility_range()

    # Compute the positions of cells within the circular visibility range
    visible_cells = []
    for y in range(center_y - visibility_range_squares, center_y + visibility_range_squares + 1):
        for x in range(center_x - visibility_range_squares, center_x + visibility_range_squares + 1):
            dx = x - center_x
            dy = y - center_y
            distance = math.sqrt(dx * dx + dy * dy)
            if distance <= visibility_range_squares:
                # Positions are relative to the player's position
                visible_cells.append({'x': x - center_x, 'y': y - center_y})

    # Prepare previous positions relative to the player's current position
    relative_previous_positions = []
    for pos in game_state.get('previous_positions', []):
        rel_x = pos['x'] - center_x
        rel_y = pos['y'] - center_y
        relative_previous_positions.append({'x': rel_x, 'y': rel_y})

    # Return the visibility range and the list of visible cells
    return jsonify({
        'visibility_range': visibility_range_squares,
        'visible_cells': visible_cells,
        'previous_positions': relative_previous_positions,
        'team_code': team_code
    })

@app.route('/move', methods=['POST'])
def move():
    if 'team_code' not in session:
        return jsonify({'status': 'error', 'message': 'Not in a game'}), 400

    team_code = session['team_code']
    player_id = session.get('player_id')

    direction = request.json.get('direction')
    if not direction:
        return jsonify({'status': 'error', 'message': 'No direction provided'}), 400

    # Load game state from Redis
    game_state_json = redis_client.get(team_code)
    if not game_state_json:
        return jsonify({'status': 'error', 'message': 'Game state not found'}), 400

    game_state = json.loads(game_state_json)

    # Get player's position
    if not player_id or player_id not in game_state['players']:
        return jsonify({'status': 'error', 'message': 'Player not found in game state'}), 400

    player_position = game_state['players'][player_id]

    # Update previous positions
    game_state.setdefault('previous_positions', []).append({'x': player_position['x'], 'y': player_position['y']})

    # Update player's position based on direction
    if direction == 'up':
        player_position['y'] -= 1
    elif direction == 'down':
        player_position['y'] += 1
    elif direction == 'left':
        player_position['x'] -= 1
    elif direction == 'right':
        player_position['x'] += 1
    else:
        return jsonify({'status': 'error', 'message': 'Invalid direction'}), 400

    # Limit the length of previous positions to avoid too much data
    if len(game_state['previous_positions']) > 100:
        game_state['previous_positions'] = game_state['previous_positions'][-100:]

    # Update game state in Redis
    redis_client.set(team_code, json.dumps(game_state))

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use the PORT environment variable if available
    app.run(debug=False, host='0.0.0.0', port=port)  # Listen on all interfaces

from flask import Flask, render_template, jsonify, request, make_response
from terrain_creator import *
import os

app = Flask(__name__)

# Global game state (for demonstration purposes)
map_width = 300
map_height = 300
height_map = generate_height_map(map_width, map_height, scale=20)
terrain_map = assign_terrain_types(height_map)

player_state = {
    'x': 50,
    'y': 50,
    'previous_positions': [],
    'moves': 0
}

enemy_positions = [(60, 55), (45, 48), (52, 53)]  # Sample enemy positions

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/game_state')
def game_state():
    player_x = player_state['x']
    player_y = player_state['y']
    viewer_height_ft = 6  # Height of the viewer in feet
    square_size_miles = 0.1  # Size of each square in miles
    observer_elevation_ft = height_map[player_x][player_y]  # Player's elevation in feet

    # Calculate visibility range based on viewer's height and elevation
    visibility_range = calculate_visibility(viewer_height_ft, observer_elevation_ft, square_size_miles)

    visible_cells_coords = get_visible_cells(player_x, player_y, visibility_range, map_width, map_height, height_map)

    # Collect data for the visible cells
    visible_terrain = []
    for cell in visible_cells_coords:
        cell_data = {
            'x': cell[0],
            'y': cell[1],
            'terrain': terrain_map[cell[0]][cell[1]],
            'elevation': height_map[cell[0]][cell[1]]
        }
        visible_terrain.append(cell_data)
    
    # Get weather and time of day
    weather = get_weather()
    time = get_time_of_day()
    
    # Calculate signal strength
    signal_strength = calculate_signal_strength(player_x, player_y, 0, 0)  # Assuming signal source at (0,0)
    
    # Get sounds
    sounds = get_sounds(player_x, player_y, enemy_positions, terrain_map, weather)
    
    # Enemy line of sight
    enemies_in_sight = []
    for enemy in enemy_positions:
        if enemy_can_see_player(player_x, player_y, enemy[0], enemy[1], terrain_map):
            enemies_in_sight.append({'x': enemy[0], 'y': enemy[1]})
    
    response = {
        'player_position': {'x': player_x, 'y': player_y},
        'visible_terrain': visible_terrain,
        'weather': weather,
        'time_of_day': time,
        'signal_strength': signal_strength,
        'sounds': sounds,
        'enemies_in_sight': enemies_in_sight,
        'previous_positions': player_state['previous_positions'],
        'visibility_range': visibility_range  # Include visibility range in the response
    }
    response = make_response(jsonify(response))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/move', methods=['POST'])
def move():
    data = request.json
    target_x = data.get('x')
    target_y = data.get('y')
    player_x = player_state['x']
    player_y = player_state['y']

    # Check if the target cell is adjacent
    if abs(target_x - player_x) <= 1 and abs(target_y - player_y) <= 1:
        # Check if the move is within the map bounds
        if 0 <= target_x < map_width and 0 <= target_y < map_height:
            player_state['previous_positions'].append((player_x, player_y))
            player_state['x'] = target_x
            player_state['y'] = target_y
            player_state['moves'] += 1
            return jsonify({'status': 'moved'})
        else:
            return jsonify({'status': 'error', 'message': 'Target cell is out of bounds.'})
    else:
        return jsonify({'status': 'error', 'message': 'You can only move to adjacent cells.'})

@app.route('/view_terrain')
def view_terrain():
    return render_template('view_terrain.html')

@app.route('/terrain_data')
def terrain_data():
    terrain_data = []
    for i in range(map_width):
        row = []
        for j in range(map_height):
            row.append(terrain_map[i][j])
        terrain_data.append(row)
    return jsonify({'terrain_data': terrain_data, 'map_width': map_width, 'map_height': map_height})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use port from environment variable or default to 5000
    app.run(debug=True, host='0.0.0.0', port=port)
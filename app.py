from flask import Flask, render_template, jsonify, request
from terrain_creator import *

app = Flask(__name__)

# Global game state (for demonstration purposes)
map_width = 100
map_height = 100
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
    elevation = height_map[player_x][player_y]
    visibility_range = calculate_visibility(elevation)
    visible_cells = get_visible_cells(player_x, player_y, visibility_range, map_width, map_height)
    
    # Collect data for the visible cells
    visible_terrain = []
    for cell in visible_cells:
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
        'previous_positions': player_state['previous_positions']
    }
    return jsonify(response)

@app.route('/move', methods=['POST'])
def move():
    direction = request.json.get('direction')
    dx, dy = 0, 0
    if direction == 'north':
        dx = -1
    elif direction == 'south':
        dx = 1
    elif direction == 'east':
        dy = 1
    elif direction == 'west':
        dy = -1
    # Add diagonal movements if needed
    new_x = player_state['x'] + dx
    new_y = player_state['y'] + dy
    if 0 <= new_x < map_width and 0 <= new_y < map_height:
        player_state['previous_positions'].append((player_state['x'], player_state['y']))
        player_state['x'] = new_x
        player_state['y'] = new_y
        player_state['moves'] += 1
    return jsonify({'status': 'moved'})

if __name__ == '__main__':
    app.run(debug=True)
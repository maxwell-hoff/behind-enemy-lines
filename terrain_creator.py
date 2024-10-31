import numpy as np
from perlin_noise import PerlinNoise
import random

weather_conditions = ['Clear', 'Rain', 'Fog', 'Snow']
time_of_day = ['Day', 'Night', 'Dawn', 'Dusk']

def generate_height_map(width, height, scale):
    noise = PerlinNoise(octaves=4, seed=1)
    height_map = np.zeros((height, width))
    for i in range(height):
        for j in range(width):
            x = i / scale
            y = j / scale
            height_map[i][j] = noise([x, y])
    return height_map

def assign_terrain_types(height_map):
    terrain_map = np.empty(height_map.shape, dtype=str)
    for i in range(height_map.shape[0]):
        for j in range(height_map.shape[1]):
            elevation = height_map[i][j]
            if elevation < -0.05:
                terrain_map[i][j] = 'Water'
            elif elevation < 0.0:
                terrain_map[i][j] = 'Sand'
            elif elevation < 0.3:
                terrain_map[i][j] = 'Grass'
            elif elevation < 0.6:
                terrain_map[i][j] = 'Forest'
            else:
                terrain_map[i][j] = 'Mountain'
    return terrain_map

def calculate_visibility(elevation):
    base_visibility = 3  # Base number of squares visible
    additional_visibility = int(elevation * 10)  # Increase visibility with elevation
    return base_visibility + additional_visibility

def get_visible_cells(player_x, player_y, visibility_range, map_width, map_height):
    visible_cells = []
    for i in range(player_x - visibility_range, player_x + visibility_range + 1):
        for j in range(player_y - visibility_range, player_y + visibility_range + 1):
            if 0 <= i < map_width and 0 <= j < map_height:
                # Calculate distance based on actual grid distance
                distance = max(abs(player_x - i), abs(player_y - j))
                if distance <= visibility_range:
                    visible_cells.append((i, j))
    return visible_cells

def get_weather():
    return random.choice(weather_conditions)

def get_time_of_day():
    return random.choice(time_of_day)

def calculate_signal_strength(player_x, player_y, signal_source_x, signal_source_y):
    max_strength = 5
    distance = np.hypot(player_x - signal_source_x, player_y - signal_source_y)
    signal_strength = max(0, max_strength - int(distance / 3))
    return signal_strength

def get_sounds(player_x, player_y, enemy_positions, terrain_map, weather):
    sounds = []
    for enemy in enemy_positions:
        distance = np.hypot(player_x - enemy[0], player_y - enemy[1])
        max_hearing_distance = 5
        if weather == 'Rain':
            max_hearing_distance -= 1
        if terrain_map[player_x][player_y] == 'Forest':
            max_hearing_distance -= 1
        if distance <= max_hearing_distance:
            sounds.append('Gunfire to the {} units away.'.format(int(distance)))
    return sounds

def enemy_can_see_player(player_x, player_y, enemy_x, enemy_y, terrain_map):
    # Simplified line of sight calculation
    if terrain_map[player_x][player_y] == 'Forest':
        return False
    distance = np.hypot(player_x - enemy_x, player_y - enemy_y)
    if distance <= 5:
        return True
    return False
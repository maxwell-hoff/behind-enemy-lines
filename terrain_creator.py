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

def get_visible_cells(player_x, player_y, visibility_range, map_width, map_height, terrain_map, height_map):
    visible_cells = []
    for i in range(player_x - visibility_range, player_x + visibility_range + 1):
        for j in range(player_y - visibility_range, player_y + visibility_range + 1):
            if 0 <= i < map_width and 0 <= j < map_height:
                distance = np.hypot(player_x - i, player_y - j)
                if distance <= visibility_range:
                    # Perform line-of-sight check with elevation
                    line_cells = bresenham_line(player_x, player_y, i, j)
                    blocked = False
                    prev_elevation = height_map[player_x][player_y]
                    for cell in line_cells:
                        terrain = terrain_map[cell[0]][cell[1]]
                        current_elevation = height_map[cell[0]][cell[1]]
                        elevation_diff = current_elevation - prev_elevation
                        if is_blocking_terrain(terrain) and cell != (player_x, player_y):
                            blocked = True
                            break
                        if elevation_diff > 0.1:  # Threshold for elevation blocking view
                            blocked = True
                            break
                        prev_elevation = current_elevation
                    if not blocked:
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

def is_blocking_terrain(terrain_type):
    return terrain_type in ['Mountain', 'Forest']

def bresenham_line(x0, y0, x1, y1):
    """Bresenham's Line Algorithm to get the cells along a line."""
    cells = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = -1 if x0 > x1 else 1
    sy = -1 if y0 > y1 else 1
    if dx > dy:
        err = dx / 2.0
        while x != x1:
            cells.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y1:
            cells.append((x, y))
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    cells.append((x1, y1))
    return cells
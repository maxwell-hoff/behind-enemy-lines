import numpy as np
from perlin_noise import PerlinNoise
import random

weather_conditions = ['Clear', 'Rain', 'Fog', 'Snow']
time_of_day = ['Day', 'Night', 'Dawn', 'Dusk']

def generate_height_map(width, height, scale):
    noise = PerlinNoise(octaves=2, seed=1)  # Reduced octaves for smoother terrain
    height_map = np.zeros((height, width))
    for i in range(height):
        for j in range(width):
            x = i / scale
            y = j / scale
            elevation = noise([x, y])
            height_map[i][j] = elevation
    # Scale the elevation to realistic values in feet
    min_elevation = 0    # Sea level
    max_elevation = 500  # Maximum elevation in feet
    # Normalize height_map to range between min_elevation and max_elevation
    height_map = (height_map - height_map.min()) / (height_map.max() - height_map.min())
    height_map = height_map * (max_elevation - min_elevation) + min_elevation
    return height_map

def assign_terrain_types(height_map):
    terrain_map = np.empty(height_map.shape, dtype=str)
    for i in range(height_map.shape[0]):
        for j in range(height_map.shape[1]):
            elevation = height_map[i][j]
            if elevation < 1:
                terrain_map[i][j] = 'Water'
            elif elevation < 5:
                terrain_map[i][j] = 'Sand'
            elif elevation < 100:
                terrain_map[i][j] = 'Grass'
            elif elevation < 300:
                terrain_map[i][j] = 'Forest'
            else:
                terrain_map[i][j] = 'Mountain'
    return terrain_map


def calculate_visibility(viewer_height_ft, observer_elevation_ft, square_size_miles):
    # Total viewer height is the sum of observer elevation and viewer height
    total_height_ft = viewer_height_ft + observer_elevation_ft
    # Horizon distance in miles: d = 1.22 * sqrt(h), where h is in feet
    horizon_distance_miles = 1.22 * np.sqrt(total_height_ft)
    # Convert horizon distance to number of squares
    visibility_range = int(horizon_distance_miles / square_size_miles)
    return visibility_range


def get_visible_cells(player_x, player_y, visibility_range, map_width, map_height, height_map):
    visible_cells = []
    observer_elevation_ft = height_map[player_x][player_y]
    viewer_height_ft = 6  # Height of the viewer in feet

    for i in range(player_x - visibility_range, player_x + visibility_range + 1):
        for j in range(player_y - visibility_range, player_y + visibility_range + 1):
            if 0 <= i < map_width and 0 <= j < map_height:
                dx = player_x - i
                dy = player_y - j
                distance = np.sqrt(dx * dx + dy * dy)
                if distance <= visibility_range:
                    # Adjust visibility based on elevation difference
                    target_elevation_ft = height_map[i][j]
                    elevation_diff = target_elevation_ft - observer_elevation_ft
                    if elevation_diff <= 0 or distance <= calculate_visibility(viewer_height_ft, target_elevation_ft, 0.1):
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
function updateGameState() {
    fetch('/game_state')
    .then(response => response.json())
    .then(data => {
        // Clear existing grid
        const grid = document.getElementById('grid');
        grid.innerHTML = '';

        // Determine the grid size (e.g., 7x7)
        const gridSize = 7; // Must be an odd number to center on player
        const halfGrid = Math.floor(gridSize / 2);

        // Get player position
        const playerX = data.player_position.x;
        const playerY = data.player_position.y;

        // Create cells
        for (let row = -halfGrid; row <= halfGrid; row++) {
            for (let col = -halfGrid; col <= halfGrid; col++) {
                const cellX = playerX + row;
                const cellY = playerY + col;
                const cell = document.createElement('div');
                cell.classList.add('cell');

                // Check if the cell is within the visible terrain
                const visibleCell = data.visible_terrain.find(c => c.x === cellX && c.y === cellY);
                if (visibleCell) {
                    cell.classList.add(visibleCell.terrain);
                    cell.title = `Terrain: ${visibleCell.terrain}\nElevation: ${visibleCell.elevation.toFixed(2)}`;
                } else {
                    // Cell is not visible
                    cell.style.backgroundColor = 'black';
                }

                // Mark previous positions
                data.previous_positions.forEach(pos => {
                    if (pos[0] === cellX && pos[1] === cellY) {
                        cell.classList.add('Previous');
                    }
                });

                // Mark enemies
                data.enemies_in_sight.forEach(enemy => {
                    if (enemy.x === cellX && enemy.y === cellY) {
                        cell.classList.add('Enemy');
                        cell.title += '\nEnemy Present';
                    }
                });

                // Mark player position
                if (cellX === playerX && cellY === playerY) {
                    cell.classList.add('Player');
                    cell.title += '\nYou are here';
                }

                grid.appendChild(cell);
            }
        }

        // Update info panel
        document.getElementById('info').innerHTML = `
            Weather: ${data.weather}<br>
            Time of Day: ${data.time_of_day}<br>
            Signal Strength: ${data.signal_strength}<br>
            Sounds: ${data.sounds.join(', ') || 'None'}
        `;
    });
}

function move(direction) {
    fetch('/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({'direction': direction})
    }).then(response => response.json())
    .then(data => {
        if (data.status === 'moved') {
            updateGameState();
        }
    });
}

// Initial game state update
updateGameState();

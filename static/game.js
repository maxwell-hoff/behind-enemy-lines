function updateGameState() {
    fetch('/game_state')
    .then(response => response.json())
    .then(data => {
        // Clear existing grid
        const grid = document.getElementById('grid');
        grid.innerHTML = '';

        // Determine the grid size (e.g., 7x7)
        const gridSize = 15; // Increased from 7 to 15
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
                    cell.style.display = 'none';
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

                // Make adjacent cells clickable for movement
                if (Math.abs(cellX - playerX) <= 1 && Math.abs(cellY - playerY) <= 1 && !(cellX === playerX && cellY === playerY)) {
                    cell.classList.add('clickable');
                    cell.addEventListener('click', function() {
                        moveToCell(cellX, cellY);
                    });
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

function moveToCell(x, y) {
    fetch('/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({'x': x, 'y': y})
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'moved') {
            updateGameState();  // Refresh the game state
        } else {
            alert(data.message || 'Unable to move to that cell.');
        }
    });
}

// Remove the directional move function if not needed
/*
function move(direction) {
    // ... existing code ...
}
*/

// Initial game state update
updateGameState();

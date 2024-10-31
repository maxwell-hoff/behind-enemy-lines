// Initialize the map
var map = L.map('map').setView([0, 0], 2);

// Add a basic tile layer (you can customize this)
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    // Attribution can be customized or removed
}).addTo(map);

function updateGameState() {
    fetch('/game_state')
    .then(response => response.json())
    .then(data => {
        // Clear existing layers
        map.eachLayer(function (layer) {
            if (layer instanceof L.Marker || layer instanceof L.Circle) {
                map.removeLayer(layer);
            }
        });
        // Update player position
        var playerPos = [data.player_position.x, data.player_position.y];
        L.marker(playerPos).addTo(map).bindPopup('You are here').openPopup();
        // Update visible terrain
        data.visible_terrain.forEach(cell => {
            var color;
            switch(cell.terrain) {
                case 'Water': color = 'blue'; break;
                case 'Sand': color = 'yellow'; break;
                case 'Grass': color = 'green'; break;
                case 'Forest': color = 'darkgreen'; break;
                case 'Mountain': color = 'gray'; break;
                default: color = 'white';
            }
            L.circle([cell.x, cell.y], {
                color: color,
                radius: 100
            }).addTo(map);
        });
        // Update enemies in sight
        data.enemies_in_sight.forEach(enemy => {
            L.marker([enemy.x, enemy.y], {icon: L.icon({
                iconUrl: 'enemy_icon.png',
                iconSize: [25, 25]
            })}).addTo(map).bindPopup('Enemy');
        });
        // Update info panel
        document.getElementById('info').innerHTML = `
            Weather: ${data.weather}<br>
            Time of Day: ${data.time_of_day}<br>
            Signal Strength: ${data.signal_strength}<br>
            Sounds: ${data.sounds.join(', ')}
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
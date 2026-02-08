const API_BASE = '/api';
let currentSession = null;
let currentPlayerId = null;
let isCreator = false;
let gameState = null;
let timers = {};
let lobbyRefreshInterval = null;
let lastPhase = 'waiting';
let autoRefreshInterval = null;

console.log('Game script loaded successfully');

// Show message helper
function showMessage(message, type = 'info') {
    const msgEl = type === 'error' ? document.getElementById('error-message') : document.getElementById('success-message');
    msgEl.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
    msgEl.style.display = 'block';
    setTimeout(() => {
        msgEl.style.display = 'none';
    }, 5000);
}

// Toggle form visibility
function toggleCreateForm() {
    console.log('toggleCreateForm() called');
    const createForm = document.getElementById('create-form');
    const joinForm = document.getElementById('join-form');
    createForm.style.display = createForm.style.display === 'none' ? 'block' : 'none';
    if (joinForm.style.display === 'block') joinForm.style.display = 'none';
    console.log('Create form display:', createForm.style.display);
}

function toggleJoinForm() {
    console.log('toggleJoinForm() called');
    const createForm = document.getElementById('create-form');
    const joinForm = document.getElementById('join-form');
    joinForm.style.display = joinForm.style.display === 'none' ? 'block' : 'none';
    if (createForm.style.display === 'block') createForm.style.display = 'none';
    console.log('Join form display:', joinForm.style.display);
}

// Create Game
async function createGame() {
    console.log('createGame() called');
    const name = document.getElementById('creator-name').value.trim();
    const category = document.getElementById('game-category').value;
    const maxPlayers = parseInt(document.getElementById('max-players').value);

    console.log('Form values:', { name, category, maxPlayers });

    if (!name) {
        console.log('Name is empty');
        showMessage('Please enter your name', 'error');
        return;
    }

    if (!category) {
        console.log('Category is empty');
        showMessage('Please select a category', 'error');
        return;
    }

    try {
        console.log('Sending API request to create game...');
        const response = await fetch(`${API_BASE}/game/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                player_name: name,
                game_category: category,
                max_players: maxPlayers
            })
        });

        console.log('API Response status:', response.status);
        const data = await response.json();
        console.log('API Response data:', data);

        if (data.success) {
            console.log('Game created successfully');
            currentSession = data.session_id;
            currentPlayerId = data.player_id;
            isCreator = true;

            document.getElementById('initial-screen').style.display = 'none';
            document.getElementById('game-created-screen').style.display = 'block';
            document.getElementById('game-code-display').textContent = data.session_id;
            document.getElementById('game-category-display').textContent = data.game_category;
            document.getElementById('start-btn').style.display = 'block';

            showMessage(`Game created! Code: ${data.session_id}`, 'success');
            refreshLobby();
            startLobbyAutoRefresh();
        } else {
            console.log('API returned error:', data.message);
            showMessage(data.message, 'error');
        }
    } catch (error) {
        console.error('Catch error:', error);
        showMessage('Error creating game: ' + error.message, 'error');
    }
}

// Join Game
async function joinGame() {
    const name = document.getElementById('join-player-name').value.trim();
    const sessionId = document.getElementById('session-id').value.trim();

    if (!name || !sessionId) {
        showMessage('Please enter name and game code', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/game/${sessionId}/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_name: name })
        });

        const data = await response.json();

        if (data.success) {
            currentSession = sessionId;
            currentPlayerId = data.player_id;
            isCreator = false;

            document.getElementById('initial-screen').style.display = 'none';
            document.getElementById('game-created-screen').style.display = 'block';
            document.getElementById('game-code-display').textContent = sessionId;
            document.getElementById('start-btn').style.display = 'none';

            showMessage(`Joined game: ${sessionId}`, 'success');
            refreshLobby();
            startLobbyAutoRefresh();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('Error joining game: ' + error.message, 'error');
    }
}

// Refresh Lobby
// Refresh Lobby
async function refreshLobby() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}?player_id=${currentPlayerId}`);
        const data = await response.json();

        if (data.success) {
            // Check if game phase has changed from waiting to playing (for joined players to detect start)
            if (lastPhase === 'waiting' && data.current_phase !== 'waiting') {
                lastPhase = data.current_phase;
                // Game has been started by creator, transition to game screen
                stopLobbyAutoRefresh();
                document.getElementById('game-created-screen').style.display = 'none';
                document.getElementById('game-playing-screen').style.display = 'block';
                loadGameState();
                startGameTimers();
                startAutoRefresh();
                return;
            }
            lastPhase = data.current_phase;

            const playersHtml = data.players.map(p => 
                `<div class="player-item">
                    <span class="player-name">${p.player_name}</span>
                    <span class="player-status">${p.is_alive ? '✅ Active' : '❌ Voted Out'}</span>
                </div>`
            ).join('');

            document.getElementById('lobby-players').innerHTML = playersHtml;
            
            // Only show start button to creator
            if (isCreator) {
                const startBtn = document.getElementById('start-btn');
                startBtn.disabled = data.players.length < 2;
                if (data.players.length < 2) {
                    startBtn.textContent = `Start Game (Need ${2 - data.players.length} more players)`;
                } else {
                    startBtn.textContent = 'Start Game';
                }
            }
        }
    } catch (error) {
        console.error('Error refreshing lobby:', error);
    }
}

// Manual refresh trigger
async function manualRefreshLobby() {
    const btn = event.target;
    btn.style.transform = 'rotate(360deg)';
    btn.style.transition = 'transform 0.6s ease-in-out';
    
    await refreshLobby();
    
    setTimeout(() => {
        btn.style.transform = 'rotate(0deg)';
    }, 600);
}

// Start auto-refresh for lobby (every 5 seconds)
function startLobbyAutoRefresh() {
    if (lobbyRefreshInterval) clearInterval(lobbyRefreshInterval);
    
    lobbyRefreshInterval = setInterval(() => {
        if (document.getElementById('game-created-screen').style.display !== 'none') {
            refreshLobby();
        }
    }, 5000);
}

// Stop lobby auto-refresh
function stopLobbyAutoRefresh() {
    if (lobbyRefreshInterval) {
        clearInterval(lobbyRefreshInterval);
        lobbyRefreshInterval = null;
    }
}

// Start Game
async function startGame() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}/start`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showMessage('Game started!', 'success');
            stopLobbyAutoRefresh();
            document.getElementById('game-created-screen').style.display = 'none';
            document.getElementById('game-playing-screen').style.display = 'block';
            loadGameState();
            startGameTimers();
            startAutoRefresh();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('Error starting game: ' + error.message, 'error');
    }
}

// Load Game State
async function loadGameState() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}?player_id=${currentPlayerId}`);
        const data = await response.json();

        if (data.success) {
            gameState = data;

            // Display the topic word
            document.getElementById('topic-display').textContent = data.your_topic || 'Loading...';

            // Display players
            const playersHtml = data.players.map(p => 
                `<div class="player-item ${!p.is_alive ? 'voted-out' : ''}">
                    <span class="player-name">${p.player_name} ${currentPlayerId === p.player_id ? '(You)' : ''}</span>
                    <span class="player-status">${!p.is_alive ? '❌ Voted Out' : '✅ Active'}</span>
                </div>`
            ).join('');

            document.getElementById('game-players').innerHTML = playersHtml;

            if (data.current_phase === 'voting') {
                showVotingPhase(data);
            } else if (data.current_phase === 'result') {
                showGameResult();
            }
        }
    } catch (error) {
        console.error('Error loading game state:', error);
    }
}

// Show Voting Phase
function showVotingPhase(data) {
    document.getElementById('discussion-actions').style.display = 'none';
    document.getElementById('voting-section').style.display = 'block';

    const votingButtonsHtml = data.players
        .filter(p => p.is_alive)
        .map(p => 
            `<button onclick="submitVote('${p.player_id}')">${p.player_name}</button>`
        ).join('');

    document.getElementById('voting-buttons').innerHTML = votingButtonsHtml;
}

// Submit Vote
async function submitVote(targetPlayerId) {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}/vote?player_id=${currentPlayerId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voted_for_id: targetPlayerId })
        });

        const data = await response.json();

        if (data.success) {
            showMessage('Vote submitted!', 'success');
            loadGameState();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('Error submitting vote: ' + error.message, 'error');
    }
}

// Transition to Voting
async function transitionToVoting() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}/transition-voting`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            loadGameState();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('Error transitioning to voting: ' + error.message, 'error');
    }
}

// Complete Voting
async function completeVoting() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}/end-voting`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showGameResult(data.game_result);
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('Error completing voting: ' + error.message, 'error');
    }
}

// Show Game Result
async function showGameResult() {
    try {
        const response = await fetch(`${API_BASE}/game/${currentSession}`);
        const data = await response.json();

        if (data.success && data.game_result) {
            const result = data.game_result;
            const resultHtml = `
                <div class="alert ${result.is_imposter_caught ? 'alert-success' : 'alert-warning'}" style="font-size: 16px; padding: 20px; text-align: center;">
                    <strong>${result.message}</strong>
                    <p style="margin-top: 10px; font-size: 14px;">Voted out: <strong>${result.voted_out_name}</strong></p>
                    <p style="margin-top: 5px; font-size: 14px;">Winners: <strong>${result.winners}</strong></p>
                </div>
            `;
            document.getElementById('game-result-content').innerHTML = resultHtml;

            const tableHtml = data.players.map(p => `
                <tr>
                    <td>${p.player_name}</td>
                    <td>${p.player_id === result.imposter_id ? '🕵️ Imposter' : '👥 Player'}</td>
                    <td>${p.is_alive ? '✅ Alive' : '❌ Voted Out'}</td>
                </tr>
            `).join('');
            document.getElementById('result-table-body').innerHTML = tableHtml;

            document.getElementById('game-playing-screen').style.display = 'none';
            document.getElementById('game-result-screen').style.display = 'block';
            
            clearGameTimers();
        }
    } catch (error) {
        console.error('Error loading result:', error);
    }
}

// List Available Games
async function listGames() {
    try {
        const response = await fetch(`${API_BASE}/games/available`);
        const data = await response.json();

        if (data.success && data.games.length > 0) {
            const gamesHtml = `
                <h3 style="margin-top: 30px;">🎮 Available Games</h3>
                <div class="games-grid">
                    ${data.games.map(game => `
                        <div class="game-item" onclick="selectGame('${game.session_id}')">
                            <h4>📂 ${game.game_category}</h4>
                            <p>👥 Players: ${game.player_count}/${game.max_players}</p>
                            <p>🕐 Created: ${new Date(game.created_at).toLocaleTimeString()}</p>
                            <button onclick="selectGame('${game.session_id}', event)" style="width: 100%; padding: 8px;">Join This Game</button>
                        </div>
                    `).join('')}
                </div>
            `;
            document.getElementById('available-games').innerHTML = gamesHtml;
        } else {
            document.getElementById('available-games').innerHTML = '<p style="text-align: center; color: #999; margin-top: 30px;">No games available. Create one!</p>';
        }
    } catch (error) {
        showMessage('Error loading games: ' + error.message, 'error');
    }
}

// Select Game to Join
function selectGame(sessionId, event) {
    if (event) event.stopPropagation();
    document.getElementById('session-id').value = sessionId;
    document.getElementById('session-id').focus();
}

// Game Timers
function startGameTimers() {
    let elapsedTime = 0;
    const maxDiscussionTime = 600; // 10 minutes

    timers.discussion = setInterval(() => {
        const mins = Math.floor(elapsedTime / 60);
        const secs = elapsedTime % 60;
        document.getElementById('game-timer').textContent = 
            `${mins}:${secs.toString().padStart(2, '0')}`;
        elapsedTime++;

        // Auto-transition to voting after 10 minutes
        if (elapsedTime > maxDiscussionTime) {
            clearInterval(timers.discussion);
            showMessage('10 minutes elapsed! Starting voting phase...', 'info');
            transitionToVoting();
        }
    }, 1000);
}

function clearGameTimers() {
    Object.values(timers).forEach(timer => clearInterval(timer));
    timers = {};
}

// Auto-refresh game state
function startAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    autoRefreshInterval = setInterval(() => {
        if (document.getElementById('game-created-screen').style.display !== 'none') {
            refreshLobby();
        } else if (document.getElementById('game-playing-screen').style.display !== 'none') {
            loadGameState();
        }
    }, 2000);
}

// Go Back
function goBack() {
    clearGameTimers();
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    stopLobbyAutoRefresh();
    
    document.getElementById('initial-screen').style.display = 'block';
    document.getElementById('game-created-screen').style.display = 'none';
    document.getElementById('game-playing-screen').style.display = 'none';
    document.getElementById('game-result-screen').style.display = 'none';
    document.getElementById('create-form').style.display = 'none';
    document.getElementById('join-form').style.display = 'none';
    
    currentSession = null;
    currentPlayerId = null;
    isCreator = false;
    gameState = null;
    lastPhase = 'waiting';
}

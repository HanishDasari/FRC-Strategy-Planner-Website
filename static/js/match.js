// Global variables for notification
let currentNotificationInviteId = null;
let notificationTimeout = null;

// Global function for responding to invites (called from onclick in rendered HTML)
async function respondToInvite(inviteId, status) {
    try {
        const res = await fetch(`/api/invites/${inviteId}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });

        if (res.ok) {
            // Trigger a data refresh
            window.location.reload(); // Simple approach - reload to refresh all data
        } else {
            const result = await res.json();
            alert(result.error || 'Failed to respond to invite');
        }
    } catch (err) {
        console.error(err);
        alert('Failed to respond to invite');
    }
}

// Handle notification popup response
function handleNotificationResponse(action) {
    if (!currentNotificationInviteId) return;

    const status = action === 'accept' ? 'Accepted' : 'Declined';
    hideNotification();
    respondToInvite(currentNotificationInviteId, status);
}

// Show notification popup
function showNotification(invite) {
    const notification = document.getElementById('invite-notification');
    const title = document.getElementById('notification-title');
    const message = document.getElementById('notification-message');

    if (!notification) return;

    currentNotificationInviteId = invite.id;
    title.textContent = '🎯 New Match Invite!';
    message.textContent = `Team ${invite.from_team_number} has invited you to join this match`;

    notification.classList.add('show');

    // Auto-dismiss after 10 seconds
    if (notificationTimeout) clearTimeout(notificationTimeout);
    notificationTimeout = setTimeout(() => {
        hideNotification();
    }, 10000);
}

// Hide notification popup
function hideNotification() {
    const notification = document.getElementById('invite-notification');
    if (notification) {
        notification.classList.remove('show');
    }
    currentNotificationInviteId = null;
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
        notificationTimeout = null;
    }
}

// ...existing code...
document.addEventListener('DOMContentLoaded', () => {

    const socket = io();

    // Join room
    socket.emit('join', { match_id: MATCH_ID });

    const state = {
        phase: 'Autonomous',
        color: 'red',
        isDrawing: false,
        lastX: 0,
        lastY: 0,
        // drawingData is now a dictionary: { 'Autonomous': [], 'Teleop': [], 'Endgame': [] }
        drawingData: { 'Autonomous': [], 'Teleop': [], 'Endgame': [] },
        messages: [],
        strategies: {},
        teams: [],
        invites: [],
        lastInviteCheck: null // Track last invite to detect new ones
    };

    // DOM Elements
    const canvas = document.getElementById('field-canvas');
    const ctx = canvas.getContext('2d');
    const strategyText = document.getElementById('strategy-text');
    const chatDiv = document.getElementById('chat-messages');
    const teamsListDiv = document.getElementById('active-teams-list');
    const invitesListDiv = document.getElementById('match-invites-list');

    // --- Socket Listeners ---

    socket.on('message', (msg) => {
        state.messages.push(msg);
        const div = document.createElement('div');
        div.className = 'message';
        div.innerHTML = `
            <strong>${msg.team_number} <small>${new Date(msg.timestamp).toLocaleTimeString()}</small></strong>
            ${msg.content}
        `;
        chatDiv.appendChild(div);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    });

    socket.on('drawing_update', (data) => {
        if (data.phase && data.drawing_data) {
            state.drawingData[data.phase] = JSON.parse(data.drawing_data);
            if (data.phase === state.phase) {
                renderDrawings();
            }
        }
    });

    socket.on('strategy_update', (data) => {
        if (data.phase && data.text_content !== undefined) {
            state.strategies[data.phase] = data.text_content;
            if (data.phase === state.phase && document.activeElement !== strategyText) {
                strategyText.value = data.text_content;
            }
        }
    });

    // --- Canvas Logic ---

    // Use an image as the field background
    const fieldImg = new Image();
    fieldImg.src = '/static/images/FRC_Field_TopView.png'; // add your image at static/images/FRC_Field_TopView.png
    let fieldImageLoaded = false;

    fieldImg.onload = () => {
        // Swap width and height for 90-degree rotation
        canvas.width = fieldImg.naturalHeight || 800;
        canvas.height = fieldImg.naturalWidth || 500;
        fieldImageLoaded = true;
        renderDrawings(); // initial render once image ready
    };

    // If image already loaded or failed
    if (fieldImg.complete) {
        fieldImg.onload();
    }

    function drawField() {
        if (fieldImageLoaded) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Save the current context state
            ctx.save();

            // Rotate 90 degrees counterclockwise (-90 degrees)
            // Move to center, rotate, then translate back
            ctx.translate(0, canvas.height);
            ctx.rotate(-Math.PI / 2);

            // Draw the image (now rotated)
            ctx.drawImage(fieldImg, 0, 0, fieldImg.naturalWidth, fieldImg.naturalHeight);

            // Restore the context state
            ctx.restore();
        } else {
            // fallback while image loads
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#666';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Field Lines (Simplified fallback)
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.strokeRect(50, 50, canvas.width - 100, canvas.height - 100);

            ctx.beginPath();
            ctx.moveTo(canvas.width / 2, 0);
            ctx.lineTo(canvas.width / 2, canvas.height);
            ctx.stroke();
        }
    }

    function renderDrawings() {
        drawField(); // Clear and redraw field

        // Get current phase drawings
        const currentDrawings = state.drawingData[state.phase] || [];

        // Draw each path
        ctx.save();
        for (const path of currentDrawings) {
            if (!path || !Array.isArray(path.points) || path.points.length === 0) continue;
            ctx.beginPath();
            ctx.strokeStyle = path.color || 'red';
            ctx.lineWidth = 3;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';

            const first = path.points[0];
            ctx.moveTo(first.x, first.y);
            for (let i = 1; i < path.points.length; i++) {
                const p = path.points[i];
                ctx.lineTo(p.x, p.y);
            }
            ctx.stroke();
        }
        ctx.restore();
    }

    // --- Interaction handlers ---

    canvas.addEventListener('mousedown', (e) => {
        state.isDrawing = true;
        const rect = canvas.getBoundingClientRect();
        state.lastX = e.clientX - rect.left;
        state.lastY = e.clientY - rect.top;

        // Ensure array exists and handles potential object-from-server issue
        if (!state.drawingData[state.phase] || !Array.isArray(state.drawingData[state.phase])) {
            state.drawingData[state.phase] = [];
        }

        // Start new path in current phase
        state.drawingData[state.phase].push({
            color: state.color,
            points: [{ x: state.lastX, y: state.lastY }]
        });
    });

    canvas.addEventListener('mousemove', (e) => {
        if (!state.isDrawing) return;

        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Add point to current path
        const currentPhaseDrawings = state.drawingData[state.phase];
        const currentPath = currentPhaseDrawings[currentPhaseDrawings.length - 1];
        currentPath.points.push({ x, y });

        renderDrawings();

        state.lastX = x;
        state.lastY = y;
    });

    canvas.addEventListener('mouseup', () => {
        if (!state.isDrawing) return;
        state.isDrawing = false;
        saveDrawing();
    });

    canvas.addEventListener('mouseout', () => {
        if (!state.isDrawing) return;
        state.isDrawing = false;
        saveDrawing();
    });

    // Clear Button
    const clearBtn = document.getElementById('clear-drawing-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            state.drawingData[state.phase] = [];
            renderDrawings();
            saveDrawing();
        });
    }

    // Color Picker
    document.querySelectorAll('.color-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.color = btn.dataset.color;
        });
    });

    // --- API Calls ---

    async function fetchData() {
        try {
            const res = await fetch(`/api/matches/${MATCH_ID}/data`);
            if (res.ok) {
                const data = await res.json();
                updateUI(data);
                const statusEl = document.getElementById('connection-status');
                if (statusEl) {
                    statusEl.textContent = 'Connected (Live)';
                    statusEl.style.color = '#4ade80'; // green
                }
            } else {
                console.error("Fetch error");
            }
        } catch (err) {
            console.error(err);
            const statusEl = document.getElementById('connection-status');
            if (statusEl) {
                statusEl.textContent = 'Disconnected';
                statusEl.style.color = '#f87171'; // red
            }
        }
    }

    function updateUI(data) {
        // Initial Chat Load
        if (data.messages) {
            state.messages = data.messages;
            chatDiv.innerHTML = '';
            state.messages.forEach(msg => {
                const div = document.createElement('div');
                div.className = 'message';
                div.innerHTML = `
                    <strong>${msg.team_number} <small>${new Date(msg.timestamp).toLocaleTimeString()}</small></strong>
                    ${msg.content}
                `;
                chatDiv.appendChild(div);
            });
            chatDiv.scrollTop = chatDiv.scrollHeight;
        }

        state.strategies = data.strategies || {};
        if (strategyText && document.activeElement !== strategyText) {
            strategyText.value = state.strategies[state.phase] || '';
        }

        if (data.drawings) {
            for (const [phase, json] of Object.entries(data.drawings)) {
                try {
                    const parsed = JSON.parse(json);
                    state.drawingData[phase] = Array.isArray(parsed) ? parsed : [];
                } catch (e) {
                    state.drawingData[phase] = [];
                }
            }
            renderDrawings();
        }

        // Teams
        if (data.teams) {
            state.teams = data.teams;
            renderTeams();
        }

        // Invites
        if (data.invites) {
            // Check for new invites to current user
            const newInvites = data.invites.filter(invite => {
                // Must be for us
                if (invite.to_team_number !== CURRENT_TEAM_NUMBER) return false;

                // Check if this is a new invite we haven't seen
                const isNew = !state.invites.find(old => old.id === invite.id);
                return isNew;
            });

            // Show notification for first new invite
            if (newInvites.length > 0 && state.lastInviteCheck !== null) {
                showNotification(newInvites[0]);
            }

            state.invites = data.invites;
            state.lastInviteCheck = Date.now();
            renderInvites();
        }
    }

    function renderTeams() {
        if (!teamsListDiv) return;
        teamsListDiv.innerHTML = '';

        if (state.teams.length === 0) {
            teamsListDiv.innerHTML = '<div style="padding: 0.5rem; color: var(--text-secondary); font-size: 0.85em;">No teams yet</div>';
            return;
        }

        state.teams.forEach(team => {
            const div = document.createElement('div');
            div.className = 'team-item';
            const allianceClass = team.alliance_color ? team.alliance_color.toLowerCase() : '';
            const activeStatus = team.is_active ?
                '<span style="height: 8px; width: 8px; background-color: #4ade80; border-radius: 50%; display: inline-block; margin-left: 5px;"></span>' :
                '<span style="height: 8px; width: 8px; background-color: #666; border-radius: 50%; display: inline-block; margin-left: 5px;"></span>';

            div.innerHTML = `<div><strong>${team.team_number}</strong> ${team.alliance_color ? `<span class="team-badge ${allianceClass}">${team.alliance_color}</span>` : ''} ${activeStatus}</div>`;
            teamsListDiv.appendChild(div);
        });
    }

    function renderInvites() {
        if (!invitesListDiv) return;
        invitesListDiv.innerHTML = '';

        if (state.invites.length === 0) {
            invitesListDiv.innerHTML = '<div style="padding: 0.5rem; color: var(--text-secondary); font-size: 0.85em;">No pending invites</div>';
            return;
        }

        state.invites.filter(i => i.status === 'Pending').forEach(invite => {
            const div = document.createElement('div');
            div.className = 'invite-item';

            // Check if this is an invite TO us or FROM us
            const isReceived = invite.to_team_number === CURRENT_TEAM_NUMBER;

            div.innerHTML = `
                <div><strong>Team ${invite.from_team_number}</strong> → <strong>Team ${invite.to_team_number}</strong></div>
                ${isReceived ? `
                    <div class="invite-actions">
                        <button onclick="respondToInvite(${invite.id}, 'Accepted')" class="btn">Accept</button>
                        <button onclick="respondToInvite(${invite.id}, 'Declined')" class="btn btn-secondary">Decline</button>
                    </div>
                ` : '<div style="color: var(--text-secondary);">Pending...</div>'}
            `;
            invitesListDiv.appendChild(div);
        });
    }

    // --- Socket Actions ---

    function saveStrategy() {
        if (!strategyText) return;
        const text = strategyText.value;
        state.strategies[state.phase] = text;
        socket.emit('update_strategy', {
            match_id: MATCH_ID,
            phase: state.phase,
            text_content: text
        });
    }

    function saveDrawing() {
        socket.emit('update_drawing', {
            match_id: MATCH_ID,
            phase: state.phase,
            drawing_data: JSON.stringify(state.drawingData[state.phase])
        });
    }

    // Chat Send
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = e.target.elements['content'];
            if (!input.value) return;
            socket.emit('chat_message', {
                match_id: MATCH_ID,
                team_id: CURRENT_TEAM_ID,
                team_number: CURRENT_TEAM_NUMBER,
                content: input.value,
                timestamp: new Date().toISOString()
            });
            input.value = '';
        });
    }

    // Strategy Save
    const saveStrategyBtn = document.getElementById('save-strategy-btn');
    if (saveStrategyBtn) saveStrategyBtn.addEventListener('click', saveStrategy);
    if (strategyText) strategyText.addEventListener('blur', saveStrategy); // Auto-save on blur

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            state.phase = tab.dataset.phase;
            if (strategyText) strategyText.value = state.strategies[state.phase] || '';
            renderDrawings(); // Switch drawing context
        });
    });

    // Invite Team Form
    const inviteForm = document.getElementById('invite-team-form');
    if (inviteForm) {
        inviteForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const teamNumber = e.target.elements['team_number'].value;

            try {
                const res = await fetch('/api/invites', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        match_id: MATCH_ID,
                        to_team_number: teamNumber
                    })
                });

                const result = await res.json();

                if (res.ok) {
                    e.target.reset();
                    fetchData(); // Refresh to show new invite
                } else {
                    alert(result.error || 'Failed to send invite');
                }
            } catch (err) {
                console.error(err);
                alert('Failed to send invite');
            }
        });
    }

    // Init Logic
    // drawField and render will be triggered when image loads; if no image present, call once
    if (!fieldImageLoaded) {
        // set a reasonable default size if image absent
        if (!canvas.width) canvas.width = 800;
        if (!canvas.height) canvas.height = 500;
        drawField();
    }
    fetchData();
    setInterval(fetchData, 10000); // Poll every 10s for non-socket data (teams, invites)
});
// ...existing code...
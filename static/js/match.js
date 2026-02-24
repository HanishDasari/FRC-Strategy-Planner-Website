// Global variables for notification
let currentNotificationInviteId = null;
let notificationTimeout = null;

// Global function for responding to invites
async function respondToInvite(inviteId, status) {
    try {
        const res = await fetch(`/api/invites/${inviteId}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });

        if (res.ok) {
            // Re-fetch data instead of full reload if possible, but reload is safer for complex state
            window.location.reload();
        } else {
            const result = await res.json();
            alert(result.error || 'Failed to respond to invite');
        }
    } catch (err) {
        console.error(err);
        alert('Failed to respond to invite');
    }
}

// Show notification popup
function showNotification(invite) {
    const notification = document.getElementById('invite-notification');
    const title = document.getElementById('notification-title');
    const message = document.getElementById('notification-message');
    const acceptBtn = document.getElementById('notification-accept-btn');
    const declineBtn = document.getElementById('notification-decline-btn');

    if (!notification) return;

    title.textContent = "🎯 New Match Invite!";
    message.textContent = `Team ${invite.from_team_number} has invited you to join this match`;

    acceptBtn.onclick = () => respondToInvite(invite.id, 'Accepted');
    declineBtn.onclick = () => respondToInvite(invite.id, 'Declined');

    notification.classList.add('show');

    // Auto-dismiss after 10 seconds
    if (notificationTimeout) clearTimeout(notificationTimeout);
    notificationTimeout = setTimeout(() => {
        notification.classList.remove('show');
    }, 10000);
}

document.addEventListener('DOMContentLoaded', () => {

    const socket = io();

    socket.on('connect', () => {
        console.log("Connected to match socket");
        // Join match room AND team room (handled by server on 'join' event)
        socket.emit('join', { match_id: MATCH_ID });
    });

    const state = {
        phase: 'Autonomous',
        color: 'red',
        isDrawing: false,
        lastX: 0,
        lastY: 0,
        drawingData: { 'Autonomous': [], 'Teleop': [], 'Endgame': [] },
        messages: [],
        strategies: {},
        teams: [],
        invites: [],
        lastInviteCheck: null
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

    socket.on('new_invite', (invite) => {
        if (invite.match_id === MATCH_ID) {
            fetchData();
        }
        showNotification(invite);
    });

    socket.on('refresh_data', (data) => {
        if (data.match_id === MATCH_ID) {
            fetchData();
        }
    });

    // --- Canvas Logic ---

    const fieldImg = new Image();
    fieldImg.src = '/static/images/FRC_Field_TopView.png';
    let fieldImageLoaded = false;

    fieldImg.onload = () => {
        canvas.width = fieldImg.naturalHeight || 800;
        canvas.height = fieldImg.naturalWidth || 500;
        fieldImageLoaded = true;
        renderDrawings();
    };

    if (fieldImg.complete) {
        fieldImg.onload();
    }

    function drawField() {
        if (fieldImageLoaded) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.save();
            ctx.translate(0, canvas.height);
            ctx.rotate(-Math.PI / 2);
            ctx.drawImage(fieldImg, 0, 0, fieldImg.naturalWidth, fieldImg.naturalHeight);
            ctx.restore();
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#666';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.strokeRect(50, 50, canvas.width - 100, canvas.height - 100);
        }
    }

    function renderDrawings() {
        drawField();
        const currentDrawings = state.drawingData[state.phase] || [];
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
                ctx.lineTo(path.points[i].x, path.points[i].y);
            }
            ctx.stroke();
        }
        ctx.restore();
    }

    // Interaction
    canvas.addEventListener('mousedown', (e) => {
        state.isDrawing = true;
        const rect = canvas.getBoundingClientRect();
        state.lastX = e.clientX - rect.left;
        state.lastY = e.clientY - rect.top;
        if (!Array.isArray(state.drawingData[state.phase])) state.drawingData[state.phase] = [];
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
        const currentPhaseDrawings = state.drawingData[state.phase];
        const currentPath = currentPhaseDrawings[currentPhaseDrawings.length - 1];
        currentPath.points.push({ x, y });
        renderDrawings();
        state.lastX = x;
        state.lastY = y;
    });

    canvas.addEventListener('mouseup', () => { if (state.isDrawing) { state.isDrawing = false; saveDrawing(); } });
    canvas.addEventListener('mouseout', () => { if (state.isDrawing) { state.isDrawing = false; saveDrawing(); } });

    // Buttons
    const clearBtn = document.getElementById('clear-drawing-btn');
    if (clearBtn) clearBtn.onclick = () => {
        state.drawingData[state.phase] = [];
        renderDrawings();
        saveDrawing();
    };

    document.querySelectorAll('.color-btn').forEach(btn => {
        btn.onclick = () => {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.color = btn.dataset.color;
        };
    });

    // API
    async function fetchData() {
        try {
            const res = await fetch(`/api/matches/${MATCH_ID}/data`);
            if (res.ok) {
                const data = await res.json();
                updateUI(data);
                const statusEl = document.getElementById('connection-status');
                if (statusEl) { statusEl.textContent = 'Connected (Live)'; statusEl.style.color = '#4ade80'; }
            }
        } catch (err) {
            const statusEl = document.getElementById('connection-status');
            if (statusEl) { statusEl.textContent = 'Disconnected'; statusEl.style.color = '#f87171'; }
        }
    }

    function updateUI(data) {
        if (data.messages) {
            state.messages = data.messages;
            chatDiv.innerHTML = '';
            state.messages.forEach(msg => {
                const div = document.createElement('div');
                div.className = 'message';
                div.innerHTML = `<strong>${msg.team_number} <small>${new Date(msg.timestamp).toLocaleTimeString()}</small></strong> ${msg.content}`;
                chatDiv.appendChild(div);
            });
            chatDiv.scrollTop = chatDiv.scrollHeight;
        }
        state.strategies = data.strategies || {};
        if (strategyText && document.activeElement !== strategyText) strategyText.value = state.strategies[state.phase] || '';

        if (data.drawings) {
            for (const [phase, json] of Object.entries(data.drawings)) {
                try { state.drawingData[phase] = JSON.parse(json) || []; } catch (e) { state.drawingData[phase] = []; }
            }
            renderDrawings();
        }
        if (data.teams) { state.teams = data.teams; renderTeams(); }
        if (data.invites) { state.invites = data.invites; renderInvites(); }
    }

    function renderTeams() {
        if (!teamsListDiv) return;
        teamsListDiv.innerHTML = '';
        state.teams.forEach(team => {
            const div = document.createElement('div');
            div.className = 'team-item';
            const activeStatus = team.is_active ?
                '<span style="height: 8px; width: 8px; background-color: #4ade80; border-radius: 50%; display: inline-block; margin-left: 5px;"></span>' :
                '<span style="height: 8px; width: 8px; background-color: #666; border-radius: 50%; display: inline-block; margin-left: 5px;"></span>';
            div.innerHTML = `<div><strong>${team.team_number}</strong> ${activeStatus}</div>`;
            teamsListDiv.appendChild(div);
        });
    }

    function renderInvites() {
        if (!invitesListDiv) return;
        invitesListDiv.innerHTML = '';
        state.invites.filter(i => i.status === 'Pending').forEach(invite => {
            const div = document.createElement('div');
            div.className = 'invite-item';
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

    function saveStrategy() {
        if (!strategyText) return;
        socket.emit('update_strategy', { match_id: MATCH_ID, phase: state.phase, text_content: strategyText.value });
    }

    function saveDrawing() {
        socket.emit('update_drawing', { match_id: MATCH_ID, phase: state.phase, drawing_data: JSON.stringify(state.drawingData[state.phase]) });
    }

    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.onsubmit = (e) => {
            e.preventDefault();
            const input = e.target.elements['content'];
            if (!input.value) return;
            socket.emit('chat_message', { match_id: MATCH_ID, content: input.value, timestamp: new Date().toISOString() });
            input.value = '';
        };
    }

    const saveStrategyBtn = document.getElementById('save-strategy-btn');
    if (saveStrategyBtn) saveStrategyBtn.onclick = saveStrategy;
    if (strategyText) strategyText.onblur = saveStrategy;

    document.querySelectorAll('.tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.phase = tab.dataset.phase;
            if (strategyText) strategyText.value = state.strategies[state.phase] || '';
            renderDrawings();
        };
    });

    const inviteForm = document.getElementById('invite-team-form');
    if (inviteForm) {
        const teamInput = inviteForm.querySelector('input[name="team_number"]');
        const statusSpan = document.createElement('span');
        statusSpan.style.display = 'block'; statusSpan.style.fontSize = '0.75em'; statusSpan.style.marginTop = '0.25rem';
        teamInput.parentNode.insertBefore(statusSpan, teamInput.nextSibling);

        let statusTimeout = null;
        teamInput.oninput = () => {
            clearTimeout(statusTimeout);
            if (!teamInput.value) { statusSpan.textContent = ''; return; }
            statusTimeout = setTimeout(async () => {
                const res = await fetch(`/api/teams/${teamInput.value}/status`);
                const data = await res.json();
                if (!data.exists) { statusSpan.textContent = 'Team not found'; statusSpan.style.color = '#f87171'; }
                else { statusSpan.textContent = data.active ? 'Active' : 'Inactive'; statusSpan.style.color = data.active ? '#4ade80' : '#9ca3af'; }
            }, 500);
        };

        inviteForm.onsubmit = async (e) => {
            e.preventDefault();
            const res = await fetch('/api/invites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ match_id: MATCH_ID, to_team_number: e.target.elements['team_number'].value })
            });
            if (res.ok) { e.target.reset(); statusSpan.textContent = ''; fetchData(); }
        };
    }

    fetchData();
    setInterval(fetchData, 10000);
});
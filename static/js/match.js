document.addEventListener('DOMContentLoaded', () => {

    // State
    const state = {
        phase: 'Autonomous',
        color: 'red',
        isDrawing: false,
        lastX: 0,
        lastY: 0,
        drawingData: [], // Array of paths: {color, points: [{x, y}]}
        messages: [],
        strategies: {}
    };

    // DOM Elements
    const canvas = document.getElementById('field-canvas');
    const ctx = canvas.getContext('2d');
    const strategyText = document.getElementById('strategy-text');
    const chatDiv = document.getElementById('chat-messages');

    // --- Canvas Logic ---

    function drawField() {
        // Background
        ctx.fillStyle = '#666';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Field Lines (Simplified)
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.strokeRect(50, 50, canvas.width - 100, canvas.height - 100);

        ctx.beginPath();
        ctx.moveTo(canvas.width / 2, 0);
        ctx.lineTo(canvas.width / 2, canvas.height);
        ctx.stroke();
    }

    function renderDrawings() {
        drawField(); // Clear and redraw field

        state.drawingData.forEach(path => {
            if (path.points.length < 2) return;

            ctx.beginPath();
            ctx.strokeStyle = path.color;
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.moveTo(path.points[0].x, path.points[0].y);

            for (let i = 1; i < path.points.length; i++) {
                ctx.lineTo(path.points[i].x, path.points[i].y);
            }
            ctx.stroke();
        });
    }

    canvas.addEventListener('mousedown', (e) => {
        state.isDrawing = true;
        const rect = canvas.getBoundingClientRect();
        state.lastX = e.clientX - rect.left;
        state.lastY = e.clientY - rect.top;

        // Start new path
        state.drawingData.push({
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
        const currentPath = state.drawingData[state.drawingData.length - 1];
        currentPath.points.push({ x, y });

        renderDrawings();

        state.lastX = x;
        state.lastY = y;
    });

    canvas.addEventListener('mouseup', () => {
        state.isDrawing = false;
        saveDrawing();
    });

    canvas.addEventListener('mouseout', () => {
        state.isDrawing = false;
    });

    // Clear Button
    document.getElementById('clear-drawing-btn').addEventListener('click', () => {
        state.drawingData = [];
        renderDrawings();
        saveDrawing();
    });

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
                document.getElementById('connection-status').textContent = 'Connected';
                document.getElementById('connection-status').style.color = '#4ade80'; // green
            } else {
                console.error("Fetch error");
            }
        } catch (err) {
            console.error(err);
            document.getElementById('connection-status').textContent = 'Disconnected';
            document.getElementById('connection-status').style.color = '#f87171'; // red
        }
    }

    function updateUI(data) {
        // Chat
        if (data.messages.length > state.messages.length) {
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

        // Strategy (Only update if not focused to avoid overwriting user typing)
        // Or better: update internal cache, but only text area if different phase or first load
        state.strategies = data.strategies;
        if (document.activeElement !== strategyText) {
            strategyText.value = state.strategies[state.phase] || '';
        }

        // Drawings (Merge or overwrite? Overwrite for simplicity, but only if not drawing)
        if (!state.isDrawing) {
            try {
                const serverDrawing = JSON.parse(data.drawing);
                // Simple equality check to avoid redraw flicker (could be better)
                if (JSON.stringify(serverDrawing) !== JSON.stringify(state.drawingData)) {
                    state.drawingData = Array.isArray(serverDrawing) ? serverDrawing : [];
                    renderDrawings();
                }
            } catch (e) {
                // ignore
            }
        }
    }

    // --- Actions ---

    async function saveStrategy() {
        const text = strategyText.value;
        state.strategies[state.phase] = text;

        await fetch(`/api/matches/${MATCH_ID}/strategy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phase: state.phase,
                text_content: text
            })
        });
    }

    async function saveDrawing() {
        await fetch(`/api/matches/${MATCH_ID}/drawing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                drawing_data: JSON.stringify(state.drawingData)
            })
        });
    }

    // Chat Send
    document.getElementById('chat-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = e.target.elements['content'];
        const content = input.value;
        if (!content) return;

        await fetch(`/api/matches/${MATCH_ID}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });

        input.value = '';
        fetchData(); // Immediate update
    });

    // Strategy Save
    document.getElementById('save-strategy-btn').addEventListener('click', saveStrategy);
    strategyText.addEventListener('blur', saveStrategy); // Auto-save on blur

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Save prev phase strategy just in case? already handled by blur, but safe to force it?

            state.phase = tab.dataset.phase;
            strategyText.value = state.strategies[state.phase] || '';
        });
    });

    // Init Logic
    drawField();
    fetchData();
    setInterval(fetchData, 2000); // Poll every 2s
});

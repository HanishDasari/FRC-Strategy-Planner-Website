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
            const result = await res.json();
            if (status === 'Accepted' && result.match_url) {
                // Redirect to the match room that was accepted
                window.location.href = result.match_url;
            } else {
                window.location.reload();
            }
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
    // Don't show notification to the sender
    if (typeof CURRENT_USER_ID !== 'undefined' && Number(invite.from_user_id) === Number(CURRENT_USER_ID)) {
        return;
    }

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
        document.body.classList.add('connected');
        const connBadge = document.getElementById('connection-status');
        if (connBadge) connBadge.textContent = "Connected";
        socket.emit('join', { match_id: MATCH_ID });
    });

    socket.on('disconnect', () => {
        console.log("Disconnected from match socket");
        document.body.classList.remove('connected');
        const connBadge = document.getElementById('connection-status');
        if (connBadge) connBadge.textContent = "Disconnected";
    });

    socket.on('new_invite', (invite) => {
        if (Number(invite.match_id) === Number(MATCH_ID)) {
            fetchData();
        }
        showNotification(invite);
    });

    socket.on('refresh_data', (data) => {
        if (Number(data.match_id) === Number(MATCH_ID)) {
            fetchData();
        }
    });

    socket.on('match_deleted', (data) => {
        if (Number(data.match_id) === Number(MATCH_ID)) {
            alert("This match has been deleted by another user. You are being redirected to the dashboard.");
            window.location.href = '/dashboard';
        }
    });

    const state = {
        phase: 'Autonomous',
        color: 'red',
        isDrawing: false,
        lastX: 0,
        lastY: 0,
        isEraser: false,
        drawingData: { 'Autonomous': [], 'Teleop': [], 'Endgame': [] },
        undoData: { 'Autonomous': [], 'Teleop': [], 'Endgame': [] },
        strategies: {},
        teams: [],
        invites: [],
    };

    function restorePhase() {
        try {
            if (typeof MATCH_ID === 'undefined') return;
            const savedPhase = localStorage.getItem(`frc_phase_${MATCH_ID}`);
            if (savedPhase && ['Autonomous', 'Teleop', 'Endgame'].includes(savedPhase)) {
                console.log("Restoring phase:", savedPhase);
                state.phase = savedPhase;
                const tabs = document.querySelectorAll('.phase-tab');
                tabs.forEach(t => {
                    t.classList.toggle('active', t.dataset.phase === state.phase);
                });
                const strategyEl = document.getElementById('strategy-text');
                if (strategyEl) strategyEl.value = state.strategies[state.phase] || '';
            }
        } catch (e) { console.warn("Restore phase error:", e); }
    }

    // DOM Elements
    const canvas = document.getElementById('field-canvas');
    const ctx = canvas.getContext('2d');
    const strategyText = document.getElementById('strategy-text');
    const teamsListDiv = document.getElementById('active-teams-list');
    const invitesListDiv = document.getElementById('match-invites-list');

    // --- Socket Listeners ---

    // --- Socket Listeners ---

    socket.on('drawing_update', (data) => {
        if (data.phase && data.drawing_data) {
            try {
                let parsed = JSON.parse(data.drawing_data);
                if (!Array.isArray(parsed)) parsed = [];
                state.drawingData[data.phase] = parsed;
            } catch (e) {
                state.drawingData[data.phase] = [];
            }
            if (data.phase === state.phase) {
                renderDrawings();
            }
        }
    });

    socket.on('strategy_update', (data) => {
        if (data.phase && data.strategy_text !== undefined) {
            state.strategies[data.phase] = data.strategy_text;
            if (data.phase === state.phase && document.activeElement !== strategyText) {
                strategyText.value = data.strategy_text;
            }
        }
    });


    // --- Canvas: Two-Layer Architecture ---
    const fieldCanvas = document.getElementById('field-canvas');
    if (!fieldCanvas) return; // Guard
    const pContent = fieldCanvas.parentElement;
    if (pContent) {
        // Force vertical scrolling only, NO sideways scrolling
        pContent.style.display = 'block';
        pContent.style.textAlign = 'center';
        pContent.style.padding = '0';
        pContent.style.overflowY = 'auto';
        pContent.style.overflowX = 'hidden';
        pContent.style.height = '100%';
    }

    const fieldCtx = fieldCanvas.getContext('2d');

    // Dynamic dimensions (Vertical Orientation)
    let CANVAS_W = 400;
    let CANVAS_H = 800;
    let fieldImageLoaded = false;
    let canvasIsReady = false;

    // Create the drawing canvas and overlay it on top of the field canvas
    const drawCanvas = document.createElement('canvas');
    drawCanvas.id = 'drawing-canvas';
    const drawCtx = drawCanvas.getContext('2d', { alpha: true });

    // Wrapper setup — ALLOW vertical scrolling, NO sideways
    const canvasWrapper = document.createElement('div');
    canvasWrapper.id = 'canvas-wrapper';
    canvasWrapper.style.cssText = 'position: relative; display: block; margin: 0 auto; line-height: 0; width: 100%; box-sizing: border-box; background: #000;';

    fieldCanvas.parentElement.insertBefore(canvasWrapper, fieldCanvas);
    canvasWrapper.appendChild(fieldCanvas);
    canvasWrapper.appendChild(drawCanvas);

    function resizeCanvases(w, h) {
        console.log("Responsive resize triggered:", w, h);

        // Get actual container size for "Cover" fit
        const container = fieldCanvas.parentElement;
        const rect = container.getBoundingClientRect();

        CANVAS_W = rect.width || 800;
        CANVAS_H = rect.height || 400;

        fieldCanvas.width = CANVAS_W;
        fieldCanvas.height = CANVAS_H;
        drawCanvas.width = CANVAS_W;
        drawCanvas.height = CANVAS_H;

        // Container is already sized by CSS
        canvasWrapper.style.width = '100%';
        canvasWrapper.style.height = '100%';
        canvasWrapper.style.position = 'absolute';
        canvasWrapper.style.top = '0';
        canvasWrapper.style.left = '0';

        fieldCanvas.style.display = 'block';
        fieldCanvas.style.width = '100%';
        fieldCanvas.style.height = '100%';
        fieldCanvas.style.objectFit = 'cover'; // Backup for image draw

        drawCanvas.style.cssText = `position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; z-index: 1000; pointer-events: all;`;

        canvasIsReady = true;
        restorePhase();
        drawFieldImage();
        renderDrawings();
    }

    const fieldImg = new Image();
    fieldImg.src = '/static/images/FRC_Field_TopView.png';

    function updateCanvasSize() {
        // ALWAYS use horizontal dimensions
        const imgW = fieldImg.naturalWidth || 800;
        const imgH = fieldImg.naturalHeight || 400;

        resizeCanvases(imgW, imgH);
    }

    window.addEventListener('resize', () => {
        if (fieldImageLoaded) {
            updateCanvasSize();
        }
    });

    function getCoverParams() {
        const isHorizontal = window.innerWidth >= 768;
        const iw = fieldImg.naturalWidth || 800;
        const ih = fieldImg.naturalHeight || 400;
        const cw = CANVAS_W;
        const ch = CANVAS_H;

        let scale, ox, oy;
        let effectiveW, effectiveH;

        if (isHorizontal) {
            effectiveW = iw;
            effectiveH = ih;
        } else {
            // Vertical view: Image is rotated 90deg
            effectiveW = ih;
            effectiveH = iw;
        }

        const iRatio = effectiveW / effectiveH;
        const cRatio = cw / ch;

        if (cRatio > iRatio) {
            scale = cw / effectiveW;
            ox = 0;
            oy = (ch - effectiveH * scale) / 2;
        } else {
            scale = ch / effectiveH;
            ox = (cw - effectiveW * scale) / 2;
            oy = 0;
        }

        return { scale, ox, oy, iw, ih, isHorizontal };
    }

    function drawFieldImage() {
        if (!fieldCtx) return;
        fieldCtx.clearRect(0, 0, CANVAS_W, CANVAS_H);
        if (fieldImageLoaded) {
            const { scale, ox, oy, iw, ih, isHorizontal } = getCoverParams();
            if (isHorizontal) {
                fieldCtx.drawImage(fieldImg, 0, 0, iw, ih, ox, oy, iw * scale, ih * scale);
            } else {
                // Vertical: Rotate 90deg Clockwise
                fieldCtx.save();
                fieldCtx.translate(ox + (ih * scale), oy);
                fieldCtx.rotate(Math.PI / 2);
                fieldCtx.drawImage(fieldImg, 0, 0, iw, ih, 0, 0, iw * scale, ih * scale);
                fieldCtx.restore();
            }
        } else {
            fieldCtx.fillStyle = '#111';
            fieldCtx.fillRect(0, 0, CANVAS_W, CANVAS_H);
        }
    }

    fieldImg.onload = () => {
        console.log("Field image loaded successfully.");
        fieldImageLoaded = true;
        updateCanvasSize();
    };

    fieldImg.onerror = () => {
        console.error("FAILED to load field image from:", fieldImg.src);
        resizeCanvases(800, 400);
    };

    // Immediate fallback initialization
    if (fieldImg.complete && fieldImg.naturalWidth > 0) {
        fieldImg.onload();
    } else {
        resizeCanvases(800, 400);
    }

    function renderDrawings() {
        if (!drawCtx || !canvasIsReady) return;
        drawCtx.clearRect(0, 0, CANVAS_W, CANVAS_H);
        drawCtx.globalCompositeOperation = 'source-over';
        const currentDrawings = state.drawingData[state.phase] || [];

        const { scale, ox, oy, iw, ih, isHorizontal } = getCoverParams();

        for (const path of currentDrawings) {
            if (!path || !Array.isArray(path.points) || path.points.length < 2) continue;
            drawCtx.beginPath();
            if (path.isEraser) {
                drawCtx.globalCompositeOperation = 'destination-out';
                drawCtx.lineWidth = path.thickness || 20;
            } else {
                drawCtx.globalCompositeOperation = 'source-over';
                drawCtx.strokeStyle = path.color || 'red';
                drawCtx.lineWidth = path.thickness || 3;
            }
            drawCtx.lineJoin = 'round';
            drawCtx.lineCap = 'round';

            // Render Normalized -> Display conversion
            for (let i = 0; i < path.points.length; i++) {
                const { x, y } = path.points[i]; // nX, nY (Horizonatal Normalized)
                let px, py;
                if (isHorizontal) {
                    px = x * (iw * scale) + ox;
                    py = y * (ih * scale) + oy;
                } else {
                    // Vertical: Rotate 90deg Clockwise
                    // NHS -> Vertical Display
                    const rx = ih - (y * ih);
                    const ry = x * iw;
                    px = rx * scale + ox;
                    py = ry * scale + oy;
                }

                if (i === 0) {
                    drawCtx.moveTo(px, py);
                } else {
                    drawCtx.lineTo(px, py);
                }
            }
            drawCtx.stroke();
        }
        drawCtx.globalCompositeOperation = 'source-over';
    }

    function getCoords(e) {
        let rect = drawCanvas.getBoundingClientRect();

        // Robust fallback
        if (rect.width === 0 || rect.height === 0) {
            console.warn("Canvas rect is 0x0. Using fallback dimensions.");
            resizeCanvases(CANVAS_W, CANVAS_H);
            rect = drawCanvas.getBoundingClientRect();
            if (rect.width === 0) {
                rect = { left: 0, top: 0, width: CANVAS_W, height: CANVAS_H };
            }
        }

        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;

        const scaleX = CANVAS_W / rect.width;
        const scaleY = CANVAS_H / rect.height;

        const px = (clientX - rect.left) * scaleX;
        const py = (clientY - rect.top) * scaleY;

        // Display -> Normalized conversion
        const { scale, ox, oy, iw, ih, isHorizontal } = getCoverParams();
        let nx, ny;
        if (isHorizontal) {
            nx = (px - ox) / (iw * scale);
            ny = (py - oy) / (ih * scale);
        } else {
            // Vertical: Rotate 90deg Clockwise
            const rx = (px - ox) / scale;
            const ry = (py - oy) / scale;
            nx = ry / iw;
            ny = (ih - rx) / ih;
        }
        return { x: nx, y: ny };
    }

    function startDrawing(e) {
        const coords = getCoords(e);

        console.log("Drawing start at:", coords.x, coords.y);
        state.isDrawing = true;
        state.lastX = coords.x;
        state.lastY = coords.y;

        const baseThickness = parseInt(document.getElementById('thickness-slider')?.value || 3);

        // Ensure phase exists to prevent push errors
        if (!state.drawingData[state.phase]) state.drawingData[state.phase] = [];
        if (!state.undoData[state.phase]) state.undoData[state.phase] = [];

        // Clear redo stack on new drawing
        state.undoData[state.phase] = [];

        state.drawingData[state.phase].push({
            color: state.color,
            isEraser: state.isEraser,
            thickness: state.isEraser ? baseThickness * 3 : baseThickness,
            points: [{ x: state.lastX, y: state.lastY }]
        });
        if (e.cancelable) e.preventDefault();
    }

    function moveDrawing(e) {
        if (!state.isDrawing) return;
        const coords = getCoords(e);

        const currentPhaseDrawings = state.drawingData[state.phase];
        if (!currentPhaseDrawings || currentPhaseDrawings.length === 0) return;
        const currentPath = currentPhaseDrawings[currentPhaseDrawings.length - 1];
        if (!currentPath) return;

        currentPath.points.push({ x: coords.x, y: coords.y });
        renderDrawings();
        if (e.cancelable) e.preventDefault();
    }

    function stopDrawing() {
        if (state.isDrawing) {
            console.log("Drawing stop. Saving...");
            state.isDrawing = false;
            saveDrawing();
        }
    }

    // Interaction Listeners (Z-INDEX 9999)
    drawCanvas.addEventListener('mousedown', startDrawing, true);
    drawCanvas.addEventListener('mousemove', moveDrawing, true);
    drawCanvas.addEventListener('mouseup', stopDrawing, true);
    drawCanvas.addEventListener('mouseout', stopDrawing, true);

    // Touch Support for mobile/tablets
    drawCanvas.addEventListener('touchstart', startDrawing, { passive: false });
    drawCanvas.addEventListener('touchmove', moveDrawing, { passive: false });
    drawCanvas.addEventListener('touchend', stopDrawing);

    // Keyboard Hotkeys for Undo / Redo
    document.addEventListener('keydown', (e) => {
        // Prevent hotkeys from triggering if user is typing in chat or strategy box
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        if (e.ctrlKey || e.metaKey) {
            const currentPhaseDrawings = state.drawingData[state.phase];
            const currentPhaseUndo = state.undoData[state.phase];

            if (e.key === 'z' && !e.shiftKey) {
                // Undo
                e.preventDefault();
                if (currentPhaseDrawings.length > 0) {
                    const lastDrawing = currentPhaseDrawings.pop();
                    currentPhaseUndo.push(lastDrawing);
                    renderDrawings();
                    saveDrawing();
                    console.log("Undo triggered.");
                }
            } else if ((e.key === 'z' && e.shiftKey) || e.key === 'y') {
                // Redo (Ctrl+Y or Ctrl+Shift+Z)
                e.preventDefault();
                if (currentPhaseUndo.length > 0) {
                    const redoDrawing = currentPhaseUndo.pop();
                    currentPhaseDrawings.push(redoDrawing);
                    renderDrawings();
                    saveDrawing();
                    console.log("Redo triggered.");
                }
            }
        }
    });

    // Tool Listeners
    const clearBtn = document.getElementById('clear-drawing-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (!confirm('Clear all drawings for this phase?')) return;
            state.drawingData[state.phase] = [];
            state.undoData[state.phase] = []; // also clear redo history
            renderDrawings();
            saveDrawing();
        });
    }

    const colorBtns = document.querySelectorAll('.color-btn:not(#eraser-btn)');
    colorBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.color = btn.dataset.color || 'white';
            state.isEraser = false;
            console.log("Active Color:", state.color);
        });
    });

    const eraserBtn = document.getElementById('eraser-btn');
    if (eraserBtn) {
        eraserBtn.addEventListener('click', () => {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
            eraserBtn.classList.add('active');
            state.isEraser = true;
            console.log("Eraser Active");
        });
    }

    const thicknessSlider = document.getElementById('thickness-slider');
    const thicknessVal = document.getElementById('thickness-val');
    if (thicknessSlider) {
        thicknessSlider.addEventListener('input', (e) => {
            const val = e.target.value;
            if (thicknessVal) thicknessVal.textContent = val + 'px';
        });
    }

    // API
    async function fetchData() {
        console.log("Fetching match data...");
        try {
            const res = await fetch(`/api/matches/${MATCH_ID}/data`);
            if (!res.ok) {
                console.error("Match data fetch failed:", res.status);
                return;
            }
            const data = await res.json();
            console.log("Match data received:", data);
            updateUI(data);
            const statusEl = document.getElementById('connection-status');
            if (statusEl) { statusEl.textContent = 'Connected (Live)'; statusEl.style.color = '#4ade80'; }
        } catch (err) {
            console.error("Fetch error:", err);
            const statusEl = document.getElementById('connection-status');
            if (statusEl) { statusEl.textContent = 'Disconnected'; statusEl.style.color = '#f87171'; }
        }
    }

    function updateUI(data) {
        console.log("Updating UI with received data...");
        // --- Teams & Invites ---
        try {
            if (data.teams) {
                state.teams = data.teams;
                renderTeams();
            }
        } catch (e) { console.error('renderTeams error:', e); }

        try {
            if (data.invites) {
                state.invites = data.invites;
                renderInvites();
            }
        } catch (e) { console.error('renderInvites error:', e); }

        // --- Strategy ---
        try {
            if (data.strategies) {
                // Merge strategies
                for (const [phase, content] of Object.entries(data.strategies)) {
                    state.strategies[phase] = content || '';
                }
            }
            if (strategyText && document.activeElement !== strategyText) {
                strategyText.value = state.strategies[state.phase] || '';
            }
        } catch (e) { console.error('strategy render error:', e); }

        // --- Drawings: isolated so canvas errors never block above sections ---
        try {
            if (data.drawings) {
                for (const [phase, json] of Object.entries(data.drawings)) {
                    if (json) {
                        try {
                            let parsed = JSON.parse(json);
                            if (Array.isArray(parsed)) {
                                state.drawingData[phase] = parsed;
                            }
                        } catch (e) {
                            console.error(`Error parsing drawing data for phase ${phase}:`, e);
                        }
                    } else {
                        state.drawingData[phase] = state.drawingData[phase] || [];
                    }
                }
                renderDrawings();
            }
        } catch (e) { console.error('renderDrawings error:', e); }
    }

    function renderTeams() {
        if (!teamsListDiv) return;
        teamsListDiv.innerHTML = '';
        state.teams.forEach(team => {
            const div = document.createElement('div');
            div.className = 'team-item';

            const isActive = !!team.is_active;
            const dotColor = isActive ? '#4ade80' : '#666';
            const statusDot = `<span style="height: 10px; width: 10px; background-color: ${dotColor}; border-radius: 50%; display: inline-block; margin-right: 10px;"></span>`;

            div.style.padding = '0.75rem 1rem';
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.borderBottom = '1px solid var(--border)';

            div.innerHTML = `
                ${statusDot}
                <div style="flex-grow: 1;">
                    <div style="font-weight: 700; color: var(--text-primary); font-size: 0.95rem;">Team ${team.team_number}</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${team.team_name}</div>
                </div>
            `;
            teamsListDiv.appendChild(div);
        });
    }

    function renderInvites() {
        if (!invitesListDiv) return;
        invitesListDiv.innerHTML = '';

        const pendingInvites = state.invites.filter(i => i.status === 'Pending');

        if (pendingInvites.length === 0) {
            invitesListDiv.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.8rem; text-align: center; padding: 1rem;">No pending invites</div>';
            return;
        }

        pendingInvites.forEach(invite => {
            const div = document.createElement('div');
            div.className = 'invite-item';
            div.style.padding = '0.6rem 0.75rem';
            div.style.backgroundColor = 'rgba(255,255,255,0.03)';
            div.style.borderRadius = '8px';
            div.style.marginBottom = '0.5rem';
            div.style.fontSize = '0.8rem';
            div.style.border = '1px solid rgba(255,255,255,0.05)';

            const isReceived = Number(invite.to_team_number) === Number(CURRENT_TEAM_NUMBER);

            let actionsHtml = '';
            const isFromMe = typeof CURRENT_USER_ID !== 'undefined' && Number(invite.from_user_id) === Number(CURRENT_USER_ID);

            if (isFromMe) {
                actionsHtml = `
                    <div style="display: flex; align-items: center; gap: 5px; color: var(--text-secondary); font-style: italic; font-size: 0.7rem;">
                        Invite Pending...
                    </div>
                `;
            } else if (isReceived) {
                actionsHtml = `
                    <div class="invite-actions" style="display: flex; gap: 0.4rem;">
                        <button class="btn btn-accept-invite" style="padding: 0.3rem 0.6rem; font-size: 0.7rem;">Accept</button>
                        <button class="btn btn-secondary btn-decline-invite" style="padding: 0.3rem 0.6rem; font-size: 0.7rem;">Decline</button>
                    </div>
                `;
            } else {
                actionsHtml = `
                    <div style="display: flex; align-items: center; gap: 5px; color: var(--accent); font-weight: 600; font-size: 0.7rem;">
                        <span class="pulse" style="width: 6px; height: 6px; background: var(--accent); border-radius: 50%;"></span>
                        Pending...
                    </div>
                `;
            }

            div.innerHTML = `
                <div style="margin-bottom: 0.4rem;">
                    <strong>Team ${invite.from_team_number}</strong> → <strong>Team ${invite.to_team_number}</strong>
                </div>
                ${actionsHtml}
            `;

            if (isReceived && !isFromMe) {
                div.querySelector('.btn-accept-invite').addEventListener('click', () => respondToInvite(invite.id, 'Accepted'));
                div.querySelector('.btn-decline-invite').addEventListener('click', () => respondToInvite(invite.id, 'Declined'));
            }

            invitesListDiv.appendChild(div);
        });
        invitesListDiv.scrollTop = invitesListDiv.scrollHeight;
    }

    let strategyTimeout = null;
    function saveStrategy(isManual = false) {
        if (!strategyText || !saveStrategyBtn) return;

        if (isManual) {
            saveStrategyBtn.textContent = 'Saving...';
            saveStrategyBtn.classList.add('btn-loading');
        }

        socket.emit('update_strategy', {
            match_id: MATCH_ID,
            phase: state.phase,
            strategy_text: strategyText.value
        });

        if (isManual) {
            setTimeout(() => {
                saveStrategyBtn.textContent = 'Saved!';
                saveStrategyBtn.style.background = '#3fb950';
                setTimeout(() => {
                    saveStrategyBtn.textContent = 'Save Plan';
                    saveStrategyBtn.style.background = '';
                    saveStrategyBtn.classList.remove('btn-loading');
                }, 2000);
            }, 500);
        }
    }

    if (strategyText) {
        strategyText.oninput = () => {
            clearTimeout(strategyTimeout);
            strategyTimeout = setTimeout(() => saveStrategy(false), 1000);
        };
        strategyText.onblur = () => saveStrategy(true);
    }

    const saveStrategyBtn = document.getElementById('save-strategy-btn');
    if (saveStrategyBtn) {
        saveStrategyBtn.onclick = () => {
            clearTimeout(strategyTimeout);
            saveStrategy(true);
        };
    }

    function saveDrawing() {
        socket.emit('update_drawing', { match_id: MATCH_ID, phase: state.phase, drawing_data: JSON.stringify(state.drawingData[state.phase]) });
    }

    document.querySelectorAll('.phase-tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.phase-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.phase = tab.dataset.phase;
            localStorage.setItem(`frc_phase_${MATCH_ID}`, state.phase);
            console.log("Phase switched to:", state.phase);
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
            const submitBtn = inviteForm.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn.textContent;

            submitBtn.disabled = true;
            submitBtn.textContent = '...';

            try {
                const res = await fetch('/api/invites', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        match_id: MATCH_ID,
                        to_team_number: e.target.elements['team_number'].value
                    })
                });

                if (res.ok) {
                    e.target.reset();
                    statusSpan.textContent = 'Invite sent!';
                    statusSpan.style.color = '#4ade80';
                    fetchData();
                    setTimeout(() => { if (statusSpan.textContent === 'Invite sent!') statusSpan.textContent = ''; }, 3000);
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed to send invite');
                    statusSpan.textContent = data.error || 'Failed';
                    statusSpan.style.color = '#f87171';
                }
            } catch (err) {
                console.error(err);
                alert('Connection error. Failed to send invite.');
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = originalBtnText;
            }
        };
    }

    restorePhase();
    fetchData();
    setInterval(fetchData, 10000);
});
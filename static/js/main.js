// --- Dashboard Logic ---
let CURRENT_USER_TEAM_ID = null;

document.addEventListener('DOMContentLoaded', () => {
    // Eye icon toggle
    const toggles = document.querySelectorAll('.password-toggle');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const input = toggle.parentElement.querySelector('input');
            const icon = toggle.querySelector('.eye-icon');
            if (input.type === 'password') {
                input.type = 'text';
                icon.textContent = '👀';
            } else {
                input.type = 'password';
                icon.textContent = '👁️';
            }
        });
    });

    // AJAX Login Handler
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            const btn = loginForm.querySelector('button[type="submit"]');
            if (!btn) return;

            // If already logging in, don't do it again
            if (btn.innerText === 'Logging in...') return;

            e.preventDefault();
            btn.innerText = 'Logging in...';
            btn.style.opacity = '0.7';
            btn.disabled = true;

            const formData = new FormData(loginForm);
            try {
                const response = await fetch(loginForm.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (response.redirected) {
                    window.location.href = response.url;
                } else {
                    const text = await response.text();
                    if (text.includes('dashboard') || response.url.includes('dashboard')) {
                        window.location.href = '/dashboard';
                    } else {
                        window.location.reload();
                    }
                }
            } catch (err) {
                console.error('Login Error:', err);
                loginForm.submit();
            }
        });
    }

    // Password strength meter
    const strengthInputs = document.querySelectorAll('input[data-strength-meter="true"]');
    strengthInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const val = e.target.value;
            const container = e.target.closest('.form-group');
            const bar = container.querySelector('.strength-bar');
            const textElement = container.querySelector('#strength-text');
            const reqLength = container.querySelector('.req-length');
            const reqUpper = container.querySelector('.req-upper');
            const reqNumber = container.querySelector('.req-number');
            const reqSpecial = container.querySelector('.req-special');

            if (!bar) return;

            let strength = 0;
            const hasLength = val.length >= 10;
            const hasUpper = /[A-Z]/.test(val);
            const hasNumber = /[0-9]/.test(val);
            const hasSpecial = /[^A-Za-z0-9]/.test(val);

            if (hasLength) strength += 1;
            if (hasUpper) strength += 1;
            if (hasNumber) strength += 1;
            if (hasSpecial) strength += 1;

            if (reqLength) {
                if (hasLength) { reqLength.textContent = '✓ 10+ characters'; reqLength.classList.add('req-met'); }
                else { reqLength.textContent = '✗ 10+ characters'; reqLength.classList.remove('req-met'); }
            }
            if (reqUpper) {
                if (hasUpper) { reqUpper.textContent = '✓ 1 uppercase letter'; reqUpper.classList.add('req-met'); }
                else { reqUpper.textContent = '✗ 1 uppercase letter'; reqUpper.classList.remove('req-met'); }
            }
            if (reqNumber) {
                if (hasNumber) { reqNumber.textContent = '✓ 1 number'; reqNumber.classList.add('req-met'); }
                else { reqNumber.textContent = '✗ 1 number'; reqNumber.classList.remove('req-met'); }
            }
            if (reqSpecial) {
                if (hasSpecial) { reqSpecial.textContent = '✓ 1 special character'; reqSpecial.classList.add('req-met'); }
                else { reqSpecial.textContent = '✗ 1 special character'; reqSpecial.classList.remove('req-met'); }
            }

            bar.className = 'strength-bar';

            const meterContainer = container.querySelector('.strength-meter-container');

            if (val.length === 0) {
                if (meterContainer) meterContainer.style.display = 'none';
                bar.style.width = '5%';
                bar.style.backgroundColor = 'var(--danger)';
                if (textElement) { textElement.textContent = 'Strength: Weak'; textElement.style.color = 'var(--danger)'; }
                return; // Stop here if empty
            } else {
                if (meterContainer) meterContainer.style.display = 'block';
            }

            if (strength === 0 || strength === 1) {
                bar.classList.add('strength-weak');
                bar.style.width = '';
                bar.style.backgroundColor = '';
                if (textElement) { textElement.textContent = 'Strength: Weak'; textElement.style.color = 'var(--danger)'; }
            } else if (strength === 2) {
                bar.classList.add('strength-fair');
                bar.style.width = '';
                bar.style.backgroundColor = '';
                if (textElement) { textElement.textContent = 'Strength: Fair'; textElement.style.color = '#f59e0b'; }
            } else if (strength === 3) {
                bar.classList.add('strength-good');
                bar.style.width = '';
                bar.style.backgroundColor = '';
                if (textElement) { textElement.textContent = 'Strength: Good'; textElement.style.color = '#3b82f6'; }
            } else if (strength >= 4) {
                bar.classList.add('strength-strong');
                bar.style.width = '';
                bar.style.backgroundColor = '';
                if (textElement) { textElement.textContent = 'Strength: Strong ✓'; textElement.style.color = 'var(--success)'; }
            }
        });
    });
});

async function initDashboard() {
    loadUserInfo();
    loadMatches();
    loadInvites();

    // Logout
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            window.location.href = '/auth/logout';
        });
    }

    // Create Match
    const createForm = document.getElementById('create-match-form');
    if (createForm) {
        createForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(createForm);
            const data = Object.fromEntries(formData.entries());

            try {
                const res = await fetch('/api/matches', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    createForm.reset();
                    loadMatches();
                } else {
                    const result = await res.json();
                    alert(result.error || 'Failed to create match');
                }
            } catch (err) {
                console.error(err);
                alert('An error occurred while creating the match');
            }
        });
    }

    // Socket.IO for real-time invites
    const socket = io();
    socket.on('connect', () => {
        console.log("Connected to dashboard socket");
        // Join team room for invites
        socket.emit('join', { match_id: null });
    });

    socket.on('new_invite', (invite) => {
        showNotification(invite);
        loadInvites();
    });

    socket.on('refresh_data', () => {
        loadMatches();
        loadInvites();
    });

    socket.on('match_deleted', () => {
        loadMatches();
        loadInvites();
    });

    // Automatically refresh invites every 60 seconds.
    // This naturally triggers the backend deletion of expired invites
    setInterval(loadInvites, 60000);
}

function showNotification(invite) {
    // Don't show notification to the sender
    if (typeof CURRENT_USER_ID !== 'undefined' && invite.from_user_id === CURRENT_USER_ID) {
        return;
    }

    const notification = document.getElementById('invite-notification');
    const title = document.getElementById('notification-title');
    const message = document.getElementById('notification-message');
    const acceptBtn = document.getElementById('notification-accept-btn');
    const declineBtn = document.getElementById('notification-decline-btn');

    if (!notification) return;

    title.textContent = invite.is_same_team ? "Team Notification" : "New Match Invite!";

    if (invite.is_same_team) {
        const sender = invite.from_user_name || invite.from_team_name || `Team ${invite.from_team_number}`;
        message.textContent = `${sender} is inviting you to Match ${invite.match_number}`;
    } else {
        message.textContent = `Team ${invite.from_team_number} has invited you to Match ${invite.match_number}`;
    }

    const handleResponse = async (status) => {
        try {
            const res = await fetch(`/api/invites/${invite.id}/respond`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status === 'accept' ? 'Accepted' : 'Declined' })
            });
            const result = await res.json();

            notification.classList.remove('show');

            if (status === 'accept' && result.match_url) {
                window.location.href = result.match_url;
                return;
            }

            loadInvites();
            loadMatches();
        } catch (e) {
            console.error(e);
        }
    };

    acceptBtn.onclick = () => handleResponse('accept');
    declineBtn.onclick = () => handleResponse('decline');

    notification.classList.add('show');

    // Auto-hide after 10 seconds
    setTimeout(() => {
        notification.classList.remove('show');
    }, 10000);
}

async function loadUserInfo() {
    try {
        const res = await fetch('/auth/me');
        if (res.ok) {
            const data = await res.json();
            const displayName = data.name || data.email;
            const userInfo = document.getElementById('user-info');
            if (userInfo) {
                userInfo.textContent = `${displayName} | Team ${data.team_number}`;
            }
            CURRENT_USER_TEAM_ID = data.team_id;
        }
    } catch (e) {
        console.error("Failed to load user info", e);
    }
}

async function loadMatches() {
    const list = document.getElementById('matches-list');
    try {
        const res = await fetch('/api/matches');
        const matches = await res.json();

        list.innerHTML = '';
        if (matches.length === 0) {
            list.innerHTML = '<p style="color: var(--text-secondary);">No matches found.</p>';
            return;
        }

        matches.forEach(m => {
            const div = document.createElement('div');
            div.className = 'match-item';
            div.style.padding = '1rem';
            div.style.borderBottom = '1px solid var(--border)';
            div.style.display = 'flex';
            div.style.justifyContent = 'space-between';
            div.style.alignItems = 'center';

            // Left info section
            const info = document.createElement('div');
            info.innerHTML = `<strong>${m.match_type} ${m.match_number}</strong>
                <span style="color: var(--text-secondary); font-size: 0.9em; margin-left: 0.5rem;">Created by Team ${m.creator_team_number}</span>`;

            // Action buttons
            const actions = document.createElement('div');
            actions.style.display = 'flex';
            actions.style.gap = '0.5rem';
            actions.style.alignItems = 'center';

            const openBtn = document.createElement('a');
            openBtn.href = `/match/${m.id}`;
            openBtn.className = 'btn';
            openBtn.textContent = 'Open';

            const delBtn = document.createElement('button');
            delBtn.className = 'btn btn-secondary';
            delBtn.textContent = 'Delete';
            delBtn.style.backgroundColor = 'var(--red-alliance)';
            delBtn.style.border = 'none';
            delBtn.style.padding = '0.5rem 0.8rem';
            // Use addEventListener so Chrome allows confirm() and fetch
            delBtn.addEventListener('click', () => deleteMatch(m.id));

            actions.appendChild(openBtn);
            actions.appendChild(delBtn);
            div.appendChild(info);
            div.appendChild(actions);
            list.appendChild(div);
        });
    } catch (err) {
        list.textContent = 'Error loading matches.';
    }
}

async function loadInvites() {
    const list = document.getElementById('invites-list');
    try {
        const res = await fetch('/api/invites/pending');
        const invites = await res.json();

        list.innerHTML = '';
        if (invites.length === 0) {
            list.innerHTML = '<p style="color: var(--text-secondary);">No pending invites.</p>';
            return;
        }

        invites.forEach(inv => {
            const div = document.createElement('div');
            div.style.padding = '0.5rem';
            div.style.borderBottom = '1px solid var(--border)';

            const sender = inv.is_same_team
                ? (inv.from_user_name || inv.from_team_name || `Team ${inv.from_team}`)
                : `Team ${inv.from_team}`;

            const isFromMe = typeof CURRENT_USER_ID !== 'undefined' && Number(inv.from_user_id) === Number(CURRENT_USER_ID);

            div.innerHTML = `
                <div style="margin-bottom: 0.5rem">
                    <strong>${sender}</strong> invites you to Match ${inv.match_number}
                </div>
                ${isFromMe ? '<div style="font-size: 0.75rem; color: var(--text-secondary); font-style: italic;">Invite Pending...</div>' : `
                <div style="display: flex; gap: 0.5rem;">
                    <button onclick="respondInvite(${inv.id}, 'Accepted')" class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;">Accept</button>
                    <button onclick="respondInvite(${inv.id}, 'Declined')" class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;">Decline</button>
                </div>
                `}
            `;
            list.appendChild(div);
        });
    } catch (err) {
        console.error(err);
    }
}

async function respondInvite(id, status) {
    try {
        const res = await fetch(`/api/invites/${id}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        const result = await res.json();

        if (status === 'Accepted' && result.match_url) {
            window.location.href = result.match_url;
            return;
        }

        loadInvites();
        loadMatches();
    } catch (err) {
        alert('Action failed');
    }
}

async function deleteMatch(id) {
    if (!confirm('Are you sure you want to delete this match? This will permanently remove all strategy notes, drawings, and chat messages.')) {
        return;
    }

    try {
        const res = await fetch(`/api/matches/${id}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            loadMatches();
        } else {
            const data = await res.json();
            alert(data.error || 'Failed to delete match');
        }
    } catch (err) {
        console.error(err);
        alert('An error occurred while deleting the match');
    }
}

document.addEventListener('DOMContentLoaded', () => {

    // Auth Tabs
    const tabs = document.querySelectorAll('.tab');
    if (tabs.length > 0) {
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                // Toggle tabs
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Toggle forms
                const target = tab.dataset.target;
                document.querySelector('#login-form').classList.toggle('hidden', target !== 'login');
                document.querySelector('#register-form').classList.toggle('hidden', target !== 'register');
                document.querySelector('#auth-error').style.display = 'none';
            });
        });
    }

    // Login Handler
    const loginForm = document.querySelector('#login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(loginForm);
            const data = Object.fromEntries(formData.entries());

            try {
                const res = await fetch('/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await res.json();

                if (res.ok) {
                    window.location.href = '/dashboard';
                } else {
                    showError(result.error);
                }
            } catch (err) {
                showError('Login failed. Please try again.');
            }
        });
    }

    // Register Handler
    const registerForm = document.querySelector('#register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(registerForm);
            const data = Object.fromEntries(formData.entries());

            try {
                const res = await fetch('/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await res.json();

                if (res.ok) {
                    // Auto login or ask to login? Let's just alert for now or switch tabs.
                    alert('Registration successful! Please login.');
                    document.querySelector('.tab[data-target="login"]').click();
                } else {
                    showError(result.error);
                }
            } catch (err) {
                showError('Registration failed.');
            }
        });
    }
});

function showError(msg) {
    const el = document.querySelector('#auth-error');
    if (el) {
        el.textContent = msg;
        el.style.display = 'block';
    } else {
        alert(msg);
    }
}

// --- Dashboard Logic ---

async function initDashboard() {
    loadUserInfo();
    loadMatches();
    loadInvites();

    // Logout
    document.getElementById('logout-btn').addEventListener('click', async () => {
        await fetch('/auth/logout', { method: 'POST' });
        window.location.href = '/';
    });

    // Create Match
    const createForm = document.getElementById('create-match-form');
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
                alert('Failed to create match');
            }
        } catch (err) {
            console.error(err);
        }
    });
}

async function loadUserInfo() {
    const res = await fetch('/auth/me');
    const data = await res.json();
    if (data.username) {
        document.getElementById('user-info').textContent = `${data.username} | Team ${data.team_number}`;
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

            div.innerHTML = `
                <div>
                    <strong>${m.match_type} ${m.match_number}</strong>
                    <span style="color: var(--text-secondary); font-size: 0.9em; margin-left: 0.5rem;">
                        Created by Team ${m.creator_team_number}
                    </span>
                </div>
                <a href="/match/${m.id}" class="btn">Open</a>
            `;
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

            div.innerHTML = `
                <div style="margin-bottom: 0.5rem">
                    <strong>Team ${inv.from_team}</strong> invites you to Match ${inv.match_number}
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <button onclick="respondInvite(${inv.id}, 'Accepted')" class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;">Accept</button>
                    <button onclick="respondInvite(${inv.id}, 'Declined')" class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;">Decline</button>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (err) {
        console.error(err);
    }
}

async function respondInvite(id, status) {
    try {
        await fetch(`/api/invites/${id}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        loadInvites();
        loadMatches();
    } catch (err) {
        alert('Action failed');
    }
}


// --- Dashboard Logic ---

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
                const loginSection = document.getElementById('login-section');
                const registerSection = document.getElementById('register-section');

                if (target === 'login') {
                    loginSection.style.display = 'block';
                    registerSection.style.display = 'none';
                } else {
                    loginSection.style.display = 'none';
                    registerSection.style.display = 'block';
                }
            });
        });
    }
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
                    alert('Failed to create match');
                }
            } catch (err) {
                console.error(err);
            }
        });
    }
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

            div.innerHTML = `
                <div>
                    <strong>${m.match_type} ${m.match_number}</strong>
                    <span style="color: var(--text-secondary); font-size: 0.9em; margin-left: 0.5rem;">
                        Created by Team ${m.creator_team_number}
                    </span>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <a href="/match/${m.id}" class="btn">Open</a>
                    <button onclick="deleteMatch(${m.id})" class="btn btn-secondary" style="background-color: var(--red-alliance); border: none; padding: 0.5rem 0.8rem;">Delete</button>
                </div>
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

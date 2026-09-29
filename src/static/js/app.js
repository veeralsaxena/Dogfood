// Hackathon Raptors Client Interactions

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
}

// Initialize theme from storage
(function() {
  const saved = localStorage.getItem('theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
  }
})();

// Open / Close Project Modal
function openProjectModal(id) {
  const modal = document.getElementById(`modal-${id}`);
  if (modal) {
    modal.classList.add('active');
  }
}

function closeProjectModal(id) {
  const modal = document.getElementById(`modal-${id}`);
  if (modal) {
    modal.classList.remove('active');
  }
}

// Community Vote
async function castVote(projectId, btnElement) {
  try {
    const res = await fetch('/api/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId })
    });
    if (res.status === 401) {
      alert("Sign-in required: Please sign in or register to cast your verified community vote.");
      window.location.href = "/login?next=/vote";
      return;
    }
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      btnElement.innerHTML = '✓ Voted';
      btnElement.classList.add('badge-emerald');
      alert(data.message);
    } else {
      alert(data.detail || data.message || 'Could not record vote');
    }
  } catch (e) {
    alert('Voting failed: ' + e);
  }
}

// Pairwise Arena Vote
async function votePairwise(winnerId, loserId) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('auth_token');
  if (token) {
    headers['Authorization'] = token.startsWith('Token ') || token.startsWith('Bearer ') ? token : `Token ${token}`;
  }

  try {
    const res = await fetch('/api/arena/vote', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ winner_id: winnerId, loser_id: loserId })
    });
    if (res.status === 401) {
      alert('Authentication required. Please sign in to vote.');
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      return;
    }
    if (res.ok) {
      await fetchNextPairOrReload();
    } else {
      const err = await res.json();
      alert(err.detail || 'Failed to submit comparison');
    }
  } catch (e) {
    alert('Pairwise vote error: ' + e);
  }
}

async function skipMatchup() {
  await fetchNextPairOrReload();
}

async function fetchNextPairOrReload() {
  try {
    const trackParam = new URLSearchParams(window.location.search).get('track');
    let pairUrl = '/api/arena/pair';
    if (trackParam) {
      pairUrl += '?track=' + encodeURIComponent(trackParam);
    }
    const res = await fetch(pairUrl);
    if (res.ok) {
      const data = await res.json();
      if (data.project_a && data.project_b) {
        updateArenaCards(data.project_a, data.project_b);
        return;
      }
    }
    window.location.reload();
  } catch (e) {
    window.location.reload();
  }
}

function updateArenaCards(pa, pb) {
  if (!pa || !pb) {
    window.location.reload();
    return;
  }
  // Update card A
  const tbA = document.getElementById('track-badge-a');
  if (tbA) tbA.innerText = pa.track_name || pa.track_id || '';
  const titleA = document.getElementById('title-a');
  if (titleA) titleA.innerText = pa.title || '';
  const teamA = document.getElementById('team-a');
  if (teamA) teamA.innerText = `Team: ${pa.team_name || pa.team_id} (${pa.id})`;
  const sumA = document.getElementById('summary-a');
  if (sumA) sumA.innerText = pa.summary || '';
  const descContainerA = document.getElementById('desc-container-a');
  const descA = document.getElementById('desc-a');
  if (descContainerA && descA) {
    if (pa.description && pa.description !== pa.summary) {
      descA.innerText = pa.description;
      descContainerA.style.display = 'block';
    } else {
      descContainerA.style.display = 'none';
    }
  }
  const repoA = document.getElementById('repo-a');
  if (repoA) {
    if (pa.repo_url) {
      repoA.href = pa.repo_url;
      repoA.style.display = 'inline-block';
    } else {
      repoA.style.display = 'none';
    }
  }
  const demoA = document.getElementById('demo-a');
  if (demoA) {
    if (pa.demo_url) {
      demoA.href = pa.demo_url;
      demoA.style.display = 'inline-block';
    } else {
      demoA.style.display = 'none';
    }
  }
  const btnA = document.getElementById('btn-vote-a');
  if (btnA) {
    btnA.setAttribute('onclick', `votePairwise('${pa.id}', '${pb.id}')`);
  }

  // Update card B
  const tbB = document.getElementById('track-badge-b');
  if (tbB) tbB.innerText = pb.track_name || pb.track_id || '';
  const titleB = document.getElementById('title-b');
  if (titleB) titleB.innerText = pb.title || '';
  const teamB = document.getElementById('team-b');
  if (teamB) teamB.innerText = `Team: ${pb.team_name || pb.team_id} (${pb.id})`;
  const sumB = document.getElementById('summary-b');
  if (sumB) sumB.innerText = pb.summary || '';
  const descContainerB = document.getElementById('desc-container-b');
  const descB = document.getElementById('desc-b');
  if (descContainerB && descB) {
    if (pb.description && pb.description !== pb.summary) {
      descB.innerText = pb.description;
      descContainerB.style.display = 'block';
    } else {
      descContainerB.style.display = 'none';
    }
  }
  const repoB = document.getElementById('repo-b');
  if (repoB) {
    if (pb.repo_url) {
      repoB.href = pb.repo_url;
      repoB.style.display = 'inline-block';
    } else {
      repoB.style.display = 'none';
    }
  }
  const demoB = document.getElementById('demo-b');
  if (demoB) {
    if (pb.demo_url) {
      demoB.href = pb.demo_url;
      demoB.style.display = 'inline-block';
    } else {
      demoB.style.display = 'none';
    }
  }
  const btnB = document.getElementById('btn-vote-b');
  if (btnB) {
    btnB.setAttribute('onclick', `votePairwise('${pb.id}', '${pa.id}')`);
  }
}

// Quick filter in gallery
function filterProjects() {
  const query = document.getElementById('search-input')?.value.toLowerCase() || '';
  const cards = document.querySelectorAll('.project-card');
  cards.forEach(card => {
    const title = card.getAttribute('data-title')?.toLowerCase() || '';
    const summary = card.getAttribute('data-summary')?.toLowerCase() || '';
    if (title.includes(query) || summary.includes(query)) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

// Executive Role Switcher
async function switchRole(role) {
  try {
    const res = await fetch('/api/auth/switch-role', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: role })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.token) {
        localStorage.setItem('auth_token', 'Token ' + data.token);
      } else {
        localStorage.removeItem('auth_token');
      }
      if (role === 'participant') {
        window.location.href = '/participant/dashboard';
      } else if (role.startsWith('judge')) {
        window.location.href = '/judge';
      } else if (role === 'organizer') {
        window.location.href = '/war-room';
      } else {
        window.location.href = '/projects';
      }
    }
  } catch (e) {
    console.error('Role switch failed', e);
  }
}

// Initialize active role on load
(async function initActiveRole() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      const me = await res.json();
      const badge = document.getElementById('current-role-badge');
      if (badge) {
        badge.innerText = me.authenticated ? `${me.name} (${me.role})` : 'Public Visitor';
      }
      const activeRole = me.authenticated ? (me.id === 'jdg_01' ? 'judge_a' : (me.id === 'jdg_02' ? 'judge_b' : me.role)) : 'visitor';
      document.querySelectorAll('.persona-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById(`pbtn-${activeRole}`);
      if (activeBtn) activeBtn.classList.add('active');
    }
  } catch (e) {
    console.error('Failed to fetch active role', e);
  }
})();

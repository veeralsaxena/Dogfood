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
    if (res.ok) {
      btnElement.innerHTML = '✓ Voted';
      btnElement.classList.add('badge-emerald');
    } else {
      const err = await res.json();
      alert(err.detail || 'Could not record vote');
    }
  } catch (e) {
    alert('Voting failed: ' + e);
  }
}

// Pairwise Arena Vote
async function votePairwise(winnerId, loserId) {
  const token = localStorage.getItem('auth_token') || 'Token judgea0000000000000000000000000000000000';
  try {
    const res = await fetch('/api/arena/vote', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token
      },
      body: JSON.stringify({ winner_id: winnerId, loser_id: loserId })
    });
    if (res.ok) {
      window.location.reload();
    } else {
      const err = await res.json();
      alert(err.detail || 'Failed to submit comparison');
    }
  } catch (e) {
    alert('Pairwise vote error: ' + e);
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

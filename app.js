/* ================================================================
   Wumpus World Logic Agent  –  Frontend 
   New:
     - 'backtracking_home' status: agent animates path home with gold
     - 'backtracking_stuck' status: agent animates return to (0,0)
     - 'home_arrived' event: victory toast + auto-restart countdown
     - 'restarted' event: silent new run begins
     - Gold-carry indicator on agent icon
     - Run counter in metrics
   ================================================================ */

const API = 'http://127.0.0.1:5000/api';

let gameState  = null;
let agentState = null;
let autoTimer  = null;
let revealed   = false;

/* ----------------------------------------------------------------
   API helpers
   ---------------------------------------------------------------- */
async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ----------------------------------------------------------------
   Game controls
   ---------------------------------------------------------------- */
async function newGame() {
  stopAuto();
  revealed = false;
  const rows = +document.getElementById('rows').value;
  const cols = +document.getElementById('cols').value;
  try {
    const data = await api('/new_game', 'POST', { rows, cols });
    gameState  = data.env;
    agentState = data.agent;
    render();
    setButtons(true);
    toast('New game started! 🎮', 'blue');
  } catch (e) {
    toast('❌ Cannot connect to backend. Is app.py running?', 'red');
  }
}

async function stepAgent() {
  if (!gameState) return;
  try {
    const data = await api('/step', 'POST');
    gameState  = data.env;
    agentState = data.agent;
    render();
    handleStepEvent(data);
  } catch (e) {
    toast('❌ Step failed: ' + e.message, 'red');
    stopAuto();
  }
}

function handleStepEvent(data) {
  const ev = data.event;
  const st = agentState ? agentState.status : '';

  if (ev === 'gold') {
    toast('✨ Gold grabbed! Backtracking home…', 'gold');
  } else if (ev === 'backtrack_step') {
    if (data.carrying_gold) {
      toast('🏃 Heading home with gold…', 'gold');
    } else {
      toast('↩️ Backtracking to start…', 'yellow');
    }
  } else if (ev === 'home_arrived') {
    toast('🏆 Gold delivered! Run complete.', 'gold');
    stopAuto();
  } else if (ev === 'stuck_backtrack_started') {
    toast('⚠️ Stuck! Returning to (0,0)…', 'yellow');
  } else if (ev === 'stuck_end') {
    toast('⚠️ Agent got stuck. Run ended.', 'yellow');
    stopAuto();
  } else if (ev === 'pit') {
    toast('💀 Fell into a pit! Game over.', 'red');
    stopAuto();
    revealAll();
  } else if (ev === 'wumpus') {
    toast('👹 Eaten by the Wumpus! Game over.', 'red');
    stopAuto();
    revealAll();
  } else if (!data.success) {
    toast(data.message || 'Agent stopped.', 'yellow');
    stopAuto();
  }

  // Stop auto on terminal states
  if (st === 'dead' || st === 'won' || st === 'stuck') {
    stopAuto();
  }
}

function toggleAuto() {
  if (autoTimer) { stopAuto(); return; }
  const btn   = document.getElementById('auto-btn');
  btn.textContent = '⏸ Pause';
  btn.classList.add('btn-danger');
  const speed = 600;  // Fixed speed in milliseconds
  autoTimer = setInterval(async () => {
    await stepAgent();
    if (agentState && agentState.status === 'dead') {
      stopAuto();
    }
  }, speed);
}

function stopAuto() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  const btn = document.getElementById('auto-btn');
  if (btn) {
    btn.textContent = '▶️ Auto Play';
    btn.classList.remove('btn-danger');
  }
}

async function revealAll() {
  if (revealed) return;
  revealed = true;
  try {
    const data = await api('/reveal');
    gameState = data.env;
    render(true);
  } catch(e) {}
}

function setButtons(enabled) {
  document.getElementById('step-btn').disabled = !enabled;
  document.getElementById('auto-btn').disabled = !enabled;
}

/* ----------------------------------------------------------------
   Rendering
   ---------------------------------------------------------------- */
function render(showAll = false) {
  if (!gameState || !agentState) return;
  renderGrid(showAll);
  renderMetrics();
  renderPercepts();
}

function renderGrid(showAll = false) {
  const env   = gameState;
  const agent = agentState;
  const rows  = env.rows;
  const cols  = env.cols;

  const container = document.getElementById('grid-container');
  container.style.gridTemplateColumns = `repeat(${cols}, 62px)`;
  container.innerHTML = '';

  const visited       = new Set(agent.visited.map(c => c.join(',')));
  const safe          = new Set(agent.safe_cells.map(c => c.join(',')));
  const frontier      = new Set(agent.frontier.map(c => c.join(',')));
  const pits          = new Set(agent.confirmed_pits.map(c => c.join(',')));
  const wumpusConf    = new Set(agent.confirmed_wumpus.map(c => c.join(',')));
  const agentPos      = env.agent_pos.join(',');
  const goldPos       = env.gold_pos ? env.gold_pos.join(',') : null;
  const hasGold       = env.agent_has_gold;
  const isBacktracking = ['backtracking_home', 'backtracking_stuck'].includes(agent.status);

  for (let r = rows - 1; r >= 0; r--) {
    for (let c = 0; c < cols; c++) {
      const key       = `${r}_${c}`;
      const cell_data = env.grid[key] || {};
      const coordKey  = `${r},${c}`;

      const div = document.createElement('div');
      div.className = 'cell';
      div.title = `(${r},${c})`;

      // Coord label
      const coord = document.createElement('div');
      coord.className = 'coord';
      coord.textContent = `${r},${c}`;
      div.appendChild(coord);

      let icon       = '';
      let stateClass = 'unknown';

      const isAgent    = coordKey === agentPos;
      const isVisited  = visited.has(coordKey);
      const isSafe     = safe.has(coordKey);
      const isFrontier = frontier.has(coordKey);
      const isPit      = pits.has(coordKey);
      const isWumpus   = wumpusConf.has(coordKey);
      const isStart    = r === 0 && c === 0;

      if (showAll) {
        if (cell_data.pit)             { stateClass = 'pit';    icon = '🕳️'; }
        else if (cell_data.wumpus)     { stateClass = 'wumpus'; icon = '👹'; }
        else if (cell_data.gold)       { icon = '💰'; stateClass = 'safe'; }
        else if (isVisited)            { stateClass = 'visited'; icon = '✓'; }
        else if (isSafe || isFrontier) { stateClass = 'frontier'; icon = '·'; }
        else                           { stateClass = 'unknown'; icon = '?'; }
      } else {
        if (isAgent) {
          stateClass = isBacktracking ? 'backtracking' : 'agent';
          // Show gold-carry indicator
          icon = hasGold ? '🤖💰' : '🤖';
        } else if (isPit)        { stateClass = 'pit';    icon = '🕳️'; }
        else if (isWumpus)       { stateClass = 'wumpus'; icon = '👹'; }
        else if (goldPos === coordKey) { icon = '💰'; stateClass = isVisited ? 'visited' : 'frontier'; }
        else if (isVisited)      { stateClass = 'visited'; icon = '✓'; }
        else if (isFrontier)     { stateClass = 'frontier'; icon = '?'; }
        else if (isSafe)         { stateClass = 'safe'; icon = '·'; }
        else                     { stateClass = 'unknown'; }
      }

      if (isStart && !isAgent) div.classList.add('start');
      div.classList.add(stateClass);

      const iconEl = document.createElement('div');
      iconEl.style.fontSize = '1.3rem';
      iconEl.textContent = icon;
      div.appendChild(iconEl);

      // Percept hints on current cell
      if (isVisited && !showAll) {
        const p = env.percepts;
        if (coordKey === agentPos && (p.breeze || p.stench || p.glitter)) {
          const hints = document.createElement('div');
          hints.className = 'percept-icons';
          let h = '';
          if (p.breeze)  h += '💨';
          if (p.stench)  h += '💀';
          if (p.glitter) h += '✨';
          hints.textContent = h;
          div.appendChild(hints);
        }
      }

      container.appendChild(div);
    }
  }
}

function renderMetrics() {
  const a = agentState;
  document.getElementById('inference-steps').textContent = a.inference_steps.toLocaleString();
}

function renderPercepts() {
  const p   = gameState.percepts || {};
  const box = document.getElementById('percepts-display');
  const items = [];
  if (p.breeze)  items.push('<span class="percept-tag breeze">💨 Breeze</span>');
  if (p.stench)  items.push('<span class="percept-tag stench">💀 Stench</span>');
  if (p.glitter) items.push('<span class="percept-tag glitter">✨ Glitter</span>');
  box.innerHTML = items.length
    ? items.join(' ')
    : '<span class="percept-tag none">None – cell is clear</span>';
}


/* ----------------------------------------------------------------
   Toast notifications
   ---------------------------------------------------------------- */
function toast(msg, type = 'blue') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `show ${type === 'red' ? 'red' : type === 'gold' ? 'gold' : type === 'green' ? 'green' : type === 'yellow' ? 'yellow' : ''}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = ''; }, 3200);
}

/* ----------------------------------------------------------------
   Init
   ---------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('step-btn').addEventListener('click', stepAgent);
  document.getElementById('auto-btn').addEventListener('click', toggleAuto);

  toast('Welcome! Configure grid and click New Game 🎮', 'blue');
});

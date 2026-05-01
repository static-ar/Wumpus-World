# Wumpus-World

A Knowledge-Based Wumpus World agent with propositional logic, resolution refutation, animated backtracking, and automatic exploration restart.

## What's new in v2

| Feature | v1 | v2 |
|---|---|---|
| Gold collection | Ends game | Agent backtracks home with gold |
| Backtrack animation | ❌ | ✅ Step-by-step, animated |
| Stuck recovery | Shows "Stuck" | Backtracks to (0,0), restarts |
| Auto-restart | ❌ | ✅ Continues on new path |
| Gold runs counter | ❌ | ✅ In metrics dashboard |

## File Structure

```
wumpus_agent/
├── requirements.txt
├── README.md
├── backend/
│   ├── app.py           ← Flask API (state machine for all phases)
│   ├── agent.py         ← KB agent + backtrack/restart logic
│   ├── environment.py   ← Grid world (gold-carry + home events)
│   └── kb.py            ← Propositional KB + resolution (unchanged)
└── frontend/
    ├── index.html       ← UI with gold-runs metric
    ├── app.js           ← Event handling for all new states
    └── style.css        ← Backtracking cell style (purple pulse)
```

## Setup

```bash
pip install flask flask-cors
cd backend
python app.py
```

Then open `frontend/index.html` in your browser.

## Agent State Machine

```
exploring  ──gold found──▶  backtracking_home  ──arrived (0,0)──▶  exploring (new run)
exploring  ──no safe cell──▶ backtracking_stuck ──arrived (0,0)──▶  exploring (new run)
exploring  ──pit/wumpus──▶  dead  (game ends)
```

## How Backtracking Works

1. Agent steps onto gold cell → `gold` event fires
2. `agent.build_backtrack_home(pos)` builds BFS path from current pos → (0,0) through already-safe cells
3. Each `/api/step` call pops one cell from the queue and moves the agent
4. Frontend shows purple pulsing agent icon during backtrack
5. On arrival at (0,0): `agent.begin_new_run()` resets frontier but keeps KB → exploration continues

## How Stuck Recovery Works

1. `choose_next_cell()` returns `None`
2. `agent.build_stuck_return(pos)` builds BFS path → (0,0)
3. Same step-by-step animation plays
4. On arrival: agent restarts with existing KB knowledge (avoids previously explored paths)

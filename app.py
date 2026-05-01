"""
Flask REST API for the Wumpus World Logic Agent  –  v2

Endpoints:
  POST /api/new_game        – Start a new episode
  POST /api/step            – One agent step (explore / backtrack / restart)
  GET  /api/state           – Current game + agent state
  GET  /api/reveal          – Reveal full ground-truth grid

Step state-machine (handled here, not in agent/environment):
  status == 'exploring'
      → choose_next_cell()
      → if gold event  : agent.build_backtrack_home() → status = 'backtracking_home'
      → if stuck       : agent.build_stuck_return()   → status = 'backtracking_stuck'
      → if dead        : status = 'dead'

  status == 'backtracking_home'
      → agent.next_backtrack_step()
      → move agent (skip hazard checks – path is safe)
      → if arrived (0,0): env.enter_cell triggers 'home' event
                          → agent.begin_new_run() → status = 'exploring'  (NO game_over)

  status == 'backtracking_stuck'
      → agent.next_backtrack_step()
      → move agent one step toward (0,0)
      → if queue empty  : agent.begin_new_run() → status = 'exploring'
"""

from flask import Flask, jsonify, request
from flask_cors import CORS

from environment import WumpusEnvironment
from agent import WumpusAgent

app = Flask(__name__)
CORS(app)

env:   WumpusEnvironment = None
agent: WumpusAgent       = None


# ------------------------------------------------------------------ #
#  /api/new_game                                                       #
# ------------------------------------------------------------------ #

@app.route('/api/new_game', methods=['POST'])
def new_game():
    global env, agent

    data     = request.get_json(silent=True) or {}
    rows     = max(4, min(10, int(data.get('rows',     4))))
    cols     = max(4, min(10, int(data.get('cols',     4))))
    num_pits = data.get('num_pits', None)
    if num_pits is not None:
        num_pits = max(1, int(num_pits))

    env   = WumpusEnvironment(rows, cols, num_pits)
    agent = WumpusAgent(rows, cols)

    percepts = env.get_percepts()
    log      = agent.perceive_and_infer((0, 0), percepts)

    return jsonify({
        'success': True,
        'env':     env.to_dict(),
        'agent':   agent.get_state(),
        'log':     log,
    })


# ------------------------------------------------------------------ #
#  /api/step                                                           #
# ------------------------------------------------------------------ #

@app.route('/api/step', methods=['POST'])
def step():
    global env, agent

    if env is None or agent is None:
        return jsonify({'error': 'No game in progress. Call /api/new_game first.'}), 400

    # Hard game-over (pit / wumpus death)
    if env.game_over or not env.agent_alive:
        return jsonify({
            'success': False,
            'message': env.game_message,
            'env':     env.to_dict(),
            'agent':   agent.get_state(),
        })

    # Run is complete (won or stuck)
    if agent.status in ('won', 'stuck'):
        return jsonify({
            'success': False,
            'message': 'Run is complete. Start a new game to continue.',
            'env':     env.to_dict(),
            'agent':   agent.get_state(),
        })

    # ---- Route by current status ----

    status = agent.status

    # ============================================================
    # BACKTRACKING HOME (carrying gold)
    # ============================================================
    if status == 'backtracking_home':
        return _do_backtrack_step(carrying_gold=True)

    # ============================================================
    # BACKTRACKING AFTER STUCK
    # ============================================================
    if status == 'backtracking_stuck':
        return _do_backtrack_step(carrying_gold=False)

    # ============================================================
    # NORMAL EXPLORATION
    # ============================================================
    # Don't explore if agent is carrying gold - force immediate backtrack home
    if env.agent_has_gold:
        agent.build_backtrack_home(pos)
        return jsonify({
            'success': True,
            'event':   'gold_already_held',
            'message': 'Agent already has gold - backtracking home.',
            'env':     env.to_dict(),
            'agent':   agent.get_state(),
        })
    
    pos       = tuple(env.agent_pos)
    next_cell = agent.choose_next_cell(pos)

    if next_cell is None:
        # Stuck – build return path and start backtracking
        agent.build_stuck_return(pos)
        if not agent._backtrack_queue:
            # Already at (0,0) – run ends
            agent.status = 'stuck'
            percepts = env.get_percepts()
            agent.perceive_and_infer((0, 0), percepts)
            return jsonify({
                'success': False,
                'event':   'stuck_end',
                'message': 'Agent stuck at start. Run ended.',
                'env':     env.to_dict(),
                'agent':   agent.get_state(),
            })
        return jsonify({
            'success': True,
            'event':   'stuck_backtrack_started',
            'message': 'Agent stuck — backtracking to (0,0) before new run.',
            'env':     env.to_dict(),
            'agent':   agent.get_state(),
        })

    # Move agent
    event = env.enter_cell(*next_cell)

    if event in ('pit', 'wumpus'):
        agent.status = 'dead'
        return jsonify({
            'success': False,
            'event':   event,
            'message': env.game_message,
            'env':     env.to_dict(),
            'agent':   agent.get_state(),
        })

    if event == 'gold':
        # Start animated backtrack home
        percepts = env.get_percepts()
        agent.perceive_and_infer(tuple(env.agent_pos), percepts)
        agent.build_backtrack_home(tuple(env.agent_pos))
        return jsonify({
            'success':  True,
            'event':    'gold',
            'moved_to': list(next_cell),
            'message':  env.game_message,
            'env':      env.to_dict(),
            'agent':    agent.get_state(),
        })

    # Normal move
    percepts = env.get_percepts()
    log      = agent.perceive_and_infer(tuple(env.agent_pos), percepts)

    return jsonify({
        'success':  True,
        'event':    event,
        'moved_to': list(next_cell),
        'message':  env.game_message,
        'env':      env.to_dict(),
        'agent':    agent.get_state(),
        'log':      log,
    })


# ------------------------------------------------------------------ #
#  Shared backtrack helper                                             #
# ------------------------------------------------------------------ #

def _do_backtrack_step(carrying_gold: bool):
    """Execute one step of the backtrack queue."""
    next_cell = agent.next_backtrack_step()

    if next_cell is None:
        # Queue exhausted – agent is at (or should be at) (0,0)
        if carrying_gold:
            # Gold delivered - END THE RUN
            event = env.enter_cell(0, 0)   # idempotent if already there
            agent.status = 'won'  # Mark as won, don't restart
            percepts = env.get_percepts()
            agent.perceive_and_infer((0, 0), percepts)
            return jsonify({
                'success': True,
                'event':   'home_arrived',
                'message': '🏆 Gold delivered! Run complete.',
                'env':     env.to_dict(),
                'agent':   agent.get_state(),
            })
        else:
            # Stuck recovery complete - END THE RUN
            agent.status = 'stuck'  # Mark as stuck, don't restart
            percepts = env.get_percepts()
            agent.perceive_and_infer((0, 0), percepts)
            return jsonify({
                'success': False,
                'event':   'stuck_end',
                'message': 'Agent got stuck and returned to (0,0). Run ended.',
                'env':     env.to_dict(),
                'agent':   agent.get_state(),
            })

    # Move one step
    event = env.enter_cell(*next_cell)

    if event == 'home':
        # Gold delivered - END THE RUN (don't auto-restart)
        agent.status = 'won'  # Mark as won
        percepts = env.get_percepts()
        agent.perceive_and_infer((0, 0), percepts)
        return jsonify({
            'success':  True,
            'event':    'home_arrived',
            'moved_to': list(next_cell),
            'message':  '🏆 Gold delivered! Run complete.',
            'env':      env.to_dict(),
            'agent':    agent.get_state(),
        })

    return jsonify({
        'success':  True,
        'event':    'backtrack_step',
        'moved_to': list(next_cell),
        'carrying_gold': carrying_gold,
        'message':  env.game_message or ('Backtracking…' if not carrying_gold else '✨ Heading home with gold…'),
        'env':      env.to_dict(),
        'agent':    agent.get_state(),
    })


# ------------------------------------------------------------------ #
#  /api/state  and  /api/reveal                                        #
# ------------------------------------------------------------------ #

@app.route('/api/state', methods=['GET'])
def get_state():
    if env is None or agent is None:
        return jsonify({'error': 'No game in progress'}), 400
    return jsonify({'env': env.to_dict(), 'agent': agent.get_state()})


@app.route('/api/reveal', methods=['GET'])
def reveal():
    if env is None:
        return jsonify({'error': 'No game in progress'}), 400
    return jsonify({'env': env.to_dict()})


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

if __name__ == '__main__':
    print("=" * 55)
    print("  Wumpus World Logic Agent v2 – Flask API")
    print("  Running on http://127.0.0.1:5000")
    print("  Open frontend/index.html in your browser")
    print("=" * 55)
    app.run(debug=True, port=5000)

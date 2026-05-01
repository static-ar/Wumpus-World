"""
Wumpus World Environment.
Manages the grid, hazard placement, percept generation, and agent movement.

Changes from v1:
  - gold_grabbed: True once agent picks up gold (gold is removed from grid)
  - agent_has_gold: True while agent is carrying gold back
  - enter_cell now returns 'gold_grabbed' when agent steps onto gold cell
"""

import random


class WumpusEnvironment:

    def __init__(self, rows: int, cols: int, num_pits: int = None):
        self.rows = rows
        self.cols = cols
        self.num_pits = num_pits if num_pits is not None else max(1, (rows * cols) // 5)
        self._setup()

    # ------------------------------------------------------------------ #
    #  Setup                                                               #
    # ------------------------------------------------------------------ #

    def _setup(self):
        self.agent_pos      = (0, 0)
        self.agent_alive    = True
        self.agent_has_gold = False   # True while carrying gold home
        self.gold_collected = False   # True once gold is delivered to (0,0)
        self.wumpus_alive   = True
        self.wumpus_pos     = None
        self.gold_pos       = None
        self.game_over      = False
        self.game_message   = ''
        self.move_count     = 0

        # grid[(r,c)] = {'pit': bool, 'wumpus': bool, 'gold': bool}
        self.grid = {(r, c): {'pit': False, 'wumpus': False, 'gold': False}
                     for r in range(self.rows) for c in range(self.cols)}

        self._place_hazards()

    def _place_hazards(self):
        all_cells = [(r, c) for r in range(self.rows) for c in range(self.cols)]
        safe_zone = {(0, 0), (0, 1), (1, 0)}
        non_start = [c for c in all_cells if c not in safe_zone]
        random.shuffle(non_start)

        # Place pits
        placed = 0
        idx = 0
        while placed < self.num_pits and idx < len(non_start):
            self.grid[non_start[idx]]['pit'] = True
            placed += 1
            idx += 1

        # Place Wumpus in a non-pit cell
        candidates = [c for c in non_start if not self.grid[c]['pit']]
        if candidates:
            self.wumpus_pos = random.choice(candidates)
            self.grid[self.wumpus_pos]['wumpus'] = True

        # Place gold in a non-pit, non-wumpus cell
        gold_candidates = [c for c in non_start
                           if not self.grid[c]['pit'] and c != self.wumpus_pos]
        if not gold_candidates:
            gold_candidates = non_start   # fallback
        if gold_candidates:
            self.gold_pos = random.choice(gold_candidates)
            self.grid[self.gold_pos]['gold'] = True

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def get_adjacent(self, r, c):
        """Return valid (row, col) neighbours (up/down/left/right)."""
        return [
            (r + dr, c + dc)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]
            if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols
        ]

    # ------------------------------------------------------------------ #
    #  Percepts                                                            #
    # ------------------------------------------------------------------ #

    def get_percepts(self, pos=None):
        r, c = pos if pos else self.agent_pos
        p = {'breeze': False, 'stench': False, 'glitter': False}
        for ar, ac in self.get_adjacent(r, c):
            if self.grid[(ar, ac)]['pit']:
                p['breeze'] = True
            if self.grid[(ar, ac)]['wumpus'] and self.wumpus_alive:
                p['stench'] = True
        if self.grid[(r, c)]['gold']:
            p['glitter'] = True
        return p

    # ------------------------------------------------------------------ #
    #  Movement                                                            #
    # ------------------------------------------------------------------ #

    def enter_cell(self, nr: int, nc: int) -> str:
        """
        Move agent to (nr, nc).
        Returns event: 'pit' | 'wumpus' | 'gold' | 'home' | 'ok'

        'gold'  – agent just grabbed the gold (now must backtrack home)
        'home'  – agent arrived at (0,0) while carrying gold → Victory
        'ok'    – normal move
        """
        self.agent_pos = (nr, nc)
        self.move_count += 1
        cell = self.grid[(nr, nc)]

        # Hazards only trigger if agent does NOT already have gold
        # (gold-carrying phase: agent retraces known-safe path, so
        #  theoretically impossible to enter a pit/wumpus cell,
        #  but we check anyway for safety)
        if not self.agent_has_gold:
            if cell['pit']:
                self.agent_alive = False
                self.game_over   = True
                self.game_message = f'Agent fell into a pit at ({nr},{nc})! Game Over.'
                return 'pit'

            if cell['wumpus'] and self.wumpus_alive:
                self.agent_alive = False
                self.game_over   = True
                self.game_message = f'Agent eaten by Wumpus at ({nr},{nc})! Game Over.'
                return 'wumpus'

            if cell['gold']:
                # Grab the gold
                self.agent_has_gold = True
                self.grid[(nr, nc)]['gold'] = False
                self.gold_pos = None
                self.game_message = '✨ Gold grabbed! Backtracking to start…'
                return 'gold'

        else:
            # Agent is carrying gold – check if reached home
            if (nr, nc) == (0, 0):
                self.agent_has_gold = False
                self.gold_collected = True
                self.game_message = '🏆 Gold delivered! Victory!'
                # NOTE: game_over is NOT set here – the agent will restart
                return 'home'

        return 'ok'

    # ------------------------------------------------------------------ #
    #  Serialisation                                                       #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {
            'rows':           self.rows,
            'cols':           self.cols,
            'agent_pos':      list(self.agent_pos),
            'agent_alive':    self.agent_alive,
            'agent_has_gold': self.agent_has_gold,
            'gold_collected': self.gold_collected,
            'wumpus_alive':   self.wumpus_alive,
            'wumpus_pos':     list(self.wumpus_pos) if self.wumpus_pos else None,
            'gold_pos':       list(self.gold_pos)   if self.gold_pos   else None,
            'game_over':      self.game_over,
            'game_message':   self.game_message,
            'move_count':     self.move_count,
            # grid serialised as "r_c" → cell dict
            'grid': {
                f'{r}_{c}': v
                for (r, c), v in self.grid.items()
            },
            'percepts': self.get_percepts() if self.agent_alive else {},
        }

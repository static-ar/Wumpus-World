"""
Knowledge-Based Wumpus Agent  –  v2

Status flow:
  exploring        → normal KB-driven exploration
  backtracking_home → agent grabbed gold, retracing path to (0,0) step-by-step
  restarting       → agent delivered gold (or was stuck) and is now heading back
                     to (0,0) to begin a new search on a fresh path
  exploring        → (again) after successful restart
  won              → gold delivered home  (game ends with Victory stats)
  dead             → fell into pit or eaten
  stuck            → (internal only, immediately triggers backtrack-to-start)

New public helpers used by app.py:
  next_backtrack_step()   – pops one cell from the backtrack queue
  begin_restart()         – resets KB-related exploration state for new run
  next_restart_step()     – one step toward (0,0) after a stuck situation

PHASE 2 NOTE:
  The backtrack path is built in perceive_and_infer() when 'gold' event fires,
  and in _handle_stuck() when no safe cell can be found.
  Both cases use _bfs_path() through already-visited/safe cells.
"""

from collections import deque
from kb import KnowledgeBase


class WumpusAgent:

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

        self.kb = KnowledgeBase()

        self.visited:          set  = set()
        self.safe_cells:       set  = {(0, 0)}
        self.frontier:         list = []
        self.confirmed_pits:   set  = set()
        self.confirmed_wumpus: set  = set()

        # ---- v2 additions ----
        # Ordered path of cells the agent will walk step-by-step.
        # Used for both backtrack-home and stuck-recovery.
        self._backtrack_queue: list = []

        # How many times the agent has completed a gold run
        self.gold_runs: int = 0

        # Visited cells from PREVIOUS runs – used to avoid repeating
        # the exact same path on restart
        self._previous_paths: list = []   # list of frozensets (one per run)

        self.status    = 'exploring'
        self.step_log  = []

        # (0,0) is always safe
        self.kb.tell(['-P_0_0'])
        self.kb.tell(['-W_0_0'])

    # ------------------------------------------------------------------ #
    #  Grid helper                                                         #
    # ------------------------------------------------------------------ #

    def _adj(self, r, c):
        return [
            (r + dr, c + dc)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]\
            if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols
        ]

    # ------------------------------------------------------------------ #
    #  PERCEIVE → TELL → ASK                                              #
    # ------------------------------------------------------------------ #

    def perceive_and_infer(self, pos: tuple, percepts: dict) -> dict:
        r, c = pos
        self.visited.add((r, c))
        if (r, c) in self.frontier:
            self.frontier.remove((r, c))

        adj     = self._adj(r, c)
        breeze  = percepts.get('breeze', False)
        stench  = percepts.get('stench', False)

        new_safe    = []
        new_dangers = []

        # ---- TELL ----
        if not breeze:
            for ar, ac in adj:
                self.kb.tell([f'-P_{ar}_{ac}'])
        else:
            self.kb.tell([f'P_{ar}_{ac}' for ar, ac in adj])

        if not stench:
            for ar, ac in adj:
                self.kb.tell([f'-W_{ar}_{ac}'])
        else:
            self.kb.tell([f'W_{ar}_{ac}' for ar, ac in adj])

        # ---- ASK ----
        for ar, ac in adj:
            if (ar, ac) in self.visited:
                continue
            if (ar, ac) in self.confirmed_pits or (ar, ac) in self.confirmed_wumpus:
                continue

            if self.kb.ask_safe(ar, ac):
                if (ar, ac) not in self.safe_cells:
                    self.safe_cells.add((ar, ac))
                    self.frontier.append((ar, ac))
                    new_safe.append([ar, ac])
            elif (ar, ac) not in self.safe_cells:
                if self.kb.ask_pit(ar, ac):
                    self.confirmed_pits.add((ar, ac))
                    new_dangers.append({'cell': [ar, ac], 'type': 'pit'})
                elif self.kb.ask_wumpus(ar, ac):
                    self.confirmed_wumpus.add((ar, ac))
                    new_dangers.append({'cell': [ar, ac], 'type': 'wumpus'})

        entry = {
            'pos':         [r, c],
            'percepts':    percepts,
            'new_safe':    new_safe,
            'new_dangers': new_dangers,
            'kb_stats':    self.kb.summary(),
        }
        self.step_log.append(entry)
        if len(self.step_log) > 20:
            self.step_log.pop(0)

        return entry

    # ------------------------------------------------------------------ #
    #  Navigation – normal exploration                                     #
    # ------------------------------------------------------------------ #

    def choose_next_cell(self, pos: tuple):
        """
        Return next cell to move to, or None if no safe reachable cell.
        When None is returned the caller should trigger backtrack-to-start.
        """
        r, c = pos

        # 1) Direct adjacent safe unvisited
        for cell in self._adj(r, c):
            if cell in self.safe_cells and cell not in self.visited:
                return cell

        # 2) BFS toward nearest safe unvisited via known-safe path
        target = self._nearest_frontier(pos)
        if target is None:
            return None

        path = self._bfs_path(pos, target, self.safe_cells | self.visited)
        if path and len(path) > 1:
            return path[1]

        return None

    # ------------------------------------------------------------------ #
    #  Backtrack – step-by-step home after gold grab                      #
    # ------------------------------------------------------------------ #

    def build_backtrack_home(self, pos: tuple):
        """
        Build the step-by-step path from current pos back to (0,0).
        Called by app.py immediately after 'gold' event.
        Sets status → 'backtracking_home'.
        """
        path = self._bfs_path(pos, (0, 0), self.safe_cells | self.visited)
        if path and len(path) > 1:
            # path[0] is current pos, skip it
            self._backtrack_queue = path[1:]
        else:
            # Already at (0,0) somehow
            self._backtrack_queue = []
        self.status = 'backtracking_home'

    def next_backtrack_step(self):
        """
        Pop and return the next cell in the backtrack queue.
        Returns None when queue is empty (agent has reached (0,0)).
        """
        if self._backtrack_queue:
            return self._backtrack_queue.pop(0)
        return None

    # ------------------------------------------------------------------ #
    #  Stuck recovery – backtrack to (0,0) then restart on new path       #
    # ------------------------------------------------------------------ #

    def build_stuck_return(self, pos: tuple):
        """
        When agent is stuck, build path back to (0,0).
        Sets status → 'backtracking_stuck'.
        """
        path = self._bfs_path(pos, (0, 0), self.safe_cells | self.visited)
        if path and len(path) > 1:
            self._backtrack_queue = path[1:]
        else:
            self._backtrack_queue = []
        self.status = 'backtracking_stuck'

    # ------------------------------------------------------------------ #
    #  Restart after delivery or stuck-recovery                           #
    # ------------------------------------------------------------------ #

    def begin_new_run(self):
        """
        Called when agent arrives back at (0,0) after delivering gold
        or after a stuck-recovery.
        Resets exploration state but keeps KB knowledge.
        Sets status → 'exploring'.

        The agent will now explore again but the frontier prefers
        unvisited safe cells not covered in previous runs.
        """
        # Save this run's visited set so we can deprioritise those paths
        self._previous_paths.append(frozenset(self.visited))

        # Keep visited / safe / confirmed – the KB already encodes them.
        # Only reset frontier to unvisited safe cells.
        self.frontier = [
            c for c in self.safe_cells
            if c not in self.visited
        ]
        self._backtrack_queue = []
        self.gold_runs += 1
        self.status = 'exploring'

    # ------------------------------------------------------------------ #
    #  BFS helpers                                                         #
    # ------------------------------------------------------------------ #

    def _nearest_frontier(self, start: tuple):
        passable = self.safe_cells | self.visited
        queue  = deque([start])
        seen   = {start}
        while queue:
            pos = queue.popleft()
            if pos in self.safe_cells and pos not in self.visited and pos != start:
                return pos
            for nb in self._adj(*pos):
                if nb not in seen and nb in passable:
                    seen.add(nb)
                    queue.append(nb)
        return None

    def _bfs_path(self, start: tuple, goal: tuple, passable: set):
        """Shortest path from start to goal through passable cells."""
        if start == goal:
            return [start]
        queue = deque([[start]])
        seen  = {start}
        while queue:
            path = queue.popleft()
            for nb in self._adj(*path[-1]):
                if nb not in seen and nb in passable:
                    new_path = path + [nb]
                    if nb == goal:
                        return new_path
                    seen.add(nb)
                    queue.append(new_path)
        return None

    # ------------------------------------------------------------------ #
    #  Serialisation                                                       #
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict:
        return {
            'visited':              [list(c) for c in self.visited],
            'safe_cells':           [list(c) for c in self.safe_cells],
            'frontier':             [list(c) for c in self.frontier],
            'confirmed_pits':       [list(c) for c in self.confirmed_pits],
            'confirmed_wumpus':     [list(c) for c in self.confirmed_wumpus],
            'kb_clauses':           self.kb.clause_count(),
            'inference_steps':      self.kb.inference_steps,
            'status':               self.status,
            'step_log':             self.step_log[-5:],
            'gold_runs':            self.gold_runs,
            'backtrack_queue_len':  len(self._backtrack_queue),
        }

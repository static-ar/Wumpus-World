"""
Propositional Logic Knowledge Base with Resolution Refutation.

Literals are strings:
  Positive:  'P_2_2'   → there is a pit at row 2, col 2
  Negative:  '-P_2_2'  → there is NO pit at row 2, col 2
  'W_r_c'  = Wumpus at (r,c)

Clauses are frozensets of literal strings (CNF representation).

Resolution Refutation:
  To prove α, add ¬α to KB as a unit clause and derive the empty clause.
"""


class KnowledgeBase:
    def __init__(self):
        self.clauses: set = set()        # frozensets of literal strings
        self.inference_steps: int = 0
        self._proved_cache: dict = {}    # cache: literal → bool

    def reset(self):
        self.clauses = set()
        self.inference_steps = 0
        self._proved_cache = {}

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _neg(lit: str) -> str:
        """Return the negation of a literal string."""
        return lit[1:] if lit.startswith('-') else '-' + lit

    # ------------------------------------------------------------------ #
    #  TELL – add knowledge                                                #
    # ------------------------------------------------------------------ #

    def tell(self, clause):
        """
        Add a clause to the KB.
        clause: list / tuple / set of literal strings representing a disjunction.
        E.g. tell(['-P_2_2']) means  ¬P_{2,2}  (unit clause)
             tell(['P_1_2','P_2_1']) means  P_{1,2} ∨ P_{2,1}
        """
        c = frozenset(clause)
        if c not in self.clauses:
            self.clauses.add(c)
            self._proved_cache.clear()   # invalidate cache on new knowledge

    # ------------------------------------------------------------------ #
    #  Resolution core                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve(ci: frozenset, cj: frozenset) -> set:
        """
        Compute all binary resolvents of clauses ci and cj.
        For each literal L in ci, if ¬L ∈ cj produce the resolvent
        (ci − {L}) ∪ (cj − {¬L}).
        """
        resolvents = set()
        for lit in ci:
            neg = KnowledgeBase._neg(lit)
            if neg in cj:
                new_c = (ci - frozenset([lit])) | (cj - frozenset([neg]))
                resolvents.add(frozenset(new_c))
        return resolvents

    def pl_resolution(self, query_literal: str) -> bool:
        """
        Prove query_literal using Resolution Refutation (AIMA PL-RESOLUTION).

        Algorithm:
          1. Negate query_literal → neg_q
          2. Add {neg_q} as a unit clause to a working copy of KB
          3. Repeatedly resolve pairs of clauses
          4. If empty clause {} derived → contradiction → query proved (True)
          5. If no new clauses can be derived → query not provable (False)

        Returns: True  if query_literal follows from KB
                 False if it cannot be proved
        """
        if query_literal in self._proved_cache:
            return self._proved_cache[query_literal]

        neg_q = self._neg(query_literal)
        clauses = set(self.clauses) | {frozenset([neg_q])}
        seen   = set(clauses)

        MAX_CLAUSES = 4000   # safety cap to avoid infinite loops on big grids

        while True:
            new = set()
            clause_list = list(clauses)
            n = len(clause_list)

            for i in range(n):
                for j in range(i + 1, n):
                    self.inference_steps += 1
                    resolvents = self._resolve(clause_list[i], clause_list[j])

                    if frozenset() in resolvents:
                        self._proved_cache[query_literal] = True
                        return True

                    for r in resolvents:
                        if r not in seen:
                            new.add(r)
                            seen.add(r)

            if not new:
                self._proved_cache[query_literal] = False
                return False

            clauses.update(new)

            if len(clauses) > MAX_CLAUSES:
                self._proved_cache[query_literal] = False
                return False

    # ------------------------------------------------------------------ #
    #  ASK – query knowledge                                               #
    # ------------------------------------------------------------------ #

    def ask_no_pit(self, r: int, c: int) -> bool:
        """Prove ¬P_{r,c} – there is definitely no pit at (r,c)."""
        return self.pl_resolution(f'-P_{r}_{c}')

    def ask_no_wumpus(self, r: int, c: int) -> bool:
        """Prove ¬W_{r,c} – there is definitely no wumpus at (r,c)."""
        return self.pl_resolution(f'-W_{r}_{c}')

    def ask_safe(self, r: int, c: int) -> bool:
        """Prove cell (r,c) is safe: ¬P_{r,c} ∧ ¬W_{r,c}."""
        return self.ask_no_pit(r, c) and self.ask_no_wumpus(r, c)

    def ask_pit(self, r: int, c: int) -> bool:
        """Prove P_{r,c} – cell definitely has a pit."""
        return self.pl_resolution(f'P_{r}_{c}')

    def ask_wumpus(self, r: int, c: int) -> bool:
        """Prove W_{r,c} – cell definitely has the Wumpus."""
        return self.pl_resolution(f'W_{r}_{c}')

    # ------------------------------------------------------------------ #
    #  Diagnostics                                                         #
    # ------------------------------------------------------------------ #

    def clause_count(self) -> int:
        return len(self.clauses)

    def summary(self) -> dict:
        return {
            'clause_count':    self.clause_count(),
            'inference_steps': self.inference_steps,
        }

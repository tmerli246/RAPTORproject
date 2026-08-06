"""Records exchanged between the evaluator and the allocator.

The evaluator emits Strategy records, the allocator consumes them, and the
synthetic generator imitates them. Nothing here computes anything beyond
trivial derived quantities.
"""

from dataclasses import dataclass, field


@dataclass
class Strategy:
    """One candidate treatment strategy for one patient.

    pid       patient identifier
    sid       strategy identifier, unique within the patient
    modality  'pt' or 'xt'
    n_fx      number of fractions
    tau       proton machine occupancy per fraction, minutes. Zero for 'xt'
    ntcp      absolute NTCP per endpoint, {endpoint: probability}
    scheme    fractionation scheme label. 'std' is the standard schedule
    n_adapt   number of adapted blocks, carried for reporting
    baseline  True for the locked reference strategy (XT-NA, standard schedule)
    """

    pid: str
    sid: str
    modality: str
    n_fx: int
    tau: float
    ntcp: dict = field(default_factory=dict)
    scheme: str = 'std'
    n_adapt: int = 0
    baseline: bool = False

    def __post_init__(self):
        if self.modality not in ('pt', 'xt'):
            raise ValueError(f"{self.pid}/{self.sid}: modality must be 'pt' or 'xt'")
        if self.modality == 'xt' and self.tau != 0.0:
            raise ValueError(f"{self.pid}/{self.sid}: photon strategies do not consume proton capacity")
        if self.n_fx <= 0:
            raise ValueError(f"{self.pid}/{self.sid}: n_fx must be positive")
        if not self.ntcp:
            raise ValueError(f"{self.pid}/{self.sid}: no endpoints")

    @property
    def ntcp_tot(self):
        """Union probability over the active endpoints."""
        q = 1.0
        for v in self.ntcp.values():
            q *= (1.0 - v)
        return 1.0 - q

    @property
    def occupancy(self):
        """Total proton machine minutes over the course."""
        return self.n_fx * self.tau


@dataclass
class Facility:
    """Machine capacity over the horizon.

    cap_min_day  available proton machine minutes per treatment day
    days         treatment days in the horizon
    """

    cap_min_day: float
    days: int = 1

    @property
    def budget(self):
        return self.cap_min_day * self.days


@dataclass
class Cohort:
    """A set of strategies spanning several patients."""

    strategies: list

    def __post_init__(self):
        self._base = {}
        for pid, opts in self.by_patient().items():
            base = [s for s in opts if s.baseline]
            if len(base) != 1:
                raise ValueError(f"{pid}: expected exactly one baseline strategy, found {len(base)}")
            self._base[pid] = base[0]

    @property
    def pids(self):
        seen = []
        for s in self.strategies:
            if s.pid not in seen:
                seen.append(s.pid)
        return seen

    def by_patient(self):
        """Option sets keyed by patient, preserving insertion order."""
        out = {}
        for s in self.strategies:
            out.setdefault(s.pid, []).append(s)
        return out

    def baseline(self):
        """The locked reference strategy per patient."""
        return self._base

    def dntcp(self, s):
        """Utility of a strategy: reduction in union NTCP against the baseline."""
        return self._base[s.pid].ntcp_tot - s.ntcp_tot

    def restrict(self, keep):
        """Sub-cohort holding only the strategies satisfying `keep`.

        The baseline is always retained, so every patient keeps at least one
        option and the multiple-choice constraint stays satisfiable. Policies
        use this to express the workflows they are allowed to consider.
        """
        opts = [s for s in self.strategies if s.baseline or keep(s)]
        return Cohort(opts)


@dataclass
class Allocation:
    """Result of solving the allocation problem."""

    choice: dict           # pid -> Strategy
    used: float            # proton machine minutes consumed
    mean_dntcp: float      # cohort mean, denominator is the full cohort
    lam: float = None      # shadow price, utility per machine-minute

    @property
    def n_pt(self):
        return sum(1 for s in self.choice.values() if s.modality == 'pt')


@dataclass
class LPSolution:
    """Result of the linear relaxation.

    value    cohort total delta NTCP at the LP optimum
    lam      shadow price of capacity, delta NTCP per machine-minute
    used     proton machine minutes consumed
    choice   integral part of the solution, pid -> Strategy
    frac     (pid, sid, weight) of the single fractionally taken upgrade, or None
    kept     surviving options per patient after dominance removal, pid -> [sid]
    """

    value: float
    lam: float
    used: float
    choice: dict
    frac: tuple = None
    kept: dict = field(default_factory=dict)

    def n_dominated(self, cohort):
        """Options removed as LP-dominated, per patient."""
        return {pid: len(opts) - len(self.kept[pid])
                for pid, opts in cohort.by_patient().items()}

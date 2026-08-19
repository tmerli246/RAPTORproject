"""Records exchanged between the evaluator and the allocator.

The evaluator emits Strategy records, the allocator consumes them, and the
synthetic generator imitates them. Nothing here computes anything beyond
trivial derived quantities.

Two resources are carried, following version 5 of the allocator design:
proton machine time and photon adaptation time. No strategy consumes both,
which is what makes a patient's option set two chains meeting at XT-NA.
"""

from dataclasses import dataclass, field

@dataclass
class Strategy:
    """One candidate treatment strategy for one patient.

    pid       patient identifier
    sid       strategy identifier, unique within the patient
    modality  'pt' or 'xt'
    n_fx      number of fractions
    tau_pt    proton machine occupancy per fraction, minutes. Zero for 'xt'
    tau_xt    photon adaptation time per fraction, minutes. Zero for 'pt'
              and for XT-NA. The adaptation increment only: photon delivery
              is unconstrained, so no baseline photon session is charged
    ntcp      absolute NTCP per endpoint, {endpoint: probability}
    scheme    fractionation scheme label. 'std' is the standard schedule
    n_adapt   number of adapted blocks, carried for reporting
    baseline  True for the locked reference strategy (XT-NA, standard schedule)
    """

    pid: str
    sid: str
    modality: str
    n_fx: int
    tau_pt: float
    tau_xt: float = 0.0
    ntcp: dict = field(default_factory = dict)
    scheme: str = 'std'
    n_adapt: int = 0
    baseline: bool = False

    def __post_init__(self):
        if self.modality not in ('pt', 'xt'):
            raise ValueError(f"{self.pid}/{self.sid}: modality must be 'pt' or 'xt'")
        if self.modality == 'xt' and self.tau_pt != 0.0:
            raise ValueError(f"{self.pid}/{self.sid}: photon strategies do not consume proton capacity")
        if self.modality == 'pt' and self.tau_xt != 0.0:
            raise ValueError(f"{self.pid}/{self.sid}: proton strategies do not consume the photon adaptation budget")
        if self.baseline and self.tau_xt != 0.0:
            raise ValueError(f"{self.pid}/{self.sid}: the locked baseline consumes neither budget")
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
    def occ_pt(self):
        """Total proton machine minutes over the course."""
        return self.n_fx * self.tau_pt

    @property
    def occ_xt(self):
        """Total photon adaptation minutes over the course."""
        return self.n_fx * self.tau_xt

@dataclass
class Facility:
    """Machine capacity over the horizon.

    cap_pt_min_day  available proton machine minutes per treatment day
    cap_xt_min_day  available photon adaptation minutes per treatment day.
                    A study parameter swept rather than measured; zero
                    recovers the single-resource problem of version 4
    days            treatment days in the horizon
    """

    cap_pt_min_day: float
    cap_xt_min_day: float = 0.0
    days: int = 1

    @property
    def budget_pt(self):
        return self.cap_pt_min_day * self.days

    @property
    def budget_xt(self):
        return self.cap_xt_min_day * self.days

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
        """The locked reference strategy per patient.

        The baseline retains this role regardless of its own admissibility as
        an assignable option: every delta NTCP in the study is referenced to
        the same arm on every patient (evaluator design, Section 6.3).
        """
        return self._base

    def dntcp(self, s):
        """Utility of a strategy: reduction in union NTCP against the baseline."""
        return self._base[s.pid].ntcp_tot - s.ntcp_tot

    def demand_xt(self):
        """Cohort photon adaptation demand: the budget beyond which the photon
        constraint cannot bind. Normalises the C_XT sweep axis (T9 is 1)."""
        out = 0.0
        for opts in self.by_patient().values():
            out += max(s.occ_xt for s in opts)
        return out

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
    used_pt: float         # proton machine minutes consumed
    used_xt: float         # photon adaptation minutes consumed
    mean_dntcp: float      # cohort mean, denominator is the full cohort

    @property
    def n_pt(self):
        return sum(1 for s in self.choice.values() if s.modality == 'pt')

    @property
    def n_xt_adapted(self):
        return sum(1 for s in self.choice.values()
                   if s.modality == 'xt' and s.n_adapt > 0)

@dataclass
class LPSolution:
    """Result of the linear relaxation.

    value    cohort total delta NTCP at the LP optimum
    lam_pt   shadow price of proton capacity, delta NTCP per machine-minute
    lam_xt   shadow price of photon adaptation capacity, same units
    used_pt  proton machine minutes consumed
    used_xt  photon adaptation minutes consumed
    choice   integral part of the solution, pid -> Strategy (largest weight)
    frac     list of fractionally taken (pid, sid, weight); at most one per
             binding constraint, so at most two entries generically
    kept     surviving options per patient after dominance removal, pid ->
             [sid]. Filled by the greedy solver; empty for the LP solver,
             whose dominance structure is reported by report.dominance_counts
    """

    value: float
    lam_pt: float
    lam_xt: float
    used_pt: float
    used_xt: float
    choice: dict
    frac: list = field(default_factory = list)
    kept: dict = field(default_factory = dict)

    def n_dominated(self, cohort):
        """Options removed as LP-dominated, per patient."""
        return {pid: len(opts) - len(self.kept[pid])
                for pid, opts in cohort.by_patient().items()}

"""Records exchanged between the evaluator and the allocator.

The evaluator emits Strategy records, the allocator consumes them, and the
synthetic generator imitates them. Nothing here computes anything beyond
trivial derived quantities.

Two resources are carried, following version 6 of the allocator design:
proton machine time and photon adaptation time. No strategy consumes both,
which is what makes a patient's option set two chains meeting at XT-NA.

Modality, adaptation and fractionation are chosen once, at prescription. All
three are scalar fields of this record, so a course that changes any of them
part-way is not representable rather than merely disallowed. A patient holds
four strategies per fractionation scheme and eight over two schemes,
independently of the number of blocks (allocator design, Section 5.1).

XT-NA is free on both budgets under either fractionation scheme, so a patient
may hold two zero-cost options rather than one (A27). It carries two roles that
are logically distinct and are kept apart here:

    reference arm   the numeraire of delta NTCP. Fixed across every patient
                    and every policy, so that the zero point never moves
    default arm     what a patient receives when no capacity is spent on
                    them. Must be assignable, and free on both budgets if
                    the allocation is to be guaranteed no worse than the
                    reference

`baseline` marks the first role, `admissible` the second. They normally
coincide. They separate when the coverage screen rejects a patient's
non-adapted photon plan, which the evaluator may do on either modality
(allocator design, Section 8.2): the arm remains the numeraire but stops
being assignable, and an optimal allocation may then have to assign a
strategy of negative delta NTCP.
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
    adapted   True if this is an adapted arm. An adapted arm adapts at every
              block and a non-adapted arm never adapts (A24), so no count of
              adapted blocks is carried and none is representable
    baseline  True for the locked reference strategy (XT-NA, standard
              schedule). Defines the zero of delta NTCP whether or not the
              strategy is assignable
    admissible True if the strategy passed the coverage screen and may
              therefore be assigned. Coverage is the only screen that sets
              this: no harm is reported rather than enforced, so strategies
              of negative utility stay in the option set and are declined by
              dominance (allocator design, Section 8.3). The reference arm
              can be inadmissible: it keeps its role as numeraire either way
    """

    pid: str
    sid: str
    modality: str
    n_fx: int
    tau_pt: float
    tau_xt: float = 0.0
    ntcp: dict = field(default_factory = dict)
    scheme: str = 'std'
    adapted: bool = False
    baseline: bool = False
    admissible: bool = True

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
        for pid, opts in self.all_by_patient().items():
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

    def all_by_patient(self):
        """Every strategy keyed by patient, admissible or not.

        For diagnostics and for locating the reference arm. Solvers and
        policies must use `by_patient`, which excludes what the evaluator
        screened out.
        """
        out = {}
        for s in self.strategies:
            out.setdefault(s.pid, []).append(s)
        return out

    def by_patient(self):
        """Assignable option sets keyed by patient, preserving insertion order.

        A patient whose every strategy was screened out keeps its key with an
        empty list, so that the condition surfaces where it matters rather
        than the patient disappearing from the problem.
        """
        out = {}
        for pid, opts in self.all_by_patient().items():
            out[pid] = [s for s in opts if s.admissible]
        return out

    def baseline(self):
        """The reference strategy per patient, the numeraire of delta NTCP.

        The reference arm retains this role regardless of its own
        admissibility as an assignable option: every delta NTCP in the study
        is referenced to the same arm on every patient (evaluator design,
        Section 6.3). Use `default` for the arm a patient actually receives
        when no capacity is spent on them.
        """
        return self._base

    def default(self):
        """The arm a patient receives when no capacity is spent on them.

        The cheapest assignable option on the two budgets, ties broken on
        utility. Normally this is the reference arm, which is free on both
        budgets and has delta NTCP identically zero. Where the reference arm
        is inadmissible the default is whatever remains cheapest, which may
        consume capacity and may carry a negative delta NTCP.

        Raises if a patient has no assignable option.
        """
        out = {}
        for pid, opts in self.by_patient().items():
            if not opts:
                raise ValueError(f"{pid}: no admissible strategy")
            out[pid] = min(opts, key = lambda s: (s.occ_pt, s.occ_xt, -self.dntcp(s)))
        return out

    def no_option(self):
        """Patients with no assignable option at all.

        The multiple-choice constraint cannot be satisfied for these patients
        at any capacity, so the problem is infeasible (allocator design,
        Section 8.4).
        """
        return [pid for pid, opts in self.by_patient().items() if not opts]

    def no_free_option(self):
        """Patients with no assignable option that is free on both budgets.

        This list being empty is what guarantees that no allocation makes a
        patient worse than the reference arm: a free option is then always
        available, and it dominates every option of negative utility, on both
        the linear and the integer problem. No sign constraint is imposed
        anywhere, and none is needed.

        Under two fractionation schemes a patient normally has two free
        options, XT-NA under each schedule, so the guarantee survives the loss
        of either one alone (A21 as amended, A27). The count of patients for
        whom it does not is what makes the no-harm property empirical rather
        than structural, and it is reported as n_no_free_option.

        Where the list is not empty, an optimal allocation may assign a
        strategy of negative delta NTCP to those patients. That is the
        correct answer to the question of what to do with a patient who must
        be treated and whose reference plan is not deliverable, not a defect
        of the solver.
        """
        out = []
        for pid, opts in self.by_patient().items():
            if not any(s.occ_pt == 0.0 and s.occ_xt == 0.0 for s in opts):
                out.append(pid)
        return out

    def dntcp(self, s):
        """Utility of a strategy: reduction in union NTCP against the baseline."""
        return self._base[s.pid].ntcp_tot - s.ntcp_tot

    def demand_xt(self):
        """Cohort photon adaptation demand: the budget beyond which the photon
        constraint cannot bind. Normalises the C_XT sweep axis (T9 is 1)."""
        out = 0.0
        for opts in self.by_patient().values():
            out += max((s.occ_xt for s in opts), default = 0.0)
        return out

    def restrict(self, keep):
        """Sub-cohort holding only the strategies satisfying `keep`.

        The reference arm is always retained, since it defines the zero of
        delta NTCP whether or not it is assignable. Where the filter would
        leave a patient with no assignable option, that patient's default arm
        is retained as well, so the multiple-choice constraint stays
        satisfiable and every policy remains defined on every patient.
        Policies use this to express the workflows they are allowed to
        consider.
        """
        opts = [s for s in self.strategies if s.baseline or keep(s)]
        sub = Cohort(opts)

        missing = sub.no_option()
        if not missing:
            return sub
        dflt = self.default()
        return Cohort(opts + [dflt[pid] for pid in missing])

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
                   if s.modality == 'xt' and s.adapted)

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

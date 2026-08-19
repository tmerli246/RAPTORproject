"""Tests on the sign of delta NTCP and on the separation of the two roles the
reference arm plays.

Claims under test:

    A1  no policy ever assigns a strategy of negative utility while a free
        reference arm exists, and no sign constraint is needed to achieve it
    A2  the Pareto reduction is what removes those strategies from the chains
    A3  no solver or policy ever assigns an inadmissible strategy
    A4  with the reference arm inadmissible and nothing free to replace it,
        the exact optimum assigns a negative utility rather than raising
    A5  an empty assignable option set raises and names the patient
    A6  restrict keeps every patient assignable
    A7  the heuristics respect both budgets when a default arm already
        consumes one of them
    A8  the diagnostics count what they claim to count
"""

import numpy as np
import pytest

from tps5d.core.schema import Strategy, Cohort, Facility
from tps5d.allocator.dominance import chains, ladders, pareto
from tps5d.allocator.solve import solve_exact, solve_lp, solve_dp, solve_greedy
from tps5d.allocator.policies import POLICIES, compare
from tps5d.allocator.report import admissibility_counts, summarise
from tps5d.generator.synth import villarroel_cohort, ladder_cohort

BASE = 0.30

# Fixtures

def harm_cohort(n = 6, seed = 0):
    """Cohort in which some proton strategies are worse than the reference.

    Every patient keeps a free assignable reference arm, so the harmful
    strategies are options the allocator may see and must never take.
    """
    rng = np.random.default_rng(seed)
    d = rng.uniform(-0.06, 0.08, n)
    out = []
    for i in range(n):
        pid = f"p{i:02d}"
        out.append(Strategy(pid, 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                            ntcp = {'tot': BASE}, baseline = True))
        out.append(Strategy(pid, 'pt', 'pt', n_fx = 1, tau_pt = 30.0,
                            ntcp = {'tot': BASE - d[i]}, n_adapt = 1))
    return Cohort(out), d

def stranded_cohort(tau_pt = 30.0, harm = 0.05):
    """Two patients, one of whom has no assignable free arm.

    p00 is ordinary. p01 has an inadmissible reference arm, so its only
    assignable option is a proton strategy that is worse than the reference by
    `harm`. The reference arm stays in the cohort as the numeraire.
    """
    out = [
        Strategy('p00', 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True),
        Strategy('p00', 'pt', 'pt', n_fx = 1, tau_pt = tau_pt,
                 ntcp = {'tot': BASE - 0.10}, n_adapt = 1),
        Strategy('p01', 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True, admissible = False),
        Strategy('p01', 'pt', 'pt', n_fx = 1, tau_pt = tau_pt,
                 ntcp = {'tot': BASE + harm}, n_adapt = 1),
    ]
    return Cohort(out)

def photon_default_cohort(dtau_xt = 4.0):
    """A patient whose only assignable options consume the photon budget.

    Exercises the path where the proton chain is empty and the default arm is
    photon-adapted, so photon minutes are committed before any policy runs.
    """
    out = [
        Strategy('p00', 'xt', 'xt', n_fx = 10, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True),
        Strategy('p00', 'pt', 'pt', n_fx = 10, tau_pt = 30.0,
                 ntcp = {'tot': BASE - 0.10}, n_adapt = 1),
        Strategy('p01', 'xt', 'xt', n_fx = 10, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True, admissible = False),
        Strategy('p01', 'xt1', 'xt', n_fx = 10, tau_pt = 0.0, tau_xt = dtau_xt,
                 ntcp = {'tot': BASE - 0.01}, n_adapt = 1),
        Strategy('p01', 'xt2', 'xt', n_fx = 10, tau_pt = 0.0,
                 tau_xt = 2 * dtau_xt,
                 ntcp = {'tot': BASE - 0.03}, n_adapt = 2),
    ]
    return Cohort(out)

# A1: harmful strategies are never assigned while a free reference arm exists

def test_negative_utility_never_assigned():
    cohort, d = harm_cohort()
    fac = Facility(cap_pt_min_day = 1e4)          # capacity deliberately ample
    assert (d < 0).any(), "fixture must contain harmful strategies"

    for name, fn in POLICIES.items():
        alloc = fn(cohort, fac)
        worst = min(cohort.dntcp(s) for s in alloc.choice.values())
        assert worst >= 0.0, f"{name} assigned a strategy worse than the reference"

def test_harmful_patients_stay_on_the_reference_arm():
    cohort, d = harm_cohort()
    fac = Facility(cap_pt_min_day = 1e4)
    alloc = solve_exact(cohort, fac)
    for i, v in enumerate(d):
        s = alloc.choice[f"p{i:02d}"]
        assert s.baseline == (v < 0.0)

def test_no_sign_constraint_is_needed_capacity_is_not_spent_on_harm():
    """The harmful options are free to take under ample capacity. The optimum
    declines them, which is the dominance argument rather than a constraint."""
    cohort, d = harm_cohort()
    fac = Facility(cap_pt_min_day = 1e4)
    alloc = solve_exact(cohort, fac)
    assert alloc.used_pt == pytest.approx(30.0 * (d > 0).sum())

# A2: the Pareto reduction is what removes them

def test_pareto_removes_negative_utility_options():
    cohort, d = harm_cohort()
    ch = chains(cohort)
    for i, v in enumerate(d):
        pid = f"p{i:02d}"
        assert len(ch[pid]) == (2 if v > 0 else 1)
        assert ch[pid][0].baseline

def test_pareto_keeps_the_cheapest_point_whatever_its_sign():
    """The first point survives unconditionally, which is what lets a chain
    start below zero when the reference arm is inadmissible."""
    assert pareto([(0.0, -0.05), (30.0, -0.02)]) == [0, 1]
    assert pareto([(0.0, -0.05), (30.0, -0.08)]) == [0]

# A3: inadmissible strategies are never assigned

def test_inadmissible_strategies_are_never_assigned():
    cohort = stranded_cohort()
    fac = Facility(cap_pt_min_day = 1e4)
    for name, fn in POLICIES.items():
        alloc = fn(cohort, fac)
        for pid, s in alloc.choice.items():
            assert s.admissible, f"{name} assigned an inadmissible strategy to {pid}"

def test_inadmissible_reference_arm_remains_the_numeraire():
    cohort = stranded_cohort(harm = 0.05)
    base = cohort.baseline()['p01']
    assert base.baseline and not base.admissible
    assert cohort.dntcp(base) == pytest.approx(0.0)
    assert cohort.by_patient()['p01'] == [s for s in cohort.strategies
                                          if s.pid == 'p01' and s.admissible]

# A4: a negative assignment is the correct answer, not an error

def test_stranded_patient_receives_a_negative_utility_strategy():
    cohort = stranded_cohort(harm = 0.05)
    fac = Facility(cap_pt_min_day = 1e4)

    assert cohort.no_free_option() == ['p01']

    alloc = solve_exact(cohort, fac)
    assert cohort.dntcp(alloc.choice['p01']) == pytest.approx(-0.05)
    assert cohort.dntcp(alloc.choice['p00']) == pytest.approx(0.10)

def test_stranded_patient_is_served_before_a_beneficial_one_under_scarcity():
    """With room for one proton slot the model must still treat p01, because
    p01 has no alternative. The multiple-choice constraint, not the utility,
    decides this."""
    cohort = stranded_cohort(tau_pt = 30.0, harm = 0.05)
    fac = Facility(cap_pt_min_day = 30.0)

    alloc = solve_exact(cohort, fac)
    assert alloc.choice['p01'].modality == 'pt'
    assert alloc.choice['p00'].baseline
    assert alloc.used_pt == pytest.approx(30.0)

def test_stranded_cohort_is_infeasible_without_capacity():
    cohort = stranded_cohort()
    fac = Facility(cap_pt_min_day = 0.0)
    with pytest.raises(RuntimeError, match = 'p01'):
        solve_exact(cohort, fac)

def test_no_free_option_is_empty_for_an_ordinary_cohort():
    cohort = ladder_cohort(n = 5, x_gain = 0.02, dtau_xt = 3.0)
    assert cohort.no_free_option() == []
    assert cohort.no_option() == []

# A5: an empty assignable set raises and names the patient

def test_empty_option_set_raises_and_names_the_patient():
    out = [
        Strategy('p00', 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True),
        Strategy('p01', 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                 ntcp = {'tot': BASE}, baseline = True, admissible = False),
    ]
    cohort = Cohort(out)
    assert cohort.no_option() == ['p01']
    with pytest.raises(ValueError, match = 'p01'):
        solve_exact(cohort, Facility(cap_pt_min_day = 480.0))
    with pytest.raises(ValueError, match = 'p01'):
        cohort.default()

# A6: restrict keeps every patient assignable

def test_restrict_retains_the_default_when_the_filter_would_empty_a_patient():
    cohort = stranded_cohort()
    sub = cohort.restrict(lambda s: False)         # keeps reference arms only
    assert sub.no_option() == []
    assert sub.by_patient()['p01'][0].modality == 'pt'
    assert sub.baseline()['p01'].baseline

def test_restrict_preserves_the_numeraire():
    cohort = stranded_cohort()
    sub = cohort.restrict(lambda s: s.modality == 'pt')
    for pid in cohort.pids:
        assert sub.baseline()[pid] is cohort.baseline()[pid]
        assert sub.dntcp(sub.baseline()[pid]) == pytest.approx(0.0)

# A7: the heuristics respect both budgets when a default already spends one

def test_photon_budget_is_not_spent_twice():
    cohort = photon_default_cohort(dtau_xt = 4.0)
    demand = cohort.demand_xt()
    fac = Facility(cap_pt_min_day = 480.0, cap_xt_min_day = demand)

    for name, fn in POLICIES.items():
        alloc = fn(cohort, fac)
        assert alloc.used_xt <= fac.budget_xt + 1e-9, f"{name} overspent the photon budget"

def test_empty_proton_chain_falls_back_to_the_default_arm():
    cohort = photon_default_cohort()
    ch = chains(cohort)
    kept, _ = ladders(cohort)
    assert len(ch['p01']) == 1
    assert ch['p01'][0].sid == 'xt1'
    assert kept['p01'][0].sid == 'xt1'

def test_greedy_leaves_the_stranded_patient_on_its_default():
    cohort = photon_default_cohort()
    fac = Facility(cap_pt_min_day = 480.0)
    alloc = solve_greedy(cohort, fac)
    assert alloc.choice['p01'].sid == 'xt1'
    assert alloc.choice['p00'].modality == 'pt'

# A8: the diagnostics count what they claim to count

def test_admissibility_counts_are_consistent():
    cohort = stranded_cohort()
    c = admissibility_counts(cohort)
    assert c['n_patients'] == 2
    assert c['n_options'] == 4
    assert c['n_inadmissible'] == 1
    assert c['n_dntcp_le0'] == 1          # p01's proton arm; reference arms excluded
    assert c['n_no_free_option'] == 1
    assert c['n_no_option'] == 0

def test_summarise_reports_the_sign_of_the_assignment():
    cohort = stranded_cohort(harm = 0.05)
    fac = Facility(cap_pt_min_day = 1e4)
    rec = summarise(cohort, solve_exact(cohort, fac), fac)
    assert rec['n_dntcp_neg'] == 1
    assert rec['min_dntcp'] == pytest.approx(-0.05)

def test_ordinary_cohort_reports_no_violations():
    cohort = ladder_cohort(n = 6)
    fac = Facility(cap_pt_min_day = 300.0, days = 30)
    rec = summarise(cohort, solve_exact(cohort, fac), fac)
    assert rec['n_dntcp_neg'] == 0
    assert admissibility_counts(cohort)['n_no_free_option'] == 0

# Backward compatibility: the all-admissible case is unchanged

def test_all_admissible_cohort_matches_the_dynamic_program():
    cohort = ladder_cohort(n = 6, n_block = 3, shape = 'convex')
    fac = Facility(cap_pt_min_day = 400.0, days = 30)
    a = solve_exact(cohort, fac)
    b = solve_dp(cohort, fac)
    assert a.mean_dntcp == pytest.approx(b.mean_dntcp, abs = 1e-9)

def test_policy_ordering_is_preserved():
    cohort = ladder_cohort(n = 8, n_block = 3, x_gain = 0.02, dtau_xt = 3.0)
    fac = Facility(cap_pt_min_day = 400.0, cap_xt_min_day = 200.0, days = 30)
    out = compare(cohort, fac)
    assert out['P0'].mean_dntcp <= out['P3'].mean_dntcp + 1e-9
    assert out['P2b'].mean_dntcp <= out['P3'].mean_dntcp + 1e-9

def test_villarroel_cohort_is_unaffected():
    cohort = villarroel_cohort(n = 14)
    fac = Facility(cap_pt_min_day = 480.0)
    assert cohort.no_free_option() == []
    alloc = solve_exact(cohort, fac)
    lp = solve_lp(cohort, fac)
    assert lp.value >= alloc.mean_dntcp * len(cohort.pids) - 1e-9

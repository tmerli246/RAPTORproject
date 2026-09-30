"""Algorithmic claims stated in the allocator design, as tests.

T1  with two options per patient and constant occupancy, the allocator
    reproduces the reference study's scenario ladder
T5  solving on absolute NTCP (DP) and on delta NTCP (ILP) give the same allocation
"""

import numpy as np
import pytest

from tps5d.core.schema import Facility, Strategy, Cohort
from tps5d.allocator.solve import solve_exact, solve_dp

from tps5d.generator.synth import villarroel_cohort

# The reference study: 480 min/day, 14 patients, 34.2 min baseline session, and
# the extra minutes per adapted fraction that define scenarios S1 to S6.
EXTRA = [0.0, 2.4, 5.7, 9.3, 13.7, 19.0, 25.7]
N_PT = [14, 13, 12, 11, 10, 9, 8]

@pytest.mark.parametrize('extra, expected', list(zip(EXTRA, N_PT)))
def test_t1_patient_count(extra, expected):
    """The number of proton patients matches the reference study's ladder."""
    cohort = villarroel_cohort(n = 14, extra = extra)
    alloc = solve_exact(cohort, Facility(480.0))
    assert alloc.n_pt == expected
    assert alloc.used_pt <= 480.0 + 1e-9

@pytest.mark.parametrize('extra', EXTRA)
def test_t1_displaced_are_lowest_benefit(extra):
    """Patients displaced to photons are those with the smallest delta NTCP."""
    cohort = villarroel_cohort(n = 14, extra = extra)
    alloc = solve_exact(cohort, Facility(480.0))

    pt = {pid for pid, s in alloc.choice.items() if s.modality == 'pt'}
    benefit = {s.pid: cohort.dntcp(s)
               for s in cohort.strategies if s.modality == 'pt'}
    order = sorted(benefit, key=benefit.get, reverse=True)
    assert pt == set(order[:len(pt)])

def test_t5_dp_on_absolute_ntcp_agrees_with_the_ilp_on_delta_when_baselines_differ():
    """T5. The dynamic program minimises absolute union NTCP and the ILP
    maximises delta NTCP; they are the same problem because each patient takes
    one option and the baseline is a constant. Each patient's option set is
    shifted by a different constant, so that absolute and delta differ per
    patient, and the two solvers are compared."""
    rng = np.random.default_rng(5)
    shift = rng.uniform(0.0, 0.3, 14)
    cohort = villarroel_cohort(n = 14, extra = 9.3)
    for s in cohort.strategies:
        k = int(s.pid[1:])
        s.ntcp = {name: v + shift[k] for name, v in s.ntcp.items()}
    fac = Facility(480.0)
    dp, ilp = solve_dp(cohort, fac), solve_exact(cohort, fac)
    assert {p for p, s in dp.choice.items() if s.modality == 'pt'} == \
           {p for p, s in ilp.choice.items() if s.modality == 'pt'}
    assert dp.mean_dntcp == pytest.approx(ilp.mean_dntcp, abs = 1e-12)

def test_dp_rounds_costs_up_never_down():
    """36.95 min is 369.5 units. Rounded down, 13 patients cost 4797 units and
    fit a 4800 unit budget, but 13 x 36.95 = 480.35 min exceeds 480. The
    correct answer is 12."""
    out = []
    for i in range(13):
        pid = f"p{i:02d}"
        out += [Strategy(pid, 'xt', 'xt', n_fx = 1, tau_pt = 0.0, ntcp = {'tot': 0.30}, baseline = True),
                Strategy(pid, 'pt', 'pt', n_fx = 1, tau_pt = 36.95, ntcp = {'tot': 0.25})]
    alloc = solve_dp(Cohort(out), Facility(480.0))
    assert alloc.n_pt == 12
    assert alloc.used_pt <= 480.0

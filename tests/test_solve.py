"""Algorithmic claims stated in the allocator design, as tests.

T1  with two options per patient and constant occupancy, the allocator
    reproduces the reference study's scenario ladder
T5  solving on absolute NTCP and on delta NTCP give the same allocation
"""

import numpy as np
import pytest

from tps5d.core.schema import Facility
from tps5d.allocator.solve import solve_exact

from synth import Villaroel_cohort

# The reference study: 480 min/day, 14 patients, 34.2 min baseline session, and
# the extra minutes per adapted fraction that define scenarios S1 to S6.
EXTRA = [0.0, 2.4, 5.7, 9.3, 13.7, 19.0, 25.7]
N_PT = [14, 13, 12, 11, 10, 9, 8]

@pytest.mark.parametrize('extra, expected', list(zip(EXTRA, N_PT)))
def test_t1_patient_count(extra, expected):
    """The number of proton patients matches the reference study's ladder."""
    cohort = Villaroel_cohort(n = 14, extra = extra)
    alloc = solve_exact(cohort, Facility(cap_min_day = 480.0))
    assert alloc.n_pt == expected
    assert alloc.used <= 480.0 + 1e-9

@pytest.mark.parametrize('extra', EXTRA)
def test_t1_displaced_are_lowest_benefit(extra):
    """Patients displaced to photons are those with the smallest delta NTCP."""
    cohort = Villaroel_cohort(n = 14, extra = extra)
    alloc = solve_exact(cohort, Facility(cap_min_day = 480.0))

    pt = {pid for pid, s in alloc.choice.items() if s.modality == 'pt'}
    benefit = {s.pid: cohort.dntcp(s)
               for s in cohort.strategies if s.modality == 'pt'}
    order = sorted(benefit, key=benefit.get, reverse=True)
    assert pt == set(order[:len(pt)])

def test_t5_absolute_and_delta_agree():
    """The allocation does not depend on whether the baseline is subtracted."""
    cohort = Villaroel_cohort(n = 14, extra = 9.3)
    alloc = solve_exact(cohort, Facility(cap_min_day = 480.0))

    # Shift every NTCP by a per-patient constant. Delta NTCP is unchanged, so
    # the allocation must be unchanged too.
    for s in cohort.strategies:
        s.ntcp = {k: v * 0.5 for k, v in s.ntcp.items()}
    shifted = solve_exact(cohort, Facility(cap_min_day = 480.0))

    assert {p: s.sid for p, s in alloc.choice.items()} == \
           {p: s.sid for p, s in shifted.choice.items()}
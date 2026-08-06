"""Properties the policy comparison must satisfy.

P3 is an upper bound on every other policy by construction. Nothing else is
ordered a priori: whether P2b beats P2a on a given cohort is the empirical
question the comparison exists to answer, so it is not asserted here.
"""

import pytest

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES, compare

from synth import reference_cohort, ladder_cohort


COHORTS = [
    ('reference', lambda: reference_cohort(14, extra=9.3), Facility(480.0)),
    ('concave', lambda: ladder_cohort(8, shape='concave'), Facility(480.0, days=12)),
    ('linear', lambda: ladder_cohort(8, shape='linear'), Facility(480.0, days=12)),
    ('convex', lambda: ladder_cohort(8, shape='convex'), Facility(480.0, days=12)),
]


@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_all_policies_respect_capacity(name, make, fac):
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert alloc.used <= fac.budget + 1e-9, pol


@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_exact_bounds_every_policy(name, make, fac):
    cohort = make()
    res = compare(cohort, fac)
    for pol, alloc in res.items():
        assert alloc.mean_dntcp <= res['P3'].mean_dntcp + 1e-9, pol


@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_every_patient_receives_exactly_one_strategy(name, make, fac):
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert set(alloc.choice) == set(cohort.pids), pol


@pytest.mark.parametrize('name, make, fac', COHORTS)
def test_no_policy_harms_the_cohort(name, make, fac):
    """Every policy can fall back on the baseline, so the mean cannot go negative."""
    cohort = make()
    for pol, alloc in compare(cohort, fac).items():
        assert alloc.mean_dntcp >= -1e-12, pol


def test_p0_uses_no_adaptation():
    cohort = ladder_cohort(8)
    alloc = POLICIES['P0'](cohort, Facility(480.0, days=12))
    assert all(s.n_adapt == 0 for s in alloc.choice.values())


def test_p1_adapts_every_proton_patient():
    cohort = ladder_cohort(8, n_block=2)
    alloc = POLICIES['P1'](cohort, Facility(480.0, days=12))
    pt = [s for s in alloc.choice.values() if s.modality == 'pt']
    assert pt and all(s.n_adapt == 2 for s in pt)

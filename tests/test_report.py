"""Properties of the reporting layer.

The figures are not tested for appearance; the numbers behind them are.
"""

import pytest

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES, p3
from tps5d.allocator.report import (
    arm_label, summarise, dominance_counts, sweep, sweep_budget_xt, to_csv,
)

from tps5d.generator.synth import (arm_cohort, two_scheme_cohort,
                                   villarroel_cohort)

FAC = Facility(480.0, days = 12)

def test_summary_counts_every_patient_once():
    c = arm_cohort(10)
    rec = summarise(c, p3(c, FAC), FAC)
    arm_keys = [k for k in rec if k.startswith('n_') and
                k not in ('n_patients', 'n_pt', 'n_xt_adapted', 'n_adapted',
                          'n_hypo', 'n_dntcp_neg')]
    assert sum(rec[k] for k in arm_keys) == rec['n_patients'] == 10

def test_summary_mean_matches_the_allocation():
    c = arm_cohort(8)
    a = p3(c, FAC)
    assert summarise(c, a, FAC)['mean_dntcp'] == pytest.approx(a.mean_dntcp)

def test_utilisation_never_exceeds_one():
    c = arm_cohort(10)
    rec = summarise(c, p3(c, FAC), FAC)
    assert rec['utilisation'] <= 1.0 + 1e-9
    assert rec['utilisation_xt'] <= 1.0 + 1e-9

def test_per_endpoint_matches_union_for_a_single_endpoint():
    """With one endpoint the per-endpoint value is the union value."""
    c = arm_cohort(8)
    rec = summarise(c, p3(c, FAC), FAC)
    assert rec['dntcp_tot'] == pytest.approx(rec['mean_dntcp'])

def test_arm_label_distinguishes_the_four_arms():
    c = arm_cohort(4, x_gain = 0.02, dtau_xt = 16.0)
    assert {arm_label(s) for s in c.strategies} == \
           {'XT-NA', 'XT-A', 'PT-NA', 'PT-A'}

def test_arm_label_carries_the_scheme_when_it_is_not_standard():
    c = two_scheme_cohort(4, x_gain = 0.02, dtau_xt = 16.0)
    labels = {arm_label(s) for s in c.strategies}
    assert {'XT-NA', 'XT-A', 'PT-NA', 'PT-A'} <= labels
    assert {'XT-NA hyp', 'XT-A hyp', 'PT-NA hyp', 'PT-A hyp'} <= labels

def test_dominance_counts_are_disjoint_and_bounded():
    """Pareto and LP removals partition what was discarded, and nothing is
    counted twice."""
    c = two_scheme_cohort(10, shape = 'nonconcave', x_gain = 0.02, dtau_xt = 16.0)
    per, tot = dominance_counts(c)
    assert tot['n_pareto'] + tot['n_lp'] <= tot['n_options']
    for pid, d in per.items():
        assert d['n_pareto_dominated'] >= 0
        assert d['n_lp_dominated'] >= 0
        assert d['n_pareto_dominated'] + d['n_lp_dominated'] < d['n_options']

def test_reference_cohort_has_nothing_to_dominate():
    """Two options per patient, one free: neither reduction can remove
    anything."""
    _, tot = dominance_counts(villarroel_cohort(14, extra = 9.3))
    assert tot['n_pareto'] == 0
    assert tot['n_lp'] == 0

def test_sweep_covers_every_point_and_policy():
    dtaus = [5.0, 15.0]
    recs = sweep(lambda dt: arm_cohort(6, dtau = dt), FAC, dtaus, POLICIES)
    assert len(recs) == len(dtaus) * len(POLICIES)
    assert {r['dtau'] for r in recs} == set(dtaus)
    assert {r['policy'] for r in recs} == set(POLICIES)

def test_sweep_shadow_price_is_shared_within_a_point():
    """Lambda is a property of the cohort and capacity, not of the policy."""
    recs = sweep(lambda dt: arm_cohort(6, dtau = dt), FAC, [9.0], POLICIES)
    assert len({r['lambda_pt'] for r in recs}) == 1

def test_exact_policy_is_never_beaten_in_the_sweep():
    recs = sweep(lambda dt: arm_cohort(8, dtau = dt), FAC, [5.0, 20.0], POLICIES)
    for dt in {r['dtau'] for r in recs}:
        at = [r for r in recs if r['dtau'] == dt]
        best = next(r for r in at if r['policy'] == 'P3')['mean_dntcp']
        assert all(r['mean_dntcp'] <= best + 1e-9 for r in at)

def test_budget_sweep_endpoints_are_the_two_limits():
    """At frac 0 the photon constraint forces XT-NA; at frac 1 it cannot bind,
    so lambda_xt is zero. These are T8 and T9 read through the sweep."""
    c = arm_cohort(8, x_gain = 0.02, dtau_xt = 16.0)
    recs = sweep_budget_xt(c, Facility(240.0, days = 12), [0.0, 1.0])
    at0 = next(r for r in recs if r['cxt_frac'] == 0.0)
    at1 = next(r for r in recs if r['cxt_frac'] == 1.0)
    assert at0['cxt_min'] == 0.0
    assert at1['lambda_xt'] == pytest.approx(0.0, abs = 1e-12)

def test_csv_round_trips(tmp_path):
    import csv
    recs = sweep(lambda dt: arm_cohort(5, dtau = dt), FAC, [10.0], POLICIES)
    path = to_csv(recs, tmp_path / 'out.csv')
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(recs)
    assert float(rows[0]['dtau']) == 10.0

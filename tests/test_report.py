"""Properties of the reporting layer.

The figures are not tested for appearance; the numbers behind them are.
"""

import pytest

from tps5d.core.schema import Facility
from tps5d.allocator.policies import POLICIES, p3
from tps5d.allocator.report import (
    arm_label, summarise, dominance_counts, sweep, to_csv,
)

from synth import ladder_cohort, Villaroel_cohort

FAC = Facility(480.0, days = 12)

def test_summary_counts_every_patient_once():
    c = ladder_cohort(10, n_block = 2)
    rec = summarise(c, p3(c, FAC), FAC)
    arm_keys = [k for k in rec if k.startswith('n_') and
                k not in ('n_patients', 'n_pt', 'n_adapt_total')]
    assert sum(rec[k] for k in arm_keys) == rec['n_patients'] == 10

def test_summary_mean_matches_the_allocation():
    c = ladder_cohort(8)
    a = p3(c, FAC)
    assert summarise(c, a, FAC)['mean_dntcp'] == pytest.approx(a.mean_dntcp)

def test_utilisation_never_exceeds_one():
    c = ladder_cohort(10, n_block = 2)
    assert summarise(c, p3(c, FAC), FAC)['utilisation'] <= 1.0 + 1e-9

def test_per_endpoint_matches_union_for_a_single_endpoint():
    """With one endpoint the per-endpoint value is the union value."""
    c = ladder_cohort(8)
    rec = summarise(c, p3(c, FAC), FAC)
    assert rec['dntcp_tot'] == pytest.approx(rec['mean_dntcp'])

def test_arm_label_distinguishes_adaptation_counts():
    c = ladder_cohort(4, n_block = 2)
    labels = {arm_label(s) for s in c.strategies}
    assert 'photons' in labels
    assert 'PT, no adapt' in labels
    assert 'PT, 2 adapt' in labels

def test_dominance_counts_are_disjoint_and_bounded():
    """Pareto and LP removals partition what was discarded, and nothing is
    counted twice."""
    c = ladder_cohort(10, n_block = 3)
    per, tot = dominance_counts(c)
    assert tot['n_pareto'] + tot['n_lp'] <= tot['n_options']
    for pid, d in per.items():
        assert d['n_pareto_dominated'] >= 0
        assert d['n_lp_dominated'] >= 0
        assert d['n_pareto_dominated'] + d['n_lp_dominated'] < d['n_options']

def test_reference_cohort_has_nothing_to_dominate():
    """Two options per patient, one free: neither reduction can remove
    anything."""
    _, tot = dominance_counts(Villaroel_cohort(14, extra = 9.3))
    assert tot['n_pareto'] == 0
    assert tot['n_lp'] == 0 

def test_sweep_covers_every_point_and_policy():
    dtaus = [5.0, 15.0]
    recs = sweep(lambda dt: ladder_cohort(6, dtau = dt), FAC, dtaus, POLICIES)
    assert len(recs) == len(dtaus) * len(POLICIES)
    assert {r['dtau'] for r in recs} == set(dtaus)
    assert {r['policy'] for r in recs} == set(POLICIES)

def test_sweep_shadow_price_is_shared_within_a_point():
    """Lambda is a property of the cohort and capacity, not of the policy."""
    recs = sweep(lambda dt: ladder_cohort(6, dtau = dt), FAC, [9.0], POLICIES)
    assert len({r['lambda'] for r in recs}) == 1

def test_exact_policy_is_never_beaten_in_the_sweep():
    recs = sweep(lambda dt: ladder_cohort(8, dtau = dt), FAC, [5.0, 20.0], POLICIES)
    for dt in {r['dtau'] for r in recs}:
        at = [r for r in recs if r['dtau'] == dt]
        best = next(r for r in at if r['policy'] == 'P3')['mean_dntcp']
        assert all(r['mean_dntcp'] <= best + 1e-9 for r in at)

def test_csv_round_trips(tmp_path):
    import csv
    recs = sweep(lambda dt: ladder_cohort(5, dtau = dt), FAC, [10.0], POLICIES)
    path = to_csv(recs, tmp_path / 'out.csv')
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(recs)
    assert float(rows[0]['dtau']) == 10.0
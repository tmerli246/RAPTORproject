"""Structural tests on the synthetic generator, version 7.

Covers the two mechanical consequences of the September 2026 supervisory
decision that schema, generator and reporting can verify without
composition or evaluation, which remain frozen pending real imaging data
(allocator design 7.0; evaluator design 6.0; STATE.md Section 6):

    the option set is seven strategies per patient with the photon adapted
    arm present, not eight, because XT-NA carries one fractionation
    schedule rather than two (A32)
    a non-adapted arm's block_plans sequence records rescue events, and
    report.rescue_counts summarises exactly what that sequence contains

Neither test touches V95% or dose accumulation, since neither exists in the
generator or the evaluator yet: block_plans is metadata standing in for a
coverage-screen outcome the evaluator has not yet been updated to produce.
"""

import numpy as np
import pytest

from tps5d.core.schema import Cohort
from tps5d.allocator.report import rescue_counts
from tps5d.generator.synth import (
    arm_cohort, two_scheme_cohort, _rescue_sequence,
)

# _rescue_sequence: the mechanism in isolation

def test_rescue_sequence_first_block_is_always_planned_on_pct():
    rng = np.random.default_rng(0)
    seq = _rescue_sequence(rng, n_blocks = 5, p0 = 1.0, decay = 1.0)
    assert seq[0].block_index == 0
    assert seq[0].role == 'planned'
    assert seq[0].source_image == 'pCT'

def test_rescue_sequence_length_matches_n_blocks():
    rng = np.random.default_rng(1)
    seq = _rescue_sequence(rng, n_blocks = 4, p0 = 0.3, decay = 0.5)
    assert [bp.block_index for bp in seq] == [0, 1, 2, 3]

def test_rescue_sequence_at_p0_zero_never_rescues():
    rng = np.random.default_rng(0)
    seq = _rescue_sequence(rng, n_blocks = 6, p0 = 0.0, decay = 0.5)
    assert all(bp.role == 'planned' for bp in seq)
    assert {bp.source_image for bp in seq} == {'pCT'}

def test_rescue_sequence_at_p0_one_and_decay_one_rescues_every_later_block():
    """decay = 1 recovers a constant per-block probability; at p0 = 1 every
    block after the first fails, so each is a distinct, freshly imaged
    rescue."""
    rng = np.random.default_rng(0)
    seq = _rescue_sequence(rng, n_blocks = 5, p0 = 1.0, decay = 1.0)
    assert all(bp.role == 'rescue' for bp in seq[1:])
    assert len({bp.source_image for bp in seq}) == 5

def test_rescue_decay_reduces_the_probability_of_a_further_rescue():
    """Monte Carlo check that a second rescue is rarer than the first at
    decay < 1, over enough draws to separate the two rates comfortably from
    each other and from their nominal values."""
    p0, decay, trials = 0.5, 0.3, 20_000
    rng = np.random.default_rng(42)
    first, second, second_opportunities = 0, 0, 0
    for _ in range(trials):
        seq = _rescue_sequence(rng, n_blocks = 3, p0 = p0, decay = decay)
        if seq[1].role == 'rescue':
            first += 1
            second_opportunities += 1
            if seq[2].role == 'rescue':
                second += 1
    rate1 = first / trials
    rate2 = second / second_opportunities
    assert rate2 < rate1
    assert rate1 == pytest.approx(p0, abs = 0.02)
    assert rate2 == pytest.approx(p0 * decay, abs = 0.03)

# Option-set structure: seven strategies, one XT-NA schedule

def test_two_scheme_cohort_holds_seven_options_with_the_full_arm_set():
    """The design's seven-strategy option set (allocator 5.1) assumes the
    adapted photon arm exists; x_gain > 0 is what turns it on here."""
    cohort = two_scheme_cohort(n = 6, x_gain = 0.02, dtau_xt = 16.0)
    for pid, opts in cohort.all_by_patient().items():
        assert len(opts) == 7, pid

def test_two_scheme_cohort_without_photon_adaptation_holds_five():
    """x_gain = 0 is the deliberate single-resource simplification already
    documented in the module: XT-A is absent, not merely zero-utility."""
    cohort = two_scheme_cohort(n = 6, x_gain = 0.0)
    for pid, opts in cohort.all_by_patient().items():
        assert len(opts) == 5, pid

def test_xt_na_carries_exactly_one_schedule_per_patient():
    cohort = two_scheme_cohort(n = 6, x_gain = 0.02, dtau_xt = 16.0)
    for pid, opts in cohort.all_by_patient().items():
        assert sum(1 for s in opts if s.baseline) == 1, pid

def test_xt_na_schedule_follows_hypo_frac_at_its_deterministic_endpoints():
    """A21/A32: at hypo_frac = 0 every patient's XT-NA is std; at 1, every
    patient's is hyp. Checked at the endpoints rather than at a default
    fraction, which would depend on the seed to exercise both branches."""
    all_std = two_scheme_cohort(n = 6, hypo_frac = 0.0)
    for pid in all_std.pids:
        assert all_std.baseline()[pid].scheme == 'std'

    all_hyp = two_scheme_cohort(n = 6, hypo_frac = 1.0)
    for pid in all_hyp.pids:
        assert all_hyp.baseline()[pid].scheme == 'hyp'

def test_arm_cohort_option_count_is_unaffected_by_the_xt_na_change():
    """A single-schedule cohort has no second schedule for XT-NA to avoid,
    so its structure (four arms, or three without x_gain) is unchanged."""
    cohort = arm_cohort(n = 5)
    for pid, opts in cohort.all_by_patient().items():
        assert len(opts) == 3, pid          # XT-NA, PT-NA, PT-A
    cohort = arm_cohort(n = 5, x_gain = 0.02, dtau_xt = 16.0)
    for pid, opts in cohort.all_by_patient().items():
        assert len(opts) == 4, pid

# Adapted arms never carry a rescue in generated cohorts

def test_adapted_arms_are_never_rescued_in_generated_cohorts():
    cohort = two_scheme_cohort(n = 10, x_gain = 0.02, dtau_xt = 16.0,
                               p_rescue0 = 1.0, rescue_decay = 1.0)
    for s in cohort.strategies:
        if s.adapted:
            assert s.n_rescues == 0, s.sid
            assert all(bp.role == 'planned' for bp in s.block_plans)

def test_non_adapted_arms_carry_independent_block_plans():
    """XT-NA and PT-NA are drawn from separate rng calls (per-arm, not
    cumulative across arms), so their rescue counts need not agree even
    though they share a p0 and decay."""
    cohort = arm_cohort(n = 20, p_rescue0 = 0.5, rescue_decay = 0.5,
                        n_blocks = 4, seed = 7)
    xt_rescues = [s.n_rescues for s in cohort.strategies
                 if s.modality == 'xt' and not s.adapted]
    pt_rescues = [s.n_rescues for s in cohort.strategies
                 if s.modality == 'pt' and not s.adapted]
    assert xt_rescues != pt_rescues

# Integration with report.rescue_counts

def test_rescue_counts_matches_the_generated_sequence():
    n, n_blocks = 5, 4
    cohort = arm_cohort(n = n, p_rescue0 = 1.0, rescue_decay = 1.0,
                        n_blocks = n_blocks)
    counts = rescue_counts(cohort)

    rescuable_blocks = n_blocks - 1                # block 0 never rescues
    expected_per_arm = n * rescuable_blocks
    assert counts['by_arm']['XT-NA'] == expected_per_arm
    assert counts['by_arm']['PT-NA'] == expected_per_arm
    assert 'PT-A' not in counts['by_arm']           # adapted, never rescued
    assert set(counts['by_block']) == set(range(1, n_blocks))
    for b in range(1, n_blocks):
        assert counts['by_block'][b] == n * 2        # XT-NA and PT-NA both fail
    assert counts['n_events'] == 2 * expected_per_arm
    assert counts['n_modelled'] == len(cohort.strategies)

def test_rescue_counts_excludes_strategies_with_no_block_plans():
    """A cohort built by hand, as several other test fixtures are, carries
    no block_plans and must contribute nothing rather than a false zero."""
    from tps5d.core.schema import Strategy
    out = [Strategy('p00', 'xt', 'xt', n_fx = 1, tau_pt = 0.0,
                    ntcp = {'tot': 0.3}, baseline = True)]
    counts = rescue_counts(Cohort(out))
    assert counts == {'by_arm': {}, 'by_block': {}, 'n_events': 0,
                      'n_modelled': 0}

def test_rescue_counts_is_zero_at_p0_zero():
    cohort = arm_cohort(n = 8, p_rescue0 = 0.0, n_blocks = 4)
    counts = rescue_counts(cohort)
    assert counts['by_arm'] == {}
    assert counts['by_block'] == {}
    assert counts['n_events'] == 0
    assert counts['n_modelled'] == len(cohort.strategies)   # still modelled

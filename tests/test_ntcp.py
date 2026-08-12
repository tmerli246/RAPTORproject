"""Analytical properties of the biological layer.

Everything here is checkable without patient data. The identities come from the
linear quadratic model itself, so a failure is a coding error, not a modelling
disagreement.
"""

import numpy as np
import pytest

from tps5d.evaluator.ntcp import (
    bed, eqd2, eqd2_from_bed, geud, geud_from_cumulative_dvh, lkb_from_geud,
)
from tps5d.evaluator.registry import REGISTRY, evaluate_dose

RNG = np.random.default_rng(7)

# EQD2 and BED identities
def test_eqd2_is_identity_at_2gy_per_fraction():
    """A course delivered at exactly 2 Gy/fx is its own EQD2."""
    dose = np.full(500, 60.0)
    out = eqd2(dose, n_fx = 30, ab = 3.0)
    assert np.allclose(out, dose)

def test_eqd2_penalizes_hypofractionation_for_low_ab():
    """At alpha/beta 3, 7 Gy/fx inflates EQD2: 35 Gy in 5 fx -> 70 Gy.
    This is the worked example in the road document, section 3.6."""
    dose = np.full(100, 35.0)
    out = eqd2(dose, n_fx = 5, ab = 3.0)
    assert np.allclose(out, 70.0)

def test_eqd2_at_tumor_ab():
    """Same schedule at alpha/beta 10: 35 Gy in 5 fx -> 49.6 Gy."""
    dose = np.full(100, 35.0)
    out = eqd2(dose, n_fx = 5, ab = 10.0)
    assert np.allclose(out, 35.0 * (7.0 + 10.0) / 12.0)

def test_bed_is_additive_over_segments():
    """BED of a mixed course equals the sum of segment BEDs.
    Ten fractions at 1.8 Gy plus five at 4 Gy, per voxel."""
    d1 = RNG.uniform(0.0, 20.0, 300)
    d2 = RNG.uniform(0.0, 25.0, 300)
    total = bed(d1, 10, 3.0) + bed(d2, 5, 3.0)
    # No single-course call reproduces this, which is the point: the mixed
    # course has no global fraction count. Check against the closed form.
    expect = d1 * (1 + d1 / 10 / 3.0) + d2 * (1 + d2 / 5 / 3.0)
    assert np.allclose(total, expect)

def test_eqd2_from_bed_inverts_the_reference_condition():
    """BED of a 2 Gy/fx course converts back to its physical dose."""
    dose = np.full(200, 50.0)
    b = bed(dose, n_fx = 25, ab = 3.0)
    assert np.allclose(eqd2_from_bed(b, 3.0), dose)

# gEUD properties
def test_geud_equals_mean_dose_at_n_one():
    dose = RNG.uniform(0.0, 60.0, 1000)
    assert np.isclose(geud(dose, n = 1.0), dose.mean())

def test_geud_bounded_by_mean_and_max():
    """For n <= 1 the power mean sits between mean and max dose, and it
    increases as n decreases. Convergence to the max is logarithmically slow
    in 1/n, so no rate is asserted, only the ordering."""
    dose = RNG.uniform(0.0, 60.0, 1000)
    g_small = geud(dose, n = 0.01)
    assert dose.mean() < g_small < dose.max()
    assert g_small > geud(dose, n = 0.1)

def test_geud_is_monotone_in_n_between_mean_and_max():
    dose = RNG.uniform(10.0, 60.0, 1000)
    values = [geud(dose, n) for n in (0.05, 0.1, 0.3, 1.0)]
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert dose.mean() <= values[-1] <= values[0] <= dose.max()

def test_geud_uniform_dose_is_itself():
    dose = np.full(400, 42.0)
    for n in (0.05, 0.5, 1.0):
        assert np.isclose(geud(dose, n), 42.0)

# DVH boundary (assumption E3 harness)
# In production the DVH comes from OpenTPS. The helper below reproduces the
# shape OpenTPS returns from DVH.histogram, namely bin centres in Gy and the
# volume receiving at least that dose in per cent, so that the reduction is
# testable without OpenTPS installed. 
def cumulative_dvh(dose, n_bins = 4096, max_dose = 100.0):
    """Cumulative DVH in the form OpenTPS returns."""
    dose = np.clip(dose, 0.0, None)
    edges = np.linspace(0.0, max_dose, n_bins + 1)
    edges[-1] = max(max_dose, float(dose.max())) + 1e-9
    counts, _ = np.histogram(dose, bins = edges)
    above = np.cumsum(counts[::-1])[::-1]
    centres = edges[:n_bins] + 0.5 * (edges[1] - edges[0])
    return centres, above * 100.0 / dose.size

def test_geud_from_dvh_matches_voxelwise():
    """The binned route agrees with the voxel-wise route for serial and
    parallel volume parameters. This is the check to rerun on the first
    exported case, with the DVH taken from OpenTPS."""
    dose = np.concatenate([RNG.uniform(0.0, 30.0, 5000),
                           RNG.uniform(45.0, 55.0, 2000)])
    bins, vol = cumulative_dvh(dose)
    for n in (0.09, 0.5, 1.0):
        assert geud_from_cumulative_dvh(bins, vol, n) == pytest.approx(
            geud(dose, n), rel = 0.01)

def test_geud_from_dvh_exact_for_uniform_dose():
    dose = np.full(4000, 42.0)
    bins, vol = cumulative_dvh(dose)
    assert geud_from_cumulative_dvh(bins, vol, 0.09) == pytest.approx(42.0, rel = 0.01)

def test_geud_from_dvh_rejects_an_empty_histogram():
    bins, vol = np.linspace(0, 100, 10), np.zeros(10)
    with pytest.raises(ValueError, match = "empty DVH"):
        geud_from_cumulative_dvh(bins, vol, 0.09)

# LKB probit
def test_ntcp_is_half_at_td50():
    dose = np.full(300, 76.9)          # uniform dose at TD50, already EQD2
    m = REGISTRY["rectum_bleeding_g2"]
    g = geud(dose, m.params['n'])
    assert lkb_from_geud(g, m.params['td50'], m.params['m']) == pytest.approx(0.5, abs = 1e-9)

def test_ntcp_monotone_in_dose():
    m = REGISTRY["rectum_bleeding_g2"]
    levels = [30.0, 45.0, 60.0, 76.9, 90.0]
    vals = [evaluate_dose(m, np.full(200, d), 28) for d in levels]
    assert all(a < b for a, b in zip(vals, vals[1:]))

def test_lkb_from_geud_vectorizes_over_parameters():
    """The propagation loops over perturbed (td50, m) at fixed gEUD."""
    td50 = RNG.normal(76.9, 3.0, 1000)
    m = np.abs(RNG.normal(0.13, 0.02, 1000))
    out = lkb_from_geud(60.0, td50, m)
    assert out.shape == (1000,)
    assert np.all((out >= 0.0) & (out <= 1.0))

def test_hypofractionation_raises_ntcp_at_fixed_physical_dose():
    """Same physical dose in fewer fractions must give higher NTCP for an
    organ with low alpha/beta. Sign check on the whole chain."""
    m = REGISTRY["rectum_bleeding_g2"]
    dose = np.full(300, 60.0)
    assert evaluate_dose(m, dose, 5) > evaluate_dose(m, dose, 30)
"""Registry mechanics and the analytical properties of each model form."""

import numpy as np
import pytest

from tps5d.evaluator.ntcp import eqd2, geud, lkb_from_geud
from tps5d.evaluator.registry import (
    Model, REGISTRY, required_rois, required_covariates, alpha_beta_union,
    validate_cohort, evaluate, evaluate_dose,
)

RNG = np.random.default_rng(11)


class FakePatient:
    def __init__(self, pid, rois, covariates=None):
        self.pid = pid
        self.rois = set(rois)
        self.covariates = covariates or {}


# Record validation

def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown kind"):
        Model(name='x', site='pelvis', kind='banana', roi='Rectum')

def test_missing_params_raise_by_name():
    with pytest.raises(ValueError, match="td50"):
        Model(name='x', site='pelvis', kind='lkb', roi='Rectum',
              alpha_beta=3.0, params={'n': 0.1, 'm': 0.1})

def test_voxel_forms_require_alpha_beta():
    with pytest.raises(ValueError, match="alpha_beta"):
        Model(name='x', site='pelvis', kind='lkb', roi='Rectum',
              params={'n': 0.1, 'm': 0.1, 'td50': 70.0})

def test_fractionation_correctability_is_a_property_of_the_form():
    lkb = REGISTRY['rectum_bleeding_g2']
    logi = Model(name='y', site='lung', kind='logistic', roi='Lungs',
                 params={'b0': -3.0, 'terms': {'mld': 0.1}})
    assert lkb.fractionation_correctable
    assert not logi.fractionation_correctable


# Engine: validation before dose work

def test_cohort_validation_names_the_missing_roi():
    models = [REGISTRY['rectum_bleeding_g2']]
    good = FakePatient('p00', rois=['Rectum', 'Bowel'])
    bad = FakePatient('p01', rois=['Bowel'])
    validate_cohort(models, [good])
    with pytest.raises(ValueError, match="p01.*Rectum"):
        validate_cohort(models, [good, bad])

def test_cohort_validation_names_the_missing_covariate():
    m = Model(name='y', site='lung', kind='logistic', roi='Lungs',
              params={'b0': -3.0, 'terms': {'age': 0.02}},
              covariates=['age'])
    with pytest.raises(ValueError, match="p00.*age"):
        validate_cohort([m], [FakePatient('p00', rois=['Lungs'])])

def test_alpha_beta_union_sizes_the_composition_workload():
    a = REGISTRY['rectum_bleeding_g2']
    b = Model(name='y', site='pelvis', kind='rseriality', roi='Bladder',
              alpha_beta=5.0, params={'d50': 60.0, 'gamma': 2.0, 's': 0.5})
    c = Model(name='z', site='lung', kind='logistic', roi='Lungs',
              params={'b0': 0.0, 'terms': {}})
    assert alpha_beta_union([a, b, c]) == [3.0, 5.0]


# LKB through the registry agrees with the direct route

def test_registry_lkb_matches_the_explicit_chain():
    """The registry route agrees with EQD2, gEUD and probit applied by hand."""
    dose = RNG.uniform(20.0, 70.0, 800)
    m = REGISTRY['rectum_bleeding_g2']
    g = geud(eqd2(dose, 28, m.alpha_beta), m.params['n'])
    direct = float(lkb_from_geud(g, m.params['td50'], m.params['m']))
    assert evaluate_dose(m, dose, 28) == pytest.approx(direct, abs=1e-12)

def test_evaluate_dose_rejects_metric_based_forms():
    m = Model(name='y', site='lung', kind='logistic', roi='Lungs',
              params={'b0': 0.0, 'terms': {}})
    with pytest.raises(ValueError, match="metric-based"):
        evaluate_dose(m, np.full(10, 20.0), 28)


# Logistic form

def test_logistic_at_zero_predictor_is_half():
    m = Model(name='y', site='lung', kind='logistic', roi='Lungs',
              params={'b0': 0.0, 'terms': {}})
    assert evaluate(m, metrics={}) == pytest.approx(0.5)

def test_logistic_reads_metrics_and_covariates_and_is_monotone():
    m = Model(name='y', site='lung', kind='logistic', roi='Lungs',
              params={'b0': -4.0, 'terms': {'mld': 0.15, 'age': 0.02}},
              covariates=['age'])
    lo = evaluate(m, metrics={'mld': 10.0}, covariates={'age': 60})
    hi = evaluate(m, metrics={'mld': 20.0}, covariates={'age': 60})
    assert 0.0 < lo < hi < 1.0

def test_logistic_missing_term_raises_by_name():
    m = Model(name='y', site='lung', kind='logistic', roi='Lungs',
              params={'b0': 0.0, 'terms': {'mld': 0.1}})
    with pytest.raises(ValueError, match="mld"):
        evaluate(m, metrics={})


# Relative seriality

RS = Model(name='w', site='pelvis', kind='rseriality', roi='Rectum',
           alpha_beta=3.0, params={'d50': 60.0, 'gamma': 2.0, 's': 1.0})

def test_rseriality_uniform_dose_at_d50_gives_poisson_value():
    """At uniform D = D50 the voxel response is 2^(-exp(0)) = 0.5, and at
    s = 1 with uniform dose the whole-organ NTCP equals the voxel response."""
    dose = np.full(500, 60.0)
    assert evaluate(RS, eqd2_dose=dose) == pytest.approx(0.5, abs=1e-9)

def test_rseriality_monotone_in_dose():
    levels = [30.0, 45.0, 60.0, 75.0]
    vals = [evaluate(RS, eqd2_dose=np.full(300, d)) for d in levels]
    assert all(a < b for a, b in zip(vals, vals[1:]))

def test_rseriality_seriality_raises_sensitivity_to_hot_subvolume():
    """A hot subvolume matters more for a serial organ (large s) than a
    parallel one (small s)."""
    dose = np.concatenate([np.full(900, 30.0), np.full(100, 70.0)])
    serial = Model(name='a', site='pelvis', kind='rseriality', roi='Rectum',
                   alpha_beta=3.0, params={'d50': 60.0, 'gamma': 2.0, 's': 4.0})
    parallel = Model(name='b', site='pelvis', kind='rseriality', roi='Rectum',
                     alpha_beta=3.0, params={'d50': 60.0, 'gamma': 2.0, 's': 0.01})
    assert evaluate(serial, eqd2_dose=dose) > evaluate(parallel, eqd2_dose=dose)

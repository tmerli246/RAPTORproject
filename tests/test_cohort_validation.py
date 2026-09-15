"""Cohort-level orchestration: validate_cohort against registry.py's real
models, evaluator design 11.2's remaining open item.

`test_end_to_end.py` proves the pipeline correct for one strategy on one
patient, built by hand. What it does not exercise is `validate_cohort`
itself: the check `registry.py`'s own docstring describes as running
"before any dose work", so a missing ROI or covariate surfaces at cohort
assembly rather than after hours of accumulation. This file exercises
that check directly, against the real `REGISTRY`, with a minimal local
Patient shape rather than a new production Cohort class: `validate_cohort`
only requires `.pid`, `.rois`, `.covariates`, per its own docstring, and
introducing a class to carry that shape into the pipeline is a design
choice for whoever writes the real cohort loader once ingest is driven
across many patients, not this file's decision to make unilaterally.
"""

from dataclasses import dataclass, field

import pytest

from tps5d.evaluator import registry


@dataclass
class Patient:
    """The minimal shape validate_cohort's own docstring specifies:
    .pid, .rois, .covariates. Local to this test file, not part of the
    production codebase: see the module docstring.
    """
    pid: str
    rois: set = field(default_factory=set)
    covariates: dict = field(default_factory=dict)


class TestValidateCohortAgainstRealRegistry:

    def test_passes_when_every_patient_has_the_required_roi(self):
        models = [registry.REGISTRY['rectum_bleeding_g2']]
        patients = [
            Patient(pid='pt1', rois={'Rectum', 'Bladder'}),
            Patient(pid='pt2', rois={'Rectum'}),
        ]
        registry.validate_cohort(models, patients)  # no raise

    def test_raises_naming_the_patient_and_the_missing_roi(self):
        models = [registry.REGISTRY['rectum_bleeding_g2']]
        patients = [
            Patient(pid='pt1', rois={'Rectum'}),
            Patient(pid='pt2', rois={'Bladder'}),   # missing Rectum
        ]
        with pytest.raises(ValueError, match="pt2.*Rectum"):
            registry.validate_cohort(models, patients)

    def test_first_missing_patient_is_reported_not_the_last(self):
        """validate_cohort iterates and raises on the first failure: this
        pins that it is pt1, not pt2, in a cohort where pt1 is listed
        first and is the one missing the ROI.
        """
        models = [registry.REGISTRY['rectum_bleeding_g2']]
        patients = [
            Patient(pid='pt1', rois=set()),
            Patient(pid='pt2', rois={'Rectum'}),
        ]
        with pytest.raises(ValueError, match='pt1'):
            registry.validate_cohort(models, patients)

    def test_empty_cohort_does_not_raise(self):
        """No patients means nothing to check: this is a degenerate but
        valid call, not an error, since the loop simply does not execute.
        """
        registry.validate_cohort([registry.REGISTRY['rectum_bleeding_g2']], [])


class TestValidateCohortWithCovariates:
    """The real REGISTRY's only populated model has no covariates
    (`rectum_bleeding_g2`, kind 'lkb'), so the covariate-checking path is
    untested by the class above. A local 'logistic' Model, not added to
    REGISTRY, exercises it: registry.py's own population is Tommaso's
    decision, not this test file's to make by adding an entry.
    """

    def _logistic_model_with_covariates(self):
        return registry.Model(
            name='test_logistic',
            site='test',
            kind='logistic',
            roi='Bladder',
            params={'b0': -1.0, 'terms': {'dose_metric': 0.05, 'age': 0.01}},
            covariates=['age'],
        )

    def test_passes_when_covariate_present(self):
        model = self._logistic_model_with_covariates()
        patients = [Patient(pid='pt1', rois={'Bladder'}, covariates={'age': 65})]
        registry.validate_cohort([model], patients)  # no raise

    def test_raises_naming_the_missing_covariate(self):
        model = self._logistic_model_with_covariates()
        patients = [Patient(pid='pt1', rois={'Bladder'}, covariates={})]
        with pytest.raises(ValueError, match="pt1.*age"):
            registry.validate_cohort([model], patients)

    def test_roi_checked_before_covariates_for_the_same_patient(self):
        """Both a missing ROI and a missing covariate exist for the same
        patient; the ROI check runs first in validate_cohort's own loop
        order, so that is the error that surfaces.
        """
        model = self._logistic_model_with_covariates()
        patients = [Patient(pid='pt1', rois=set(), covariates={})]
        with pytest.raises(ValueError, match='ROI'):
            registry.validate_cohort([model], patients)


class TestValidateCohortThenEvaluateForARealCohort:
    """The full shape: validate a small cohort, then evaluate each patient
    who passes, using the pre-populated model and a directly-supplied
    EQD2 array rather than re-running the whole DICOM pipeline, which
    test_end_to_end.py already covers for one patient.
    """

    def test_two_patient_cohort_validates_then_evaluates(self):
        import numpy as np

        model = registry.REGISTRY['rectum_bleeding_g2']
        patients = [
            Patient(pid='pt1', rois={'Rectum'}),
            Patient(pid='pt2', rois={'Rectum'}),
        ]
        registry.validate_cohort([model], patients)

        # Each patient's own accumulated EQD2 inside Rectum, distinct
        # values to confirm they are not accidentally sharing one result.
        eqd2_pt1 = np.full(50, 93.2)
        eqd2_pt2 = np.full(50, 70.0)

        ntcp_pt1 = registry.evaluate(model, eqd2_dose=eqd2_pt1)
        ntcp_pt2 = registry.evaluate(model, eqd2_dose=eqd2_pt2)

        assert ntcp_pt1 != pytest.approx(ntcp_pt2)
        assert 0.0 <= ntcp_pt1 <= 1.0
        assert 0.0 <= ntcp_pt2 <= 1.0

    def test_cohort_with_one_invalid_patient_stops_before_any_evaluation(self):
        """The point of validating first: a bad cohort must not reach
        evaluate() for any patient, not even the valid ones, since
        registry.py's own docstring states the check runs before any dose
        work, for the whole cohort at once.
        """
        model = registry.REGISTRY['rectum_bleeding_g2']
        patients = [
            Patient(pid='pt1', rois={'Rectum'}),
            Patient(pid='pt2', rois=set()),   # invalid
        ]
        with pytest.raises(ValueError):
            registry.validate_cohort([model], patients)
        # no evaluate() call follows: this test's assertion is the raise
        # above, not a reachability check on evaluate() itself

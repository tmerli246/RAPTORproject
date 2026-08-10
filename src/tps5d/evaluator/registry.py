"""NTCP model registry.

Models are declarative records rather than classes: what varies between sites
is which structures matter, which endpoints are modelled and which parameters
those models use, and none of that is code. Three functional forms cover
nearly everything in use; `kind` selects one.

    lkb          probit on gEUD, voxel-wise EQD2 input
    logistic     sigmoid on a linear predictor over dose metrics and clinical
                 covariates, as used by the Dutch protocol models
    rseriality   relative seriality (Kallman), voxel-wise EQD2 input

The engine contract: given a cohort and a model list, collect the union of
required ROIs, covariates and alpha/beta values, validate the cohort against
that union before any dose work, then evaluate. A missing covariate surfaces
at cohort assembly, not after hours of accumulation.

Fractionation-correctability is a property of the form, not of the fit. LKB
and relative seriality act on a voxel-wise EQD2 field with a declared
alpha/beta, so they admit a dose-per-fraction correction. The multivariable
logistic fits contain no alpha/beta and no fractionation term of any kind, so
they do not; a study arm that changes the fractionation scheme cannot reuse
them. This is the endpoint-selection constraint of the road document, made
queryable.
"""

from dataclasses import dataclass, field
import numpy as np

from tps5d.evaluator.ntcp import eqd2, geud, lkb_from_geud

KINDS = ('lkb', 'logistic', 'rseriality')

@dataclass
class Model:
    """One endpoint model.

    name        short identifier
    site        anatomical site the registry entry belongs to
    kind        'lkb' | 'logistic' | 'rseriality'
    roi         TG-263 canonical structure name the model reads
    alpha_beta  Gy, used by the evaluator to build the EQD2 field this model
                consumes. None for forms that take metrics, not voxels
    params      form-specific parameters, see evaluate()
    covariates  clinical covariate names the model requires from the cohort
    source      literature reference
    fitted_on   delineation, modality and fractionation the fit assumes
    """
    name: str
    site: str
    kind: str
    roi: str
    alpha_beta: float = None
    params: dict = field(default_factory = dict)
    covariates: list = field(default_factory = list)
    source: str = ""
    fitted_on: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: unknown kind '{self.kind}'")
        need = {'lkb': {'n', 'm', 'td50'},
                'logistic': {'b0', 'terms'},
                'rseriality': {'d50', 'gamma', 's'}}[self.kind]
        missing = need - set(self.params)
        if missing:
            raise ValueError(f"{self.name}: missing params {sorted(missing)}")
        if self.kind in ('lkb', 'rseriality') and self.alpha_beta is None:
            raise ValueError(f"{self.name}: voxel-based form requires alpha_beta")

    @property
    def fractionation_correctable(self):
        """Whether the form admits an explicit dose-per-fraction correction."""
        return self.kind in ('lkb', 'rseriality')

# Registry, populated only for the site in use in task 0 for now. The mechanism is general.
REGISTRY = {
    'rectum_bleeding_g2': Model(
        name = 'rectum_bleeding_g2',
        site ='pelvis',
        kind = 'lkb',
        roi = 'Rectum',
        alpha_beta = 3.0,
        params = {'n': 0.09, 'm': 0.13, 'td50': 76.9},
        source = 'Michalski et al., QUANTEC, IJROBP 2010',
        fitted_on = 'solid rectum, photon, 1.8-2.0 Gy/fx',
    ),
}

# Engine
def required_rois(models):
    return sorted({m.roi for m in models})

def required_covariates(models):
    out = set()
    for m in models:
        out |= set(m.covariates)
    return sorted(out)

def alpha_beta_union(models):
    """Distinct alpha/beta values, which sizes the composition workload: one
    warped BED field per (block, scheme, alpha/beta)."""
    return sorted({m.alpha_beta for m in models if m.alpha_beta is not None})

def validate_cohort(models, patients):
    """Check every patient carries what the active models need.

    patients : iterable of objects with .pid, .rois (set of canonical names)
               and .covariates (dict)
    Raises with the patient and the missing item. Runs before any dose work.
    """
    rois = required_rois(models)
    covs = required_covariates(models)
    for p in patients:
        for r in rois:
            if r not in p.rois:
                raise ValueError(f"{p.pid}: missing ROI '{r}'")
        for c in covs:
            if c not in p.covariates:
                raise ValueError(f"{p.pid}: missing covariate '{c}'")

def evaluate(model, eqd2_dose=None, metrics=None, covariates=None):
    """NTCP of one model.

    eqd2_dose  voxel EQD2 inside model.roi, for 'lkb' and 'rseriality'. The
               evaluator builds this field at model.alpha_beta
    metrics    dict of dose metrics, for 'logistic'
    covariates dict of clinical covariates, for 'logistic'

    Logistic params: {'b0': intercept,
                      'terms': {name: coefficient}}
    where each name is looked up in metrics first, then covariates.
    """
    if model.kind == 'lkb':
        g = geud(np.asarray(eqd2_dose), model.params['n'])
        return float(lkb_from_geud(g, model.params['td50'], model.params['m']))

    if model.kind == 'logistic':
        s = model.params['b0']
        pool = {**(metrics or {}), **(covariates or {})}
        for term, coef in model.params['terms'].items():
            if term not in pool:
                raise ValueError(f"{model.name}: missing term '{term}'")
            s += coef * pool[term]
        return float(1.0 / (1.0 + np.exp(-s)))

    # Relative seriality (Kallman). Equal-volume voxels.
    d = np.clip(np.asarray(eqd2_dose, dtype=float), 0.0, None)
    d50, gamma, srs = model.params['d50'], model.params['gamma'], model.params['s']
    p_vox = 2.0 ** (-np.exp(np.e * gamma * (1.0 - d / d50)))
    v = 1.0 / d.size
    prod = np.prod((1.0 - p_vox ** srs) ** v)
    return float((1.0 - prod) ** (1.0 / srs))

def evaluate_dose(model, dose, n_fx):
    """NTCP of one model from a single plan's physical dose.

    Convenience for the one-segment case: converts to EQD2 at the model's
    alpha/beta, then evaluates. A multi-block course goes through the
    evaluator's accumulation path instead (BED per block, deform, sum over
    blocks, one final conversion) and calls evaluate() on the resulting field.
    """
    if model.alpha_beta is None:
        raise ValueError(f"{model.name}: metric-based form, use evaluate()")
    return evaluate(model, eqd2_dose = eqd2(dose, n_fx, model.alpha_beta))
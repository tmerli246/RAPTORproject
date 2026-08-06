# Imports
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm

# Model definitions
@dataclass
class NTCPModel:
    """LKB parameters for one OAR/endpoint.
    name     : short identifier
    endpoint : toxicity endpoint the parameters were fitted to
    n        : volume parameter (small n serial, large n parallel)
    m        : slope of the dose-response curve
    td50     : dose to 50% complication (Gy, EQD2, 2 Gy/fx reference)
    ab       : alpha/beta for the EQD2 correction (Gy)
    source   : literature reference for the parameters
    """
    name: str
    endpoint: str
    n: float
    m: float
    td50: float
    ab: float
    source: str

# Rectum: QUANTEC-recommended LKB fit for late rectal bleeding grade >=2
# (Michalski et al., IJROBP 2010). Derived from prostate cohorts at ~74 Gy, 2 Gy/fx.
# Applying it to a 50.4 Gy gynae plan extrapolates below the calibration dose range,
# so absolute NTCP values will be small and differences matter more than magnitudes.
# Alternative fit (Gulliford et al., RT01, Radiother Oncol 2012): n=0.13, m=0.15, td50=68.5.
#
# Bowel: no consensus LKB exists for acute grade >=2 diarrhoea in gynae RT, which is
# usually modelled by absolute-volume constraints (V5, V15, V45 in cc). The values below
# are a PLACEHOLDER borrowed from the QUANTEC stomach bleeding fit and are NOT validated
# for the acute diarrhoea endpoint. Replace before drawing any conclusion on bowel.

MODELS = {
    "rectum_bleeding_g2": NTCPModel(
        name="rectum_bleeding_g2",
        endpoint="late rectal bleeding, grade >=2",
        n=0.09, m=0.13, td50=76.9, ab=3.0,
        source="Michalski et al., QUANTEC, IJROBP 2010",
    ),
    "bowel_placeholder": NTCPModel(
        name="bowel_placeholder",
        endpoint="GI toxicity (PLACEHOLDER, not validated for acute diarrhoea)",
        n=0.09, m=0.30, td50=59.0, ab=3.0,
        source="QUANTEC stomach bleeding fit, Kavanagh et al. IJROBP 2010 (placeholder)",
    ),
}

# Core model
def eqd2(dose, n_fx, ab):
    """Convert total dose to EQD2 voxel-wise using the linear-quadratic model.
    dose : total dose over all fractions (Gy)
    n_fx : number of fractions
    ab   : alpha/beta (Gy)
    Returns the EQD2 array (Gy).
    """
    dose = np.clip(dose, 0.0, None)
    d = dose / n_fx  # per-fraction dose, assumed uniform over fractions
    return dose * (d + ab) / (2.0 + ab)

def geud(dose, n):
    """Generalized equivalent uniform dose from equal-volume voxel doses.
    dose : voxel doses (Gy)
    n    : LKB volume parameter
    """
    dose = np.clip(dose, 0.0, None)
    return np.mean(dose ** (1.0 / n)) ** n

def lkb_ntcp(dose, n_fx, model):
    """NTCP for one structure using the LKB model with EQD2 correction.
    dose  : voxel doses inside the OAR (total dose over all fractions, Gy)
    n_fx  : number of fractions
    model : NTCPModel
    Returns NTCP in [0, 1].
    """
    dose_eqd2 = eqd2(dose, n_fx, model.ab)
    g = geud(dose_eqd2, model.n)
    t = (g - model.td50) / (model.m * model.td50)
    return float(norm.cdf(t))

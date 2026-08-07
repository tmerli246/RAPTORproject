# Imports
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm

# Model definitions
@dataclass
class NTCPModel:
    """LKB parameters for one OAR/endpoint.
    name      : short identifier
    endpoint  : toxicity endpoint the parameters were fitted to
    n         : volume parameter (small n serial, large n parallel)
    m         : slope of the dose-response curve
    td50      : dose to 50% complication (Gy, EQD2, 2 Gy/fx reference)
    ab        : alpha/beta for the EQD2 correction (Gy)
    source    : literature reference for the parameters
    fitted_on : delineation, modality and fractionation the fit assumes.
                Every mismatch with our use is an assumption, so it is a field
                rather than a comment.
    """
    name: str
    endpoint: str
    n: float
    m: float
    td50: float
    ab: float
    source: str
    fitted_on: str = ""

# Example from Task 0
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
        name = "rectum_bleeding_g2",
        endpoint = "late rectal bleeding, grade >=2",
        n = 0.09, m = 0.13, td50 = 76.9, ab = 3.0,
        source = "Michalski et al., QUANTEC, IJROBP 2010",
        fitted_on = "solid rectum, photon, 1.8-2.0 Gy/fx",
    ),
    "bowel_placeholder": NTCPModel(
        name = "bowel_placeholder",
        endpoint = "GI toxicity (PLACEHOLDER, not validated for acute diarrhoea)",
        n = 0.09, m = 0.30, td50 = 59.0, ab = 3.0,
        source = "QUANTEC stomach bleeding fit, Kavanagh et al. IJROBP 2010 (placeholder)",
        fitted_on = "stomach, photon, conventional fractionation",
    ),
}

# Biological conversion
# The course is composed of blocks that may differ in dose per fraction, and
# the evaluator's accumulation ordering is: BED per block on its own geometry,
# deform, sum over blocks, convert the total to EQD2 once. BED is additive over
# segments because the LQ model is multiplicative in survival; EQD2 is not.

def bed(dose, n_fx, ab):
    """Biologically effective dose of one segment, voxel-wise.
    dose : total physical dose of the segment (Gy)
    n_fx : number of fractions in the segment
    ab   : alpha/beta (Gy)
    """
    dose = np.clip(dose, 0.0, None)
    d = dose / n_fx
    return dose * (1.0 + d / ab)

def eqd2_from_bed(bed_total, ab):
    """Convert an accumulated BED field to EQD2."""
    return np.asarray(bed_total) / (1.0 + 2.0 / ab)

def eqd2(dose, n_fx, ab):
    """EQD2 of a single uniform-fractionation course, voxel-wise.
    Convenience wrapper for the one-segment case; multi-block courses go
    through bed() and eqd2_from_bed().
    """
    return eqd2_from_bed(bed(dose, n_fx, ab), ab)

# Dose reduction
# The cache boundary is the DVH: TD50 and m enter only at the final evaluation,
# but the volume parameter n enters through the gEUD exponent, so a cached gEUD
# cannot be re-evaluated at a perturbed n while a cached DVH can.

def dvh(dose, bin_width = 0.1):
    """Differential DVH with equal-volume voxels.
    dose : voxel doses (Gy)
    Returns (edges, frac) where frac[i] is the volume fraction in
    [edges[i], edges[i+1]).
    """
    dose = np.clip(dose, 0.0, None)
    hi = max(float(dose.max()) + bin_width, bin_width)
    edges = np.arange(0.0, hi + bin_width, bin_width)
    counts, edges = np.histogram(dose, bins = edges)
    return edges, counts / dose.size

def geud(dose, n):
    """Generalized equivalent uniform dose from equal-volume voxel doses.
    dose : voxel doses (Gy)
    n    : LKB volume parameter
    """
    dose = np.clip(dose, 0.0, None)
    return np.mean(dose ** (1.0 / n)) ** n

def geud_from_dvh(edges, frac, n):
    """gEUD recomputed from a differential DVH at bin centres.
    Binning error is controlled by the bin width and verified against the
    voxel-wise route on the first real case (assumption E3).
    """
    centres = 0.5 * (edges[:-1] + edges[1:])
    return np.sum(frac * centres ** (1.0 / n)) ** n

# NTCP
# The probit step is separate from the dose reduction so that the Monte Carlo
# parameter propagation can loop over (td50, m) at a fixed gEUD, and over n at
# a fixed DVH, without touching any dose array.

def lkb_from_geud(g, td50, m):
    """LKB probit on a precomputed gEUD. Vectorized over parameters."""
    t = (g - td50) / (m * td50)
    return norm.cdf(t)

def lkb_ntcp(dose, n_fx, model):
    """NTCP for one structure using the LKB model with EQD2 correction.
    dose  : voxel doses inside the OAR (total dose over all fractions, Gy)
    n_fx  : number of fractions
    model : NTCPModel
    Returns NTCP in [0, 1].
    """
    dose_eqd2 = eqd2(dose, n_fx, model.ab)
    g = geud(dose_eqd2, model.n)
    return float(lkb_from_geud(g, model.td50, model.m))
"""Biological functions for the evaluator.

Pure functions only. Endpoint models and their parameters live in 
the registry, which is the single place a parameter is written down. 
"""

import numpy as np
from scipy.stats import norm

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
# a fixed DVH, without touching any dose array. [Uncertainty propagation]
def lkb_from_geud(g, td50, m):
    """LKB probit on a precomputed gEUD. Vectorized over parameters."""
    t = (g - td50) / (m * td50)
    return norm.cdf(t)
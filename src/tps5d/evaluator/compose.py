"""Dose composition: BED per block, warping, summation, EQD2, DVH, gEUD.

Evaluator design 4, 5 and 7.1 specify this machinery; this module turns the
specification into functions, evaluator design 11. It does **not**
reimplement the biological math: `evaluator/ntcp.py` already has `bed`,
`eqd2_from_bed` and `geud_from_cumulative_dvh`, confirmed by reading it
directly on 14 September 2026, and its own docstring states the reason not
to duplicate them, that a parameter changed in one copy and not the other
makes a result depend on which module was imported. This module's job is
narrower and is what `ntcp.py` explicitly does not do, by its own
docstring: OpenTPS-geometry-aware operations, warping a field, summing
fields on a shared grid, and constructing the DVH `ntcp.py` says it takes
as given rather than computing. Every array of actual biology, BED, EQD2,
gEUD, is computed by calling into `ntcp.py`, not by this module's own
arithmetic.

**Dose convention bridged, not changed.** `ntcp.bed(dose, n_fx, ab)` takes
`dose` as a segment's **total** physical dose. Extractor design 5 stores
dose **per fraction**. `compute_bed` below takes the extractor's native
per-fraction form, since that is what every caller actually has, and
multiplies by `n_fx` before calling `ntcp.bed`, which immediately divides
by `n_fx` again to recover the per-fraction value internally. The
round trip costs nothing numerically and changes nothing in `ntcp.py`;
it exists so this module's public signature matches what the extractor
produces without asking every caller to remember a second dose
convention.

Geometry-preserving throughout: every function that transforms an
Image3D-family object (DoseImage or a plain BED/EQD2 field of the same
family) uses that object's own `.copy()` rather than constructing a new one
by hand, since `.copy()` is what DoseImage, ROIMask and CTImage override to
preserve subclass type and deep-copy the array (extractor design 3.2, X1),
and the base Image3D.copy() does neither.
"""

import numpy as np

from opentps.core.data import DVH

from . import ntcp


def compute_bed(dose_per_fraction, n_fx: int, alpha_beta: float):
    """BED_b(x) via ntcp.bed, from the extractor's per-fraction dose.

    Parameters
    ----------
    dose_per_fraction : DoseImage
        On the block's own native geometry, per extractor design 5:
        conversion precedes deformation, never the reverse.
    n_fx : int
        This block's fraction count.
    alpha_beta : float
        Gy, for the ROI this BED field is being computed for. BED_b depends
        on it, so one field exists per (block, scheme, alpha/beta), per
        evaluator design 4.3.

    Returns
    -------
    Same type as `dose_per_fraction`, same geometry, BED values.
    """
    total_dose = dose_per_fraction.imageArray * n_fx
    bed_array = ntcp.bed(total_dose, n_fx, alpha_beta)

    result = dose_per_fraction.copy()
    result._imageArray = np.asarray(bed_array, dtype=np.float32)
    return result


def warp_bed(bed_field, dvf):
    """Apply an already-computed deformation field to a BED field.

    Takes `dvf` as given rather than calling extractor.adapters.get_dvf
    itself: registration is expensive and is performed once per image pair
    and cached (extractor design 6, evaluator design 4.3); applying a
    cached field to an array is cheap and is repeated once per (block,
    scheme, alpha/beta) combination. Keeping the two separate here is what
    makes evaluator design 4.3's "four applications, not four
    registrations" true in the code, not only in the design document.

    Parameters
    ----------
    bed_field : DoseImage-family object
        On the block's native geometry, as returned by compute_bed.
    dvf : Deformation3D
        fixed = pCT, moving = the block's repeat image, per extractor
        design 6.2 and X3. Already resampled onto the working grid, per
        extractor design 6.1: this function does not resample and does not
        check that it was done, since that is get_dvf's contract, not this
        function's.

    Returns
    -------
    Same type as `bed_field`, on `dvf`'s fixed grid.
    """
    return dvf.deformImage(bed_field)


def sum_bed(bed_fields: list):
    """Sum warped BED fields into one accumulated field, evaluator design 5.1.

    BED is additive over segments because the underlying model is
    multiplicative in survival (evaluator design 4.1); summation after
    deformation is therefore exact, not an approximation. All fields must
    already be on the same grid, since they were all warped onto the same
    fixed image by warp_bed; this is checked rather than assumed, the same
    discipline extractor design 5's union_bounding_box applies to masks.

    Parameters
    ----------
    bed_fields : list of DoseImage-family objects, same type, same grid.

    Returns
    -------
    Same type as the inputs, same grid, summed values.
    """
    if not bed_fields:
        raise ValueError("sum_bed: no fields given")

    ref = bed_fields[0]
    ref_shape = ref.imageArray.shape
    for f in bed_fields[1:]:
        if f.imageArray.shape != ref_shape:
            raise ValueError(
                f"sum_bed: fields do not share a grid: {ref_shape} vs "
                f"{f.imageArray.shape}. Every field must already be warped "
                f"onto the same fixed image by warp_bed before summation."
            )
        if not np.allclose(f.origin, ref.origin) or not np.allclose(f.spacing, ref.spacing):
            raise ValueError(
                "sum_bed: fields share a shape but not an origin or "
                "spacing: same grid_size does not imply same grid."
            )

    total = np.zeros(ref_shape, dtype=np.float32)
    for f in bed_fields:
        total += f.imageArray

    result = ref.copy()
    result._imageArray = total
    return result


def bed_to_eqd2(bed_total, alpha_beta: float):
    """EQD2(x) via ntcp.eqd2_from_bed, applied once to the summed field.

    Applied to the summed field, never per block: converting before
    summation would be the ordering evaluator design 4.1 rejects, since the
    conversion is nonlinear and does not commute with the deformation
    already applied to each block. This function does not know or check
    that its input has already been summed; get that ordering right by
    construction of the call sequence, not by a check here that could
    itself be fooled by a single-block edge case.

    Returns
    -------
    Same type as `bed_total`, same geometry, EQD2 values.
    """
    eqd2_array = ntcp.eqd2_from_bed(bed_total.imageArray, alpha_beta)

    result = bed_total.copy()
    result._imageArray = np.asarray(eqd2_array, dtype=np.float32)
    return result


def reduce_to_dvh(eqd2_field, roi_mask, *, max_dvh: float = None):
    """DVH of an accumulated EQD2 field over one ROI, evaluator design 7.1's cache boundary.

    ntcp.py's own docstring states it takes the DVH as given rather than
    computing one: this function is that supplier.

    `max_dvh`, when not given, is set from the field's own maximum with a
    5% margin, never left at DVH.computeDVH's 100 Gy absolute default:
    evaluator design 7.2, verified 11 September 2026, that default would
    silently truncate accumulated EQD2 in hypofractionated schedules at low
    alpha/beta, exactly the field this function is built to reduce. At 4096
    bins even a wide margin keeps the bin width near 0.05 Gy on a 200 Gy
    axis, so the margin costs nothing in resolution.

    Parameters
    ----------
    eqd2_field : DoseImage-family object
        Accumulated, as returned by bed_to_eqd2.
    roi_mask : ROIMask
    max_dvh : float, Gy, optional
        Explicit override. Passed through unchanged if given: extractor
        design 3.4's rule against defaults applies to the caller's own
        choice here too, this function does not second-guess an explicit
        value against the field's actual maximum.

    Returns
    -------
    DVH, no prescription set: this DVH is on EQD2, where a percentage of
    prescription is not a meaningful quantity (extractor design 7's scope
    note makes the same point for the extractor's own DVH use). Metrics
    read off it, D98/D95/Dmean directly, gEUD via geud_from_dvh below.
    """
    if max_dvh is None:
        max_dvh = float(eqd2_field.imageArray.max()) * 1.05

    dvh = DVH(roi_mask, eqd2_field)
    dvh.computeDVH(maxDVH=max_dvh)
    return dvh


def geud_from_dvh(dvh, n: float) -> float:
    """gEUD via ntcp.geud_from_cumulative_dvh, from a DVH's own histogram.

    `n` is the LKB volume parameter, matching ntcp.py's and registry.py's
    own convention (Model.params['n'] for the 'lkb' kind) rather than the
    `a = 1/n` this function took in an earlier draft: that was a second,
    unnecessary convention invented before ntcp.py had been read, and is
    removed rather than kept alongside the established one.

    This is a thin unpack-and-delegate: `dvh.histogram` returns exactly the
    (dose_bins, cumulative_volume_pct) pair ntcp.geud_from_cumulative_dvh
    expects, confirmed by reading both sides on 14 September 2026, so there
    is no conversion left to do here, only the call.

    Returns
    -------
    float, Gy.
    """
    dose_bins, cum_volume_pct = dvh.histogram
    return ntcp.geud_from_cumulative_dvh(dose_bins, cum_volume_pct, n)

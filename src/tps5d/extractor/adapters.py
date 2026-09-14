"""The only module that imports opentps (X1, extractor design 3.2).

Every function is free-standing: settings are passed in on every call and
nothing is read back from an OpenTPS object after construction, since that
object can rewrite its own attributes (RegistrationMorphons.nbProcesses is
the case in point, X2). This is the reason functions were chosen over a
stateful adapter class: a class would reproduce, in this module, the exact
failure mode X2 exists to describe.

Nothing here is called with its defaults (extractor design 3.4): every
OpenTPS entry point with a default that changes a result gets that argument
supplied explicitly, and the value supplied is what the caller records for
provenance, not what the object happens to hold afterwards.
"""

import numpy as np

from opentps.core.data import DVH
from opentps.core.data.images import Deformation3D
from opentps.core.processing.registration.registrationMorphons import RegistrationMorphons

from .records import DIRSettings, WorkingGrid, CropBounds


# Binarisation threshold for ROIContour.get_partial_volume_mask, X10. The
# deprecated getBinaryMask hardcoded 0.5 internally; get_partial_volume_mask's
# own default is None, which returns a float partial-volume array rather than
# the bool the storage schema requires (extractor design 5). 0.5 is adopted
# explicitly, matching the deprecated wrapper's behaviour, rather than left to
# whatever the next OpenTPS release decides.
#
# Applies only when get_partial_volume_mask is present. Confirmed on 12
# September 2026, against the project's own OpenTPS checkout, that an older
# getBinaryMask also exists with no threshold or precision concept at all: a
# hard polygon fill, boolean by construction. The two are not numerically
# equivalent: ~35% difference in measured volume on an identical synthetic
# contour. extract_roi_mask raises rather than silently ignoring these two
# parameters if the environment falls back to that older implementation.
ROI_BINARIZATION_THRESHOLD = 0.5

# Supersampling factor for the same call. OpenTPS's own default; passed
# explicitly per extractor 3.4 rather than relied upon.
ROI_RASTER_PRECISION = 16


# ---------------------------------------------------------------------------
# Registration (extractor design 6)
# ---------------------------------------------------------------------------

def get_dvf(*, moving, fixed, settings: DIRSettings, working_spacing):
    """Deformation field from `moving` onto `fixed`'s grid.

    Keyword-only by construction (extractor design 6.1): RegistrationMorphons
    takes (fixed, moving) in the opposite order, both positional and both the
    same type, so a transposition would not raise, it would return a
    plausible field in the wrong direction. Keyword-only arguments make that
    transposition unexpressible rather than merely unlikely.

    fixed = pCT, moving = rCT_j is the project convention (X3): the required
    output is on the pCT grid, and deformImage(moving) returns an image on
    the fixed grid, which is why pCT must be fixed. Verifying this is the
    caller's responsibility, exercised by the ground-truth test in
    test_adapters.py, not this function's: get_dvf takes fixed and moving as
    given and does not know which anatomy either represents.

    settings.backend selects the implementation:
      'morphons'  computed here, via RegistrationMorphons
      'imported'  a stub (X2). Raises NotImplementedError until the export
                  conventions are known

    The field this returns is NOT yet on `working_spacing`: Morphons' own
    grid is bounded by two floors, base_resolution and the fixed image's
    grid, and is generally coarser than either (extractor design 6.1). This
    function resamples explicitly onto working_spacing before returning, so
    that no caller relies on deformImage's own silent resample (Deformation3D
    logs "Image and field dimensions do not match" and proceeds regardless,
    which is exactly the implicit behaviour extractor 3.4 rules out).

    Parameters
    ----------
    moving, fixed : Image3D
    settings : DIRSettings
    working_spacing : tuple of 3 floats, mm
        The grid the returned field must be resampled onto.

    Returns
    -------
    Deformation3D, on `fixed`'s grid at `working_spacing`.
    """
    if settings.backend == 'imported':
        raise NotImplementedError(
            "imported DVF backend is a stub pending known RayStation export "
            "conventions (X2, X7)")

    reg = RegistrationMorphons(
        fixed, moving,
        baseResolution=settings.base_resolution,
        nbProcesses=settings.n_processes,
        tryGPU=settings.try_gpu,
    )
    field = reg.compute()

    # Deformation3D.resample mutates in place and returns None, confirmed
    # against the installed environment on 11 September 2026; it does not
    # return a new object. Calling it as `field = field.resample(...)` would
    # silently discard the field. This is exactly the class of behaviour
    # extractor 3.4 warns about: taken on trust, it fails without raising.
    field.resample(
        spacing=working_spacing,
        gridSize=fixed.gridSize,
        origin=fixed.origin,
    )
    return field


# ---------------------------------------------------------------------------
# Target metrics (extractor design 7)
# ---------------------------------------------------------------------------

def target_metrics(dose, roi_mask, *, n_fx: int, rx_dose_gy: float):
    """Coverage metrics for one plan on one image, course dose against
    course prescription.

    dose is the stored per-fraction physical dose (extractor design 5); this
    function multiplies by n_fx before building the DVH, since DVH.computeVx
    takes its threshold as a percentage of the prescription passed to the
    constructor, and comparing a per-fraction dose to a course prescription
    would put every plan at a few percent and return v95 = 0.0 for the whole
    cohort, silently (extractor design 7).

    maxDVH is set from the accumulated field's own maximum plus margin,
    never left at DVH.computeDVH's 100.0 Gy default: that default truncates
    at 100 Gy absolute, which physical per-fraction dose never reaches, so
    it is safe here specifically. It is not safe for the evaluator's DVH on
    accumulated EQD2, which does cross 100 Gy at prescription level in
    hypofractionated schedules (evaluator design 7.2, E10); this function
    does not compute that DVH and the caller must not reuse this default for
    it.

    Parameters
    ----------
    dose : DoseImage
        Physical dose per fraction, on the ROI's grid.
    roi_mask : ROIMask
        The target ROI, same grid as `dose`.
    n_fx : int
        Fraction count of this plan's scheme.
    rx_dose_gy : float
        Course prescription for this plan's scheme.

    Returns
    -------
    TargetMetrics
    """
    from .records import TargetMetrics

    course_dose = dose.copy()
    course_dose._imageArray = course_dose._imageArray * n_fx

    # maxDVH must cover two things, not one. It must exceed the actual dose
    # maximum, or a hot plan is truncated exactly as DVH.computeDVH's own
    # 100 Gy default would truncate it (extractor 3.4). And it must reach at
    # least the prescription, or a cold plan's dose-percentage axis never
    # reaches the 95% query point: DVH.computeVx then calls np.searchsorted
    # past the end of the array and raises IndexError instead of returning
    # 0.0. This second failure was found by running this function against a
    # cold plan on 11 September 2026, after fixing the first: setting
    # maxDVH from the observed maximum alone, with no floor at the
    # prescription, silently reintroduces the same class of bug it was
    # written to close, on the opposite tail.
    max_dvh = max(float(course_dose.imageArray.max()), rx_dose_gy) * 1.05

    dvh = DVH(roi_mask, course_dose, prescription=rx_dose_gy)
    dvh.computeDVH(maxDVH=max_dvh)

    v95 = dvh.computeVx(95.0)

    return TargetMetrics(
        v95_pct=v95,
        d98_gy=dvh.D98,
        d95_gy=dvh.D95,
        dmean_gy=dvh.Dmean,
        dmax_gy=dvh.Dmax,
    )


# ---------------------------------------------------------------------------
# ROI masks (extractor design 3.1, 5, 9)
# ---------------------------------------------------------------------------

def _contour_physical_bounds(contour):
    """Min/max physical (x, y, z), mm, spanned by a contour's polygon vertices.

    Reads polygonMesh directly, in the same flat [x0,y0,z0, x1,y1,z1, ...]
    layout ROIContour.get_partial_volume_mask itself parses.
    """
    xs, ys, zs = [], [], []
    for poly in contour.polygonMesh:
        coords = np.asarray(poly, dtype=float)
        xs.append(coords[0::3])
        ys.append(coords[1::3])
        zs.append(coords[2::3])
    xs, ys, zs = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
    return ((float(xs.min()), float(ys.min()), float(zs.min())),
            (float(xs.max()), float(ys.max()), float(zs.max())))


def roi_mask_algorithm() -> str:
    """Which OpenTPS ROI-rasterisation method extract_roi_mask uses in this
    environment: 'get_partial_volume_mask' or 'getBinaryMask'.

    Not a per-call choice: a fact about the installed OpenTPS, fixed for as
    long as the environment is. The two are not numerically equivalent,
    confirmed on 12 September 2026 by rasterising an identical synthetic
    cylinder both ways: ~35% difference in measured volume. This is exactly
    the kind of fact the provenance table of extractor 13.1 must record as
    a mask's `source` once that table exists; there is nowhere else to put
    it until then, so a caller building provenance manually should call
    this and record the result now.
    """
    from opentps.core.data._roiContour import ROIContour
    if hasattr(ROIContour, 'get_partial_volume_mask'):
        return 'get_partial_volume_mask'
    return 'getBinaryMask'


def extract_roi_mask(rtstruct, dicom_name: str, *, grid: WorkingGrid,
                     binarization_threshold: float = ROI_BINARIZATION_THRESHOLD,
                     precision: int = ROI_RASTER_PRECISION):
    """Binary mask for one structure, on an explicit working grid.

    `dicom_name` is the literal name as it appears in the RTSTRUCT. This
    function does no name matching: resolving a TG-263 canonical name to
    this literal name is the mapping file's job (extractor design 9), kept
    separate so that no fuzzy-matching logic can end up here by accident.

    RTStruct.getContourByName does not raise when the name is absent: it
    prints a message to stdout and returns None (read from the OpenTPS
    source on 11 September 2026). Chaining straight into a mask call on
    that None would raise an AttributeError two calls away from the actual
    problem. This function raises KeyError immediately instead, with the
    available names attached, which is what extractor design 9's "an
    unmapped structure raises" means concretely.

    **Two OpenTPS implementations exist across the environments this
    project runs in, and neither signals a grid mismatch safely.**
    `get_partial_volume_mask`, present in the public OpenTPS 3.0.1, logs
    rather than raises when the working grid does not contain the
    contour's bounding box, and that internal logging call is itself
    malformed and raises TypeError under some logging configurations
    rather than printing, confirmed under pytest's own capture on 11
    September 2026. `getBinaryMask`, the implementation confirmed present
    in the project's own OpenTPS checkout on 12 September 2026, gives no
    signal at all: it resamples onto the requested grid with `fillValue=0`
    and silently truncates whatever falls outside it. This function
    therefore checks physical containment itself, from the contour's own
    `polygonMesh`, before calling into OpenTPS at all, regardless of which
    backend `roi_mask_algorithm()` selects.

    **Which backend runs is detected via `roi_mask_algorithm()`, not
    assumed.** `get_partial_volume_mask` is called when present, with
    `binarization_threshold` and `precision` explicit per extractor 3.4,
    since the method's own default for the threshold is `None` and returns
    a float array rather than the bool the schema requires. Where it is
    absent, `getBinaryMask` is called instead: confirmed by reading its
    source to be a hard polygon fill with no threshold or precision
    concept whatsoever, boolean by construction, and empirically confirmed
    on 12 September 2026 to honour the requested origin, spacing and
    gridSize exactly. Because the two are not numerically equivalent, a
    caller who has overridden `binarization_threshold` or `precision` away
    from their defaults gets a raised error rather than a silently ignored
    argument if the environment falls back to `getBinaryMask`.

    `getBinaryMask` also has its own silent-failure edge case, found by
    reading its source: a contour on a single z-slice makes it return
    `imageArray=None` rather than raising. Checked for explicitly below.

    Returns
    -------
    ROIMask, on `grid`.
    """
    contour = rtstruct.getContourByName(dicom_name)
    if contour is None:
        available = sorted(c.name for c in rtstruct.contours)
        raise KeyError(
            f"no contour named {dicom_name!r} in this RTSTRUCT. "
            f"getContourByName does not raise on a miss (it prints and "
            f"returns None); this wrapper raises instead, per extractor "
            f"design 9. Available names: {available}"
        )

    lo_phys, hi_phys = _contour_physical_bounds(contour)
    grid_lo = np.asarray(grid.origin, dtype=float)
    grid_hi = grid_lo + (np.asarray(grid.grid_size, dtype=float) - 1) * np.asarray(grid.spacing, dtype=float)
    tol = 1e-6
    if np.any(np.asarray(lo_phys) < grid_lo - tol) or np.any(np.asarray(hi_phys) > grid_hi + tol):
        raise ValueError(
            f"working grid does not contain the physical extent of "
            f"{dicom_name!r}: contour spans {lo_phys} to {hi_phys} mm, "
            f"grid covers {tuple(grid_lo)} to {tuple(grid_hi)} mm. "
            f"Neither OpenTPS backend signals this safely on its own "
            f"(verified 11 and 12 September 2026); this check runs first "
            f"rather than trusting either."
        )

    algo = roi_mask_algorithm()

    if algo == 'getBinaryMask':
        if (binarization_threshold != ROI_BINARIZATION_THRESHOLD
                or precision != ROI_RASTER_PRECISION):
            raise ValueError(
                f"this environment's OpenTPS has no get_partial_volume_mask "
                f"(confirmed 12 September 2026 against the project's own "
                f"checkout), so extract_roi_mask falls back to "
                f"getBinaryMask, a hard polygon fill with no threshold or "
                f"precision concept at all. binarization_threshold="
                f"{binarization_threshold} and precision={precision} would "
                f"be silently ignored rather than honoured; raising instead "
                f"of doing that."
            )
        mask = contour.getBinaryMask(
            origin=grid.origin,
            gridSize=grid.grid_size,
            spacing=grid.spacing,
        )
        if mask.imageArray is None:
            raise ValueError(
                f"getBinaryMask returned an empty mask for {dicom_name!r}: "
                f"this OpenTPS implementation returns imageArray=None, "
                f"rather than raising, for a contour on a single z-slice "
                f"(confirmed against the source on 12 September 2026)."
            )
        return mask

    return contour.get_partial_volume_mask(
        origin=grid.origin,
        gridSize=grid.grid_size,
        spacing=grid.spacing,
        precision=precision,
        binarization_threshold=binarization_threshold,
    )


def roi_volume_cc(mask) -> float:
    """ROI volume in cm^3 (cc).

    ROIMask.getVolume(inVoxels=False) returns mm^3 despite the name giving
    no hint of it: confirmed against the installed source on 11 September
    2026, where the docstring says "otherwise in mm^3" and nothing at the
    call site does. cc is the unit extractor design's schema uses
    (target_vol_cc) and the unit every organ volume in this project is
    otherwise reported in. This wrapper is the one place the factor of
    1000 is applied, so no call site has to remember it, and no call site
    can silently forget it either.
    """
    return mask.getVolume(inVoxels=False) / 1000.0





# ---------------------------------------------------------------------------
# Crop to the union bounding box (extractor design 5, X4)
# ---------------------------------------------------------------------------

def union_bounding_box(masks, *, margin_vox: int = 0) -> CropBounds:
    """Index bounds of the union of one or more ROIMask arrays.

    extractor design 5, X4: the crop is the bounding box of all contoured
    structures plus the target, wider than the union any single active
    NTCP model requires, so that an endpoint added later costs a mapping
    line rather than a re-extraction. This function computes that box from
    whatever mask list it is given; which ROIs belong in that list is
    decided by the caller, not here.

    All masks must share a grid (shape, origin, spacing): this is checked,
    not assumed, since a silent mismatch here would crop to the wrong
    physical region without any symptom until metrics come out wrong.

    Returns
    -------
    CropBounds, inclusive per axis, clamped to the array's own bounds after
    the margin is applied.
    """
    if not masks:
        raise ValueError("union_bounding_box: no masks given")

    ref = masks[0]
    shape = ref.imageArray.shape
    for m in masks[1:]:
        if m.imageArray.shape != shape:
            raise ValueError(
                f"masks do not share a grid: {shape} vs {m.imageArray.shape}. "
                f"extract_roi_mask must be called with the same `grid` for "
                f"every ROI before their union is taken."
            )
        if not np.allclose(m.origin, ref.origin) or not np.allclose(m.spacing, ref.spacing):
            raise ValueError(
                "masks share a shape but not an origin or spacing: same "
                "grid_size does not imply same grid."
            )

    union = np.zeros(shape, dtype=bool)
    for m in masks:
        union |= (np.asarray(m.imageArray) > 0)

    if not union.any():
        raise ValueError("union_bounding_box: union mask is empty; no "
                         "contoured voxel in any mask given")

    lo, hi = [], []
    for axis in range(3):
        other_axes = tuple(a for a in range(3) if a != axis)
        projected = np.any(union, axis=other_axes)
        idx = np.nonzero(projected)[0]
        lo.append(max(0, int(idx[0]) - margin_vox))
        hi.append(min(shape[axis] - 1, int(idx[-1]) + margin_vox))

    return CropBounds(lo=tuple(lo), hi=tuple(hi))


def crop_to_bounds(image, bounds: CropBounds):
    """Crop an Image3D-family object (DoseImage, ROIMask, CTImage, ...) to
    `bounds`, adjusting origin so every remaining voxel's physical location
    is unchanged.

    Returns a new object of the same type via `.copy()`, which DoseImage,
    ROIMask and CTImage all override to preserve type and deep-copy the
    array (verified against the installed environment on 11 September
    2026; the Image3D base class's own copy() does neither: it returns a
    plain Image3D regardless of the subclass called on. Relying on that
    base behaviour instead of each subclass's override would silently
    demote a DoseImage to an Image3D, losing referencePlan and referenceCT,
    which is a case for calling `.copy()` rather than constructing the
    array slice directly and skipping it: the override is what keeps the
    field's identity attached to the crop).
    """
    lo, hi = bounds.lo, bounds.hi
    array = image.imageArray[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1]

    cropped = image.copy()
    cropped._imageArray = array
    cropped.origin = tuple(
        image.origin[a] + lo[a] * image.spacing[a] for a in range(3)
    )
    return cropped


# ---------------------------------------------------------------------------
# Plan complexity (extractor design 8)
# ---------------------------------------------------------------------------

def extract_plan_complexity(plan):
    """Delivery-time descriptors read directly from a plan object.

    Dispatches on isinstance(plan, ProtonPlan) / isinstance(plan, PhotonPlan)
    rather than on any modality label the caller might supply separately, so
    that a plan mislabelled upstream (extractor design 4, the export
    manifest) cannot silently produce the wrong kind of count: a mismatch
    between what the manifest claims and what the plan object actually is
    raises TypeError here rather than returning zeros for fields the wrong
    branch never populates.

    n_fields is len(plan.beams) in both branches below: RTPlan.beams is
    defined once, on the shared base class both ProtonPlan and PhotonPlan
    inherit from (confirmed against the installed source on 11 September
    2026), so the expression is identical either way. It is computed
    inside each branch rather than once before the dispatch, so that an
    object of neither type reaches the TypeError below instead of failing
    on a missing `.beams` attribute first; an earlier version of this
    function got that ordering wrong and was caught by its own test.

    Proton n_layers is summed here from len(beam.layers) per beam, since
    ProtonPlan itself has no plan-level layer count property: only
    numberOfSpots and meterset are aggregated at the plan level in the
    installed OpenTPS. n_spots and mu use those plan-level aggregates
    directly rather than re-summing over beams a second time.

    target_vol_cc is deliberately left at its 0.0 default. It comes from
    the target ROI mask, not from the plan, and this function only reads
    what the RTPlan object itself carries. The caller composes it in
    separately from roi_volume_cc on the target mask (extractor design 5):
    coupling this function to an RTStruct would mix two independent inputs
    for a field neither needs the other to produce.

    Returns
    -------
    PlanComplexity
    """
    from opentps.core.data.plan import ProtonPlan, PhotonPlan
    from .records import PlanComplexity

    if isinstance(plan, ProtonPlan):
        n_fields = len(plan.beams)
        return PlanComplexity(
            modality='pt',
            n_fields=n_fields,
            n_layers=int(sum(len(beam.layers) for beam in plan.beams)),
            n_spots=int(plan.numberOfSpots),
            mu=float(plan.meterset),
        )

    if isinstance(plan, PhotonPlan):
        n_fields = len(plan.beams)
        return PlanComplexity(
            modality='xt',
            n_fields=n_fields,
            n_segments=int(plan.numberOfSegments),
            mu=float(plan.cumulativeMeterset),
        )

    raise TypeError(
        f"extract_plan_complexity: plan is {type(plan).__name__}, neither "
        f"ProtonPlan nor PhotonPlan. Extractor design 8 covers only these "
        f"two modalities; a plan of another type must be handled "
        f"explicitly here rather than silently returning zeros for both."
    )


# ---------------------------------------------------------------------------
# ROI mask by canonical name (extractor design 9)
# ---------------------------------------------------------------------------

def extract_roi_mask_by_canonical_name(rtstruct, canonical_name: str, *,
                                       mapping, grid: WorkingGrid,
                                       binarization_threshold: float = ROI_BINARIZATION_THRESHOLD,
                                       precision: int = ROI_RASTER_PRECISION):
    """extract_roi_mask, preceded by TG-263 resolution.

    A thin composition, not a new mechanism: resolve_dicom_name (roi_mapping.py)
    turns `canonical_name` into the literal name this specific rtstruct
    carries, and extract_roi_mask does everything else, containment check,
    backend dispatch, the single-slice guard, unchanged. Kept separate from
    extract_roi_mask itself so that function's contract stays "a literal
    DICOM name in, a mask out" with no name-matching logic anywhere near it,
    per extractor design 9's prohibition on fuzzy matching creeping in.

    Parameters
    ----------
    mapping : roi_mapping.RoiMapping
        Loaded via roi_mapping.load_roi_mapping.

    Returns
    -------
    ROIMask, on `grid`.
    """
    from .roi_mapping import resolve_dicom_name

    dicom_name = resolve_dicom_name(rtstruct, canonical_name, mapping)
    return extract_roi_mask(rtstruct, dicom_name, grid=grid,
                            binarization_threshold=binarization_threshold,
                            precision=precision)

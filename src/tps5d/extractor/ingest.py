"""DICOM ingest: extractor design 3.1's `io.dicomIO` entries, wrapped.

**Every OpenTPS `readDicomXxx` function reads DICOM files that may not
match what it expects, and every one of them has a way of saying so that
is not raising.** Read from `opentps.core.io.dicomIO` [OpenTPS source]:
`readDicomDose` and `readDicomStruct` return `None` on an unrecognised
pixel format or a missing `SeriesInstanceUID`; `readDicomPlan` does the
same on five separate branches, unsupported radiation type, scan mode
other than `'MODULATED'`, or an unrecognised `SOPClassUID`. A caller
that does not check for `None` gets a confusing `AttributeError` several
calls downstream, on whatever first touches the missing object, rather
than a clear signal at the point the file failed to parse. Every function
in this module checks for `None` and raises immediately, naming the file
and, where the source makes it identifiable, the reason.

`readDicomCT` has no such branch; it has a different failure mode instead,
below.
"""

import hashlib

import numpy as np
import pydicom

from opentps.core.io.dicomIO import readDicomCT, readDicomDose, readDicomStruct, readDicomPlan

from .provenance import ProvenanceRecord
from .records import DoseHeader

# Tolerance on slice positions, mm: the spacing OpenTPS assigns must agree with
# the positions in the headers, and the positions must be evenly spaced.
Z_TOL_MM = 0.01


def ingest_ct(dcm_files: list):
    """A CT series from a list of per-slice DICOM file paths.

    `readDicomCT` derives the z-spacing as `(last - first) / (n - 1)` over
    the given slices' `ImagePositionPatient` [OpenTPS source]. With one
    file this is `0/0`:
    not an exception, a `NaN` spacing that silently corrupts every
    downstream geometry calculation that touches it. With zero files the
    same source indexes `sliceLocation[-1]` on an empty array, `IndexError`
    with no indication of what was actually wrong. Both are checked here,
    before the call, with a clear message; a single-slice image is a real
    DICOM object in principle but is not one this pipeline's spacing
    assumptions can be built on, so it is rejected rather than silently
    producing `NaN`.

    Parameters
    ----------
    dcm_files : list of str
        Per-slice file paths. Order does not matter: `readDicomCT` sorts
        by `ImagePositionPatient`, not by list order.

    Returns
    -------
    CTImage
    """
    if not dcm_files:
        raise ValueError("ingest_ct: no files given")
    if len(dcm_files) < 2:
        raise ValueError(
            f"ingest_ct: {len(dcm_files)} file(s) given, need at least 2. "
            f"readDicomCT computes z-spacing as (last - first) / (n - 1) "
            f"over the slices given; with one file this is 0/0, a NaN "
            f"spacing rather than a raised error (OpenTPS source)."
        )
    image = readDicomCT(dcm_files)

    # readDicomCT takes the slice spacing from SpacingBetweenSlices or
    # SliceThickness when either is present, and from the positions only when
    # both are absent. A series with overlapping or gapped slices, or a missing
    # slice, then loads with a wrong z-spacing and no error. The positions in
    # the headers are the reference.
    z = np.sort([float(pydicom.dcmread(f, stop_before_pixels = True).ImagePositionPatient[2])
                 for f in dcm_files])
    steps = np.diff(z)
    if np.ptp(steps) > Z_TOL_MM:
        raise ValueError(
            f"ingest_ct: slice positions are not evenly spaced (steps from "
            f"{steps.min():.3f} to {steps.max():.3f} mm): a missing or "
            f"duplicated slice, or a non-uniform reconstruction."
        )
    if abs(float(image.spacing[2]) - float(steps.mean())) > Z_TOL_MM:
        raise ValueError(
            f"ingest_ct: z-spacing read as {float(image.spacing[2]):.3f} mm "
            f"but the slice positions give {float(steps.mean()):.3f} mm "
            f"(SliceThickness differs from the slice interval)."
        )
    return image


def read_dose_header(path: str) -> DoseHeader:
    """The tags of an RTDOSE file that fix what its array means, read with pydicom.

    OpenTPS fills defaults for absent tags in its own object (`PLAN`, `GY`,
    `EFFECTIVE`), so the object cannot tell an absent tag from a present one.
    Callers record this header in the provenance table (`dose_header_record`).
    """
    ds = pydicom.dcmread(path, stop_before_pixels = True)
    offsets = getattr(ds, 'GridFrameOffsetVector', None)
    if offsets is None:
        frame_offsets = 'absent'
    elif len(offsets) < 2:
        frame_offsets = 'single'
    else:
        steps = np.diff([float(v) for v in offsets])
        frame_offsets = 'increasing' if np.all(steps > 0) else 'decreasing' if np.all(steps < 0) else 'irregular'
    scaling = getattr(ds, 'DoseGridScaling', None)
    return DoseHeader(
        summation_type = getattr(ds, 'DoseSummationType', None),
        units = getattr(ds, 'DoseUnits', None),
        dose_type = getattr(ds, 'DoseType', None),
        grid_scaling = None if scaling is None else float(scaling),
        frame_offsets = frame_offsets,
    )


def dose_header_record(key: str, header: DoseHeader, n_fx_divided: int = None) -> ProvenanceRecord:
    """The provenance record of a dose file's header tags (extractor design 12.2).

    `key` is the caller's, for instance 'dose:pt12/b1/PT-A/std/planned/header'.
    """
    text = header.describe(n_fx_divided)
    return ProvenanceRecord(key = key, kind = 'measured', source = text,
                            content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16])


def ingest_dose(path: str, *, n_fx: int = None):
    """A dose distribution from one RTDOSE file, as physical dose per fraction.

    The store holds dose per fraction (extractor design 5). RayStation is
    expected to export a beam set dose for the whole plan, tagged
    `DoseSummationType = PLAN`; the array is then divided by `n_fx`, the
    fraction count of the schedule the file belongs to, and the object's
    `doseSummationType` is set to `FRACTION`. A file tagged `FRACTION` is
    left as it is. Whether the exporter does write `PLAN` is closed by the
    first export (extractor 14, X9); `read_dose_header` and
    `dose_header_record` give the tags for the provenance table.

    Raises before reading the array if
    - `DoseSummationType` or `DoseUnits` is absent, or `DoseGridScaling` is;
    - `DoseUnits` is not `GY`, which has no absolute scale otherwise;
    - `DoseSummationType` is neither `PLAN` nor `FRACTION` (BEAM,
      MULTI_PLAN, FRACTION_SESSION, ...): what such a file covers is not
      known to this function;
    - `DoseSummationType` is `PLAN` and `n_fx` is not given;
    - `GridFrameOffsetVector` decreases: for that case OpenTPS 3.0.1 flips
      the array but places the origin one slice thickness off.
    Raises if `readDicomDose` returns `None`, which it does when
    `BitsStored`/`PixelRepresentation` is not one of the four combinations
    it recognises (16 or 32 bit, signed or unsigned).

    `DoseType` is recorded and not checked: RBE-weighted proton dose may be
    labelled `EFFECTIVE`, and the convention is registered as X9.

    Returns
    -------
    DoseImage, `.referencePlan` set to the SOP instance UID of the RTPLAN
    the dose references, read from `ReferencedRTPlanSequence`.
    """
    header = read_dose_header(path)
    for name, value in (('DoseSummationType', header.summation_type),
                        ('DoseUnits', header.units),
                        ('DoseGridScaling', header.grid_scaling)):
        if value is None:
            raise ValueError(f"ingest_dose: {path!r} has no {name}. The reader would "
                             f"fill a default, which hides what the array means.")
    if header.units != 'GY':
        raise ValueError(f"ingest_dose: DoseUnits is {header.units!r} in {path!r}; "
                         f"only GY has an absolute scale.")
    if header.summation_type not in ('PLAN', 'FRACTION'):
        raise ValueError(
            f"ingest_dose: DoseSummationType is {header.summation_type!r} in {path!r}. "
            f"Only PLAN (divided by n_fx) and FRACTION are understood; what this file "
            f"covers has to be established from the export first."
        )
    if header.summation_type == 'PLAN' and not n_fx:
        raise ValueError(f"ingest_dose: {path!r} is a PLAN dose and needs the fraction "
                         f"count of its schedule (n_fx) to become dose per fraction.")
    if header.frame_offsets in ('decreasing', 'irregular'):
        raise ValueError(f"ingest_dose: GridFrameOffsetVector of {path!r} is "
                         f"{header.frame_offsets}; OpenTPS 3.0.1 misplaces the dose in "
                         f"z for that case. Extractor 14 has the item.")

    image = readDicomDose(path)
    if image is None:
        raise ValueError(
            f"ingest_dose: readDicomDose returned None for {path!r}. "
            f"Unsupported pixel data type: BitsStored/PixelRepresentation "
            f"is not one of 16-bit unsigned, 16-bit signed, 32-bit "
            f"unsigned or 32-bit signed, the four readDicomDose accepts."
        )
    if header.summation_type == 'PLAN':
        image.imageArray = (image.imageArray / n_fx).astype(np.float32)
        image.doseSummationType = 'FRACTION'
    return image


def ingest_struct(path: str):
    """A structure set from one RTSTRUCT file.

    Raises if `readDicomStruct` returns `None`, which it does when the
    file has no `SeriesInstanceUID` [OpenTPS source].

    Returns
    -------
    RTStruct
    """
    struct = readDicomStruct(path)
    if struct is None:
        raise ValueError(
            f"ingest_struct: readDicomStruct returned None for {path!r}: "
            f"the file has no SeriesInstanceUID."
        )
    return struct


def ingest_plan(path: str):
    """A treatment plan from one RTPLAN file.

    Raises if `readDicomPlan` returns `None`, which it does on five
    separate branches [OpenTPS source]: an unsupported photon or ion
    radiation type, a proton
    scan mode other than `'MODULATED'`, an unsupported ion scan mode, or
    an `SOPClassUID` it does not recognise at all. Which of the five fired
    is not distinguishable from the return value alone; the message says
    so rather than guessing.

    Returns
    -------
    RTPlan (ProtonPlan or PhotonPlan)
    """
    plan = readDicomPlan(path)
    if plan is None:
        raise ValueError(
            f"ingest_plan: readDicomPlan returned None for {path!r}. One "
            f"of five unsupported-configuration branches fired: radiation "
            f"type, scan mode (proton requires 'MODULATED'), or SOPClassUID "
            f"not recognised. Which one is not distinguishable from the "
            f"return value; check the file's RadiationType, ScanMode and "
            f"SOPClassUID tags directly."
        )
    return plan

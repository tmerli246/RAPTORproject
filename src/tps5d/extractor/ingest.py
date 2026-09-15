"""DICOM ingest: extractor design 3.1's `io.dicomIO` entries, wrapped.

**Every OpenTPS `readDicomXxx` function reads DICOM files that may not
match what it expects, and every one of them has a way of saying so that
is not raising.** Confirmed by reading `opentps.core.io.dicomIO` directly
on 15 September 2026, not assumed from one function's behaviour applied to
the rest: `readDicomDose` and `readDicomStruct` return `None` on an
unrecognised pixel format or a missing `SeriesInstanceUID`; `readDicomPlan`
does the same on five separate branches, unsupported radiation type, scan
mode other than `'MODULATED'`, or an unrecognised `SOPClassUID`. A caller
that does not check for `None` gets a confusing `AttributeError` several
calls downstream, on whatever first touches the missing object, rather
than a clear signal at the point the file failed to parse. Every function
in this module checks for `None` and raises immediately, naming the file
and, where the source makes it identifiable, the reason.

`readDicomCT` has no such branch, confirmed by the same read; it has a
different failure mode instead, below.
"""

from opentps.core.io.dicomIO import readDicomCT, readDicomDose, readDicomStruct, readDicomPlan


def ingest_ct(dcm_files: list):
    """A CT series from a list of per-slice DICOM file paths.

    `readDicomCT` derives the z-spacing as `(last - first) / (n - 1)` over
    the given slices' `ImagePositionPatient`, confirmed against the
    installed source on 15 September 2026. With one file this is `0/0`:
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
            f"spacing rather than a raised error (confirmed against the "
            f"installed source, 15 September 2026)."
        )
    return readDicomCT(dcm_files)


def ingest_dose(path: str):
    """A dose distribution from one RTDOSE file.

    Raises if `readDicomDose` returns `None`, which it does when
    `BitsStored`/`PixelRepresentation` is not one of the four combinations
    it recognises (16 or 32 bit, signed or unsigned), confirmed against
    the installed source and reproduced with a constructed 8-bit file on
    15 September 2026.

    Returns
    -------
    DoseImage, `.referencePlan` set to the SOP instance UID of the RTPLAN
    the dose references, read from `ReferencedRTPlanSequence`.
    """
    image = readDicomDose(path)
    if image is None:
        raise ValueError(
            f"ingest_dose: readDicomDose returned None for {path!r}. "
            f"Unsupported pixel data type: BitsStored/PixelRepresentation "
            f"is not one of 16-bit unsigned, 16-bit signed, 32-bit "
            f"unsigned or 32-bit signed, the four readDicomDose accepts."
        )
    return image


def ingest_struct(path: str):
    """A structure set from one RTSTRUCT file.

    Raises if `readDicomStruct` returns `None`, which it does when the
    file has no `SeriesInstanceUID`, confirmed against the installed
    source on 15 September 2026.

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
    separate branches, confirmed against the installed source on 15
    September 2026: an unsupported photon or ion radiation type, a proton
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

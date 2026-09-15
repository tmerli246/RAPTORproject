"""The export manifest, its reader, and the DICOM consistency check
(extractor design 4).

`read_manifest`, `check_row_consistency` and `check_manifest` import
nothing from OpenTPS: the first touches only the file system, the other
two read plain attributes off already-loaded objects (DoseImage, RTPlan,
RTStruct) rather than calling into OpenTPS themselves.

`discover_and_load`, added once `extractor.ingest` existed, does not keep
that property: it calls `ingest.ingest_dose`/`ingest_plan`/`ingest_struct`
to actually load the files it discovers, since discovery is only useful
if it returns loaded objects rather than paths. Stated here rather than
left for a reader to notice the module docstring no longer quite matches
one of its four functions.

Column set and the design reasoning are extractor design 4: the manifest is
the authority for arm, block, role and scheme, none of which are DICOM
concepts, and DICOM relations serve only as a consistency check on the one
thing they can verify, that a dose object assigned to block j is in fact
tied to the image of block j.
"""

import csv
import os
from dataclasses import dataclass

import pydicom

from . import ingest


VALID_ARMS = ('XT-NA', 'XT-A', 'PT-NA', 'PT-A')
VALID_ROLES = ('planned', 'rescue')   # matches core/schema.py's BlockPlan


@dataclass(frozen=True)
class ManifestRow:
    plan_uid: str
    path: str
    block_index: int
    arm: str
    role: str
    source_image_uid: str
    fx_scheme: tuple   # (n, d): fraction count, dose per fraction in Gy


def read_manifest(path: str) -> list:
    """Read a per-patient export manifest.

    CSV columns: plan_uid,path,block_index,arm,role,source_image_uid,n_fx,
    dose_per_fx_gy. `fx_scheme` is stored as two columns rather than the
    single field extractor design 4 shows, n_fx and dose_per_fx_gy, since a
    (n, d) pair does not have an unambiguous single-field CSV
    representation without inventing a delimiter; the schema's (n, d) is
    reconstructed as ManifestRow.fx_scheme on read.

    Validated on read, not deferred to whatever consumes the row later:
    `arm` must be one of the four in VALID_ARMS, `role` one of the two
    core/schema.py's BlockPlan itself accepts, `block_index` an integer.
    A row that fails here is a row with a typo or a scripting bug in
    whatever produced the manifest, and should be caught at the point it is
    read, not several stages downstream where the error message would be
    about something else entirely.
    """
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        expected = ['plan_uid', 'path', 'block_index', 'arm', 'role',
                   'source_image_uid', 'n_fx', 'dose_per_fx_gy']
        if reader.fieldnames != expected:
            raise ValueError(
                f"{path}: expected header {expected}, got {reader.fieldnames}"
            )

        for i, raw in enumerate(reader):
            if raw['arm'] not in VALID_ARMS:
                raise ValueError(
                    f"{path}, row {i}: arm={raw['arm']!r} is not one of "
                    f"{VALID_ARMS}."
                )
            if raw['role'] not in VALID_ROLES:
                raise ValueError(
                    f"{path}, row {i}: role={raw['role']!r} is not one of "
                    f"{VALID_ROLES}."
                )
            try:
                block_index = int(raw['block_index'])
            except ValueError:
                raise ValueError(
                    f"{path}, row {i}: block_index={raw['block_index']!r} "
                    f"is not an integer."
                )

            rows.append(ManifestRow(
                plan_uid=raw['plan_uid'],
                path=raw['path'],
                block_index=block_index,
                arm=raw['arm'],
                role=raw['role'],
                source_image_uid=raw['source_image_uid'],
                fx_scheme=(int(raw['n_fx']), float(raw['dose_per_fx_gy'])),
            ))

    if not rows:
        raise ValueError(f"{path}: manifest has no rows.")

    return rows


def check_row_consistency(row: ManifestRow, *, dose, plan, struct) -> None:
    """Check one manifest row against the DICOM objects it claims to describe.

    Three checks, each against an attribute confirmed present on the
    installed OpenTPS's parsed objects by reading readDicomDose,
    readDicomPlan and readDicomStruct directly on 14 September 2026, not
    assumed from the DICOM standard in the abstract:

    - dose.referencePlan (the RTPLAN SOPInstanceUID readDicomDose records
      from RTDOSE's ReferencedRTPlanSequence) must equal plan.sopInstanceUID:
      the dose really does reference this plan.
    - row.plan_uid must equal plan.sopInstanceUID: the manifest's own claim
      about which plan this is matches the plan object.
    - plan.frameOfReferenceUID must equal struct.frameOfReferenceUID: plan
      and structure set were defined on the same image geometry.

    A fourth, plan.frameOfReferenceUID against row.source_image_uid, is
    **not** checked here: extractor design 4 states this check verifies
    only that a dose is tied to its own plan and structure set, not which
    physical image (pCT vs a specific rCT_j) that corresponds to. Treating
    frameOfReferenceUID as identifying "the image" for that purpose is a
    convention this project adopts, not a DICOM guarantee: repeat CTs are
    not certain to receive distinct frame of reference UIDs in every export
    configuration, and RayStation's own convention here is unverified
    (extractor design X9's territory). Registered as its own assumption
    where the schema records source_image_uid, not silently folded into
    this function.

    Raises
    ------
    ValueError, listing every disagreement found, not only the first: a
    validation pass over a manifest is exactly the situation where seeing
    every problem in one run matters more than failing fast on one.
    """
    problems = []

    if dose.referencePlan != plan.sopInstanceUID:
        problems.append(
            f"dose.referencePlan ({dose.referencePlan}) does not match "
            f"plan.sopInstanceUID ({plan.sopInstanceUID})"
        )
    if row.plan_uid != plan.sopInstanceUID:
        problems.append(
            f"manifest plan_uid ({row.plan_uid}) does not match "
            f"plan.sopInstanceUID ({plan.sopInstanceUID})"
        )
    if plan.frameOfReferenceUID != struct.frameOfReferenceUID:
        problems.append(
            f"plan.frameOfReferenceUID ({plan.frameOfReferenceUID}) does "
            f"not match struct.frameOfReferenceUID "
            f"({struct.frameOfReferenceUID})"
        )

    if problems:
        raise ValueError(
            f"manifest row for plan_uid={row.plan_uid!r}, block "
            f"{row.block_index}, arm {row.arm}: " + "; ".join(problems)
        )


def check_manifest(rows, loaded: dict) -> None:
    """check_row_consistency over every row in a manifest.

    `loaded` maps plan_uid -> (dose, plan, struct). Collects every row's
    disagreements into one exception rather than raising on the first, so
    that fixing a manifest is one pass over a full list of problems and not
    one problem discovered per re-run.

    A plan_uid present in the manifest but absent from `loaded` is its own
    problem, listed rather than raising a bare KeyError: it means the
    referenced file was not found or not parsed, which is as much a
    manifest-consistency issue as a mismatched UID is.
    """
    problems = []
    for row in rows:
        if row.plan_uid not in loaded:
            problems.append(
                f"plan_uid={row.plan_uid!r} (block {row.block_index}, arm "
                f"{row.arm}) has no loaded dose/plan/struct triple"
            )
            continue
        dose, plan, struct = loaded[row.plan_uid]
        try:
            check_row_consistency(row, dose=dose, plan=plan, struct=struct)
        except ValueError as err:
            problems.append(str(err))

    if problems:
        raise ValueError(
            f"{len(problems)} manifest row(s) failed consistency:\n" +
            "\n".join(f"  - {p}" for p in problems)
        )


# ---------------------------------------------------------------------------
# Discovery (extractor design 16's open item)
# ---------------------------------------------------------------------------

def _find_dicom_by_sop_uid(directory: str, target_sop_uid: str) -> str:
    """Path of the file in `directory` whose SOPInstanceUID matches.

    Reads only the header, `stop_before_pixels=True`, so scanning a
    directory of dose or image files is cheap: pixel data is never
    decoded just to check a UID. Files that are not valid DICOM at all
    are skipped rather than failing the whole search, since a real export
    directory is not guaranteed to contain only DICOM.

    Raises on zero matches, and on more than one: a directory where two
    files claim the same SOPInstanceUID is not a search problem to work
    around silently, it is a data problem to surface.
    """
    matches = []
    for fname in os.listdir(directory):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            dcm = pydicom.dcmread(fpath, stop_before_pixels=True)
        except Exception:
            continue
        if getattr(dcm, 'SOPInstanceUID', None) == target_sop_uid:
            matches.append(fpath)

    if not matches:
        raise FileNotFoundError(
            f"no DICOM file in {directory!r} has SOPInstanceUID "
            f"{target_sop_uid!r}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"{len(matches)} files in {directory!r} claim SOPInstanceUID "
            f"{target_sop_uid!r}: {matches}"
        )
    return matches[0]


def discover_and_load(row: ManifestRow, *, search_dir: str = None):
    """The (dose, plan, struct) triple for one manifest row, plan and
    struct discovered from the dose file's own DICOM references rather
    than from extra manifest columns.

    **The design decision this function encodes, not one extractor design
    4 states on its own**: a manifest row's `path` names the dose file,
    and every other file that row needs lives alongside it in the same
    directory. Extractor design 4's schema is silent on which of "dose
    file alone" or "a directory with all three" `path` means; this
    function commits to the first, with discovery filling the gap, rather
    than adding path columns the manifest schema does not have. This is a
    decision this project controls, not a RayStation convention to wait
    for: whoever writes the manifest, most likely a script per open
    decision 26 of the allocator document, controls the directory layout
    too.

    `search_dir` defaults to the directory `row.path` is in; passed
    explicitly for a layout where the three files are not siblings.

    Discovery: `dose.referencePlan` (extractor design 4's confirmed
    attribute chain, X8) is looked up by `_find_dicom_by_sop_uid` in
    `search_dir`, then `plan.referencedStructureSetSequence[0]
    .ReferencedSOPInstanceUID` the same way. Both raise clearly, via
    `_find_dicom_by_sop_uid`, if the search does not resolve to exactly
    one file.

    Returns
    -------
    (dose, plan, struct), suitable for `check_row_consistency`.
    """
    if search_dir is None:
        search_dir = os.path.dirname(row.path) or '.'

    dose = ingest.ingest_dose(row.path)

    plan_path = _find_dicom_by_sop_uid(search_dir, dose.referencePlan)
    plan = ingest.ingest_plan(plan_path)

    if not plan.referencedStructureSetSequence:
        raise ValueError(
            f"plan {plan.sopInstanceUID!r} (from {plan_path!r}) has an "
            f"empty referencedStructureSetSequence: cannot discover its "
            f"structure set."
        )
    struct_sop_uid = plan.referencedStructureSetSequence[0].ReferencedSOPInstanceUID
    struct_path = _find_dicom_by_sop_uid(search_dir, struct_sop_uid)
    struct = ingest.ingest_struct(struct_path)

    return dose, plan, struct

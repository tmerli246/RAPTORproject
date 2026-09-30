"""The export manifest, its reader, and the DICOM consistency check
(extractor design 4).

`read_manifest`, `validate_manifest`, `check_row_consistency` and
`check_manifest` import nothing from OpenTPS: the first two touch only the
file system, the other two read plain attributes off already-loaded objects
(DoseImage, RTPlan, RTStruct). `discover_and_load` calls into `extractor.ingest`
to load what it discovers, and imports it at the call, so the rest of the
module is importable without OpenTPS.

Column set and the design reasoning are extractor design 4: the manifest is
the authority for arm, block, role and scheme, none of which are DICOM
concepts, and DICOM relations serve only as a consistency check on the one
thing they can verify, that a dose object assigned to block j is in fact
tied to the image of block j.
"""

import csv
import math
import os
from dataclasses import dataclass

import pydicom

from tps5d.core.schema import ARM_OF


VALID_ARMS = tuple(ARM_OF.values())
VALID_ROLES = ('planned', 'rescue')   # matches core/schema.py's BlockPlan

# The eight columns written before extractor design 4 gained dose_image_uid and
# the two acceptance outcomes, and the full set. A file with the first header
# reads with the three extra fields unset.
HEADER_BASE = ['plan_uid', 'path', 'block_index', 'arm', 'role',
               'source_image_uid', 'n_fx', 'dose_per_fx_gy']
HEADER_FULL = ['plan_uid', 'path', 'block_index', 'arm', 'role',
               'source_image_uid', 'dose_image_uid', 'n_fx', 'dose_per_fx_gy',
               'accept_nominal', 'accept_robust']


@dataclass(frozen = True)
class ManifestRow:
    """One exported dose object and its place in the design.

    dose_image_uid, accept_nominal and accept_robust are None when the manifest
    does not record them. `accept_*` is the RayStation acceptance judgement of
    this plan on this block, nominal and robust (allocator 8.2).
    """
    plan_uid: str
    path: str
    block_index: int
    arm: str
    role: str
    source_image_uid: str
    fx_scheme: tuple   # (n, d): fraction count, dose per fraction in Gy
    dose_image_uid: str = None
    accept_nominal: bool = None
    accept_robust: bool = None


def _parse_flag(text, where, column):
    """Acceptance outcome: '1' accepted, '0' rejected, empty for not evaluated."""
    text = text.strip()
    if text == '':
        return None
    if text in ('0', '1'):
        return text == '1'
    raise ValueError(f"{where}: {column}={text!r} is not 1, 0 or empty.")


def read_manifest(path: str) -> list:
    """Read a per-patient export manifest.

    CSV columns: HEADER_FULL (extractor design 4), or HEADER_BASE without the
    last three. `fx_scheme` is stored as two columns, n_fx and dose_per_fx_gy,
    since a (n, d) pair has no unambiguous single-field CSV representation;
    the (n, d) pair is reconstructed as ManifestRow.fx_scheme on read.
    `accept_nominal` and `accept_robust` are 1, 0 or empty (not evaluated).

    Relative `path` entries resolve against the directory of the manifest, so
    a manifest works from any working directory; absolute paths are kept.

    Validated on read, not deferred to whatever consumes the row later:
    every error names the file and the line. `arm` must be one of VALID_ARMS,
    `role` one of VALID_ROLES, `block_index` and `n_fx` integers, and the
    rows together must satisfy `validate_manifest`.
    """
    base = os.path.dirname(os.path.abspath(path))
    rows = []
    with open(path, newline = '', encoding = 'utf-8-sig') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames not in (HEADER_BASE, HEADER_FULL):
            raise ValueError(
                f"{path}: expected header {HEADER_FULL} (or the first eight "
                f"columns of it), got {reader.fieldnames}"
            )

        for raw in reader:
            where = f"{path}, line {reader.line_num}"
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError(
                    f"{where}: expected {len(reader.fieldnames)} fields."
                )
            if raw['arm'] not in VALID_ARMS:
                raise ValueError(
                    f"{where}: arm={raw['arm']!r} is not one of {VALID_ARMS}."
                )
            if raw['role'] not in VALID_ROLES:
                raise ValueError(
                    f"{where}: role={raw['role']!r} is not one of {VALID_ROLES}."
                )
            try:
                block_index = int(raw['block_index'])
            except ValueError:
                raise ValueError(
                    f"{where}: block_index={raw['block_index']!r} is not an integer."
                )
            try:
                fx_scheme = (int(raw['n_fx']), float(raw['dose_per_fx_gy']))
            except ValueError:
                raise ValueError(
                    f"{where}: n_fx={raw['n_fx']!r} and dose_per_fx_gy="
                    f"{raw['dose_per_fx_gy']!r} must be an integer and a number."
                )
            if not raw['path'].strip():
                raise ValueError(f"{where}: path is empty.")
            file_path = raw['path'].strip()
            if not os.path.isabs(file_path):
                file_path = os.path.normpath(os.path.join(base, file_path))

            full = reader.fieldnames == HEADER_FULL
            rows.append(ManifestRow(
                plan_uid = raw['plan_uid'],
                path = file_path,
                block_index = block_index,
                arm = raw['arm'],
                role = raw['role'],
                source_image_uid = raw['source_image_uid'],
                fx_scheme = fx_scheme,
                dose_image_uid = (raw['dose_image_uid'].strip() or None) if full else None,
                accept_nominal = _parse_flag(raw['accept_nominal'], where, 'accept_nominal') if full else None,
                accept_robust = _parse_flag(raw['accept_robust'], where, 'accept_robust') if full else None,
            ))

    if not rows:
        raise ValueError(f"{path}: manifest has no rows.")

    validate_manifest(rows, path)
    return rows


def validate_manifest(rows, path = 'manifest') -> None:
    """Structural checks over a whole manifest, all problems in one exception.

    Rules, each the manifest-side form of what `core.schema.Strategy` enforces
    after the manifest has been consumed:
    - n_fx is positive, and dose_per_fx_gy finite and positive;
    - a plan has one dose per block: (plan_uid, block_index) is unique;
    - one plan_uid carries one arm and one schedule;
    - block 0 is on the planning anatomy for every arm, so it is `planned`;
    - only a non-adapted arm carries a rescue;
    - block indices of an (arm, schedule) run from 0 without a gap. Several
      rows may share a block: a rejected recomputation and its rescue.
    Row numbers count from the first data row, which is line 2.
    """
    bad = []
    seen, plan_of = {}, {}
    for i, r in enumerate(rows, start = 2):
        n, d = r.fx_scheme
        if n <= 0 or not math.isfinite(d) or d <= 0.0:
            bad.append(f"row {i}: n_fx={n}, dose_per_fx_gy={d}")
        key = (r.plan_uid, r.block_index)
        if key in seen:
            bad.append(f"row {i}: plan {r.plan_uid!r} already has a dose for "
                       f"block {r.block_index} (row {seen[key]})")
        seen.setdefault(key, i)
        first = plan_of.setdefault(r.plan_uid, (r.arm, r.fx_scheme, i))
        if first[:2] != (r.arm, r.fx_scheme):
            bad.append(f"row {i}: plan {r.plan_uid!r} is {r.arm} {r.fx_scheme}, "
                       f"row {first[2]} has {first[0]} {first[1]}")
        if r.role == 'rescue' and r.block_index == 0:
            bad.append(f"row {i}: block 0 cannot carry a rescue")
        if r.role == 'rescue' and r.arm.endswith('-A'):
            bad.append(f"row {i}: adapted arm {r.arm} cannot carry a rescue")

    runs = {}
    for r in rows:
        runs.setdefault((r.arm, r.fx_scheme), set()).add(r.block_index)
    for (arm, scheme), blocks in sorted(runs.items()):
        if sorted(blocks) != list(range(len(blocks))):
            bad.append(f"{arm} {scheme}: blocks {sorted(blocks)} do not run from 0 without a gap")

    if bad:
        raise ValueError(f"{path}: " + "; ".join(bad))


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


DOSE_SCALE_BAND = (0.5, 1.5)


def check_dose_scale(row: ManifestRow, target_dmean_per_fx_gy: float) -> None:
    """The target's mean dose per fraction against the row's dose per fraction.

    Guards the dose convention (extractor design 5, X9): if the array is not
    per fraction, or `dose_per_fx_gy` is wrong, the ratio is far from 1 (a
    factor n_fx, or its inverse, for a plan-total dose or a dose scaled
    twice). The band is arbitrary and only has to separate a factor of 3 or
    more; a plan that under-covers its target passes, a plan a factor 2
    off does not. Raises with the ratio and the two hypotheses.
    """
    ratio = target_dmean_per_fx_gy / row.fx_scheme[1]
    if not DOSE_SCALE_BAND[0] <= ratio <= DOSE_SCALE_BAND[1]:
        raise ValueError(
            f"manifest row for plan_uid={row.plan_uid!r}, block {row.block_index}, "
            f"arm {row.arm}: target mean dose {target_dmean_per_fx_gy:.3f} Gy per "
            f"fraction against dose_per_fx_gy {row.fx_scheme[1]:.3f} Gy gives a ratio "
            f"of {ratio:.2f}, outside {DOSE_SCALE_BAND}. Either the array is not per "
            f"fraction (a total dose, or one scaled twice) or dose_per_fx_gy is wrong."
        )


def check_manifest(rows, loaded: dict) -> None:
    """check_row_consistency over every row in a manifest.

    `loaded` maps (plan_uid, block_index) -> (dose, plan, struct). The key is
    the pair because a non-adapted plan recomputed on several repeat images
    appears in several rows under one plan_uid, each with its own dose.
    Collects every row's disagreements into one exception rather than raising
    on the first, so that fixing a manifest is one pass over a full list of
    problems and not one problem discovered per re-run.

    A row absent from `loaded` is its own problem, listed rather than raising
    a bare KeyError: it means the referenced file was not found or not parsed,
    which is as much a manifest-consistency issue as a mismatched UID is.
    """
    problems = []
    for row in rows:
        key = (row.plan_uid, row.block_index)
        if key not in loaded:
            problems.append(
                f"plan_uid={row.plan_uid!r} (block {row.block_index}, arm "
                f"{row.arm}) has no loaded dose/plan/struct triple"
            )
            continue
        dose, plan, struct = loaded[key]
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
# Discovery (extractor design 4, X11)
# ---------------------------------------------------------------------------

def _find_dicom_by_sop_uid(directory: str, target_sop_uid: str) -> str:
    """Path of the file in `directory` whose SOPInstanceUID matches.

    Reads only the header, `stop_before_pixels=True`, so scanning a
    directory of dose or image files is cheap: pixel data is never
    decoded just to check a UID. Files that are not valid DICOM at all
    are skipped rather than failing the whole search, since a real export
    directory is not guaranteed to contain only DICOM. A DICOM file that
    cannot be read (a truncated copy, for instance) is not skipped silently:
    it is named in the error if nothing else matches.

    Raises on zero matches, and on more than one: a directory where two
    files claim the same SOPInstanceUID is not a search problem to work
    around silently, it is a data problem to surface.
    """
    matches, unreadable = [], []
    for fname in sorted(os.listdir(directory)):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            dcm = pydicom.dcmread(fpath, stop_before_pixels = True)
        except pydicom.errors.InvalidDicomError:
            continue                  # not a DICOM file at all
        except Exception as err:      # a DICOM file that cannot be read
            unreadable.append(f"{fname} ({type(err).__name__})")
            continue
        if getattr(dcm, 'SOPInstanceUID', None) == target_sop_uid:
            matches.append(fpath)

    if not matches:
        raise FileNotFoundError(
            f"no DICOM file in {directory!r} has SOPInstanceUID "
            f"{target_sop_uid!r}"
            + (f"; unreadable files that may be it: {unreadable}" if unreadable else "")
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

    `search_dir` defaults to the directory `row.path` is in (`read_manifest`
    makes `path` absolute); passed explicitly for a layout where the three
    files are not siblings.

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
    from . import ingest    # here and not at module level: OpenTPS is needed only to load

    if search_dir is None:
        search_dir = os.path.dirname(row.path) or '.'

    dose = ingest.ingest_dose(row.path, n_fx = row.fx_scheme[0])

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

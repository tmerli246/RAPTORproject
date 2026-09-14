"""TG-263 canonical name resolution (extractor design 9).

No OpenTPS import: this module only touches strings and the file system.
The one place it meets an OpenTPS object is resolve_dicom_name, which reads
`.name` off already-loaded ROIContour objects, not an opentps call itself.

The mapping file is a mechanism built now and populated later (extractor
design 9): a real mapping's content requires a real RTSTRUCT or a partner
template, neither of which exists yet. What is buildable now is the lookup
and the failure behaviour around it.
"""

import csv
import hashlib
from dataclasses import dataclass


def _normalize(name: str) -> str:
    """Mechanical normalisation only: strip whitespace, casefold.

    Deliberately not fuzzy. Extractor design 9 is explicit that fuzzy
    matching fails silently and a mismatched OAR produces a plausible
    number rather than an error; this function exists so that trivial,
    accidental variation, a trailing space, a different case, does not
    force a new mapping-file row for what is actually the same string,
    without opening the door to matching on similarity.
    """
    return name.strip().casefold()


@dataclass(frozen=True)
class RoiMapping:
    """A loaded TG-263 mapping: canonical name -> expected DICOM name.

    Carries its own content hash, since extractor design 9 requires the
    mapping file's hash to be recorded with dose provenance: a change to
    the mapping changes which voxels are counted, and provenance exists to
    make that traceable.
    """
    entries: dict       # canonical_name -> dicom_name, as stored in the file
    content_hash: str
    path: str


def load_roi_mapping(path: str) -> RoiMapping:
    """Load a two-column CSV: canonical_name,dicom_name.

    One row per structure. Comment lines starting with # and blank lines
    are skipped, so a near-empty file with only a header is a valid,
    intentionally unpopulated mapping, per extractor design 9's
    "mechanism built now, populated later".
    """
    entries = {}
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['canonical_name', 'dicom_name']:
            raise ValueError(
                f"{path}: expected header 'canonical_name,dicom_name', "
                f"got {reader.fieldnames}"
            )
        for row in reader:
            canonical = row['canonical_name'].strip()
            dicom = row['dicom_name'].strip()
            if not canonical or not dicom:
                continue
            if canonical in entries:
                raise ValueError(
                    f"{path}: canonical name {canonical!r} appears twice, "
                    f"as {entries[canonical]!r} and {dicom!r}. A mapping "
                    f"file with two answers for the same lookup is exactly "
                    f"the ambiguity this mechanism exists to remove."
                )
            entries[canonical] = dicom

    with open(path, 'rb') as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()[:16]

    return RoiMapping(entries=entries, content_hash=content_hash, path=path)


def resolve_dicom_name(rtstruct, canonical_name: str, mapping: RoiMapping) -> str:
    """The literal DICOM contour name in `rtstruct` for a TG-263 canonical name.

    Two independent ways to fail, both are "an unmapped structure raises"
    (extractor design 9), with different messages because they mean
    different things to whoever reads them:

    - `canonical_name` is not in the mapping file at all: the mapping is
      incomplete for this cohort, add a row.
    - `canonical_name` is in the mapping, but no contour in this specific
      `rtstruct` matches the expected DICOM name after normalisation: this
      patient's export does not contain a structure the mapping expects,
      which is a data problem, not a mapping problem, and the two should
      not be confused when someone is trying to fix the raise.

    Matching is by normalised name (`_normalize`), but the value returned
    is the contour's own, un-normalised `name`, since `RTStruct.getContourByName`
    and the OpenTPS mask calls it feeds do exact string comparison and
    would not find a normalised name that does not exist verbatim in the
    struct.

    Returns
    -------
    str, the exact contour name as it appears in `rtstruct`.
    """
    if canonical_name not in mapping.entries:
        raise KeyError(
            f"{canonical_name!r} is not in the ROI mapping file "
            f"({mapping.path}). Available canonical names: "
            f"{sorted(mapping.entries)}. Add a row rather than guessing a "
            f"match: extractor design 9 rules out fuzzy matching."
        )

    expected = _normalize(mapping.entries[canonical_name])
    for contour in rtstruct.contours:
        if _normalize(contour.name) == expected:
            return contour.name

    available = sorted(c.name for c in rtstruct.contours)
    raise KeyError(
        f"mapping expects {canonical_name!r} to be named "
        f"{mapping.entries[canonical_name]!r} in the RTSTRUCT, but no "
        f"contour there matches after normalisation. Structures present: "
        f"{available}. This is a data problem, not a mapping-file problem: "
        f"check the export before editing {mapping.path}."
    )

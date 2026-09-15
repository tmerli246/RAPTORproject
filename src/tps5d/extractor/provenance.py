"""Provenance table (extractor design 13.1).

No OpenTPS import: this module stores and queries plain records, it does
not compute anything about the objects those records describe.

The requirement, stated in extractor design 13, is enumerability, not
annotation: the tag exists so that the set of parameters to perturb can be
listed by query, not so that a value has a label attached somewhere. A
field scattered through every record satisfies the wording and not the
requirement, since enumerating would then mean traversing the whole store.
This module is the separate table extractor design 13.1 asks for.

Only primitives are tagged, per extractor design 13.2: dose arrays, image
and grid geometry, ROI masks and the mapping file, facility constants,
NTCP model parameters, swept study parameters, the export manifest, the
prescription, the DIR settings, the OpenTPS commit hash. Derived
quantities, D98, D95, V95%, gEUD, DVHs, accumulated dose, occupancies,
inherit from their inputs and are not tagged themselves. This module does
not and cannot enforce that distinction: it has no way to know whether a
given key names a primitive or a derived quantity, since that is a
judgement about the pipeline, not a property of a string. Callers decide
what to record; this module only stores and enumerates what they do.
"""

import csv
from dataclasses import dataclass, asdict


KINDS = ('measured', 'published', 'assumed', 'swept')


@dataclass(frozen=True)
class ProvenanceRecord:
    """One primitive's provenance.

    key           e.g. 'dose:pt12/b1/PT-A/planned'. Opaque to this module:
                  namespacing and structure are the caller's convention,
                  not something this record parses or validates.
    kind          'measured' | 'published' | 'assumed' | 'swept'
    source        e.g. 'RayStation <engine>' | 'Michalski 2010 QUANTEC' | 'X9'.
                  Where kind is 'assumed', extractor design 13.1 states this
                  names an assumption ID from the extractor, allocator or
                  evaluator register, which is what makes the register
                  checkable against the data rather than parallel to it.
                  Not enforced to match a real ID here: the three registers
                  are maintained in the design documents, not in this
                  module, and duplicating that list here would be a second
                  copy to fall out of sync with the first.
    content_hash  links to the stored object, e.g. DIRSettings.content_hash()
                  or a mapping file's hash.
    """
    key: str
    kind: str
    source: str
    content_hash: str

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.key}: kind must be one of {KINDS}, got {self.kind!r}")
        if not self.key:
            raise ValueError("key must not be empty")
        if not self.source:
            raise ValueError(f"{self.key}: source must not be empty")


class ProvenanceTable:
    """A queryable collection of ProvenanceRecord, keyed by `key`.

    Deliberately not a dict exposed directly: `add` raises on a key already
    present, since two provenance records for the same primitive is a sign
    of a logic error upstream, most likely the same quantity tagged twice
    from two different call sites that do not know about each other,
    rather than something to silently allow. `update` is the explicit,
    separate spelling for the legitimate case, re-extracting the same
    patient and replacing what was there.
    """

    def __init__(self):
        self._records = {}

    def add(self, record: ProvenanceRecord):
        if record.key in self._records:
            raise KeyError(
                f"provenance already recorded for {record.key!r}: "
                f"{self._records[record.key]}. Use update() if this is a "
                f"deliberate re-extraction, not add()."
            )
        self._records[record.key] = record

    def update(self, record: ProvenanceRecord):
        """Add or overwrite, for a deliberate re-extraction."""
        self._records[record.key] = record

    def get(self, key: str) -> ProvenanceRecord:
        if key not in self._records:
            raise KeyError(f"no provenance recorded for {key!r}")
        return self._records[key]

    def query(self, *, kind: str = None) -> list:
        """Every record, or every record of one `kind`, sorted by key.

        This is the enumerability extractor design 13 asks for: a caller
        studying sensitivity to assumed parameters calls
        `table.query(kind='assumed')` and gets the complete, current list,
        rather than maintaining a second list of what was assumed by hand.
        """
        records = self._records.values()
        if kind is not None:
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
            records = (r for r in records if r.kind == kind)
        return sorted(records, key=lambda r: r.key)

    def __len__(self):
        return len(self._records)

    def __iter__(self):
        return iter(self.query())

    def __contains__(self, key):
        return key in self._records

    def write_csv(self, path: str):
        """Write every record, key-sorted, to a four-column CSV."""
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['key', 'kind', 'source', 'content_hash'])
            writer.writeheader()
            for record in self.query():
                writer.writerow(asdict(record))

    @classmethod
    def read_csv(cls, path: str) -> 'ProvenanceTable':
        """Load a table written by write_csv. Raises on a duplicate key,
        the same as building the table up with repeated add() calls would,
        rather than silently keeping the last row for a repeated key.
        """
        table = cls()
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            expected = ['key', 'kind', 'source', 'content_hash']
            if reader.fieldnames != expected:
                raise ValueError(f"{path}: expected header {expected}, got {reader.fieldnames}")
            for row in reader:
                table.add(ProvenanceRecord(**row))
        return table

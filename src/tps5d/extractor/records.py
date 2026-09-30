"""Plain data records used across the extractor.

No OpenTPS import here. adapters.py is the only module that touches opentps
(X1, extractor design 3.2); this module is what its functions take as
arguments and return, so it stays importable and testable without the
dependency and without an environment where opentps is installed.
"""

import hashlib
from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class DIRSettings:
    """Settings for one deformable registration.

    base_resolution   mm. Sets the Morphons scale ladder. Recommended equal
                      to the working-grid spacing (extractor design 6.1);
                      below it is excluded on measurement, not merely
                      discouraged (X5). Ignored when backend='imported',
                      still required and validated: a settings object
                      should be reusable across backends without silently
                      changing shape
    n_processes       1 is the measured choice: the parallel path was slower
                      at every grid benchmarked (X2), so this is not a speed
                      knob left at a placeholder. Ignored when
                      backend='imported'
    try_gpu           False in this environment, no cupy. Passed explicitly
                      regardless, since the fallback on failure is silent
                      (X2). Ignored when backend='imported'
    backend           'morphons' or 'imported', both implemented (X2)
    imported_path     Path to a DICOM deformable registration object, read
                      via OpenTPS's readDicomVectorField. Required when
                      backend='imported', ignored otherwise

    Frozen and hashable by content rather than by identity, so the same
    settings passed twice produce the same cache key regardless of which
    call site constructed them.
    """
    base_resolution: float
    n_processes: int = 1
    try_gpu: bool = False
    backend: str = 'morphons'
    imported_path: str = None

    def __post_init__(self):
        if self.base_resolution <= 0:
            raise ValueError(f"base_resolution must be positive, got {self.base_resolution}")
        if self.n_processes < 1:
            raise ValueError(f"n_processes must be >= 1, got {self.n_processes}")
        if self.backend not in ('morphons', 'imported'):
            raise ValueError(f"backend must be 'morphons' or 'imported', got '{self.backend}'")
        if self.backend == 'imported' and self.imported_path is None:
            raise ValueError(
                "backend='imported' requires imported_path, the DICOM "
                "deformable registration file to read; none given."
            )

    def content_hash(self) -> str:
        """Short hash of the settings, for the DVF cache key (extractor 6, 12.1).

        Deliberately over the settings alone, not over the registration
        object: RegistrationMorphons rewrites n_processes in place when it
        starts negative, which would make a hash read from the object
        machine-dependent (X2). This hash is computed from what is passed
        in, before any call is made.

        Only the fields the backend uses enter it, so settings that produce
        the same field hash the same. For the imported backend that is the
        content of the file, not its path: the same path with a new file
        must not reuse a cached field. The working grid is not part of the
        settings, and the field lives on it, so a cache key also needs
        `WorkingGrid.content_hash()`.
        """
        if self.backend == 'imported':
            with open(self.imported_path, 'rb') as f:
                used = [('backend', 'imported'),
                        ('file', hashlib.sha256(f.read()).hexdigest())]
        else:
            used = [('backend', self.backend), ('base_resolution', self.base_resolution),
                    ('n_processes', self.n_processes), ('try_gpu', self.try_gpu)]
        return hashlib.sha256(repr(used).encode('utf-8')).hexdigest()[:16]


@dataclass(frozen=True)
class WorkingGrid:
    """The explicit geometry every OpenTPS geometry call is evaluated on.

    Exists as a named object rather than three loose tuples at each call
    site because extractor design 3.4's rule, nothing is called with its
    defaults, is easy to satisfy at one call and easy to drift from at the
    tenth: passing `grid` instead of `grid.origin, grid.spacing,
    grid.grid_size` separately removes the chance of supplying the three in
    an inconsistent combination across two calls that must agree, such as a
    dose extraction and a mask extraction that are later composed.

    origin, spacing : mm, length-3
    grid_size       : voxel counts, length-3 ints
    """
    origin: tuple
    spacing: tuple
    grid_size: tuple

    def __post_init__(self):
        for name in ('origin', 'spacing', 'grid_size'):
            if len(getattr(self, name)) != 3:
                raise ValueError(f"WorkingGrid.{name} must have length 3, got {getattr(self, name)!r}")
        if not all(s > 0 for s in self.spacing):
            raise ValueError(f"WorkingGrid.spacing must be positive, got {self.spacing!r}")
        if not all(int(g) == g and g > 0 for g in self.grid_size):
            raise ValueError(f"WorkingGrid.grid_size must be positive integers, got {self.grid_size!r}")

    def content_hash(self) -> str:
        """Short hash of the geometry, the second ingredient of a DVF cache key."""
        used = [tuple(float(v) for v in self.origin), tuple(float(v) for v in self.spacing),
                tuple(int(v) for v in self.grid_size)]
        return hashlib.sha256(repr(used).encode('utf-8')).hexdigest()[:16]


BLOCK_FRACTION_SOURCES = ('dates', 'assumed')


@dataclass(frozen=True)
class BlockFractions:
    """Fractions delivered in each block of one patient's course under one
    schedule (extractor design 11).

    n_b     fraction count per block, in block order. Zero is allowed, since a
            recomposition may weight a block out; the total must be positive
    source  'dates' if read off the treatment dates of the record, 'assumed'
            if set by the study (an even split, say). Provenance keeps them
            apart: an assumed split is a swept or assumed parameter, a dated
            one is measured

    Lives on the extractor side rather than on the strategy: it is one record
    per (patient, schedule), shared by up to four strategies, and only the dose
    composition reads it (evaluator design 5.1, BED_b), together with the
    constraint that the blocks sum to the course.
    """
    pid: str
    scheme: str
    n_b: tuple
    source: str

    def __post_init__(self):
        if self.source not in BLOCK_FRACTION_SOURCES:
            raise ValueError(f"{self.pid}/{self.scheme}: source must be one of "
                             f"{BLOCK_FRACTION_SOURCES}, got {self.source!r}")
        if not self.n_b or not all(int(n) == n and n >= 0 for n in self.n_b):
            raise ValueError(f"{self.pid}/{self.scheme}: n_b must be non-negative "
                             f"integers, got {self.n_b!r}")
        if sum(self.n_b) <= 0:
            raise ValueError(f"{self.pid}/{self.scheme}: n_b sums to zero")

    @property
    def n_fx(self) -> int:
        return int(sum(self.n_b))

    def check_total(self, n_fx: int) -> None:
        """Raise unless the blocks add up to the course's fraction count."""
        if self.n_fx != n_fx:
            raise ValueError(f"{self.pid}/{self.scheme}: n_b sums to {self.n_fx}, "
                             f"the schedule has {n_fx} fractions")


@dataclass(frozen=True)
class CropBounds:
    """Inclusive voxel index bounds of a crop, per axis (extractor design 5, X4).

    lo, hi : length-3 ints, hi inclusive, so array[lo[0]:hi[0]+1, ...] is
             the cropped region.
    """
    lo: tuple
    hi: tuple

    def shape(self):
        return tuple(self.hi[a] - self.lo[a] + 1 for a in range(3))


@dataclass(frozen=True)
class TargetMetrics:
    """Coverage metrics for one plan on one image, target ROI only.

    Course dose against course prescription throughout (extractor design 7):
    v95, d98 and d95 are already in the units the coverage screen uses.
    A per-fraction convention would put every plan at a few percent of
    prescription and return v95 = 0.0 for the whole cohort without raising.
    """
    v95_pct: float    # percentage of the target volume at >= 95% of course prescription
    d98_gy: float      # dose to 98% of the volume, course-equivalent, Gy
    d95_gy: float
    dmean_gy: float
    dmax_gy: float


@dataclass(frozen=True)
class DoseHeader:
    """The tags of an RTDOSE file that fix what its array means, as the file states them.

    An absent tag is None: OpenTPS fills defaults (`PLAN`, `GY`, `EFFECTIVE`)
    in its own object, so the object cannot tell an absent tag from a present
    one and the file has to be read directly (extractor design 5, X9).

    summation_type  `DoseSummationType`: PLAN, FRACTION, BEAM, ...
    units           `DoseUnits`: GY or RELATIVE
    dose_type       `DoseType`: PHYSICAL, EFFECTIVE, ...
    grid_scaling    `DoseGridScaling`
    frame_offsets   'increasing' | 'decreasing' | 'single' | 'absent', from
                    `GridFrameOffsetVector`
    """
    summation_type: str = None
    units: str = None
    dose_type: str = None
    grid_scaling: float = None
    frame_offsets: str = 'absent'

    def describe(self, n_fx_divided: int = None) -> str:
        """One line for the provenance table; states the conversion if one was made."""
        text = (f"DoseSummationType={self.summation_type};DoseUnits={self.units};"
                f"DoseType={self.dose_type};DoseGridScaling={self.grid_scaling};"
                f"GridFrameOffsetVector={self.frame_offsets}")
        if n_fx_divided is not None:
            text += f";divided_by_n_fx={n_fx_divided}"
        return text


@dataclass(frozen=True)
class PlanComplexity:
    """Descriptors feeding the delivery-time model (extractor design 8).

    Machine constants that convert these into minutes live elsewhere; this
    record carries what is actually in the plan file.
    """
    modality: str          # 'pt' | 'xt'
    n_fields: int
    n_layers: int = 0      # proton only
    n_spots: int = 0       # proton only
    n_segments: int = 0    # photon only
    mu: float = 0.0
    target_vol_cc: float = 0.0

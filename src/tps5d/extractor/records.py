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
                      discouraged (X5)
    n_processes       1 is the measured choice: the parallel path was slower
                      at every grid benchmarked (X2), so this is not a speed
                      knob left at a placeholder
    try_gpu           False in this environment, no cupy. Passed explicitly
                      regardless, since the fallback on failure is silent
                      (X2)
    backend           'morphons' (implemented) or 'imported' (stub, X2)

    Frozen and hashable by content rather than by identity, so the same
    settings passed twice produce the same cache key regardless of which
    call site constructed them.
    """
    base_resolution: float
    n_processes: int = 1
    try_gpu: bool = False
    backend: str = 'morphons'

    def __post_init__(self):
        if self.base_resolution <= 0:
            raise ValueError(f"base_resolution must be positive, got {self.base_resolution}")
        if self.n_processes < 1:
            raise ValueError(f"n_processes must be >= 1, got {self.n_processes}")
        if self.backend not in ('morphons', 'imported'):
            raise ValueError(f"backend must be 'morphons' or 'imported', got '{self.backend}'")

    def content_hash(self) -> str:
        """Short hash of the settings, for the DVF cache key (extractor 6, 13.1).

        Deliberately over the settings alone, not over the registration
        object: RegistrationMorphons rewrites n_processes in place when it
        starts negative, which would make a hash read from the object
        machine-dependent (X2). This hash is computed from what is passed
        in, before any call is made.
        """
        payload = repr(sorted(asdict(self).items())).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()[:16]


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

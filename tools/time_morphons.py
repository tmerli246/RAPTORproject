"""Time a Morphons registration on CPU. Two sweeps.

  Sweep 1, working-grid spacing. Feeds X5 and X2: how many multi-resolution
      scales run, and whether nbProcesses = 1 is affordable.
  Sweep 2, baseResolution. The 11 September run showed the returned field
      stops at baseResolution whatever the image grid, so this parameter is
      the accuracy floor of every accumulation. Its cost is unmeasured.

Run inside the project conda environment:

    conda activate OpenTPS
    python time_morphons.py

Approach. Morphons iterates a hard-coded schedule, [10]*6 + [5, 2], with no
convergence criterion, so cost is set by grid size and by how many scales run
before the loop breaks. Image content does not change the iteration count, so
a synthetic phantom gives a representative timing and this can be measured
before any patient data exists.

The phantom is a sphere in a noisy background, deformed by a known shift. The
shift magnitude does not affect timing; it is there so the run is a real
registration rather than a degenerate one.

Assumptions. Phantom geometry stands in for an abdominal field of view; the
real grid is measured on the first exported case. Peak memory is process RSS,
an upper bound on the registration's own allocation rather than a measurement
of it, since it includes the interpreter and the libraries.

Edge cases. Windows spawns rather than forks, so the multiprocessing path
needs the __main__ guard below. A configuration can exhaust memory: each is
attempted independently and announced before it runs, so a process killed
outright is still attributable to a known row.
"""

import gc
import time
import numpy as np

from opentps.core.data.images import CTImage
from opentps.core.processing.registration.registrationMorphons import RegistrationMorphons


RUN_BASE_RESOLUTION_SWEEP = True   # set False to run sweep 1 only

# Sweep 1: working-grid spacings in mm, coarse to fine. A dose grid sits
# nearer 2.5-3, a planning CT nearer 1.
SPACINGS_MM = [3.0, 2.0, 1.5]
N_PROCESSES = [1, 4]

# Sweep 2: baseResolution in mm, at one working grid.
BASE_RESOLUTIONS_MM = [3.0, 2.5, 2.0, 1.5]
SWEEP2_SPACING_MM = 2.0
SWEEP2_N_PROCESSES = 1

EXTENT_MM = (300.0, 300.0, 200.0)   # physical field of view, held fixed
DEFAULT_BASE_RESOLUTION_MM = 2.5    # the OpenTPS default
SHIFT_MM = (6.0, 0.0, 0.0)          # known displacement, fixed to moving


def make_phantom(spacing_mm, shift_mm=(0.0, 0.0, 0.0), seed=0):
    """Sphere in a noisy background, optionally shifted by a known offset."""
    spacing = np.full(3, float(spacing_mm))
    grid = np.maximum(np.round(np.asarray(EXTENT_MM) / spacing).astype(int), 8)

    coords = np.indices(grid).astype(np.float32)
    centre = (grid - 1) / 2.0 + np.asarray(shift_mm) / spacing
    r = np.sqrt(sum(((coords[i] - centre[i]) * spacing[i]) ** 2 for i in range(3)))

    image = np.where(r < 60.0, 60.0, -900.0).astype(np.float32)   # HU-like
    image += np.random.default_rng(seed).normal(0.0, 20.0, size=grid).astype(np.float32)

    return CTImage(imageArray=image, origin=(0.0, 0.0, 0.0), spacing=tuple(spacing))


def peak_rss_mb():
    """Process peak resident memory in MB, or None if psutil is absent."""
    try:
        import psutil
    except ImportError:
        return None
    info = psutil.Process().memory_info()
    return getattr(info, "peak_wset", info.rss) / 1e6


def run_one(spacing_mm, n_processes, base_resolution_mm):
    """One registration. Returns a dict of results."""
    fixed = make_phantom(spacing_mm)
    moving = make_phantom(spacing_mm, shift_mm=SHIFT_MM)
    grid = tuple(int(v) for v in fixed.gridSize)

    reg = RegistrationMorphons(fixed, moving,
                               baseResolution=base_resolution_mm,
                               nbProcesses=n_processes,
                               tryGPU=False)

    start = time.perf_counter()
    field = reg.compute()
    elapsed = time.perf_counter() - start

    result = dict(seconds=elapsed,
                  grid=grid,
                  mvoxels=float(np.prod(grid)) / 1e6,
                  peak_mb=peak_rss_mb(),
                  field_spacing=tuple(float(v) for v in field.spacing))

    del reg, field, fixed, moving
    gc.collect()
    return result


HEADER = (f"{'configuration':>22} {'grid':>14} {'Mvox':>7} "
          f"{'seconds':>9} {'s/Mvox':>9} {'peak MB':>7}  field spacing")


def format_row(label, result):
    grid = "x".join(str(v) for v in result["grid"])
    mb = f"{result['peak_mb']:7.0f}" if result["peak_mb"] is not None else f"{'n/a':>7}"
    field = "x".join(f"{v:.2f}" for v in result["field_spacing"])
    per_mvox = result["seconds"] / result["mvoxels"]
    return (f"{label:>22} {grid:>14} {result['mvoxels']:7.1f} "
            f"{result['seconds']:9.1f} {per_mvox:9.2f} {mb}  {field}")


def sweep(title, configs):
    """configs: list of (label, spacing_mm, n_processes, base_resolution_mm)."""
    print()
    print(title)
    print("-" * len(HEADER))
    print(HEADER)
    print("-" * len(HEADER))

    for label, spacing_mm, n_processes, base_res in configs:
        print(f"{label:>22}  running...", end="\r", flush=True)
        try:
            result = run_one(spacing_mm, n_processes, base_res)
        except MemoryError:
            print(f"{label:>22}  out of memory" + " " * 40, flush=True)
        except Exception as err:
            print(f"{label:>22}  failed: {type(err).__name__}: {err}"[:110],
                  flush=True)
        else:
            print(format_row(label, result), flush=True)


def main():
    print(f"extent {EXTENT_MM} mm, tryGPU False")

    configs = [(f"{s} mm, nproc {n}", s, n, DEFAULT_BASE_RESOLUTION_MM)
               for s in SPACINGS_MM for n in N_PROCESSES]
    sweep(f"Sweep 1: working grid, baseResolution {DEFAULT_BASE_RESOLUTION_MM} mm",
          configs)

    if RUN_BASE_RESOLUTION_SWEEP:
        configs = [(f"baseRes {b} mm", SWEEP2_SPACING_MM, SWEEP2_N_PROCESSES, b)
                   for b in BASE_RESOLUTIONS_MM]
        sweep(f"Sweep 2: baseResolution, working grid {SWEEP2_SPACING_MM} mm, "
              f"nproc {SWEEP2_N_PROCESSES}", configs)

    print()
    print("Registrations needed = patients x blocks. Arms share the images and")
    print("do not multiply this.")
    print("Field spacing never goes below baseResolution, whatever the image")
    print("grid: it is the accuracy floor of every accumulation. X5.")


if __name__ == "__main__":   # required on Windows: spawn, not fork
    main()

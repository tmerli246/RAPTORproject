"""Verify the OpenTPS API against the assumptions of extractor_design.md 5.0, Section 3.1.

Run inside the project conda environment:

    conda activate OpenTPS
    python check_opentps_api.py

Reports every entry rather than stopping at the first failure, so one run
gives the full picture. Nothing is imported eagerly at module scope, so a
missing subpackage degrades one row instead of killing the script.
"""

import importlib
import inspect


# (label, module path, attribute chain). An empty chain checks the module only.
CHECKS = [
    # Ingest
    ("readDicomCT",          "opentps.core.io.dicomIO", "readDicomCT"),
    ("readDicomDose",        "opentps.core.io.dicomIO", "readDicomDose"),
    ("readDicomStruct",      "opentps.core.io.dicomIO", "readDicomStruct"),
    ("readDicomPlan",        "opentps.core.io.dicomIO", "readDicomPlan"),
    ("readDicomVectorField", "opentps.core.io.dicomIO", "readDicomVectorField"),
    ("loadData",             "opentps.core.io.dataLoader", "loadData"),

    # Registration, and the deformation object
    ("RegistrationMorphons",         "opentps.core.processing.registration.registrationMorphons", "RegistrationMorphons"),
    ("RegistrationMorphons.compute", "opentps.core.processing.registration.registrationMorphons", "RegistrationMorphons.compute"),
    ("RegistrationDemons",           "opentps.core.processing.registration.registrationDemons", "RegistrationDemons"),
    ("Deformation3D.deformImage",    "opentps.core.data.images", "Deformation3D.deformImage"),
    ("Deformation3D.inverse",        "opentps.core.data.images", "Deformation3D.inverse"),
    ("Deformation3D.resample",       "opentps.core.data.images", "Deformation3D.resample"),

    # Synthetic deformation: the ground truth for the registration test, Section 3.3
    ("applyBaselineShift",  "opentps.core.processing.imageProcessing.syntheticDeformation", "applyBaselineShift"),
    ("shrinkOrgan",         "opentps.core.processing.imageProcessing.syntheticDeformation", "shrinkOrgan"),
    ("forceShiftInMask",    "opentps.core.processing.imageProcessing.syntheticDeformation", "forceShiftInMask"),

    # DVH and target metrics
    ("DVH",             "opentps.core.data", "DVH"),
    ("DVH.computeVx",   "opentps.core.data", "DVH.computeVx"),
    ("DVH.computeDx",   "opentps.core.data", "DVH.computeDx"),
    ("DVH.computeDcc",  "opentps.core.data", "DVH.computeDcc"),
    ("DVH.computeDVH",  "opentps.core.data", "DVH.computeDVH"),
    ("DVH.D98",         "opentps.core.data", "DVH.D98"),
    ("DVH.D95",         "opentps.core.data", "DVH.D95"),
    ("DVH.Dmean",       "opentps.core.data", "DVH.Dmean"),
    ("DVH.histogram",   "opentps.core.data", "DVH.histogram"),

    # ROI handling
    ("ROIContour.getBinaryMask", "opentps.core.data", "ROIContour.getBinaryMask"),
    ("RTStruct.getContourByName", "opentps.core.data", "RTStruct.getContourByName"),
    ("ROIMask.getVolume",        "opentps.core.data.images", "ROIMask.getVolume"),

    # Grid geometry
    ("Image3D.gridSize",   "opentps.core.data.images", "Image3D.gridSize"),
    ("Image3D.spacing",    "opentps.core.data.images", "Image3D.spacing"),
    ("Image3D.origin",     "opentps.core.data.images", "Image3D.origin"),
    ("Image3D.resampleOn", "opentps.core.data.images", "Image3D.resampleOn"),

    # Plan complexity, both modalities
    ("ProtonPlan.numberOfSpots",    "opentps.core.data.plan", "ProtonPlan.numberOfSpots"),
    ("PhotonPlan.numberOfSegments", "opentps.core.data.plan", "PhotonPlan.numberOfSegments"),
    ("RTPlan.numberOfFractionsPlanned", "opentps.core.data.plan", "RTPlan.numberOfFractionsPlanned"),
]


def resolve(module_path, chain):
    """Import the module and walk the dotted attribute chain. Raises on failure."""
    obj = importlib.import_module(module_path)
    for name in chain.split("."):
        obj = getattr(obj, name)
    return obj


def describe(obj):
    """One-line description: signature for callables, type otherwise."""
    if isinstance(obj, property):
        return "property"
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return type(obj).__name__


def report_version():
    from importlib.metadata import version, PackageNotFoundError
    for pkg in ("opentps-core", "opentps"):
        try:
            print(f"{pkg:16s} {version(pkg)}")
        except PackageNotFoundError:
            print(f"{pkg:16s} not installed as a distribution")
    try:
        core = importlib.import_module("opentps.core")
        print(f"{'location':16s} {getattr(core, '__file__', 'unknown')}")
    except ImportError as err:
        print(f"{'location':16s} import failed: {err}")


def main():
    print("=" * 78)
    print("OpenTPS version")
    print("=" * 78)
    report_version()

    print()
    print("=" * 78)
    print("API check against extractor_design.md 5.0, Section 3.1")
    print("=" * 78)

    missing = []
    for label, module_path, chain in CHECKS:
        try:
            obj = resolve(module_path, chain)
        except Exception as err:
            missing.append(label)
            print(f"MISSING  {label:34s} {type(err).__name__}: {err}")
        else:
            print(f"ok       {label:34s} {describe(obj)}")

    print()
    print("=" * 78)
    if missing:
        print(f"{len(missing)} of {len(CHECKS)} entries missing:")
        for label in missing:
            print(f"  {label}")
        print()
        print("Correct Section 3.1 before writing code against it.")
    else:
        print(f"All {len(CHECKS)} entries present. Signatures above still need "
              "reading: presence is not agreement.")
    print("=" * 78)


if __name__ == "__main__":
    main()

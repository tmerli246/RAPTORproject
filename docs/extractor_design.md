# Extraction Module

Version 5.9. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

The **extractor** gathers the per-patient, per-plan and per-facility quantities the downstream modules consume. Its scope is defined by their requirements.

Its consumer is the **evaluator**, which composes blocks into strategies, converts to EQD2, evaluates NTCP and computes the admissibility diagnostics. The extractor performs none of these. It produces the raw material and the registrations, and stops.

**The extractor's unit is the plan, not the strategy.** A strategy is a combination of per-block plans, and combinations are formed downstream. Storage is therefore linear in the number of blocks: each block contributes one dose per arm and schedule, plus any rescue plans, however strategies are formed.

Section 3 states which parts of the pipeline are taken from OpenTPS and which are built here. Section 13 is this module's assumptions register.

## 2. The central interface decision

The extractor emits **dose-derived quantities**. NTCP is evaluated downstream. Three reasons:

- *Model swapping.* NTCP models will change. With stored scalars, replacing a model requires re-running the whole extraction pipeline; with stored dose, it requires changing one record.
- *Uncertainty propagation.* Propagating uncertainty in LKB parameters requires thousands of NTCP re-evaluations with perturbed n, m and TD50, which is impossible from a stored scalar.
- *Composition.* NTCP is nonlinear, so the NTCP of a course whose plan changes between blocks cannot be obtained by combining per-block NTCPs. Dose must be composed first and NTCP evaluated once at the end.

**Consequence for storage.** Mean dose is additive across blocks, so per-block mean doses suffice for mean-dose-driven endpoints. gEUD with a volume parameter other than unity is **not** additive: the gEUD of an accumulated dose cannot be reconstructed from the gEUDs of its parts. The voxel grid is therefore required, not optional.

## 3. Implementation strategy

### 3.1 What is taken from OpenTPS

The mapping below was checked against the installed OpenTPS (3.0.0, a source checkout): all entries present, signatures read. Since the installation is a source checkout, the version string does not identify a state of the code, and the **commit hash** is what provenance records (Section 12.2).

The code is tested against two OpenTPS installations: the public release and the project's own checkout. They are not identical; in particular they carry different ROI rasterisation methods (Section 9, X10). Code that touches OpenTPS is checked against both, and the adapter dispatches where they differ.

| Requirement | OpenTPS module or class | What it supplies, and the constraint on its use |
|---|---|---|
| DICOM ingest | `io.dicomIO`: `readDicomCT`, `readDicomDose`, `readDicomStruct`, `readDicomPlan` | CT, RTDOSE, RTSTRUCT and RTPLAN as typed objects, for photon IMRT/VMAT and proton PBS. Three of the four readers return `None` on unrecognised input and `readDicomCT` returns a `NaN` spacing on a single slice; `extractor/ingest.py` raises on both (Section 3.4) |
| Bulk ingest | `io.dataLoader`: `loadData`, `readData` | Recursive directory scan with format detection, for a whole exported case |
| DIR, computed | `processing.registration.RegistrationMorphons` | Diffeomorphic registration; `compute()` returns a `Deformation3D`. Its argument order is the reverse of this project's, and its three settings select implementations (X2, X3, X5) |
| DIR, imported | `io.dicomIO.readDicomVectorField` | A DICOM deformable registration object, returned as a `VectorField3D` and converted to `Deformation3D` (Section 6.1) |
| Deformation as an object | `data.images.Deformation3D` | `deformImage`, `resample`, construction from a displacement field. The cached artefact of Section 6 |
| DVH and target metrics | `data.DVH` | Named dose metrics, `computeDx`, `computeVx`, `computeDcc`, and the cumulative histogram. `computeVx(x)` takes a percentage of the prescription and returns zero rather than raising where no voxel reaches it (Section 7). `maxDVH` must be set (Section 3.4) |
| ROI handling | `RTStruct.getContourByName`, `ROIMask.getVolume`, and either `ROIContour.get_partial_volume_mask` or `ROIContour.getBinaryMask` | Contour to mask on explicit geometry. The two installations provide different rasterisation methods, detected at call time by `roi_mask_algorithm()` (X10). `getVolume(inVoxels=False)` returns mm³, converted once in `roi_volume_cc` (X4) |
| Plan complexity | `data.plan`: `ProtonPlan`, `PlanProtonBeam`, `PhotonPlan`, `PlanPhotonBeam` | The descriptors of Section 8 for both modalities |
| Grid geometry | `data.images.Image3D` | `gridSize`, `spacing`, `origin`, `resample`, `resampleOn`: the working grid of Section 5 |
| Synthetic deformation, for testing | `processing.imageProcessing.syntheticDeformation` | Deforms an image and its ROI by a known amount: the ground truth of Section 3.3 |

Built here, since OpenTPS does not supply it: the TG-263 mapping and its enforcement, the export manifest, the provenance table, the crop and record form, and everything downstream in the evaluator and allocator.

**Deliberately not used: `processing.planEvaluation.robustnessEvaluation`.** Its scenario container carries setup and range error fields describing scenarios OpenTPS itself would generate, and its stored metrics (D95, D5, MSE) do not include V95%. Loading RayStation scenarios into it would attach a provenance claim that is not true. The reduction of Section 7.1 is written here instead, over DVHs computed with `data.DVH`.

### 3.2 The adapter boundary

OpenTPS objects are constructed at the point of use and are not persisted; the store holds native `tps5d` records (Section 5, X1). Two reasons.

- The classes concerned are thin. `Image3D` carries an array, an origin and a spacing, and `DoseImage` and `ROIMask` inherit from it, so reconstructing them from native records costs an adapter, not a translation layer. `Patient` is a session container with an event mechanism and is not a persistence format.
- Stored data must outlive an external package's class definitions, since MS13 is verified on implemented software and D4.1 is public. OpenTPS documents the hazard itself: `saveSerializedObjects` carries a `dictionarized` flag whose stated purpose is to avoid information loss in long-term storage when classes change.

All calls into `opentps` are confined to `extractor/adapters.py` and `extractor/ingest.py`, so the dependency surface is enumerable. Accepted consequence: extraction output is not directly loadable in the OpenTPS GUI, and visual inspection of a case requires an MHD export.

### 3.3 What can be tested before real data, and what cannot

**Testable now:** interface contracts, shapes and types; the crop and mask arithmetic; the content-hash cache; the TG-263 resolution rule, including that an unmapped structure raises; the provenance table; the manifest consistency check; ingest of synthetic DICOM files for all four readers.

**Testable with a constructed ground truth:** the registration path. `applyBaselineShift` deforms an image and its ROI by a known vector, so applying it, running Morphons and measuring the recovery tests both the DIR call and the direction convention of Section 6.2. An inverted direction fails with the wrong sign, which is visible. The residual of the round trip is a first quality measure of the registration.

**Not testable before real data:** whether the parser survives a real RayStation export; DIR performance on real abdominal anatomy, where bowel gas and sliding are the regimes in which registration fails and a smooth synthetic deformation is not representative; the true grid and mask dimensions; and whether CT, dose, masks and deformation fields share one axis convention across readers (evaluator 11.4). These are limitations of validation, not of implementation, and the assumptions they leave open are registered in Section 13.

### 3.4 Nothing is called with its defaults, and nothing fails silently

Several OpenTPS entry points this module depends on carry defaults that are wrong for it, and none fails loudly when the default is taken. The rule is therefore general: **every argument that changes a result is passed explicitly**, and the value passed is recorded. A default that is taken is a parameter whose value is recorded nowhere, which is the condition Section 12 exists to prevent.

| Entry point | Default or behaviour | Consequence if taken | What the adapter does |
|---|---|---|---|
| `ROIContour` mask methods | Geometry arguments optional | The mask is rasterised on an implicit geometry, so the working grid becomes a consequence of load order | Passes origin, grid size and spacing explicitly |
| `ROIContour.get_partial_volume_mask` | `binarization_threshold=None` returns a float partial-volume array | The storage schema requires boolean masks | Passes `binarization_threshold=0.5` and `precision` explicitly, where the method exists (X10) |
| `ROIContour.get_partial_volume_mask` | Does not raise when the grid does not contain the contour; logs instead, and the logging call itself is malformed and raises `TypeError` under eager formatting | A shifted or truncated mask, or an unrelated error | Checks physical containment from `polygonMesh` before the call |
| `DVH.computeDVH` | `maxDVH=100.0`, an absolute dose | Silent truncation of accumulated EQD2 on the hypofractionated arms (evaluator 7.2); on a cold plan, `computeVx(95)` indexes past the array | Sets `maxDVH` to `max(observed maximum, prescription) × 1.05` |
| `RegistrationMorphons` | `tryGPU=True`, `nbProcesses=-1`, `baseResolution=2.5` | Selects among different implementations, and coarsens every field | Passes all three explicitly (X2, X5) |
| `Deformation3D.deformImage` | Resamples the field itself when grids differ, choosing interpolation and fill value | An interpolation chosen elsewhere, logged only at INFO | Resamples the field explicitly beforehand (Section 6.1) |
| `Deformation3D.resample` | Mutates in place and returns `None` | Using the return value discards the field | Never uses the return value |
| `RTStruct.getContourByName` | Prints to stdout and returns `None` on a miss | An error several calls later | Raises `KeyError` naming the attempted name and the structures present (Section 9) |
| `readDicomDose`, `readDicomStruct`, `readDicomPlan` | Return `None` on unrecognised input: an unsupported pixel format, a missing `SeriesInstanceUID`, five unsupported plan configurations | An `AttributeError` several calls downstream | `ingest.py` raises at once, naming the file and, where identifiable, the reason |
| `readDicomCT` | Derives z-spacing as `(last − first)/(n − 1)` | `IndexError` on zero files; a `NaN` spacing on one file, which corrupts all downstream geometry silently | `ingest_ct` rejects both cases before the call |

### 3.5 Modules and tests

| Module | Contents | Tests |
|---|---|---|
| `extractor/records.py` | `DIRSettings` (with `content_hash`), `WorkingGrid`, `CropBounds`, `TargetMetrics`, `PlanComplexity`. No OpenTPS import | `test_adapters.py` |
| `extractor/adapters.py` | `get_dvf`, `target_metrics`, `extract_roi_mask`, `extract_roi_mask_by_canonical_name`, `roi_mask_algorithm`, `union_bounding_box`, `crop_to_bounds`, `roi_volume_cc`, `extract_plan_complexity` | `test_adapters.py`: registration against a synthetic-deformation ground truth, both DVF backends, target-metric unit conventions, mask extraction and its guards, crop arithmetic, plan complexity for both modalities |
| `extractor/ingest.py` | `ingest_ct`, `ingest_dose`, `ingest_struct`, `ingest_plan` | `test_ingest.py`: synthetic DICOM for all four readers (`tests/dicom_builders.py`), plus the `None`-return branches via substitution, since a valid file never exercises them |
| `extractor/roi_mapping.py` | `load_roi_mapping`, `resolve_dicom_name` | `test_roi_mapping.py` |
| `extractor/manifest.py` | `read_manifest`, `check_row_consistency`, `check_manifest`, `discover_and_load` | `test_manifest.py`, including discovery on synthetic RTPLAN and RTSTRUCT files |
| `extractor/provenance.py` | `ProvenanceRecord`, `ProvenanceTable` | `test_provenance.py` |

## 4. Plan identity and the export manifest

The store is keyed by (patient, block, plan), with arm, schedule, role and images. None of these are DICOM concepts. An RTDOSE carries a SOP instance UID and references to a plan and an image series; it does not carry "PT-A, block 2, rescue". The association must be supplied.

**The manifest is the authority.** One file per patient, written during plan generation, mapping each exported dose object to its place in the design:

    plan_uid | path | block_index | arm | role | source_image_uid | dose_image_uid | n_fx | dose_per_fx_gy | accept_nominal | accept_robust

- `arm` ∈ {XT-NA, XT-A, PT-NA, PT-A}; `role` ∈ {planned, rescue}.
- `source_image_uid` is the image the plan was generated on; `dose_image_uid` is the image this dose is computed on. They differ for a non-adapted plan recomputed on a repeat image, and coincide for a plan generated on the block's own image.
- `n_fx` and `dose_per_fx_gy` hold the schedule (n, d) as two columns, since a pair has no unambiguous single-field CSV representation; they are reconstructed as the pair on read.
- `accept_nominal` and `accept_robust` record the RayStation acceptance judgement for this plan on this block, nominal and robust (allocator 8.2; evaluator 6.1, 6.2).

The number of rows is not fixed in advance, since rescues depend on the anatomy. The planner, or a planning script, writes the manifest as each plan is generated and judged, so the rescue sequence of every non-adapted arm is recorded where it is decided. If plan generation is scripted, the script writes the manifest and its manual cost disappears (allocator decision 26).

**DICOM relations are the consistency check.** RTDOSE references its RTPLAN, which references its structure set and frame of reference. This check cannot verify arm, margin or role, which are not represented in DICOM. It verifies that each dose object is tied to the images the manifest assigns it, which is exactly the error a hand-written manifest produces: a row displaced by one. The extractor raises where the two disagree rather than preferring either.

`check_row_consistency` verifies, collecting all disagreements into one exception:

- `dose.referencePlan == plan.sopInstanceUID`;
- the manifest's `plan_uid == plan.sopInstanceUID`;
- `plan.frameOfReferenceUID == struct.frameOfReferenceUID`, with the frame of reference standing for the image (X8).

**What this check cannot verify for recomputed doses.** For a non-adapted plan recomputed on a repeat image, the referenced plan is the pCT plan, so the plan's frame of reference is the pCT's on every block. The chain above therefore cannot tell block 2 from block 3 of the same non-adapted arm, and these rows, which share one plan UID, are the ones most prone to displacement. The check must compare `dose_image_uid` against the dose object's own frame of reference or referenced image rather than the plan's. How that is read depends on the route by which RayStation recomputes a plan on a repeat image (allocator decision 30); it is implemented once an export can be inspected.

**Discovery.** A manifest row's `path` names the dose file. `discover_and_load` finds the row's plan and structure set in the same directory, by following `dose.referencePlan` and `plan.referencedStructureSetSequence` to matching `SOPInstanceUID`s, with an explicit search directory as an override (X11). It is the one manifest function that loads DICOM, through `ingest.py`.

## 5. Dose storage

Three rules, the first two lossless for the endpoints in use.

**Store block-level distributions, not strategy-level accumulated ones.** A strategy's accumulated dose is a sum over its blocks, so composition at evaluation time is cheap. Block-level storage also lets a composition be re-weighted or re-sequenced without re-extraction, which the first-block investigation of allocator 4 relies on.

**Crop to the union of contoured structures; keep the masks separate.** Which ROIs are relevant is determined by the endpoint selection (allocator decisions 10 and 19). Masking to the union the currently active models require would fix that choice in the stored data, and an OAR added once the site is settled would force re-extraction of the whole cohort. The rule is therefore: crop the dose to the bounding box of all contoured structures plus the target, and store per-ROI boolean masks on the same crop. Stored arrays stay rectangular, which keeps deformation and resampling simple. The crop is wider than any metric needs; its cost is measured on the first exported case, and if it proves large the crop can be narrowed without an interface change, since the masks already carry the per-ROI restriction (X4).

`union_bounding_box` takes inclusive bounds per axis and checks that masks share a grid before their union is taken, since a silent mismatch would crop the wrong physical region. `crop_to_bounds` preserves the cropped object's type (`DoseImage`, `ROIMask`, `CTImage`) through each class's own `copy()`; the shared `Image3D.copy()` would return a plain `Image3D` and drop `referencePlan` and `referenceCT`.

**The working grid is an explicit parameter.** Dose leaves RayStation on the plan's scoring grid, while ROI masks are generated from contours defined on the CT geometry. The two do not in general coincide, so either the dose is resampled onto the CT grid, the masks are generated on the dose grid, or both are placed on a third grid. The choice is not neutral. Resampling the dose at ingest introduces an interpolation upstream of everything, in the high-gradient region where a small-volume-parameter gEUD draws its weight, which is the error the accumulation ordering (evaluator 4) is arranged to avoid. Generating masks on a coarser dose grid instead changes the discretised organ volume, to which V95% and gEUD are both sensitive. The ratio of the two spacings is not known before the first export, so the choice is not made here. What is fixed is that the working grid is recorded in every plan record and is a parameter of extraction, and that the difference in gEUD between the two routes is measured once on the first case (X5).

**Store physical dose on native geometry. Do not store EQD2, and do not store warped dose.**

- EQD2 depends on dose per fraction, and fractionation is a decision variable. Storing EQD2 would fix one schedule in the data and silently invalidate every alternative.
- The conversion to BED is performed before deformation, because it is nonlinear and does not commute with interpolation. The warped object is therefore a BED field, which depends on the schedule, the block's fraction count and the structure's α/β, and is not unique. Warped fields belong to the evaluator's cache, not to the extractor's store.

The extractor stores physical dose per fraction per block on its own image, with the fraction counts and the deformation fields. Everything downstream is recomputable.

**Dose provenance.** Physical dose is computed in RayStation for both modalities and imported; OpenTPS performs no dose calculation for this study, including no use of its photon CCC implementation (evaluator E16; allocator decision 25).

**Record form, fixed now; container, fixed after measurement.**

    dose_crop      # float32[nx, ny, nz], physical dose per fraction, cropped
    roi_masks      # bool[nx, ny, nz] per ROI, canonical names, same crop
    grid           # origin, spacing, grid_size of the working grid
    bbox           # index bounds of the crop within the working grid
    n_fx           # fraction count of the schedule this plan belongs to
    units          # dose units and RBE weighting as exported (X9)

Access goes through `store_plan` and `load_plan`, so the on-disk container is a substitution rather than a rewrite. A serialised OpenTPS structure is excluded by X1. MHD holds a full rectangular array with no native notion of an accompanying mask, though it remains the format for exporting a case for visual inspection. `npz` per plan and HDF5 per patient both represent the record directly; HDF5 adds chunked partial reads and hierarchical keys, which matter only if a single array does not fit in memory. The container is fixed once grid dimensions and masked volumes are measured on the first exported case.

## 6. Conversion and caching

| Stage | Owner | Cost | Cached | Invalidated by |
|---|---|---|---|---|
| Ingest: DICOM to internal | Extractor | High, once | Yes | Source files |
| Register: deformation fields | Extractor | High | Yes, as a first-class artefact | DIR backend and settings |
| Convert to BED, warp, accumulate | Evaluator | Moderate | Yes | Fields, fraction counts, α/β, schedule |
| Reduce to DVH | Evaluator, via the OpenTPS DVH | Low | Yes. This is the cache boundary | Accumulated field, ROI mask |
| NTCP | Evaluator | Low | Never | Recompute |

Deformation fields are cached explicitly, keyed by moving image, fixed image and a hash of the DIR settings. They are the expensive and version-sensitive step, and caching warped dose without recording the field that produced it makes staleness impossible to reason about. The evaluator applies each field several times, once per (schedule, α/β) combination, so the separation between registration and application is load-bearing: registration is performed once, application is cheap.

Caches are keyed by content hash rather than by filename, and the hash is recorded in the provenance table.

### 6.1 Where the deformation field comes from

The accumulation ordering (evaluator 4) converts dose to BED before deformation, so the field must be applied in OpenTPS to BED arrays, not by RayStation's own dose mapping, which deforms physical dose. The field itself can come from either of two backends behind one interface:

    get_dvf(*, moving, fixed, settings, working_spacing) -> Deformation3D

- **Computed** in OpenTPS with Morphons. This is the backend in use: the field has to be applied in OpenTPS anyway, and computing it there does not depend on RayStation exporting its registration (X12).
- **Imported** from a RayStation deformable registration object, read by `readDicomVectorField`. The reference study mapped dose with RayStation's DIR, so this backend is kept for continuity with it.

Both are implemented, and both return a `Deformation3D` resampled onto the working grid, so callers cannot tell them apart. The study does not need to reproduce the reference study's registration, but the difference the two backends produce in gEUD on the organs driving the endpoints is measured on the first cases and reported, which converts a choice of registration provenance into evidence (X2).

**The imported field is converted.** `readDicomVectorField` returns a `VectorField3D`, which shares no interface with `Deformation3D`: `deformImage` takes an image object, `VectorField3D.warp` takes a bare array, and neither class inherits from the other. `Deformation3D().initFromDisplacementField(vector_field)` builds the `Deformation3D` from the field's own origin, spacing and angles. The conversion is tested on a synthetic DICOM deformable registration object with a known uniform displacement, recovered after conversion and resampling. `DIRSettings.imported_path` names the file to read, is validated at construction, and `moving` is unused on this path.

**The arguments are keyword-only.** `RegistrationMorphons(fixed, moving, ...)` takes the two images in the opposite order to the interface above, positionally and of the same type. A transposition would not raise; it would return a plausible field in the wrong direction. Keyword-only arguments make the transposition unexpressible. The test of Section 3.3 remains necessary.

**The Morphons settings select implementations, not speeds.** `tryGPU` selects between the cupy implementation and the CPU loop; `nbProcesses > 1` selects a different convolution routine; `baseResolution` sets the ladder of scales. No numerical agreement is guaranteed within any pair. All three enter the settings hash, read from the settings passed in rather than from the registration object, which rewrites a negative `nbProcesses` in place and would otherwise make the hash machine-dependent. The GPU path is entered under a bare `except` that logs at INFO, so any failure degrades silently to CPU; passing `tryGPU=False` makes the path a choice.

**`nbProcesses = 1`.** The parallel path was slower at every grid measured: 10.7 s against 8.3 s at 3.0 mm, 16.2 against 14.0 at 2.0 mm, 15.8 against 14.5 at 1.5 mm. Windows spawns rather than forks, so each worker re-imports OpenTPS. The parallel branch is never taken, which removes one implementation pair rather than fixing a value in the hash.

**Registration cost does not constrain the working grid.** A registration took 14.0 s at 2.0 mm and 14.5 s at 1.5 mm, for 2.2 and 5.3 Mvoxel. The work lives on the ladder's grids, set by `baseResolution`, not on the image grid. With registrations equal to patients times blocks, arms sharing the images, twenty patients at three blocks is sixty registrations, well under an hour in total, computed once and cached. The cohort size and block count are illustrative (allocator decision 23); the order of magnitude is what the estimate carries.

**The field has its own grid, bounded by two floors.** Morphons runs a fixed ladder of scales, `baseResolution` × [11.31, 8, 5.66, 4, 2.83, 2, 1.41, 1], and stops before a scale finer than the fixed image. The returned field carries the finest scale still at or above the working-grid spacing. On a 300 × 300 × 200 mm phantom at the 2.5 mm default, a 3.0 mm working grid returns a 3.54 mm field, and 2.0 mm and 1.5 mm grids both return 2.50 mm. The field is never finer than the working grid and can be coarser by up to a factor √2.

- **`baseResolution` below the working-grid spacing is excluded.** At a 2.0 mm grid, 1.5 mm costs 38.3 s against 28.9 s at 2.0 mm and returns a coarser field, 2.13 mm against 2.00 mm, because the final rung is cut off by the working grid.
- **`baseResolution` equal to the working-grid spacing is the working setting.** The last rung then lands on the grid, giving the finest field the ladder can deliver. Whether that is worth its cost against a coarser setting depends on what field resolution costs in gEUD on real anatomy, which is measured on the first case (X5).

The adapter resamples the returned field explicitly onto the working grid and never uses what `compute()` returns as it stands.

### 6.2 Direction of the deformation

The evaluator warps each block's BED field **onto the planning CT**. The block field lives on that block's repeat image, so the result must come out on the pCT grid. Getting this backwards is not free to undo, since inverting a diffeomorphic field is neither exact nor cheap.

The convention is **fixed = pCT, moving = rCT_j**, for every registration in the pipeline (X3). It is stated by the operation rather than by the name of the field: `Deformation3D.deformImage(moving)` returns an image on the fixed grid, as the Morphons implementation shows by naming its result `<moving>_registered_to_<fixed>`. OpenTPS labels the field "deformation from moving to fixed" while the field is defined on the fixed grid and points into the moving space; both describe the same object. Since the required output is on the pCT grid, the pCT is the fixed image.

## 7. Target metrics

Target coverage gates the design: a plan below the acceptance criterion would not be delivered (allocator 8.2). The judgement is made in RayStation at plan generation and recorded in the manifest; the evaluator verifies it on the exported dose (evaluator 6.1). The extractor supplies the metrics that verification needs.

Coverage cannot be inferred from NTCP. If the target shifts away from an OAR between pCT and rCT, the non-adapted plan underdoses the CTV while the OAR dose falls, so coverage fails and NTCP improves. NTCP is a function of OAR dose only and carries no information about the target.

**Metrics are per block and per plan, on the image the dose is computed on.** Coverage is a property of a plan delivered on a given anatomy, so the judgement is made where the plan is delivered. No registration, deformation or accumulation is required to produce these metrics.

Four requirements:

- **Nominal per-block metrics** for every plan.
- **Worst-case per-block metrics** from the robustness evaluation, where exportable, and the robust acceptance outcome recorded at plan generation in any case (`accept_robust`, Section 4). They are descriptive, and never accumulated (Section 7.1).
- **The photon arms are included.** Photon dose is recomputed on the repeat images and judged on the same criterion (allocator A10).
- **Rescue plans are extracted like any other plan.** Each rescue is an additional plan with its own metrics and dose grid, so the number of plans per (patient, arm) is variable, and each plan record carries its role and its images (Section 4).

**The criterion is the plan acceptance protocol used at treatment planning.** The metric list runs in two directions that are kept apart. **Target metrics**, V95% and D5 on the target, extend the criterion along the axis it already measures. **OAR metrics**, Dmean and Dmax on the organs driving the endpoints, are extracted regardless, because they are useful descriptively; whether they enter the criterion is a separate decision that changes what the primary endpoint means. Which metrics to request is allocator decision 7b.

**The prescription a plan is measured against is its own schedule's, and the units are fixed.** `DVH.computeVx(x)` takes `x` as a percentage of the prescription passed to the DVH constructor, so V95% is meaningless until two things are fixed.

- **Whose prescription.** It belongs to the schedule, not to the patient. A standard and a hypofractionated schedule differ in total dose as well as in fraction count, so a single per-patient prescription is undefined once a patient carries plans in both. Each plan is measured against the prescription of its own schedule. V95% is therefore schedule-relative, which is correct: the criterion asks whether a plan delivers what it was prescribed. Arms become commensurable downstream, in EQD2 and NTCP.
- **Which dose.** The store holds physical dose per fraction (Section 5). A course prescription against a per-fraction dose would put every plan at a few per cent of prescription and return V95% of zero for the whole cohort without raising. The convention adopted is **course dose against course prescription**: the stored dose is multiplied by the schedule's fraction count and measured against the schedule's total prescription, which matches how coverage is judged at planning. It is enforced in the adapter, since a test written in the same units as the code cannot detect the error.

The prescription is an extraction-side quantity only. The DVH the evaluator takes is on accumulated EQD2, where a percentage of prescription has no meaning.

### 7.1 Worst-case storage requires no dose grids

Worst-case metrics are per block, never accumulated (evaluator E5), and therefore never deformed or composed. Their only use is to produce metrics on the plan's own image, so the store needs no worst-case dose grids, which removes what would otherwise be the largest multiplier in the module: one grid per scenario per plan.

What is stored instead is the **per-scenario DVH per ROI**, with the derived scalars, where the export provides them (X7). A DVH contains the (volume, dose) pairs from which any DVH-derived metric can be recomputed, and a stored scalar cannot, so a change of criterion under decision 7b is not a re-extraction. The declared cost is that anything not derivable from a DVH is lost, in particular the spatial location of a hot or cold region.

**Physical scenarios are preferred to voxel-wise aggregates.** RayStation offers both individual scenario doses and voxel-wise minimum or maximum distributions. The minimum over physical scenarios of the target D95 is the D95 of the worst scenario, a quantity with a referent. The D95 of a voxel-wise minimum field is more pessimistic and corresponds to no deliverable scenario, since it combines different scenarios at different points. The physical form also determines the aggregate, while the reverse is impossible. If an aggregate is used as well, the difference between the two definitions is computed once on one case and reported.

## 8. Delivery time

The mapping from a plan to minutes splits in two, and only the first half is extractable.

**From the plan:** number of fields, energy layers per field, spots per layer, total MU, target volume. For pencil beam scanning the dominant term is energy-layer switching, so layer count is the main predictor and spot count secondary.

`extract_plan_complexity` dispatches on `isinstance(plan, ProtonPlan | PhotonPlan)` rather than on a label supplied separately, so a plan mislabelled in the manifest raises instead of returning zeros. `n_fields` reads `RTPlan.beams`, defined on the shared base class. Proton `n_layers` is summed per beam, since only `numberOfSpots` and `meterset` are plan-level aggregates. Target volume comes from the target mask through `roi_volume_cc`, not from the plan, and the caller composes the two.

**The photon side requires nothing further.** Photon delivery is unconstrained, and the photon adaptation budget is charged only Δτ_XT, an independent variable of the study rather than a quantity derived from a plan.

**Not in the plan:** the machine constants that convert those counts into minutes, and the non-delivery components entirely. Contouring, re-optimisation and QA time have no representation in a plan file. The extractor therefore supplies complexity descriptors, and the mapping from descriptors to minutes lives in a separate configuration with machine constants as named parameters, so recalibrating for a beamline does not touch extraction. If RayStation reports an estimated delivery time per plan, it is taken directly and tagged as vendor-estimated in the provenance table: a model rather than a measurement, but a machine-aware one.

Complexity is extracted per plan, since only the difference between arms enters Δτ. Two effects are kept separate: margin reduction shortens delivery through fewer layers and spots, while hypofractionation lengthens the individual fraction through higher MU and shortens the course.

## 9. ROI naming and rasterisation

Canonical names follow **TG-263**, the AAPM standardised nomenclature for radiotherapy structure names, which RayStation supports. The NTCP model registry must be able to name what it wants: a rectum model asks for `Rectum`, not for whatever the structure is called in each plan.

The resolution rule is deliberately not fuzzy matching, which fails silently and produces a plausible number from the wrong organ.

- Normalise mechanically: strip whitespace, casefold.
- Look up in an explicit per-cohort mapping file, `canonical_name,dicom_name`, versioned in the repository, with its content hash computed on load and recorded in the provenance table.
- **An unmapped structure raises.**

Matching is on the normalised form, but the value returned is the contour's own name, since the OpenTPS calls it feeds compare exactly. Two failures raise with different messages: a canonical name absent from the mapping file means a row must be added; a canonical name in the mapping but matching no contour in a patient's RTSTRUCT is a data problem for that patient.

OpenTPS provides no mapping and no raise: `getContourByName` prints and returns `None` on a miss (Section 3.4), so the raise is this project's wrapper. The contents of the mapping file need a real RTSTRUCT or a template from the clinical partner. The mechanism is built now; `config/roi_mapping.csv` ships as a header-only placeholder.

**Rasterisation depends on the installation.** The public OpenTPS release provides `get_partial_volume_mask`, a partial-volume method binarised at a threshold. The project's checkout does not; its `getBinaryMask` is a hard polygon fill with no threshold. On an identical synthetic cylinder the two differ by about 35 per cent in masked volume. `extract_roi_mask` detects which is present through `roi_mask_algorithm()` and dispatches, and raises if `binarization_threshold` or `precision` are set where they would be ignored. The polygon-fill method returns `imageArray=None` on a contour confined to a single slice; `extract_roi_mask` raises on that case. Which method produced a mask changes the number, so it is recorded in the provenance table (X10).

## 10. Relation to the NTCP model registry

The registry belongs to the evaluator (evaluator 8). Two obligations remain here.

**Cohort validation before dose work.** Given the active model list, the union of required ROIs, dose metrics and clinical covariates is collected and the cohort validated against it at assembly. A missing covariate surfaces before hours of registration and accumulation rather than after. The union of required ROIs is resolved against the mapping file at the same point, so an unmapped structure raises there. Since the crop is wider than this union, a later addition to the model list is a validation failure fixed by mapping lines, not a re-extraction.

**Sizing the composition workload.** The number of distinct α/β values in the registry determines how many warped fields per block the evaluator requires. The extractor reports it, so the storage and compute estimate is available before the pipeline runs.

## 11. Schema

**Per patient**

| Field | Content |
|---|---|
| pid, site | Identifiers |
| hypo_eligible | Clinical eligibility flag fixing the XT-NA schedule (allocator A32). May become a richer per-patient photon indication once the clinicians answer allocator decision 31 |
| covariates | As required by the NTCP model registry |
| imaging | pCT, repeat images, acquisition timestamps |
| rois | TG-263 canonical names, through the mapping file |
| grid | Working-grid geometry, crop bounds, per-ROI masks |
| manifest | The export manifest (Section 4) |

**Per (patient, block, plan)**

| Field | Content |
|---|---|
| arm | XT-NA, XT-A, PT-NA or PT-A |
| modality, technique | Derived from the arm; technique has one value per modality |
| robustness | Setup and range error. Determined by the arm, not free: the adapted arms carry the reduced setting, the non-adapted arms and their rescue plans the clinical one |
| fx_scheme | (n, d) and the protocol identifier |
| role | planned or rescue |
| source_image | The image this plan was generated on |
| dose_image | The image this dose is computed on |
| accept_nominal, accept_robust | The RayStation acceptance judgement on this block |
| dose | Physical dose per fraction, cropped, on the working grid |
| target_metrics | D98, D95, V95% and the rest of the requested list, nominal, on this block |
| plan_complexity | n_fields, n_layers, n_spots, MU, target volume |
| robust_eval | Per-scenario DVH per ROI and derived scalars, where exportable. No dose grids (Section 7.1) |

**Per (patient, block, schedule):** n_b, the fraction count of the block, derived from acquisition dates or set by hand and tagged `assumed` (evaluator E21).

**Per registration:** dvf, keyed by (moving, fixed, hash of the DIR settings).

**Per (patient, schedule):** fx_scheme (n, d) and rx_dose, the total prescribed dose. Indexed by patient as well as schedule, so that it survives either answer to whether the prescription varies by patient (Section 14).

**Per facility**

| Field | Content |
|---|---|
| cap_pt_min_day | Proton machine minutes per day |
| cap_xt_min_day | Photon adaptation minutes per day. Swept, not measured: a study parameter held in the facility record (allocator A20, decision 13) |
| days_week, uptime, n_rooms, beam_topology, staff_avail | Operating model (allocator decision 3) |

## 12. Provenance

Every metric and every model parameter carries a tag recording whether it is measured, taken from a named publication, assumed or swept. The allocator's output is a difference of small probabilities, so sensitivity to parameter uncertainty is worth studying, and the tag is what makes the set of parameters to perturb enumerable rather than hand-maintained.

**Dose is tagged RayStation-computed**, for both modalities (Section 5). The engine and the cross-modality reporting conventions are allocator decision 25.

### 12.1 Form

The requirement is **enumerability**: the set of parameters to perturb must be listable by query. A tag scattered through every record satisfies the wording and not the requirement, since enumerating would mean traversing the whole store. Provenance is therefore a separate table of declarative records, following the pattern of the evaluator's model registry:

    ProvenanceRecord(
        key,           # e.g. 'dose:pt12/b1/PT-A/std/planned'
        kind,          # 'measured' | 'published' | 'assumed' | 'swept'
        source,        # 'RayStation <engine>' | 'Michalski 2010 QUANTEC' | 'X9'
        content_hash,  # links to the stored object (Section 6)
    )

Where `kind` is `assumed`, `source` names an assumption ID from Section 13 or from the allocator and evaluator registers, so the assumptions register is checkable against the data rather than parallel to it.

`extractor/provenance.py` implements this as `ProvenanceRecord` and `ProvenanceTable`. `table.query(kind='assumed')` returns the complete list of assumed parameters. `add` raises on a key already present, since two records for the same primitive most likely mean the same quantity was tagged from two call sites; `update` is the explicit method for a deliberate re-extraction. `write_csv` and `read_csv` persist a table, and `read_csv` raises on a duplicate key as `add` would. The module does not decide which quantities are primitives; that is the caller's judgement, following Section 12.2.

### 12.2 Granularity

Tagging every metric produces thousands of near-identical rows and hides the few that matter. Quantities therefore divide into **primitives**, which have a source of their own, and **derived** quantities, which inherit from their inputs. Only primitives are tagged, which keeps the table at the order of tens of rows per patient.

**Primitives:** dose arrays; image and grid geometry; ROI masks, the mapping file and the rasterisation method that produced each mask (X10); facility constants; NTCP model parameters; swept study parameters; the export manifest; the prescription; the block fraction counts n_b; the DIR settings; the OpenTPS commit hash.

- **The prescription** is not in the dose file and must be supplied. `computeVx` divides by it, so V95% depends on it linearly, and a plan evaluated against the wrong prescription yields a plausible number.
- **n_b** is derived from acquisition dates, or set by hand where the dates do not determine it; a hand-set value is tagged `assumed`.
- **The DIR settings** select implementations (X2).
- **The OpenTPS commit hash**, not the version string: two checkouts reporting the same version can differ, and with MS13 verified on implemented software this is the difference between a reproducible result and one that is not.

**Derived:** D98, D95, V95%, gEUD, DVHs, accumulated dose, occupancies. The list of primitives is revised as the schema settles.

## 13. Assumptions register

The allocator uses the prefix A and the evaluator E; this document uses **X**. Where an assumption mirrors one in another document, the other is named rather than restated.

| ID | Assumption | Status | Risk |
|---|---|---|---|
| X1 | OpenTPS objects are constructed at the point of use and never persisted; the store holds native `tps5d` records | Design decision (Section 3.2) | The adapter must track OpenTPS API changes. Confined to two modules by construction |
| X2 | The deformation field comes from one of two backends behind `get_dvf`: Morphons in OpenTPS, the backend in use, or a RayStation field imported and converted to `Deformation3D`, kept for continuity with the reference study. Morphons runs with `tryGPU=False`, `nbProcesses=1` and `baseResolution` equal to the working-grid spacing, all three in the settings hash | Both backends implemented and tested, the imported one on a synthetic DICOM file. Morphons settings benchmarked (Section 6.1) | Neither backend has a known accuracy in the abdomen. The gEUD difference between them is measured on the first cases; if material, the choice is reported as a sensitivity rather than a convention. Reading a real RayStation export is untested (X12) |
| X3 | Every registration uses fixed = pCT, moving = rCT_j | Convention (Section 6.2), verified by the synthetic test of Section 3.3 | An inverted direction produces a plausible accumulated dose that is wrong. The test is what prevents this from being silent |
| X4 | Dose is cropped to the bounding box of all contoured structures plus the target, wider than the union the active NTCP models require. Masked volumes are converted from mm³ to cc in one place, `roi_volume_cc` | Implemented and tested (Section 5) | Storage cost is unmeasured; if large, the crop narrows without an interface change. A caller reading `getVolume()` directly would report a volume 1000 times too large |
| X5 | The working grid is an explicit parameter; whether dose is resampled to the CT grid or masks generated on the dose grid is not decided. The deformation field has a third grid, bounded by `baseResolution` and the working grid | Deferred to measurement on the first exported case (Section 5). The two floors and the exclusion of `baseResolution` below the working grid are measured (Section 6.1) | Resampling dose at ingest interpolates where the gEUD draws its weight; masks on a coarse grid change the discretised volume. Directions known, sizes not. `baseResolution` equal to the working grid is adopted because it removes a free parameter, and is compared against a coarser setting on the first case |
| X6 | Worst-case is stored as per-scenario DVHs per ROI plus derived scalars, and not as dose grids | Follows from evaluator E5 (Section 7.1) | Anything not derivable from a DVH is lost, in particular spatial location |
| X7 | RayStation can export scenario doses, or per-scenario DVH data, in a form the extractor can read | **Unverified.** The conformance statements consulted name the beam set dose and not evaluation or scenario doses; some export capability is documented as available only in non-clinical versions | The robust acceptance outcome is recorded at plan generation regardless (Section 4), so the descriptive counts survive. Scenario DVHs would be lost, or would describe voxel-wise aggregates rather than scenarios. If recomputed doses on repeat images are also evaluation doses, the same question applies to them (allocator decision 30) |
| X8 | Plan identity (arm, block, role, schedule) comes from the export manifest; DICOM relations serve as a consistency check, with the frame of reference standing for the image | Implemented for the plan and structure-set chain (Section 4). The check on `dose_image_uid` for recomputed doses depends on decision 30 | The manifest is hand-written unless planning is scripted. The frame-of-reference convention is unverified: if RayStation registers repeat CTs into a shared frame of reference, the check passes rows it should not. For recomputed doses the plan chain cannot distinguish blocks (Section 4) |
| X9 | RayStation export conventions (dose units, RBE weighting, dose-to-water or dose-to-medium, grid origin, structure naming, file layout) are as the parser assumes | **Unverified.** No export has been inspected | A wrong assumption is likely to fail loudly on units and file layout, and silently on RBE weighting and dose-to-medium. Depends on allocator decision 25 |
| X10 | ROI masks use `get_partial_volume_mask` binarised at 0.5 where OpenTPS provides it, and the polygon-fill `getBinaryMask` where it does not, detected at call time | Design decision (Sections 3.1, 9). The dispatch and the 35 per cent volume difference are measured against both installations | Which method runs changes masked volumes on the same contour. Neither is sensitivity-tested on real anatomy. The method is recorded per mask in the provenance table |
| X11 | A manifest row's `path` names the dose file; its plan and structure set are found in the same directory by following `SOPInstanceUID` references | Design decision within this project's control, since whoever writes the manifest controls where the files live (Section 4) | Tested only on directories the project's own tests populate. If a real export groups files differently, the explicit search-directory override is used and the default revisited |
| X12 | RayStation exports a DICOM deformable registration object for each pCT–rCT_j pair, in the form `readDicomVectorField` reads (`DeformableRegistrationSequence` → `DeformableRegistrationGridSequence` with position, resolution, dimensions and vector data) | **Unverified.** The conversion that consumes it is implemented and tested on a synthetic file | If the object is not exported, or its tags are populated differently, the imported backend fails at the read, in `readDicomVectorField` itself. Morphons remains available |

X7, X8, X9, X11 and X12 close only on the first real export.

## 14. Open items

- **One measurement session on the first exported case**: dose grid dimensions and masked ROI volumes, which fix the storage container; the crop-versus-mask ratio (X4); the grid ratio and the two working-grid routes (X5); `baseResolution` at the working-grid spacing against a coarser setting; the gEUD difference between the two DVF backends (X2); the sensitivity of the masking method on real contours (X10); and the axis convention across readers (evaluator 11.4).
- Whether RayStation exports scenario doses or scenario DVHs, and whether that depends on the licence tier (X7).
- The route by which RayStation recomputes a plan on a repeat image, which fixes how `dose_image_uid` is verified (allocator decision 30, X8).
- Whether repeat CTs receive distinct frames of reference in a RayStation export (X8), whether plan and structure set sit beside their dose file (X11), and whether the deformable registration object is exported (X12).
- Machine constants for the delivery-time model, or confirmation that the RayStation estimate is usable (allocator decision 3).
- The plausible range of Δτ_XT, which sets the sweep range. A question for the photon department (allocator decision 12); it does not block extraction.
- The contents of the TG-263 mapping file, which needs a real RTSTRUCT or a template from the clinical partner.
- The source of contours on the repeat images (allocator decision 29).
- Whether the prescription (D, n) for a schedule is a cohort constant or varies by patient, for instance with proximity to an organ at risk. It goes to the same clinical partners as decision 7b, and does not block extraction: the indexed form of Section 11 survives either answer.

# Extraction Module

Version 5.3. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

**Sections were renumbered at version 5.0** so that the document follows the order of the pipeline. Provenance moves from 11 to 13, and the vacant 12 to 14 of earlier versions are gone. The mapping from the old numbering is in `CHANGELOG.md`; external references in `STATE.md` and `evaluator_design.md` are updated in the same round.

## 1. Purpose and scope

The **extractor** gathers the per-patient, per-plan and per-facility quantities the downstream modules consume. Its scope is defined by their requirements.

Its consumer is now the **evaluator**, not the allocator. The evaluator composes blocks into strategies, converts to EQD2, evaluates NTCP and applies the admissibility screens. The extractor performs none of these. It produces the raw material and the registrations, and stops.

**The extractor’s unit is the plan, not the strategy.** A strategy is a combination of per-block plans, and combinations are formed downstream. The distinction keeps the storage requirement linear in the number of blocks. At version 5 it also avoided an exponential growth in the strategy count; that growth no longer exists, and the linearity now rests on the simpler fact that each block contributes two plans however strategies are formed.

Section 3 states which parts of the pipeline are taken from OpenTPS and which are built here, and is the implementation strategy for the module. Section 14 is this module’s assumptions register.

## 2. The central interface decision

The extractor emits **dose-derived quantities**. NTCP is evaluated downstream. Three reasons:

- *Model swapping.* NTCP models will change. With scalars, replacing the bowel placeholder requires re-running the whole extraction pipeline; with dose, it requires changing one record.
- *Uncertainty propagation.* Propagating uncertainty in LKB parameters requires thousands of NTCP re-evaluations with perturbed n, m and TD50. This is impossible from a stored scalar.
- *Composition.* NTCP is nonlinear, so the NTCP of a partially adapted course cannot be obtained by combining the NTCPs of adapted and non-adapted courses. Dose must be composed first and NTCP evaluated once at the end.

**Consequence for storage.** Mean dose is additive across blocks, so per-block mean doses suffice for mean-dose-driven endpoints. gEUD with a volume parameter other than unity is **not** additive: the gEUD of an accumulated dose cannot be reconstructed from the gEUDs of its parts. The voxel grid is therefore required, not optional.

## 3. Implementation strategy

### 3.1 What is taken from OpenTPS

The mapping below was checked against the installed environment on 11 September 2026: **OpenTPS 3.0.0**, all 34 entries present, signatures read. Two qualifications. The installation is a source checkout rather than a distribution, so the version string does not identify a state of the code and the **commit hash** is what provenance records, per Section 13.2. And the refactor in progress is not yet pushed, so the API below is the API in hand and is re-checked when it lands.

Presence was never the question. Reading the signatures, then the Morphons source, then benchmarking it changed the design in three places, recorded at X2 and X5 and in Section 7, and the corrections are carried in the rows below and in those sections rather than left in a note.

**Writing `adapters.py` against this table found four more, at version 5.2.** `ROIContour.getBinaryMask` is deprecated in the installed OpenTPS and forwards to `get_partial_volume_mask`, called here directly instead: X10. `RTStruct.getContourByName` does not raise on a miss, it prints to stdout and returns `None`; the "unmapped structure raises" rule of Section 9 is therefore this project's own wrapper, not anything OpenTPS provides. `ROIMask.getVolume(inVoxels=False)` returns mm³ despite the name, not cc: X4. And `get_partial_volume_mask` itself logs, rather than raises, when the working grid does not physically contain a contour, and that internal logging call is malformed and throws `TypeError` under some logging configurations rather than printing, confirmed under `pytest`'s own log capture; the adapter checks containment itself, before the call, rather than trusting it.

**Version 5.2's code was verified only against the public OpenTPS 3.0.1, and version 5.3 is what happened when it met the project's own checkout.** `get_partial_volume_mask` does not exist there: `ROIContour` carries `getBinaryMask` and `getBinaryMask_old`, and `getBinaryMask` is a hard polygon fill with no threshold or precision concept of any kind, not a deprecated wrapper. `AttributeError` on the first run against the real environment. `extract_roi_mask` now detects which is present, via `roi_mask_algorithm()`, and dispatches rather than assuming; a caller who overrides `binarization_threshold` or `precision` on an environment where they would be silently ignored gets a raised error instead. Detail in Section 9 and X10.

| Requirement | OpenTPS module or class | What it supplies |
|---|---|---|
| DICOM ingest | `io.dicomIO`: `readDicomCT`, `readDicomDose`, `readDicomStruct`, `readDicomPlan` | CT, RTDOSE, RTSTRUCT and RTPLAN as typed objects. `readDicomPlan` covers photon IMRT and VMAT and proton PBS, so both modalities are served |
| Bulk ingest | `io.dataLoader`: `loadData`, `readData` | Recursive directory scan with format detection, for a whole exported case |
| DIR, computed | `processing.registration`: `Registration`, `RegistrationMorphons`, `RegistrationDemons` | Morphons is the diffeomorphic algorithm the OpenTPS white paper presents as its reference DIR. `RegistrationMorphons(fixed, moving, baseResolution, nbProcesses, tryGPU)`; `compute()` returns a `Deformation3D` and sets `self.deformed`. The argument order is the reverse of this project's, and the three settings are not interchangeable defaults: X2, X3, X5 |
| DIR, imported | `io.dicomIO.readDicomVectorField` | A DICOM deformable registration object as a vector field, for the importing backend of Section 6.1 |
| Deformation as an object | `data.images.Deformation3D` | `deformImage`, `inverse`, `resample`, construction from displacement or velocity. This is the cached first-class artefact of Section 6 |
| DVH and target metrics | `data.DVH` | `Dmean`, `D98`, `D95`, `D50`, `D5`, `D2`, `Dmin`, `Dmax` as named properties; `computeDx`, `computeVx`, `computeDcc`; the dose and volume arrays as `histogram`. `computeVx(x)` takes `x` as a percentage of the prescription and returns zero rather than raising where no voxel reaches it, so V95% is `computeVx(95)` on a DVH built with `prescription=`. E10 of the evaluator document. Two constraints on use in Section 3.4 |
| ROI handling | `data.images.ROIMask.getVolume`, `RTStruct.getContourByName`, and **either** `ROIContour.get_partial_volume_mask` **or** `getBinaryMask`, detected at call time via `roi_mask_algorithm()` | Contour to mask with explicit geometry. Two OpenTPS implementations exist across the environments this project runs in, confirmed neither present nor equivalent to the other: the public OpenTPS 3.0.1 deprecates `getBinaryMask` in favour of `get_partial_volume_mask`, while the project's own checkout has no `get_partial_volume_mask` at all and a `getBinaryMask` that is a hard polygon fill with no threshold or precision concept, ~35% different in measured volume on an identical synthetic contour (X10). `extract_roi_mask` dispatches on which is present rather than assuming, and raises if `binarization_threshold` or `precision` are overridden on an environment where `getBinaryMask` would silently ignore them. `getVolume(inVoxels=False)` returns mm³, not cc: `roi_volume_cc` in `adapters.py` is the one place that conversion happens (X4) |
| Plan complexity | `data.plan`: `ProtonPlan`, `PlanProtonBeam`, `PhotonPlan`, `PlanPhotonBeam` | `numberOfSpots` and `meterset` are plan-level aggregates in the installed OpenTPS; `n_layers` is not, and is summed in `extract_plan_complexity` from `len(beam.layers)` per beam. `RTPlan.beams` is defined once on the shared base class, so field count reads the same way for both modalities. Dispatches on `isinstance`, not on a caller-supplied label, so a plan mislabelled upstream raises rather than silently returning zeros. Covers the descriptors of Section 8 for both modalities |
| Grid geometry | `data.images.Image3D`: `gridSize`, `spacing`, `origin`, `numberOfVoxels`, `resample`, `resampleOn` | The working grid of Section 5 |
| Synthetic deformation, for testing | `processing.imageProcessing.syntheticDeformation`: `applyBaselineShift`, `shrinkOrgan`, `forceShiftInMask` | Deforms image and ROI together by a known amount, which is the ground truth of Section 3.3 |

Not supplied by OpenTPS and built here: the TG-263 mapping and its enforcement, the export manifest, the provenance table, the crop and record form, and everything downstream in the evaluator and allocator.

Deliberately not used: `processing.planEvaluation.robustnessEvaluation`. Its scenario container is designed around scenarios OpenTPS itself would generate, carrying setup and range error fields that describe assumptions this study does not make, and its stored metrics are D95, D5 and MSE, which do not include V95%. Loading externally generated scenarios into it would attach a provenance claim that is not true, which is the failure the tagging of Section 13 exists to prevent. The reduction of Section 7.1 is written here instead, over DVHs computed with `data.DVH`.

### 3.2 The adapter boundary

Objects are constructed from OpenTPS classes at the point of use and are not persisted. The store holds native `tps5d` records, per the form given in Section 5. Three reasons, and the third is the decisive one.

The classes concerned are thin: `Image3D` carries an array, an origin and a spacing; `DoseImage` and `ROIMask` inherit from it. Reconstructing them from native records costs an adapter, not a translation layer. `Patient` is a session container with an event mechanism and is not a persistence format under any reading.

Second, MS13 at M33 is verified by implemented software and D4.1 is public, so stored data must outlive an external package’s class definitions. OpenTPS documents this hazard itself: `saveSerializedObjects` carries a `dictionarized` flag whose stated purpose is to avoid loss of information over long-term storage due to class modifications. Third, OpenTPS is mid-refactor, so the coupling would be to a moving target.

All calls into `opentps` are confined to one module, so the dependency surface is enumerable. Accepted consequence: extraction output is not directly loadable in the OpenTPS GUI, and visual inspection of a case requires an MHD export.

**The third reason stopped being hypothetical on 14 September 2026.** `extract_roi_mask`, written and verified against the public OpenTPS 3.0.1, failed on first contact with the project's own checkout: not a changed signature, a method absent entirely, X10. Code developed against a public release and code developed against an actively refactored source checkout are not the same target, and neither substitutes for the other. From this version, the project's own `opentps_core` is installed in a separate environment for testing before code that touches OpenTPS is delivered, refreshed after each pull from upstream; the public release remains useful for checking that a change is not an artefact of one specific checkout.

### 3.3 What can be tested before real data, and what cannot

Testable now: interface contracts, shapes and types; the crop and mask arithmetic on fabricated arrays; the content-hash cache; the TG-263 resolution rule, including that an unmapped structure raises; the provenance table; and the manifest consistency check against fabricated DICOM relations.

Testable now with a constructed ground truth: the registration path. `applyBaselineShift` deforms an image and its ROI by a known vector, so applying it, running Morphons, and measuring the recovery is a real test of both the DIR call and the direction convention of Section 6.2. If the direction is inverted the recovery fails with the wrong sign, which is visible. The residual of the round trip is also a first quality measure of the registration.

Not testable before real data: whether the parser survives an actual RayStation export; DIR performance on real abdominal anatomy, where bowel gas and sliding are the regimes in which registration fails and where a synthetic smooth deformation is not representative; and the true grid and mask dimensions. These are limitations of validation, not of implementation, and the assumptions they leave open are registered in Section 14.

### 3.4 Nothing is called with its defaults

Three OpenTPS entry points this module depends on carry defaults that are wrong for it, in three different ways, and none of the three fails loudly when taken. The rule is therefore general rather than a list of exceptions: **every argument that changes a result is passed explicitly**, and the value passed is recorded.

`ROIContour.getBinaryMask(origin=None, gridSize=None, spacing=None)` has all three geometry arguments optional, so omitting them selects an implicit geometry. Section 5 requires the working grid to be a parameter rather than a consequence of load order, which is exactly what the defaults would make it.

`DVH.computeDVH(maxDVH=100.0)` truncates the dose axis at **100 Gy absolute**, not at the prescription. This is harmless for physical dose and is not harmless downstream, since the DVH the evaluator takes is on accumulated EQD2, which passes 100 Gy in hypofractionated schedules at the low alpha over beta values of late-responding organs: 5 × 8 Gy at alpha over beta 2 is 100 Gy EQD2 at prescription level, before any hot spot. Truncation would fall on one arm and one endpoint class, would bias a small-volume-parameter gEUD downward by removing the upper tail it weights, and would be silent, since `Dmax` reads the array rather than the histogram and continues to report the correct value. `maxDVH` is set from the actual maximum of the field with margin. At 4096 bins a 200 Gy axis still gives a step near 0.05 Gy. Carried in the evaluator document at E10.

`RegistrationMorphons(..., tryGPU=True, nbProcesses=-1, baseResolution=2.5)` selects among genuinely different implementations rather than among speeds, and `baseResolution` left at its default silently coarsens every deformation field: see X2 and X5.

`Deformation3D.deformImage(image)` **resamples the field itself** when the grids do not match, announcing it at INFO and choosing the interpolation and fill value on the caller's behalf. Every registration in the 11 September benchmark logged this. The adapter resamples explicitly, with its own parameters, rather than letting it happen inside another call.

`ROIContour.get_partial_volume_mask(..., binarization_threshold=None)` returns a **float** partial-volume array at its own default, not the bool the storage schema of Section 5 requires. `binarization_threshold=0.5` (X10) and `precision` are always passed explicitly, and only where this method is present at all: Section 9, X10.

`get_partial_volume_mask` also does not raise when the working grid fails to physically contain the contour it is asked to rasterise: it proceeds and only logs that this "can appear as a shift or truncation". Trusting that log is doubly unsafe, since the call itself is malformed, `logger.warning(msg, RuntimeWarning, stacklevel=2)` passes a class as a %-format argument to a message with no placeholder for it, and raises `TypeError` under logging configurations that format eagerly, confirmed under `pytest`'s own capture. The adapter computes the contour's physical bounding box from `polygonMesh` and checks containment itself before the call.

The rule has a corollary for provenance. A default that is taken is a parameter whose value is not recorded anywhere, which is the condition Section 13 exists to prevent.

## 4. Plan identity and the export manifest

The store is keyed by (patient, block, plan) with modality, adaptation, scheme, role and source image. None of these are DICOM concepts. An RTDOSE carries a SOP instance UID and references to a plan and an image series; it does not carry "PT-A, block 2, rescue". The association must be supplied.

**The manifest is the authority.** One file per patient, written by whoever performs the export, mapping each exported dose object to its place in the design:

    plan_uid | path | block_index | arm | role | source_image_uid | fx_scheme

with `arm` in {XT-NA, XT-A, PT-NA, PT-A}. The number of rows is not fixed in advance, since rescues are not predictable before the screen has run.

**DICOM relations are the consistency check.** RTDOSE references its RTPLAN, which references its structure set and frame of reference, so the dose-to-image association is recoverable from the files themselves. This check cannot verify arm, margin or role, which are not represented in DICOM. It verifies one thing: that a dose object the manifest assigns to block *j* is in fact tied to the image of block *j*. That is precisely the error a hand-written manifest produces, namely a row displaced by one. The extractor raises where the two disagree rather than preferring either.

The manual cost of the manifest is a table of a few rows per case, against the cost of discovering downstream that two arms were exchanged, which no test detects and which invalidates the primary endpoint. If plan generation is scripted, the script writes the manifest and the manual cost disappears; this is a further argument for scripting and belongs with open decision 26 of the allocator document.

## 5. Dose storage

Three rules, the first two lossless for the endpoints in use.

**Store block-level distributions, not strategy-level accumulated ones.** A strategy’s accumulated dose is a weighted sum of block distributions. Storing the accumulated version per strategy means storing every combination rather than the 2B block distributions that suffice. Under version 6 the number of strategies is four per scheme rather than 2^B, so the saving is smaller than it was, but the rule is retained for two reasons that do not depend on the strategy count: composition at evaluation time is a weighted sum of arrays and is cheap, and block-level storage is what allows the first-block dose source and the mixed-strategy diagnostic of the evaluator document, Section 2, to be composed on request without re-extraction.

**Crop to the union of contoured structures; keep the masks separate.** This revises the version 1 to 4.3 rule, which was to mask to the union of the ROIs the active NTCP models require. The revision has one reason and one consequence.

The reason is that the set of relevant ROIs is determined by the endpoint selection, which is open decision 10 of the allocator document and gated on decision 19. Masking to the union of the currently active models would fix in the stored data a choice the design deliberately leaves open: an OAR added when the site is settled would not be in the store, and the whole cohort would have to be re-extracted. This is the same failure mode that the prohibition on storing EQD2 avoids in the fractionation dimension, applied to the spatial one.

The rule is therefore: crop the dose to the bounding box of all contoured structures plus the target, and store per-ROI boolean masks on that same crop. The consequence is that stored arrays stay rectangular, which keeps deformation and resampling simple, and that the crop is wider than the metric ever needs. The cost of the extra volume is not known and is measured on the first exported case, together with the sizing below. If it proves large, the crop can be narrowed without changing any interface, since the masks already carry the per-ROI restriction.

**Implemented at version 5.2** as `union_bounding_box` and `crop_to_bounds` in `adapters.py`. Bounds are inclusive per axis; masks are required to share a grid before their union is taken, checked rather than assumed, since a silent mismatch there would crop to the wrong physical region with no symptom until metrics come out wrong. The crop preserves the cropped object's own type, `DoseImage`, `ROIMask` or `CTImage`, via each class's own `.copy()` override rather than the shared `Image3D.copy()`, which returns a plain `Image3D` regardless of the subclass it is called on and would silently demote a cropped dose field, dropping `referencePlan` and `referenceCT`.

**The working grid is an explicit parameter, not an implicit consequence.** The dose leaves RayStation on the plan’s scoring grid; the ROI masks are generated from contours defined on the CT geometry. The two do not in general coincide, and one of three things must happen: the dose is resampled onto the CT grid, the masks are generated on the dose grid, or both are placed on a third grid. The choice is not neutral. Resampling the dose at ingest introduces an interpolation upstream of everything, in the high-gradient region where a small-volume-parameter gEUD draws its weight, which is the error the accumulation ordering of the evaluator document, Section 4, is arranged to avoid. Generating the masks on a coarser dose grid instead changes the discretised organ volume, to which V95% and gEUD are both sensitive.

The ratio of the two spacings is not known before the first export, so the choice is not made here. What is fixed here is that the working grid is recorded in every plan record and is a parameter of extraction rather than a side effect of load order, and that the difference in gEUD between the two routes is measured once on the first case for the organs driving the endpoints. This is the same treatment the evaluator gives to the accumulation ordering at its Section 4.4.

**Store physical dose on native geometry. Do not store EQD2, and do not store warped dose.** Two separate reasons, which version 1 conflated:

- EQD2 depends on dose per fraction, and fractionation is a decision variable. Storing EQD2 would fix one fractionation choice in the data and silently invalidate every alternative schedule.
- The conversion to biologically effective dose is performed **before** deformation, because the conversion is nonlinear and does not commute with interpolation. The warped object is therefore a BED field, which depends on both the fractionation scheme and the structure’s alpha over beta, and is not unique. Warped fields are derived products belonging to the evaluator’s cache, not to the extractor’s store.

The extractor therefore stores physical dose per block on its own image, together with the fraction count and the deformation fields. Everything downstream of that is recomputable.

**Dose provenance.** This physical dose is computed in RayStation for both modalities and imported; OpenTPS performs no dose calculation for this study, including no use of its own photon CCC implementation. See Section 13.

**Record form, fixed now; container, fixed after measurement.** What each plan contributes to the store is settled:

    dose_crop      # float32[nx, ny, nz], physical dose per fraction, cropped
    roi_masks      # bool[nx, ny, nz] per ROI, canonical names, same crop
    grid           # origin, spacing, grid_size of the working grid
    bbox           # index bounds of the crop within the working grid
    n_fx           # fraction count of the scheme this plan belongs to
    units          # dose units and RBE weighting as exported. See X9

Access goes through two functions, `store_plan` and `load_plan`, so that the on-disk container is a substitution rather than a rewrite. Three containers are viable and they differ on one axis that only measurement resolves. A serialised OpenTPS structure is excluded by X1. MHD is a poor fit, since it holds a full rectangular array with no native notion of an accompanying mask, though it remains the right format for exporting a case for visual inspection. `npz` per plan and HDF5 per patient both represent the record directly; HDF5 additionally supports chunked partial reads and native hierarchical keys, which matter only if a single array is too large to hold in memory. Grid dimensions and masked ROI volumes are not yet known and are measured on the first exported case before the container is fixed.

## 6. Conversion and caching

| Stage                             | Owner                          | Cost       | Cached                          | Invalidated by                                 |
|-----------------------------------|--------------------------------|------------|---------------------------------|------------------------------------------------|
| Ingest: DICOM to internal         | Extractor                      | High, once | Yes                             | Source files                                   |
| Register: DIR, deformation fields | Extractor                      | High       | Yes, as a first-class artefact  | DIR algorithm and settings                     |
| Convert to BED, warp, accumulate  | Evaluator                      | Moderate   | Yes                             | Fields, block weights, alpha over beta, scheme |
| Reduce to DVH                     | Evaluator, via the OpenTPS DVH | Low        | Yes. This is the cache boundary | Accumulated field, ROI mask                    |
| NTCP                              | Evaluator                      | Low        | Never                           | Recompute                                      |

Deformation vector fields are cached explicitly, keyed by moving image, fixed image and a hash of the DIR settings. They are the expensive and version-sensitive step, and caching warped dose without recording the field that produced it makes staleness impossible to reason about. Since the evaluator applies each field several times, once per (scheme, alpha over beta) combination, the separation between registration and application is load-bearing rather than cosmetic: registration is performed once, application is cheap.

Caches are keyed by content hash rather than by filename, and the hash is recorded in the provenance tag.

### 6.1 Where the deformation field comes from

Two sources are possible and the choice is not made here. The field may be computed in OpenTPS, whose registration package provides Morphons and Demons implementations, or imported from RayStation if the export includes a deformable registration object, which OpenTPS reads through `readDicomVectorField`. The second is not writable until an export exists to inspect, and neither has a known accuracy in the abdomen.

The cache key already given, (moving, fixed, DIR settings hash), is the seam that makes this a configuration choice rather than an architectural one. Extraction calls a single interface,

    get_dvf(*, moving, fixed, settings) -> Deformation3D

with the computing backend and the importing backend behind it. The Morphons backend is implemented now; the importing backend is a stub until the export conventions are known, registered as X2.

**The arguments are keyword-only, and this is not stylistic.** `RegistrationMorphons(fixed, moving, ...)` takes the two images in the opposite order to the interface above, both positionally and both of the same type. A transposition would not raise; it would return a plausible field in the wrong direction, which is the failure X3 exists to catch, reintroduced at the level of a call signature. Keyword-only arguments cost one character and make the transposition unexpressible rather than unlikely. The test of Section 3.3 remains necessary and stops being the only defence.

**The settings are three, and they are not speed controls.** `tryGPU` selects between `morphonsCupy.computeMorphonsCupy` and the CPU loop; `nbProcesses > 1` selects `morphonsComplexConvS/D` over `applyMorphonsKernels`; `baseResolution` sets the ladder of scales. Three switches, three pairs of code paths, no guarantee of numerical agreement between the members of any pair. All three enter the settings hash, read from the settings passed in and not from the registration object, which rewrites `nbProcesses` in place when it is negative and would otherwise make the hash machine-dependent.

**`nbProcesses = 1` is settled on evidence and is not a trade against reproducibility.** The parallel path was slower at every grid measured: 10.7 s against 8.3 s at 3.0 mm, 16.2 against 14.0 at 2.0 mm, 15.8 against 14.5 at 1.5 mm. Windows spawns rather than forks, so each worker re-imports OpenTPS, and at these sizes the overhead exceeds the gain. The `morphonsComplexConvS/D` branch is therefore never taken, which removes one of the three pairs of code paths rather than merely fixing a value in the hash.

**Registration cost does not constrain the working grid.** 14.0 s at 2.0 mm and 14.5 s at 1.5 mm, for 2.2 and 5.3 Mvoxel: two and a half times the voxels for the same time. The work lives on the ladder's grids, set by `baseResolution`, not on the image grid, so refining the image adds resampling only. Since the registration count is patients times blocks, arms sharing the images, a cohort of twenty patients at three blocks is sixty registrations, which at the times above is well under an hour in total, computed once and cached. That cohort size and block count are an illustration rather than a design figure: neither is fixed, and the block count would change if the hypofractionated schedule were adapted per fraction, open decision 23 of the allocator document. The order of magnitude is what the estimate carries. See X2.

**The returned field does not live on the image grid, and two things bound its resolution.** Morphons runs a fixed ladder of scales, `baseResolution` times `[11.31, 8, 5.66, 4, 2.83, 2, 1.41, 1]`, and stops before a scale whose spacing would fall below that of the fixed image. The returned field therefore carries **the finest scale still at or above the working-grid spacing**, which makes `baseResolution` one floor and the working grid the other.

Measured on 11 September 2026, on a 300 x 300 x 200 mm phantom with `baseResolution` at its 2.5 mm default: a 3.0 mm working grid returns a 3.54 mm field, the ladder having stopped one rung early; 2.0 mm and 1.5 mm grids both return 2.50 mm. The field is never finer than the working grid and can be coarser by up to the ladder's ratio of the square root of two.

**Going below the working-grid spacing is excluded.** It is strictly dominated rather than merely wasteful: at a 2.0 mm working grid, `baseResolution` of 1.5 mm costs 38.3 s against 28.9 s and returns a **coarser** field, 2.13 mm against 2.00 mm, because every rung above the floor runs on a finer grid while the final rung is cut off by the working grid anyway. Cost scales as the cube of the inverse of `baseResolution`, as a volume should: the measured factors are 1.78 and 1.86 against 1.73 and 1.95 expected. This part is settled by the measurement.

**Setting `baseResolution` equal to the working-grid spacing is the working recommendation, not a result.** At that setting the last rung lands exactly on the grid and the field comes out at the grid's own resolution, which is the finest the ladder can deliver. Whether that is worth its cost against a coarser setting is a different question and is not answered here: leaving `baseResolution` at 2.5 mm on a 2.0 mm grid buys time and spends field resolution, and what a coarser field costs in gEUD on the organs driving the endpoints is unknown until there is real anatomy to measure it on. The two settings are compared on the first exported case, alongside the other grid measurements, in the same form as the accumulation-ordering check of the evaluator document at its Section 4.4. Until then the rule above is adopted because it removes a free parameter, not because the alternative has been shown to be worse.

The adapter calls `Deformation3D.resample(spacing, gridSize, origin)` explicitly onto the working grid and never uses what `compute()` returns as it stands. See X5.

The interface has a second use beyond deferral. Where both fields exist for a case, the difference they produce in gEUD on the organs driving the endpoints is measurable and reportable, which converts a choice of registration provenance into evidence at negligible cost.

### 6.2 Direction of the deformation

The evaluator warps each block's BED field **onto the planning CT**. The block field lives on that block's repeat image, so the result must come out on the pCT grid. Getting this backwards is not free to undo, since inverting a diffeomorphic field is neither exact nor cheap.

The convention is therefore fixed: **fixed = pCT, moving = rCT_j**, for every registration in the pipeline.

**Stated operationally rather than by name.** Versions 4.3 to 5.0 argued this through the direction the field maps, which is ambiguous across conventions and invites a later reader to correct it to the opposite. OpenTPS labels the returned field "deformation from moving to fixed" while the field itself is defined on the fixed grid and points into the moving space; both statements describe the same object. The unambiguous form is the operation: `Deformation3D.deformImage(moving)` returns an image **on the fixed grid**, as the Morphons implementation shows by warping the moving image and naming the result `<moving>_registered_to_<fixed>`. Since the required output is on the pCT grid, the pCT is the fixed image. No convention of naming changes this.

Registered as X3 and verified rather than asserted, per Section 3.3.

## 7. Target metrics

Target coverage is not a secondary output. It gates the optimisation. But the screen itself is applied by the evaluator, and the extractor’s obligation is to supply metrics in the form the screen requires.

Coverage cannot be inferred from NTCP. If the target shifts away from an OAR between pCT and rCT, the non-adapted plan underdoses the CTV while the OAR dose falls, so coverage fails and NTCP improves. NTCP is a function of OAR dose only and carries no information about the target.

**Metrics are per block and per plan, on the plan’s own image.** This is a change from version 1, which required metrics on the accumulated dose. Coverage is a property of a plan delivered on a given anatomy, so the judgement is made where the plan is delivered. It follows that no registration, deformation or accumulation is required to produce the inputs to the coverage screen, which is why that screen can run before any composition and prune the strategy space cheaply.

Four requirements:

- **Nominal per-block metrics** for every plan, as the primary basis for the screen.
- **Worst-case per-block metrics** from the robustness evaluation, retained as a sensitivity analysis. They are not accumulated, since the worst scenario in one block need not be the worst in another and a sum of per-block worst cases corresponds to no physical scenario.
- **The photon arm is included.** Photon dose is recomputed on the rCTs and screened on the same criterion, so it cannot be treated as a planned-dose-only reference. This is A10 of the allocator document, inherited from the reference study rather than an amendment to it, corrected there at version 7.

- **Rescue plans are extracted like any other plan.** Under the version 7 supervisory decision a non-adapted arm whose plan fails the screen on a block acquires a replan generated on that image at unchanged margin, which carries forward. Each rescue is an additional plan with its own per-block metrics and its own dose grid, so the extraction unit is unchanged but the number of units is not known before the screen has run. The schema must therefore allow a variable number of plans per (patient, arm) rather than the fixed three of an adapted arm and one of a non-adapted arm, and each plan must record whether it is a planned or a rescue plan and on which image it was generated.

**The criterion is the plan acceptance protocol used at treatment planning**, superseding the bare V95% below 95 per cent of versions 1 to 4.2. The extractor's obligation is unchanged in form, since it supplies metrics and the evaluator applies criteria, but the metric list is now longer and runs in two directions that must be kept apart. **Target metrics**, V95% and D5 on the target, extend the screen along the axis it already measures. **OAR metrics**, Dmean and Dmax on the organs driving the endpoints, are supplied regardless because they are useful descriptively, but whether they enter the screen criteria is a separate decision that changes what the primary endpoint means: a screen that fires on OAR grounds triggers rescue for OAR reasons and truncates the upper tail of the non-adapted arms' NTCP distribution. Which metrics to request is open decision 7b of the allocator document, addressed to the clinical partners and the RTTs and gated on decision 19, since the protocol is site-specific.

**The prescription a plan is measured against is its own scheme's, and the units must be stated.** `DVH.computeVx(x)` takes `x` as a percentage of the prescription passed to the DVH constructor, so V95% is meaningless until two things are fixed.

The first is **whose prescription**. It belongs to the fractionation scheme, not to the patient: a standard and a hypofractionated schedule differ in total dose as well as in fraction count, so a single per-patient prescription is undefined once a patient carries plans in both. Each plan is measured against the prescription of its own `fx_scheme`. That V95% is therefore scheme-relative is correct rather than a defect: the coverage screen asks whether a plan delivers what it was prescribed, which is a question internal to an arm. Arms become commensurable downstream, in EQD2 and NTCP, which is the only space in which different schedules can be compared.

The second is **which dose**. The store holds physical dose **per fraction**, per Section 5. Passing a course prescription against a per-fraction dose would put every plan at a few per cent of prescription and return V95% of zero for the whole cohort, without raising, since zero is what `computeVx` returns when no voxel reaches the threshold. Two consistent conventions exist and they are equivalent: per-fraction dose against per-fraction prescription, or course dose against course prescription.

**The convention adopted is course against course**: the stored per-fraction dose is multiplied by the scheme's fraction count and measured against the scheme's total prescription. It is the one that matches how coverage is judged at planning. It is stated here and enforced in the adapter, because a test written in the same units as the code under test cannot detect the error.

**Scope.** The prescription is an extraction-side quantity only. The DVH the evaluator takes is on accumulated EQD2, where a percentage of prescription has no meaning and the metric is the gEUD, which does not pass through `computeVx`.

### 7.1 Worst-case storage requires no dose grids

The worst-case metrics are per block, are never accumulated (E5 of the evaluator document), and are therefore never deformed and never composed. Their only use is to produce metrics on the plan’s own image. It follows that the store needs no worst-case dose grids at all, which removes what would otherwise be the largest multiplier in the module: one grid per scenario per plan.

What is stored instead is the **per-scenario DVH per ROI**, plus the derived scalars. The reason for keeping the DVH rather than only the scalars is the one the evaluator gives at its Section 7.2 for caching at the DVH: a DVH contains the (volume, dose) pairs from which any DVH-derived metric can be recomputed, and a stored scalar cannot. Since open decision 7b may still change which metrics instantiate the acceptance criterion, storing only the scalars would make a change of criterion a re-extraction. The declared cost of this choice is that anything not derivable from a DVH is lost, in particular the spatial location of a hot or cold region and any scenario-to-nominal dose difference map.

**Physical scenarios are preferred to voxel-wise aggregates.** RayStation offers both: individual scenario doses, and a voxel-wise minimum or maximum distribution constructed by taking the extreme value in each voxel across scenarios. The two are not interchangeable. The minimum over physical scenarios of the target D95 is the D95 of the worst scenario, a quantity with a referent; the D95 evaluated on a voxel-wise minimum field is more pessimistic and corresponds to no deliverable scenario, since it combines different scenarios at different points. This is the argument of the fourth requirement above, applied one level lower. The physical form also determines the aggregate, while the reverse is impossible.

Two qualifications. Whether scenario doses and voxel-wise aggregates are exportable as DICOM RT Dose is registered as X7 and is not confirmed: the DICOM conformance statements consulted name the beam set dose explicitly and do not name evaluation or scenario doses, and some export capability is documented as available only in non-clinical versions. And if the voxel-wise aggregate is taken as well as, or instead of, the scenarios, the difference between the two definitions should be computed once on one case and reported rather than argued.

## 8. Delivery time

The mapping from a plan to minutes splits in two, and only the first half is extractable.

**From the plan:** number of fields, energy layers per field, spots per layer, total MU, target volume. For pencil beam scanning the dominant term is energy layer switching, so layer count is the main predictor and spot count secondary.

**Implemented at version 5.2** as `extract_plan_complexity` in `adapters.py`, dispatching on `isinstance(plan, ProtonPlan | PhotonPlan)` rather than on a modality label supplied separately, so a plan mislabelled upstream by the manifest of Section 4 raises here instead of silently returning zeros for the branch it never took. `n_fields` reads `RTPlan.beams`, defined once on the shared base class; proton `n_layers` is summed per beam, since only `numberOfSpots` and `meterset` are plan-level aggregates in the installed OpenTPS. Target volume is deliberately not produced here: it comes from the target mask via `roi_volume_cc`, not from the plan, and the caller composes the two.

**The photon side requires nothing further.** Photon delivery is modelled as unconstrained, and the photon adaptation budget is charged only the adaptation increment Δτ_XT, which is an independent variable of the study rather than a quantity derived from a plan. No photon delivery-time model and no photon baseline session length are therefore required. If the budget unit is later changed to adaptation events, as recorded in Appendix A of the allocator document, this remains true.

**Not in the plan:** the machine constants that convert those counts into minutes, and the non-delivery components entirely. Contouring, re-optimisation and QA time have no representation in a plan file.

The extractor therefore supplies complexity descriptors, and the mapping from descriptors to minutes lives in a separate configuration with machine constants as named parameters. Recalibrating for a specific beamline does not touch extraction.

If RayStation reports an estimated delivery time per plan it is taken directly and tagged as vendor-estimated in the provenance. It is a model rather than a measurement, but a machine-aware one.

Complexity is extracted per plan, since only the difference between arms enters Delta tau. Two effects must be kept separate rather than folded into one term: margin reduction shortens delivery through fewer layers and spots, while hypofractionation lengthens the individual fraction through higher MU but shortens the course.

## 9. ROI naming

Canonical names follow **TG-263**, the AAPM standardised nomenclature for radiotherapy structure names. RayStation supports it. It is required not for tidiness but because the NTCP model registry must be able to name what it wants: a rectum model asks for `Rectum` and cannot ask for whatever the structure happens to be called in each plan.

The resolution rule is deliberately not fuzzy matching. Fuzzy matching fails silently, and a structure matched to the wrong OAR produces a plausible number rather than an error.

- Normalise mechanically: strip whitespace, casefold.
- Look up in an explicit per-cohort mapping file, versioned in the repository.
- **An unmapped structure raises.** Adding a mapping line takes seconds; finding a silently mismatched OAR later does not.

The mapping file is versioned and its hash is recorded with the dose provenance, since a change to the mapping changes which voxels were counted.

Nothing in OpenTPS assists this. Its structure access is by literal name, `RTStruct.getContourByName`, on whatever string the DICOM file carries, so the mapping is entirely this project's obligation. **It is worse than a bare literal lookup**: on a miss, `getContourByName` prints a message to stdout and returns `None` rather than raising, confirmed against the installed source on 11 September 2026. "An unmapped structure raises" is therefore not a property inherited from the platform; it is this project's own wrapper, `extract_roi_mask` in `adapters.py`, converting that `None` into a `KeyError` naming the attempted lookup and the structures actually present, before anything is chained onto it that would otherwise fail two calls away from the real problem. The contents of the mapping file, that is the aliases actually in use at the partner centre, cannot be written before a real RTSTRUCT or a template from the clinical partner exists; the mechanism is built now and populated later, as with the NTCP model registry.

**The rasterisation itself is not one stable target, and this was found the hard way.** `extract_roi_mask` was written and verified against the public OpenTPS 3.0.1, then failed with `AttributeError` on its first run against the project's own checkout on 14 September 2026: `get_partial_volume_mask` does not exist there. That checkout carries `getBinaryMask` and `getBinaryMask_old`, and reading the former's source shows a different algorithm entirely, a hard polygon fill via PIL with no notion of partial-volume coverage, producing a boolean array directly rather than thresholding a float one. Measured on an identical synthetic cylinder, the two implementations differ by roughly 35% in resulting volume, confirmed rather than estimated. `extract_roi_mask` now calls `roi_mask_algorithm()` to detect which is present and dispatches accordingly, and raises if `binarization_threshold` or `precision` are supplied on an environment where `getBinaryMask` would otherwise ignore them silently. This is X10.

The older implementation carries its own silent-failure mode, also found by reading its source and since reproduced against the real checkout: a contour on a single z-slice makes it return `imageArray=None` rather than raise. `extract_roi_mask` checks for this and raises explicitly.

## 10. Relation to the NTCP model registry

The registry itself has moved to the evaluator, which is the component that evaluates NTCP. Two obligations remain here.

**Cohort validation before dose work.** Given the active model list, the extractor collects the union of required ROIs, dose metrics and clinical covariates and validates the cohort against that union at assembly time. A missing covariate surfaces before hours of registration and accumulation rather than after.

This is also where the ROI mapping of Section 9 is enforced. The union of required ROIs is resolved against the mapping file at cohort assembly, so an unmapped or missing structure raises there rather than during extraction. The crop of Section 5 is deliberately wider than this union, so a later addition to the model list is a validation failure that new mapping lines can fix, not a re-extraction.

**Sizing the composition workload.** The union of distinct alpha over beta values in the registry determines how many warped fields per block the evaluator will require. The extractor reports that union so the storage and compute estimate is available before the pipeline runs.

## 11. Synthetic cohorts

Generated by a **separate module sharing the evaluator’s output schema**. Separate, so that the test harness does not share failure modes with the component under test. Shared schema, so the allocator cannot tell the difference.

**The generator emits dose metrics, not utilities.** Emitting delta NTCP directly would leave the NTCP layer and the composition path untested until real data arrives, which defeats the purpose of the interface in Section 2. A first coarse pass may emit delta NTCP directly, purely to check the allocator for trivial coding errors, but it is not the tested configuration and is not used for any reported result.

The generator has a use beyond convenience. Whether greedy allocation is safe depends on the shape of the marginal adaptation benefit as a function of the number of adaptations. Constructing deliberately concave and deliberately convex cohorts, and measuring the departure of the incremental-efficiency greedy from the exact solve in each, is a methodological result obtainable before any patient data arrives.

## 12. Schema

    Per patient
    pid, site
    hypo_eligible     # clinical eligibility flag fixing the XT-NA schedule. A32
    covariates        # driven by the NTCP model registry's declared requirements
    imaging           # pCT, rCTs, acquisition timestamps
    rois              # TG-263 canonical names via the explicit mapping file
    grid              # working grid geometry, plus the crop bounds and per-ROI masks
    manifest          # export manifest, Section 4

    Per (patient, block, plan)
    modality          # 'pt' | 'xt'
    technique         # single value per modality initially
    robustness        # setup error, range error. Determined by `adapted`, not free:
                      # an adapted plan carries the reduced setting, a
                      # non-adapted plan the clinical one
    fx_scheme         # (n, d), protocol identifier
    adapted           # whether this plan is the adapted plan for this block
    role              # 'planned' | 'rescue'
    source_image      # the image this plan was generated on
    dose              # physical dose per fraction, cropped, on the working grid
    target_metrics    # D98, D95, V95%, nominal, on this block only
    plan_complexity   # n_fields, n_layers, n_spots, mu, target_vol
    robust_eval       # per-scenario DVH per ROI, plus derived scalars.
                      # No dose grids: Section 7.1

    Per registration
    dvf               # keyed by (moving, fixed, hash of DIR settings)

    Per (patient, scheme)
    fx_scheme         # (n, d)
    rx_dose           # total prescribed dose for this scheme, Gy
                      # Per patient rather than per cohort pending the clinical
                      # answer in Section 15. Section 7

    Per facility
    cap_pt_min_day    # proton machine minutes per day
    cap_xt_min_day    # photon adaptation minutes per day. Swept, not measured
    days_week, uptime, n_rooms, beam_topology
    staff_avail

`cap_min_day` of version 3 is renamed `cap_pt_min_day` and joined by `cap_xt_min_day`. The second is the photon adaptation budget. It has no measured anchor for this indication and is swept rather than read from the facility, so it is a study parameter that happens to live in the facility record; the allocator document states the reason at its Appendix A and open decision 13.

Two fields present in version 1 have been removed. `dose_blocks` indexed per strategy is replaced by `dose` indexed per plan, since strategies are combinations formed downstream. `strategies_ok` is removed entirely, since the screens now run in the evaluator.

Three fields are added at version 5. `role` and `source_image` carry the rescue structure of the version 7 design, matching `BlockPlan` in `core/schema.py`. `hypo_eligible` is the per-patient flag A32 requires as input. `robust_eval` changes content rather than name: it holds DVHs and scalars rather than grids.

`rx_dose` and `n_fx` move out of the per-patient record at version 5.1. They were a residue of a single-scheme design and are undefined once a patient carries plans in two schemes with different total doses. They become a per-(patient, scheme) record, which is where the prescription of Section 7 is read from. Whether that record needs a patient index at all, or whether the prescription is a cohort constant per scheme, is the clinical question in Section 15; the indexed form is the one that survives either answer.

## 13. Provenance and uncertainty

Every metric and every model parameter carries a tag recording whether it is measured, taken from a named publication, or assumed. Without it, automated uncertainty propagation is difficult. Since the allocator’s output is a difference of small probabilities, sensitivity to NTCP parameter uncertainty is worth studying, and the provenance tag is what makes the set of parameters to perturb enumerable rather than hand-maintained.

**Dose is tagged RayStation-computed.** All physical dose for paper 1, both modalities, is generated in RayStation and imported; OpenTPS calculates no dose, including no use of its own photon CCC implementation for the photon arms. The choice bears on the study's premise, since analytical proton dose is least reliable in a heterogeneous abdomen and the resulting error is systematic rather than random, falling on the arm whose anatomical degradation the study measures. Which RayStation algorithm, analytical pencil beam or Monte Carlo, and the cross-modality reporting conventions, RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin, are not yet fixed: open decision 25 of the allocator document.

### 13.1 Form

The requirement above is one of **enumerability**, not of annotation: the tag exists so that the set of parameters to perturb can be listed by query. A field scattered through every record satisfies the wording and not the requirement, since enumerating would mean traversing the whole store. Provenance is therefore a separate table of declarative records, following the pattern the evaluator uses for its model registry at Section 8, where `source` and `fitted_on` are fields precisely so that the assumptions register can be generated rather than maintained:

    ProvenanceRecord(
        key,           # e.g. 'dose:pt12/b1/PT-A/planned'
        kind,          # 'measured' | 'published' | 'assumed' | 'swept'
        source,        # 'RayStation <engine>' | 'Michalski 2010 QUANTEC' | 'X9'
        content_hash,  # links to the stored object, per Section 6
    )

Where `kind` is `assumed`, `source` names an assumption ID from Section 14 or from the allocator and evaluator registers. This is what makes the assumptions register checkable against the data rather than parallel to it.

### 13.2 Granularity

Tagging every metric produces thousands of near-identical rows and hides the few that matter; tagging every record mixes measured imaging with assumed facility constants under one label. The resolution is inheritance. Quantities divide into **primitives**, which have a source of their own, and **derived** quantities, which inherit from their inputs and have none.

Primitives: dose arrays, image and grid geometry, ROI masks and the mapping file, facility constants, NTCP model parameters, swept study parameters, the export manifest, the prescription, the DIR settings, and the OpenTPS commit hash.

The last three are additions at version 5.1 and each has a reason. **The prescription** is not in the dose file and must be supplied; `computeVx` divides by it, so V95% depends on it linearly, and a plan evaluated against the wrong prescription yields a plausible number. Which prescription enters which plan's DVH, and in which units, is settled in Section 7: the plan's own scheme, course dose against course prescription. Whether the prescription itself varies by patient within a scheme is the clinical question in Section 15. **The DIR settings** are primitive because they select implementations, per X2. **The OpenTPS commit hash** rather than its version string: the installation is a source checkout, `opentps 3.0.0` does not identify a state of the code, and two checkouts reporting the same version can differ. With MS13 at M33 verified by implemented software, this is the difference between a reproducible result and one that is not. Derived: D98, D95, V95%, gEUD, DVHs, accumulated dose, occupancies. Only primitives are tagged, which keeps the table at the order of tens of rows per patient. The list of primitives is provisional and is revised as the schema settles.

## 14. Assumptions register

New at version 5. Assumptions specific to extraction were previously carried informally in Section 15 or not at all. The allocator uses the prefix A and the evaluator E; this document uses **X**. Where an assumption mirrors one in another document, the other is named rather than restated.

| ID | Assumption | Status | Risk |
|----|------------|--------|------|
| X1 | OpenTPS objects are constructed at the point of use and never persisted; the store holds native `tps5d` records | Design decision, Section 3.2 | The adapter must track OpenTPS API changes, and a refactor is in progress. Confined to one module by construction |
| X2 | The deformation field is computed in OpenTPS by default; an imported RayStation field is an alternative backend behind the same interface. The Morphons settings `tryGPU`, `nbProcesses` and `baseResolution` select among different implementations rather than among speeds, are passed explicitly, and all three enter the settings hash. `tryGPU=False` and `nbProcesses=1`; `baseResolution` is set to the working-grid spacing pending the measurement in X5 | Design decision, Section 6.1. The importing backend is a stub. Settings read from the source and **benchmarked on 11 September 2026** | Neither source has a known accuracy in the abdomen. If the two disagree materially the choice becomes a reported sensitivity rather than a convention. The GPU path is entered under a bare `except` that logs at INFO, so any failure and not only a missing cupy degrades silently to CPU: passing `tryGPU` explicitly makes the path a choice rather than an outcome. `nbProcesses=1` is no longer a trade against reproducibility, the parallel path being slower at every grid measured, so the `morphonsComplexConvS/D` branch is never taken and one of the three pairs of code paths is removed rather than fixed |
| X3 | Every registration uses fixed = pCT, moving = rCT_j | Convention, Section 6.2, verified by the synthetic test of Section 3.3 | An inverted direction produces a plausible accumulated dose that is wrong. The test is what prevents this from being silent |
| X4 | The dose is cropped to the bounding box of all contoured structures plus the target, wider than the union the active NTCP models require. Implemented as `union_bounding_box` and `crop_to_bounds`, Section 5. `ROIMask.getVolume(inVoxels=False)` returns mm³ despite its name; `roi_volume_cc` in `adapters.py` is the one place the factor of 1000 is applied, so no call site can silently misreport a masked volume in the wrong unit | Revision at version 5 of the version 1 to 4.3 masking rule, Section 5. Crop and unit conversion **implemented and tested against the installed environment on 11 September 2026** | Storage cost is unmeasured. If large, the crop narrows without an interface change, since the per-ROI masks already carry the restriction. A caller reading `getVolume()` directly rather than through `roi_volume_cc` would silently report a volume 1000 times too large |
| X5 | The working grid is an explicit parameter; whether dose is resampled to the CT grid or masks generated on the dose grid is not decided. **There are three grids, not two**: the deformation field carries its own, and its resolution has two floors, `baseResolution` and the working grid itself, the field taking the finest ladder scale still at or above the working-grid spacing. Setting `baseResolution` below the working-grid spacing is excluded on measurement; setting it equal, at which the ladder lands on the grid, is the working recommendation pending a comparison against a coarser setting on real anatomy. The adapter resamples the field explicitly rather than using what `compute()` returns | Deferred to measurement on the first exported case, Section 5. The two floors and the rule **measured on 11 September 2026**, Section 6.1 | Resampling dose at ingest introduces interpolation where the gEUD draws its weight; generating masks on a coarse grid changes the discretised organ volume. Direction of each effect is known, size is not. Setting `baseResolution` below the working grid is strictly dominated, costing more and returning a coarser field, so that exclusion removes a failure mode rather than trading one. Setting it equal rather than coarser is not equally settled: it buys field resolution with time, and what a coarser field costs in gEUD is unknown until there is real anatomy. Adopted for now because it removes a free parameter, and compared on the first case. Registration cost is not a criterion for the working-grid choice: it is set by the ladder, not by the image grid, and was flat across a 2.4-fold change in voxel count |
| X6 | Worst-case is stored as per-scenario DVHs per ROI plus derived scalars, and not as dose grids | Follows from E5 of the evaluator document: worst-case is never accumulated and never deformed, Section 7.1 | Anything not derivable from a DVH is lost, in particular spatial location and scenario-to-nominal difference maps |
| X7 | RayStation can export scenario doses, or at least per-scenario DVH data, in a form the extractor can read | **Unverified.** The DICOM conformance statements consulted name the beam set dose and do not name evaluation or scenario doses; some export capability is documented as available only in non-clinical versions | If only aggregate voxel-wise fields are exportable, the worst-case metrics change meaning and must be reported as voxel-wise rather than as scenario worst cases |
| X8 | Plan identity, that is arm, block, role and scheme, comes from an export manifest; DICOM relations serve as a consistency check | Design decision, Section 4 | The manifest is hand-written unless planning is scripted. A displaced row is the failure mode, and the DICOM check is what catches it |
| X9 | RayStation export conventions, that is dose units, RBE weighting, dose-to-water or dose-to-medium, grid origin, structure naming and file layout, are as the parser assumes | **Unverified.** No export has been inspected | A parsing assumption that is wrong is likely to fail loudly on units and file layout, and silently on RBE weighting and dose-to-medium. Depends on open decision 25 of the allocator document |
| X10 | ROI masks use `get_partial_volume_mask`, binarised at `binarization_threshold = 0.5`, where OpenTPS provides it. Where it does not, confirmed absent from the project's own checkout on 14 September 2026, `extract_roi_mask` falls back to `getBinaryMask`, a different algorithm, a hard polygon fill with no threshold concept, detected via `roi_mask_algorithm()` rather than assumed. The threshold, where it applies, matches what the deprecated wrapper in the public OpenTPS hardcoded | Design decision, Section 3.1 and 9. The two-backend dispatch and the ~35% volume difference between them are **measured against both environments, 14 September 2026**, not adopted on read alone | Which algorithm runs is not independent of the storage-sizing measurement in X4: the two give different masked volumes on the same contour, confirmed rather than estimated, and neither has been sensitivity-tested against real anatomy. Provenance must record which algorithm produced a given mask once the table of Section 13.1 exists, since a future OpenTPS version could change which one an environment has |

X7 and X9 are the two that cannot be closed by any amount of design work. Both close on the first real export.

## 15. Open items

Two items of version 2 are closed. The coverage criterion is V95% below 95 per cent. Whether the clinical-margin adaptive arm exists is resolved: it does not, so only two plans per block are extracted, the clinical-margin pCT plan and the reduced-margin adapted plan.

**Version 6 note.** The extraction unit is unaffected by the decision to fix the workflow at prescription. Two consequences are worth recording because they are cheap to satisfy now and expensive to retrofit. The non-adapted arms require their pCT plan recomputed on every repeat image, which version 5 also required and which must not be dropped on the grounds that those arms never adapt. And if the hypofractionated schedule is adapted on in-room imaging with a block equal to a fraction, the number of plans per adapted arm rises from three to six, which changes the sizing estimate below; the granularity is open decision 23 in the allocator document.

**Version 7 note.** Three consequences of the rescue decision and one of the XT-NA schedule decision.

- The plan count per patient is no longer fixed in advance. A rescue is an additional plan, bounded above by one per block per non-adapted arm and not predictable before the screen has run. Sizing estimates should carry the worst case alongside the nominal.

- Each plan record must carry its role, planned or rescue, and the image it was generated on, so that a non-adapted arm's piecewise composition is reconstructible from the store rather than inferred.

- The metric list requested from the clinical partners now runs in two directions, target and OAR, per Section 7.

- XT-NA carries one fractionation schedule per patient rather than two, fixed by a clinical eligibility flag, which is required patient data and belongs in the schema alongside the clinical covariates. Allocator A32. The plan count for that arm falls from two to one over both schedules.

**Closed at version 5.** The question of whether the robustness export provides per-scenario dose or only DVH bands is no longer a precondition. Section 7.1 shows the worst-case needs no dose grids in either case, so the answer changes what the metrics mean, per X7, rather than whether they can be produced. What remains to ask is narrower and is stated below.

**Still open.**

- Dose grid dimensions and masked ROI volumes, to be measured on the first exported case before the storage container is fixed. Together with the crop-versus-mask ratio of X4, the grid ratio of X5, and the comparison between `baseResolution` at the working-grid spacing and at a coarser setting, these are one measurement session on one case. The measurement code exists (`union_bounding_box`, `roi_volume_cc`); what is still open is real geometry to run it on, and, newly, whether the active backend's masking, `get_partial_volume_mask` at 0.5 or `getBinaryMask`, needs sensitivity-checking against real contours at the same session, since which algorithm runs is now a confirmed source of a ~35% volume difference, not a hypothetical one (X10).
- Whether `ScriptableDicomExport` exposes evaluation and scenario doses, and whether that capability depends on the licence tier. X7.
- Machine constants for the delivery-time model, or confirmation that the RayStation estimate is usable. Belongs with the PARTICLE operating-model question.
- Plausible range for the extra photon linac time per adapted fraction, Δτ_XT, to set the sweep range. Belongs with the PARTICLE operating-model question and is open decision 12 of the allocator document. It is a range rather than a value, so it does not block extraction.
- The contents of the TG-263 mapping file, which requires a real RTSTRUCT or a template from the clinical partner. The mechanism is complete without it.
- Whether the prescription (D, n) for a scheme is a cohort constant or varies by patient, for instance modulated by proximity to an organ at risk. If it varies, the prescription is indexed by (patient, scheme) rather than by scheme. Belongs with open decision 7b, being addressed to the same clinical partners, and does not block extraction: the indexed form of Section 12 survives either answer.

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.8 there.

Sections 16 onward: version history, in `CHANGELOG.md`.

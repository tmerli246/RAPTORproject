# Extraction Module

Version 5.0. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

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

The mapping below is against the published OpenTPS API documentation. It has not been checked against the version installed in the project environment, and OpenTPS is undergoing a substantial refactor, so it is verified before implementation rather than assumed.

| Requirement | OpenTPS module or class | What it supplies |
|---|---|---|
| DICOM ingest | `io.dicomIO`: `readDicomCT`, `readDicomDose`, `readDicomStruct`, `readDicomPlan` | CT, RTDOSE, RTSTRUCT and RTPLAN as typed objects. `readDicomPlan` covers photon IMRT and VMAT and proton PBS, so both modalities are served |
| Bulk ingest | `io.dataLoader`: `loadData`, `readData` | Recursive directory scan with format detection, for a whole exported case |
| DIR, computed | `processing.registration`: `Registration`, `RegistrationMorphons`, `RegistrationDemons` | Morphons is the diffeomorphic algorithm the OpenTPS white paper presents as its reference DIR |
| DIR, imported | `io.dicomIO.readDicomVectorField` | A DICOM deformable registration object as a vector field, for the importing backend of Section 6.1 |
| Deformation as an object | `data.images.Deformation3D` | `deformImage`, `inverse`, `resample`, construction from displacement or velocity. This is the cached first-class artefact of Section 6 |
| DVH and target metrics | `data.DVH` | `Dmean`, `D98`, `D95`, `D50`, `D5`, `D2`, `Dmin`, `Dmax`; `computeDx`, `computeVx`, `computeDcc`. `computeVx` covers V95% directly. E10 of the evaluator document |
| ROI handling | `data.ROIContour.getBinaryMask`, `data.images.ROIMask.getVolume`, `RTStruct.getContourByName` | Contour to mask with explicit geometry, and the masked volume measurement the sizing of Section 5 requires |
| Plan complexity | `data.plan`: `ProtonPlan`, `PlanProtonBeam`, `PhotonPlan`, `PlanPhotonBeam` | `numberOfSpots`, `layers`, `meterset`; `numberOfSegments`, `numberOfBeamlets`. Covers the descriptors of Section 8 for both modalities |
| Grid geometry | `data.images.Image3D`: `gridSize`, `spacing`, `origin`, `numberOfVoxels`, `resample`, `resampleOn` | The working grid of Section 5 |
| Synthetic deformation, for testing | `processing.imageProcessing.syntheticDeformation`: `applyBaselineShift`, `shrinkOrgan`, `forceShiftInMask` | Deforms image and ROI together by a known amount, which is the ground truth of Section 3.3 |

Not supplied by OpenTPS and built here: the TG-263 mapping and its enforcement, the export manifest, the provenance table, the crop and record form, and everything downstream in the evaluator and allocator.

Deliberately not used: `processing.planEvaluation.robustnessEvaluation`. Its scenario container is designed around scenarios OpenTPS itself would generate, carrying setup and range error fields that describe assumptions this study does not make, and its stored metrics are D95, D5 and MSE, which do not include V95%. Loading externally generated scenarios into it would attach a provenance claim that is not true, which is the failure the tagging of Section 13 exists to prevent. The reduction of Section 7.1 is written here instead, over DVHs computed with `data.DVH`.

### 3.2 The adapter boundary

Objects are constructed from OpenTPS classes at the point of use and are not persisted. The store holds native `tps5d` records, per the form given in Section 5. Three reasons, and the third is the decisive one.

The classes concerned are thin: `Image3D` carries an array, an origin and a spacing; `DoseImage` and `ROIMask` inherit from it. Reconstructing them from native records costs an adapter, not a translation layer. `Patient` is a session container with an event mechanism and is not a persistence format under any reading.

Second, MS13 at M33 is verified by implemented software and D4.1 is public, so stored data must outlive an external package’s class definitions. OpenTPS documents this hazard itself: `saveSerializedObjects` carries a `dictionarized` flag whose stated purpose is to avoid loss of information over long-term storage due to class modifications. Third, OpenTPS is mid-refactor, so the coupling would be to a moving target.

All calls into `opentps` are confined to one module, so the dependency surface is enumerable. Accepted consequence: extraction output is not directly loadable in the OpenTPS GUI, and visual inspection of a case requires an MHD export.

### 3.3 What can be tested before real data, and what cannot

Testable now: interface contracts, shapes and types; the crop and mask arithmetic on fabricated arrays; the content-hash cache; the TG-263 resolution rule, including that an unmapped structure raises; the provenance table; and the manifest consistency check against fabricated DICOM relations.

Testable now with a constructed ground truth: the registration path. `applyBaselineShift` deforms an image and its ROI by a known vector, so applying it, running Morphons, and measuring the recovery is a real test of both the DIR call and the direction convention of Section 6.2. If the direction is inverted the recovery fails with the wrong sign, which is visible. The residual of the round trip is also a first quality measure of the registration.

Not testable before real data: whether the parser survives an actual RayStation export; DIR performance on real abdominal anatomy, where bowel gas and sliding are the regimes in which registration fails and where a synthetic smooth deformation is not representative; and the true grid and mask dimensions. These are limitations of validation, not of implementation, and the assumptions they leave open are registered in Section 14.

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

    get_dvf(moving, fixed, settings) -> Deformation3D

with the computing backend and the importing backend behind it. The Morphons backend is implemented now; the importing backend is a stub until the export conventions are known, registered as X2.

The interface has a second use beyond deferral. Where both fields exist for a case, the difference they produce in gEUD on the organs driving the endpoints is measurable and reportable, which converts a choice of registration provenance into evidence at negligible cost.

### 6.2 Direction of the deformation

The evaluator warps each block’s BED field **onto the planning CT**. The block field lives on that block’s repeat image, so the required operation is a pull-back: for each voxel of the pCT, the value is fetched from a point on rCT_j. The field that expresses this maps pCT to rCT_j, not the reverse, and the reverse is not free to obtain, since inverting a diffeomorphic field is neither exact nor cheap.

The convention is therefore fixed: **fixed = pCT, moving = rCT_j**, for every registration in the pipeline. It is a convention rather than a derivation, and it is registered as X3 and verified rather than asserted, per Section 3.3.

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

### 7.1 Worst-case storage requires no dose grids

The worst-case metrics are per block, are never accumulated (E5 of the evaluator document), and are therefore never deformed and never composed. Their only use is to produce metrics on the plan’s own image. It follows that the store needs no worst-case dose grids at all, which removes what would otherwise be the largest multiplier in the module: one grid per scenario per plan.

What is stored instead is the **per-scenario DVH per ROI**, plus the derived scalars. The reason for keeping the DVH rather than only the scalars is the one the evaluator gives at its Section 7.2 for caching at the DVH: a DVH contains the (volume, dose) pairs from which any DVH-derived metric can be recomputed, and a stored scalar cannot. Since open decision 7b may still change which metrics instantiate the acceptance criterion, storing only the scalars would make a change of criterion a re-extraction. The declared cost of this choice is that anything not derivable from a DVH is lost, in particular the spatial location of a hot or cold region and any scenario-to-nominal dose difference map.

**Physical scenarios are preferred to voxel-wise aggregates.** RayStation offers both: individual scenario doses, and a voxel-wise minimum or maximum distribution constructed by taking the extreme value in each voxel across scenarios. The two are not interchangeable. The minimum over physical scenarios of the target D95 is the D95 of the worst scenario, a quantity with a referent; the D95 evaluated on a voxel-wise minimum field is more pessimistic and corresponds to no deliverable scenario, since it combines different scenarios at different points. This is the argument of the fourth requirement above, applied one level lower. The physical form also determines the aggregate, while the reverse is impossible.

Two qualifications. Whether scenario doses and voxel-wise aggregates are exportable as DICOM RT Dose is registered as X7 and is not confirmed: the DICOM conformance statements consulted name the beam set dose explicitly and do not name evaluation or scenario doses, and some export capability is documented as available only in non-clinical versions. And if the voxel-wise aggregate is taken as well as, or instead of, the scenarios, the difference between the two definitions should be computed once on one case and reported rather than argued.

## 8. Delivery time

The mapping from a plan to minutes splits in two, and only the first half is extractable.

**From the plan:** number of fields, energy layers per field, spots per layer, total MU, target volume. For pencil beam scanning the dominant term is energy layer switching, so layer count is the main predictor and spot count secondary.

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

Nothing in OpenTPS assists this. Its structure access is by literal name, `RTStruct.getContourByName`, on whatever string the DICOM file carries, so the mapping is entirely this project’s obligation. The contents of the mapping file, that is the aliases actually in use at the partner centre, cannot be written before a real RTSTRUCT or a template from the clinical partner exists; the mechanism is built now and populated later, as with the NTCP model registry.

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
    pid, site, rx_dose, n_fx
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

    Per facility
    cap_pt_min_day    # proton machine minutes per day
    cap_xt_min_day    # photon adaptation minutes per day. Swept, not measured
    days_week, uptime, n_rooms, beam_topology
    staff_avail

`cap_min_day` of version 3 is renamed `cap_pt_min_day` and joined by `cap_xt_min_day`. The second is the photon adaptation budget. It has no measured anchor for this indication and is swept rather than read from the facility, so it is a study parameter that happens to live in the facility record; the allocator document states the reason at its Appendix A and open decision 13.

Two fields present in version 1 have been removed. `dose_blocks` indexed per strategy is replaced by `dose` indexed per plan, since strategies are combinations formed downstream. `strategies_ok` is removed entirely, since the screens now run in the evaluator.

Three fields are added at version 5. `role` and `source_image` carry the rescue structure of the version 7 design, matching `BlockPlan` in `core/schema.py`. `hypo_eligible` is the per-patient flag A32 requires as input. `robust_eval` changes content rather than name: it holds DVHs and scalars rather than grids.

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

Primitives: dose arrays, image and grid geometry, ROI masks and the mapping file, facility constants, NTCP model parameters, swept study parameters, and the export manifest. Derived: D98, D95, V95%, gEUD, DVHs, accumulated dose, occupancies. Only primitives are tagged, which keeps the table at the order of tens of rows per patient. The list of primitives is provisional and is revised as the schema settles.

## 14. Assumptions register

New at version 5. Assumptions specific to extraction were previously carried informally in Section 15 or not at all. The allocator uses the prefix A and the evaluator E; this document uses **X**. Where an assumption mirrors one in another document, the other is named rather than restated.

| ID | Assumption | Status | Risk |
|----|------------|--------|------|
| X1 | OpenTPS objects are constructed at the point of use and never persisted; the store holds native `tps5d` records | Design decision, Section 3.2 | The adapter must track OpenTPS API changes, and a refactor is in progress. Confined to one module by construction |
| X2 | The deformation field is computed in OpenTPS by default; an imported RayStation field is an alternative backend behind the same interface | Design decision, Section 6.1. The importing backend is a stub | Neither source has a known accuracy in the abdomen. If the two disagree materially the choice becomes a reported sensitivity rather than a convention |
| X3 | Every registration uses fixed = pCT, moving = rCT_j | Convention, Section 6.2, verified by the synthetic test of Section 3.3 | An inverted direction produces a plausible accumulated dose that is wrong. The test is what prevents this from being silent |
| X4 | The dose is cropped to the bounding box of all contoured structures plus the target, wider than the union the active NTCP models require | Revision at version 5 of the version 1 to 4.3 masking rule, Section 5 | Storage cost is unmeasured. If large, the crop narrows without an interface change, since the per-ROI masks already carry the restriction |
| X5 | The working grid is an explicit parameter; whether dose is resampled to the CT grid or masks generated on the dose grid is not decided | Deferred to measurement on the first exported case, Section 5 | Resampling dose at ingest introduces interpolation where the gEUD draws its weight; generating masks on a coarse grid changes the discretised organ volume. Direction of each effect is known, size is not |
| X6 | Worst-case is stored as per-scenario DVHs per ROI plus derived scalars, and not as dose grids | Follows from E5 of the evaluator document: worst-case is never accumulated and never deformed, Section 7.1 | Anything not derivable from a DVH is lost, in particular spatial location and scenario-to-nominal difference maps |
| X7 | RayStation can export scenario doses, or at least per-scenario DVH data, in a form the extractor can read | **Unverified.** The DICOM conformance statements consulted name the beam set dose and do not name evaluation or scenario doses; some export capability is documented as available only in non-clinical versions | If only aggregate voxel-wise fields are exportable, the worst-case metrics change meaning and must be reported as voxel-wise rather than as scenario worst cases |
| X8 | Plan identity, that is arm, block, role and scheme, comes from an export manifest; DICOM relations serve as a consistency check | Design decision, Section 4 | The manifest is hand-written unless planning is scripted. A displaced row is the failure mode, and the DICOM check is what catches it |
| X9 | RayStation export conventions, that is dose units, RBE weighting, dose-to-water or dose-to-medium, grid origin, structure naming and file layout, are as the parser assumes | **Unverified.** No export has been inspected | A parsing assumption that is wrong is likely to fail loudly on units and file layout, and silently on RBE weighting and dose-to-medium. Depends on open decision 25 of the allocator document |

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

- Dose grid dimensions and masked ROI volumes, to be measured on the first exported case before the storage container is fixed. Together with the crop-versus-mask ratio of X4 and the grid ratio of X5, these are one measurement session on one case.
- Whether `ScriptableDicomExport` exposes evaluation and scenario doses, and whether that capability depends on the licence tier. X7.
- Machine constants for the delivery-time model, or confirmation that the RayStation estimate is usable. Belongs with the PARTICLE operating-model question.
- Plausible range for the extra photon linac time per adapted fraction, Δτ_XT, to set the sweep range. Belongs with the PARTICLE operating-model question and is open decision 12 of the allocator document. It is a range rather than a value, so it does not block extraction.
- The contents of the TG-263 mapping file, which requires a real RTSTRUCT or a template from the clinical partner. The mechanism is complete without it.

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.8 there.

Sections 16 onward: version history, in `CHANGELOG.md`.

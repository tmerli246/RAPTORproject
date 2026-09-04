# Extraction Module

Version 4.2. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

The **extractor** gathers the per-patient, per-plan and per-facility quantities the downstream modules consume. Its scope is defined by their requirements.

Its consumer is now the **evaluator**, not the allocator. The evaluator composes blocks into strategies, converts to EQD2, evaluates NTCP and applies the admissibility screens. The extractor performs none of these. It produces the raw material and the registrations, and stops.

**The extractor’s unit is the plan, not the strategy.** A strategy is a combination of per-block plans, and combinations are formed downstream. The distinction keeps the storage requirement linear in the number of blocks. At version 5 it also avoided an exponential growth in the strategy count; that growth no longer exists, and the linearity now rests on the simpler fact that each block contributes two plans however strategies are formed.

## 2. The central interface decision

The extractor emits **dose-derived quantities**. NTCP is evaluated downstream. Three reasons:

- *Model swapping.* NTCP models will change. With scalars, replacing the bowel placeholder requires re-running the whole extraction pipeline; with dose, it requires changing one record.
- *Uncertainty propagation.* Propagating uncertainty in LKB parameters requires thousands of NTCP re-evaluations with perturbed n, m and TD50. This is impossible from a stored scalar.
- *Composition.* NTCP is nonlinear, so the NTCP of a partially adapted course cannot be obtained by combining the NTCPs of adapted and non-adapted courses. Dose must be composed first and NTCP evaluated once at the end.

**Consequence for storage.** Mean dose is additive across blocks, so per-block mean doses suffice for mean-dose-driven endpoints. gEUD with a volume parameter other than unity is **not** additive: the gEUD of an accumulated dose cannot be reconstructed from the gEUDs of its parts. The voxel grid is therefore required, not optional.

## 3. Dose storage

Three rules, the first two lossless for the endpoints in use.

**Store block-level distributions, not strategy-level accumulated ones.** A strategy’s accumulated dose is a weighted sum of block distributions. Storing the accumulated version per strategy means storing every combination rather than the 2B block distributions that suffice. Under version 6 the number of strategies is four per scheme rather than 2^B, so the saving is smaller than it was, but the rule is retained for two reasons that do not depend on the strategy count: composition at evaluation time is a weighted sum of arrays and is cheap, and block-level storage is what allows the first-block dose source and the mixed-strategy diagnostic of the evaluator document, Section 2, to be composed on request without re-extraction.

**Mask to the union of relevant ROIs.** Dose outside every contoured structure enters no metric. Keep the mask and the grid geometry so arrays remain reconstructible.

**Store physical dose on native geometry. Do not store EQD2, and do not store warped dose.** Two separate reasons, which version 1 conflated:

- EQD2 depends on dose per fraction, and fractionation is a decision variable. Storing EQD2 would fix one fractionation choice in the data and silently invalidate every alternative schedule.
- The conversion to biologically effective dose is performed **before** deformation, because the conversion is nonlinear and does not commute with interpolation. The warped object is therefore a BED field, which depends on both the fractionation scheme and the structure’s alpha over beta, and is not unique. Warped fields are derived products belonging to the evaluator’s cache, not to the extractor’s store.

The extractor therefore stores physical dose per block on its own image, together with the fraction count and the deformation fields. Everything downstream of that is recomputable.

**Dose provenance.** This physical dose is computed in RayStation for both modalities and imported; OpenTPS performs no dose calculation for this study, including no use of its own photon CCC implementation. See Section 11.

Grid dimensions and masked ROI volumes are not yet known and should be measured on the first exported case before the storage strategy is fixed.

## 4. Conversion and caching

| Stage                             | Owner                          | Cost       | Cached                          | Invalidated by                                 |
|-----------------------------------|--------------------------------|------------|---------------------------------|------------------------------------------------|
| Ingest: DICOM to internal         | Extractor                      | High, once | Yes                             | Source files                                   |
| Register: DIR, deformation fields | Extractor                      | High       | Yes, as a first-class artefact  | DIR algorithm and settings                     |
| Convert to BED, warp, accumulate  | Evaluator                      | Moderate   | Yes                             | Fields, block weights, alpha over beta, scheme |
| Reduce to DVH                     | Evaluator, via the OpenTPS DVH | Low        | Yes. This is the cache boundary | Accumulated field, ROI mask                    |
| NTCP                              | Evaluator                      | Low        | Never                           | Recompute                                      |

Deformation vector fields are cached explicitly, keyed by moving image, fixed image and a hash of the DIR settings. They are the expensive and version-sensitive step, and caching warped dose without recording the field that produced it makes staleness impossible to reason about. Since the evaluator applies each field several times, once per (scheme, alpha over beta) combination, the separation between registration and application is load-bearing rather than cosmetic: registration is performed once, application is cheap.

Caches are keyed by content hash rather than by filename, and the hash is recorded in the provenance tag.

## 5. Target metrics

Target coverage is not a secondary output. It gates the optimisation. But the screen itself is applied by the evaluator, and the extractor’s obligation is to supply metrics in the form the screen requires.

Coverage cannot be inferred from NTCP. If the target shifts away from an OAR between pCT and rCT, the non-adapted plan underdoses the CTV while the OAR dose falls, so coverage fails and NTCP improves. NTCP is a function of OAR dose only and carries no information about the target.

**Metrics are per block and per plan, on the plan’s own image.** This is a change from version 1, which required metrics on the accumulated dose. Coverage is a property of a plan delivered on a given anatomy, so the judgement is made where the plan is delivered. It follows that no registration, deformation or accumulation is required to produce the inputs to the coverage screen, which is why that screen can run before any composition and prune the strategy space cheaply.

Three requirements:

- **Nominal per-block metrics** for every plan, as the primary basis for the screen.
- **Worst-case per-block metrics** from the robustness evaluation, retained as a sensitivity analysis. They are not accumulated, since the worst scenario in one block need not be the worst in another and a sum of per-block worst cases corresponds to no physical scenario.
- **The photon arm is included.** Photon dose is recomputed on the rCTs and screened on the same criterion, so it cannot be treated as a planned-dose-only reference.

The metric and threshold are V95% below 95 per cent, with further criteria possible; the extractor’s obligation is unchanged either way, since it supplies the metrics and the evaluator applies the criteria.

## 6. Delivery time

The mapping from a plan to minutes splits in two, and only the first half is extractable.

**From the plan:** number of fields, energy layers per field, spots per layer, total MU, target volume. For pencil beam scanning the dominant term is energy layer switching, so layer count is the main predictor and spot count secondary.

**The photon side requires nothing further.** Photon delivery is modelled as unconstrained, and the photon adaptation budget is charged only the adaptation increment Δτ_XT, which is an independent variable of the study rather than a quantity derived from a plan. No photon delivery-time model and no photon baseline session length are therefore required. If the budget unit is later changed to adaptation events, as recorded in Appendix A of the allocator document, this remains true.

**Not in the plan:** the machine constants that convert those counts into minutes, and the non-delivery components entirely. Contouring, re-optimisation and QA time have no representation in a plan file.

The extractor therefore supplies complexity descriptors, and the mapping from descriptors to minutes lives in a separate configuration with machine constants as named parameters. Recalibrating for a specific beamline does not touch extraction.

If RayStation reports an estimated delivery time per plan it is taken directly and tagged as vendor-estimated in the provenance. It is a model rather than a measurement, but a machine-aware one.

Complexity is extracted per plan, since only the difference between arms enters Delta tau. Two effects must be kept separate rather than folded into one term: margin reduction shortens delivery through fewer layers and spots, while hypofractionation lengthens the individual fraction through higher MU but shortens the course.

## 7. ROI naming

Canonical names follow **TG-263**, the AAPM standardised nomenclature for radiotherapy structure names. RayStation supports it. It is required not for tidiness but because the NTCP model registry must be able to name what it wants: a rectum model asks for `Rectum` and cannot ask for whatever the structure happens to be called in each plan.

The resolution rule is deliberately not fuzzy matching. Fuzzy matching fails silently, and a structure matched to the wrong OAR produces a plausible number rather than an error.

- Normalise mechanically: strip whitespace, casefold.
- Look up in an explicit per-cohort mapping file, versioned in the repository.
- **An unmapped structure raises.** Adding a mapping line takes seconds; finding a silently mismatched OAR later does not.

The mapping file is versioned and its hash is recorded with the dose provenance, since a change to the mapping changes which voxels were counted.

## 8. Relation to the NTCP model registry

The registry itself has moved to the evaluator, which is the component that evaluates NTCP. Two obligations remain here.

**Cohort validation before dose work.** Given the active model list, the extractor collects the union of required ROIs, dose metrics and clinical covariates and validates the cohort against that union at assembly time. A missing covariate surfaces before hours of registration and accumulation rather than after.

**Sizing the composition workload.** The union of distinct alpha over beta values in the registry determines how many warped fields per block the evaluator will require. The extractor reports that union so the storage and compute estimate is available before the pipeline runs.

## 9. Synthetic cohorts

Generated by a **separate module sharing the evaluator’s output schema**. Separate, so that the test harness does not share failure modes with the component under test. Shared schema, so the allocator cannot tell the difference.

**The generator emits dose metrics, not utilities.** Emitting delta NTCP directly would leave the NTCP layer and the composition path untested until real data arrives, which defeats the purpose of the interface in Section 2. A first coarse pass may emit delta NTCP directly, purely to check the allocator for trivial coding errors, but it is not the tested configuration and is not used for any reported result.

The generator has a use beyond convenience. Whether greedy allocation is safe depends on the shape of the marginal adaptation benefit as a function of the number of adaptations. Constructing deliberately concave and deliberately convex cohorts, and measuring the departure of the incremental-efficiency greedy from the exact solve in each, is a methodological result obtainable before any patient data arrives.

## 10. Schema

    Per patient
    pid, site, rx_dose, n_fx
    covariates        # driven by the NTCP model registry's declared requirements
    imaging           # pCT, rCTs, acquisition timestamps
    rois              # TG-263 canonical names via the explicit mapping file
    grid              # geometry and ROI-union mask

    Per (patient, block, plan)
    modality          # 'pt' | 'xt'
    technique         # single value per modality initially
    robustness        # setup error, range error. Determined by `adapted`, not free:
                      # an adapted plan carries the reduced setting, a
                      # non-adapted plan the clinical one
    fx_scheme         # (n, d), protocol identifier
    adapted           # whether this plan is the adapted plan for this block
    dose              # physical dose per fraction, on the plan's own image, masked
    target_metrics    # D98, D95, V95%, nominal and worst-case, on this block only
    plan_complexity   # n_fields, n_layers, n_spots, mu, target_vol
    robust_eval       # DVH bands or voxel-wise worst case, this block only

    Per registration
    dvf               # keyed by (moving, fixed, hash of DIR settings)

    Per facility
    cap_pt_min_day    # proton machine minutes per day
    cap_xt_min_day    # photon adaptation minutes per day. Swept, not measured
    days_week, uptime, n_rooms, beam_topology
    staff_avail

`cap_min_day` of version 3 is renamed `cap_pt_min_day` and joined by `cap_xt_min_day`. The second is the photon adaptation budget. It has no measured anchor for this indication and is swept rather than read from the facility, so it is a study parameter that happens to live in the facility record; the allocator document states the reason at its Appendix A and open decision 13.

Two fields present in version 1 have been removed. `dose_blocks` indexed per strategy is replaced by `dose` indexed per plan, since strategies are combinations formed downstream. `strategies_ok` is removed entirely, since the screens now run in the evaluator.

## 11. Provenance and uncertainty

Every metric and every model parameter carries a tag recording whether it is measured, taken from a named publication, or assumed. Without it, automated uncertainty propagation is difficult. Since the allocator’s output is a difference of small probabilities, sensitivity to NTCP parameter uncertainty is worth studying, and the provenance tag is what makes the set of parameters to perturb enumerable rather than hand-maintained.

**Dose is tagged RayStation-computed.** All physical dose for paper 1, both modalities, is generated in RayStation and imported; OpenTPS calculates no dose, including no use of its own photon CCC implementation for the photon arms. The choice bears on the study's premise, since analytical proton dose is least reliable in a heterogeneous abdomen and the resulting error is systematic rather than random, falling on the arm whose anatomical degradation the study measures. Which RayStation algorithm, analytical pencil beam or Monte Carlo, and the cross-modality reporting conventions, RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin, are not yet fixed: open decision 25 of the allocator document.

## 15. Open items

Two items of version 2 are closed. The coverage criterion is V95% below 95 per cent. Whether the clinical-margin adaptive arm exists is resolved: it does not, so only two plans per block are extracted, the clinical-margin pCT plan and the reduced-margin adapted plan.

**Version 6 note.** The extraction unit is unaffected by the decision to fix the workflow at prescription. Two consequences are worth recording because they are cheap to satisfy now and expensive to retrofit. The non-adapted arms require their pCT plan recomputed on every repeat image, which version 5 also required and which must not be dropped on the grounds that those arms never adapt. And if the hypofractionated schedule is adapted on in-room imaging with a block equal to a fraction, the number of plans per adapted arm rises from three to six, which changes the sizing estimate below; the granularity is open decision 23 in the allocator document.

- Dose grid dimensions and masked ROI volumes, to be measured on the first exported case before the storage strategy is fixed.
- Machine constants for the delivery-time model, or confirmation that the RayStation estimate is usable. Belongs with the PARTICLE operating-model question.
- Whether the robustness evaluation export from RayStation provides per-scenario dose or only DVH bands, which determines what the worst-case per-block metrics can contain.
- Plausible range for the extra photon linac time per adapted fraction, Δτ_XT, to set the sweep range. Belongs with the PARTICLE operating-model question and is open decision 12 of the allocator document. It is a range rather than a value, so it does not block extraction.

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.8 there.

Sections 12 to 14: version history, moved to `CHANGELOG.md`.

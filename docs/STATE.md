# Project state

**Last updated:** 2026-10-01. Code tag `design-v6.5`. Documents: road **7.2**, allocator **7.2**, evaluator **6.9**, extractor **5.11**.

**Last round: one OpenTPS installation (1 October 2026).** The code runs on the public release, OpenTPS 3.0.1, and on no other. The dispatch between two ROI rasterisation methods is removed: `roi_mask_algorithm()`, the `getBinaryMask` branch of `extract_roi_mask`, its single-slice guard and the seven tests that existed for them are gone. `mask_method_record` takes the binarisation threshold and the precision, which are now the variable part of the method (extractor 3.4, 9, 12.1, X10). Extractor 5.11 and evaluator 6.9 carry the matching text, and `pyproject.toml`, `requirements.txt` and `README.md` declare the environment (Section 6). The rows of extractor 3.4 that carry a version were read from the 3.0.1 source, the release the code requires, and no longer wait for a confirmation on a second installation. Detail is in `CHANGELOG.md`.

**Previous round: code review and its implementation (30 September 2026, tag `design-v6.4`).** The source, the tests and the two scripts were reviewed against the 29 September documents, and the findings the review confirmed were implemented in the working tree. Behaviour that changed: a `PLAN`-tagged RTDOSE is divided by `n_fx` at ingest, and its header is read, checked and recorded (extractor 5); the manifest is validated as a whole and carries `dose_image_uid`, `accept_nominal` and `accept_robust` (extractor 4); `compute_bed` takes the block fraction count n_b (evaluator 11.1); `warp_bed` fills with 0 and refuses a ROI that would sample the fill; gEUD is evaluated scaled by the maximum dose, in float64; the integer solve runs to a relative gap of 1e-6 and reports the gap it reached; P1x adapts photon patients on the standard schedule only, which changes what P1x − P1 and P3 − P1x measure (road 5.6, allocator 5.3). The four design documents were amended where text and code disagreed: allocator 7.2 (objective of each solver, D_XT, gap, P1x, tie-breaks, T16 to T18, the shape fractions of Section 5.5 from a run, the P2a and P2b illustration removed), road 7.2 (P1x), evaluator 6.8 (n_b, guards, gEUD scaling, registry validation), extractor 5.10 (dose scale, manifest validation, mapping file rules, `get_dvf` on a `WorkingGrid`). No supervisory decision was reopened. Detail is in `CHANGELOG.md`.

Rewrite this file whenever a document version, an open decision or a code milestone changes, and before bumping a document version. It is the first file to read and the only one that describes the present.

## 1. Identity

ADAPT-5D, individual research project of DC18 in the RAPTORplus MSCA Doctoral Network (grant 101226720), hosted at KU Leuven, task T4.2. Supervisor: Sterpin. Target output: paper 1, covering WP1 (simulation infrastructure) and WP2 (workflow optimisation). WP3 (reinforcement learning) belongs to a later publication, together with per-block adaptation decisions and reallocation during the course.

**Reference study.** Borderías-Villarroel, Barragán-Montero, Sterpin, Radiother Oncol 198 (2024) 110389, in project knowledge. Sterpin is its corresponding author.

**Rescue in the reference study: settled, do not reopen.** The paper does not describe offline rescue of an arm that loses coverage, and states that planned photon doses were representative of the delivered dose. Sterpin confirmed that the rescue was applied, photon arm included, as standard clinical practice. The sentence on photon dose refers to the absence of delivery reconstruction (log files, measurements), not to the absence of rescue. The documents therefore record rescue and photon recomputation as inherited (allocator 2, A10). The manuscript states the procedure explicitly, since a reader of the paper alone would not infer it.

## 2. Document set and conventions

The four design documents, this file and `CHANGELOG.md` live in `docs/` at the repository root, alongside `README.md` and `src/tps5d/`.

| Document | Version | Owns |
|---|---|---|
| `ROAD_TO_PAPER_1.md` | 7.2 | Scientific question, hypothesis, arm set, uncertainty budget, plan budget, endpoint policy, what the paper claims, declared limitations (7.2) |
| `allocator_design.md` | 7.2 | Optimisation problem, algorithm, shadow prices, step-ratio threshold (6.2), policies, synthetic cohorts (5.5), time model, assumptions register (11), open decisions (12) |
| `evaluator_design.md` | 6.9 | Strategy construction, interface, accumulation ordering, composition, coverage verification and no-harm diagnostic, caching, NTCP model registry, assumptions register (10), implementation (11) |
| `extractor_design.md` | 5.11 | OpenTPS mapping and adapter rules (3), export manifest (4), storage (5), registration (6), target metrics (7), ROI naming (9), schema (11), provenance (12), assumptions register (13), open items (14) |
| `CHANGELOG.md` | – | Version history, retired register rows, deleted material, renumbering maps. In the repository, not in project knowledge |

**Version numbers.** The evaluator is one version behind the allocator on the major number: one supervisory decision amends both. The extractor moves when its own content moves. Code tags track behaviour, not document versions: a code round is tagged `design-vX.Y` for the document generation its behaviour matches. The first `design-v7.x` tag is earned when the evaluator composes non-adapted arms from the manifest's plan sequence, rescue plans included.

**Identifiers.** Assumptions: **A** (allocator), **E** (evaluator), **X** (extractor), no shared numbering; a mirrored assumption names its twin rather than restating it. Open-decision numbers are shared across documents. Retired identifiers are not reused; each register lists its retired IDs at the end.

## 3. Design, in one paragraph

The treatment choice is made at prescription on the planning CT. Each patient carries **seven** options: XT-A, PT-NA and PT-A under each of two fractionation schedules, plus one XT-NA whose schedule is fixed per patient by the photon protocol's eligibility criteria. The modelled workflow is systematic online adaptation, with one replan per block, on the block's repeat image, standing for the daily replans. An adapted arm adapts at every block, at reduced margin from the first fraction. A non-adapted arm carries the clinical-margin pCT plan recomputed on each repeat image, and is **rescued** by an offline replan at unchanged margin wherever it fails the acceptance criterion; the rescue carries forward and is judged again on later blocks. The acceptance criterion is fixed before planning; the judgement and every rescue are made in RayStation at plan generation and recorded in the export manifest, and the evaluator re-checks them, with RayStation governing where the two disagree. Worst-case evaluation is recorded and counted, and does not trigger rescue. Nothing is removed from any option set. Two resources are priced, proton machine time and photon adaptation time, both only for online adaptation; a rescue is unpriced. XT-NA consumes neither budget, is assignable for every patient, and is both the ΔNTCP reference and the default arm, so the no-harm property is structural. Proton hypofractionation is an investigational workflow, simulated for every patient; its tumour-control equivalence is an assumption (allocator A5).

## 4. Open decisions

### Sterpin

| ID | Question |
|---|---|
| – | Confirmation that paper 1 answers which patient receives which workflow, and that when to act within a course, and the right-time framing of the work package, belong to a later publication |
| 28 | Clinical and reduced margins for both modalities: the clinicians supply one modality, the other follows by conversion as in the reference study (robust optimisation capped at 5 mm, remainder as CTV expansion). Candidate proposes, Sterpin decides |
| 30 | Route for recomputing a plan on a repeat image in RayStation: dose on an additional examination, or plan copied as a new beam set. Decides what the export contains and how the manifest check places recomputed doses (extractor 4, X7, X8) |

### Clinical partners

| ID | Question |
|---|---|
| 3 | PARTICLE operating model: hours per day, rooms, beam sharing, slot length. Which Δτ components are extractable from RayStation plan data |
| 7b | Which metrics instantiate the acceptance criterion. Target metrics (V95%, D5) and OAR metrics (Dmean, Dmax on the driving organs) are requested separately; only the second changes the meaning of the primary endpoint. Fixed before plan generation. Gated on 19 |
| 12 | Range of Δτ_XT, and whether photon plan verification within a session is measurement-based or computational. Photon department |
| 13 | Reference photon adaptation budget C_XT^ref, in absolute minutes. With Sterpin |
| 25 | RayStation dose engine for the proton plans (analytical or Monte Carlo) and cross-modality reporting conventions: RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin |
| 29 | Source of contours on the repeat images: clinical recontouring, DIR propagation with review, or new delineation, and by whom |
| 31 | Which schedules the photon protocols sanction at the chosen site, for which patients and on which photon arm (adaptive stereotactic, non-adaptive stereotactic, conventional, hypofractionated non-adapted). The photon option set is reconstructed from the answer; a change to the current structure goes to Sterpin. Gated on 19 |
| – | Per-patient hypofractionation eligibility flag, required data under A32. Gated on 19 |
| – | Whether the prescription of a schedule varies by patient (extractor 14). Blocks nothing |

### Split

| ID | Question | Split how |
|---|---|---|
| 10 | Endpoint model family. Models without a fractionation term are evaluated on mean EQD2 at a declared α/β, with the approximation stated; never on physical dose across schedules. No longer blocks the fractionation axis | Candidate proposes, Sterpin decides; gated on 19 |
| 19 | Anatomical site: pancreas or adrenal. Criteria in order: clinical doubt between schedules and planning with the clinicians; repeat imaging; endpoint models | Partners indicate which cases exist; Sterpin judges suitability |
| 23 | Block structure of the hypofractionated schedule: which images represent its blocks, including whether images from conventionally fractionated courses are mapped by elapsed time. Fixes B and the plan budget (15 per patient with standard blocks, 19 with one block per fraction) | Candidate proposes, Sterpin decides, after the data are seen |

### Candidate

| ID | Question |
|---|---|
| 26 | Whether one objective template, scripted in RayStation, produces acceptable adapted replans and rescues without intervention. Covers every replan, so plan quality is governed by one rule across arms. The reference study re-optimised with the pCT objectives and fine-tuned where necessary, so a no-intervention template is stricter. Also open: who does the planning |

### Closed, for reference

Stated in the section each governs; the reasoning is in `CHANGELOG.md`.

| ID | Resolution | Where stated |
|---|---|---|
| 11 / A3 | Photon adaptation is rationed; photon delivery is unconstrained. Confirmed by Sterpin, September 2026 | allocator 5.1, A3 |
| 14 | Heuristics rank proton upgrades only; the photon budget is spent in decreasing ΔNTCP | allocator 5.3 |
| 15 | Reference solver is the ILP (`scipy.optimize.milp`); the DP is a cross-check at C_XT = 0 | allocator 5.1 |
| 16, 17 / A12, A22 | No harm is reported, not enforced; the protection is structural | allocator 8.3 |
| 18 / A32 | XT-NA carries one schedule, fixed by clinical eligibility; the proton arms and XT-A carry both | allocator 10.1, A32 |
| 20 | Dropped (29 September): per-replan charging prices an offline workflow the online reading excludes | allocator 9 |
| 21 / A23 | First block on the planning anatomy for every arm. Under the online reading it favours the non-adapted arms; a declared limitation, investigable by recomposition without new plans | allocator 4 |
| 22 | The reduced-margin non-adapted diagnostic is not computed | allocator 4 |
| 24 / A24, A28 to A31 | Coverage failure is rescued at unchanged margin; nothing is removed | allocator 8.2 |
| 27 / A28, A29 | Rescue is unpriced and carries forward | allocator 8.2 |
| – | Displaced patients stay in the denominator of the cohort mean | allocator 7 |

**Not decisions, recorded so they stop reappearing as ones.**

- Fourth-year funding rests on a verbal assurance from Sterpin. No source is identified and none is needed before the Career Development Plan at M13.
- DIR: Morphons is the backend in use, since the field is applied in OpenTPS for the accumulation ordering. The imported RayStation field is kept for continuity with the reference study, and the gEUD difference between the two is measured on the first cases (extractor 6.1, X2).
- Paper 1 cohort: adults at the chosen site are preferred, but the cohort will be whatever the data allow (Section 5).
- D4.1 is covered by the photon plan evaluation work (Secondment 1). The allocator is delivered as an OpenTPS plugin.

## 5. Data and the blocking chain

**Ethics.** Dossier S72661 (Ethische Commissie Onderzoek UZ/KU Leuven), accepted September 2026. Retrospective in-silico study, Sterpin coordinating investigator, pseudonymised data on the UZ Leuven research database, abdominal lesions treated at UZ Leuven or PARTICLE 2020 to 2026. The protocol targets 30 to 100 cases and may include paediatric patients, with a view to the later reinforcement-learning work. For paper 1, adults at the chosen site are preferred; both candidate sites, their protocols and the NTCP models under discussion are adult.

**What blocks what.**

1. **Data access and the first exported case** gate everything empirical: the verification of the manifest and of the acceptance judgement, composition of non-adapted arms from the manifest, the measurement session (extractor 14), and X7 to X12.
2. **Decision 19 (site)** gates 7b, 31, the eligibility flags, 10 and the prescriptions.
3. **Decisions 7b, 28, 29 and 30** gate plan generation. The acceptance criterion must be fixed before any rescue is planned, since changing it later changes which plans exist.
4. **Decision 23** gates the plan budget of the hypofractionated schedule, and depends on the images the data contain.
5. **Decision 26** sizes the planning effort; its probe needs one exported case.

Decision 10 no longer blocks the fractionation axis.

## 6. Code

Package `tps5d` in the RAPTORproject repository, `src/tps5d/` with `core`, `allocator`, `evaluator`, `generator`, `extractor`. Python 3.12, which numpy 2.5 and OpenTPS 3.0.1 both require, in a conda environment, Windows, PowerShell. `requirements.txt` and the `opentps` extra of `pyproject.toml` pin `opentps-core==3.0.1` (extractor 3.1). Tag `design-v6.5`.

| Package | Modules |
|---|---|
| `core` | `schema.py`: `Strategy` (adapted as a boolean, `arm` derived from modality and adaptation through `ARM_OF`), `BlockPlan` (`block_index`, `role` ∈ {planned, rescue}, `source_image`, and optional `dose_image`, `accept_nominal`, `accept_robust`), optional `block_plans` per strategy, the all-planned sequence enforced for adapted arms; `Facility` validated at construction; strategy identifiers unique within a patient; `Allocation.gap` |
| `allocator` | `solve.py` (ILP reference with `MIP_REL_GAP = 1e-6` and the achieved gap returned, `solve_dp` cross-check), `dominance.py` (Pareto and hull), `policies.py` (P1x on the standard schedule, tie-breaks by photon occupancy and identifier), `report.py` (including `rescue_counts`, `dominance_counts` anchored per axis, the MIP gap), `figures.py` (record-based API) |
| `generator` | `synth.py`: seven options per patient, `hypo_frac` eligibility, `SHAPES`, `pen_xt` (default 0), synthetic rescue draw (`p0 = 0.05`, `decay = 0.5`, placeholders) (allocator 5.5) |
| `evaluator` | `ntcp.py`, `registry.py` (validated records), `compose.py` |
| `extractor` | `records.py` (including `WorkingGrid`, `BlockFractions`, `DoseHeader`), `adapters.py`, `ingest.py`, `roi_mapping.py`, `manifest.py`, `provenance.py` (extractor 3.5) |
| `scripts/` | `make_figures.py` (allocator figures from a cohort or from records), `two_scheme_check.py` (regimes of the two-schedule hull over the biological penalty and Δτ_PT), `shape_fractions.py` (hull composition of the three generator shapes, the percentages of allocator 5.5) |

**Tests: 469 passed, 0 skipped, 469 collected**, run on the project machine with `python -m pytest tests -q -rs` on 1 October 2026: Windows, Python 3.12, OpenTPS 3.0.1 installed from `requirements.txt`. 299 collected in the suites that predate the extractor and composition work, including the new `test_allocator_rules.py` 9; 170 in `test_adapters.py` 33, `test_roi_mapping.py` 15, `test_manifest.py` 35, `test_compose.py` 25, `test_ingest.py` 22, `test_provenance.py` 22, `test_end_to_end.py` 9, `test_cohort_validation.py` 9. A test is kept when it guards a fix or a closed-form design claim, at most one per fix.

**Behaviour.** The allocator implements the version 7 design. The evaluator composes, converts and evaluates with the block fraction count, verified end to end on synthetic DICOM; it does not yet compose non-adapted arms from a manifest plan sequence or verify the acceptance judgement. The extractor reads and validates the extended manifest, converts a plan-total dose to per fraction at ingest, and records the dose header, the masking parameters and n_b as provenance. Rescue exists only as the generator's synthetic draw.

**Where the code is behind the documents.**

- The evaluator's composition from the manifest and its verification of the acceptance judgement (evaluator 6.1, 11.3, code review item G-5), which also earns the first `design-v7.x` tag.
- The check of `dose_image_uid` against the loaded dose waits on decision 30. The column is read and validated for form only.
- The deformation field cache is not implemented. Its key includes the hash of the `WorkingGrid` (extractor 6), which `WorkingGrid.content_hash` provides.
- Known and not scheduled: OpenTPS 3.0.1 only warns on a CT with a non-standard orientation and `ingest_ct` does not raise on it (review item S-04, the orientation part); the `DVH` constructor computes a histogram at 100 Gy and `computeDVH` then computes it again at the field's own `maxDVH` (S-07, the wasted work); `solve_greedy` is O(iterations · P · 7), 4.5 s at P = 1000 and 43 s at P = 3000 in the review, and a heap version is not applied since it changes no result (S-13).

## 7. Next actions

1. **Obtain the first exported case**, now that S72661 is accepted.
2. **One request to the clinical partners** covering 7b (target and OAR metrics separately), 31 and the eligibility flags, repeat imaging and images for short courses (23), contours on repeat images (29), 25, 3, 12, 13, and whether prescriptions vary by patient.
3. **One request to Sterpin** covering 28, 30 and the scope confirmation.
4. **Decision 26 probe** on the first case: script one adapted replan per modality from a fixed objective template, and record whether it is acceptable without intervention.
5. **Measurement session** on the first case (extractor 14): grid dimensions and masked volumes, crop ratio, grid routes, `baseResolution`, the gEUD difference between the two DVF backends, masking sensitivity, the axis convention across readers, and the dose header (`DoseSummationType`, `DoseUnits`, `DoseType`, `DoseGridScaling`, direction of `GridFrameOffsetVector`) with the target's dose per fraction before and after the conversion at ingest.
6. After decision 19: map the sign of the utility of a hypofractionated photon arm against a standard-schedule one, on synthetic DVHs, over the plausible range of α/β and volume parameter (allocator 10.1).

## 8. Calendar

Full detail in `dc18_timeline.docx`. Salient points only.

| PM | Date | Item |
|---|---|---|
| M13 | Jan 2027 | Career Development Plan, and the ADAPT-5D data description for the consortium DMP. Both drafted at M11 or M12, since M13 to M15 are fully committed |
| M14 | Feb 2027 | Training Camp 1, presentation to the EU Project Officer |
| M15 | Mar 2027 | Secondment 1, Ljubljana, Jeraj, 2 months |
| M19 | Jul 2027 | **D4.1, Upgraded OpenTPS**, covered by the photon plan evaluation. Public, posted automatically by REA. Feature freeze before departure at M14 if possible |
| M30 | Jun 2028 | Secondment 2, HPTC, Blommestein, 2 months |
| M33 | Sep 2028 | **MS13**, verified by implemented software. Internal freeze at M28 |
| M37 | Jan 2029 | D4.7, automated biological adaptive PT planning. Depends on D4.2, D4.3 and D4.5 from other groups |
| M40 | Apr 2029 | Secondment 3, COSYLAB, Anderle, 1 month |
| M42 | Jun 2029 | Funded contract ends |
| M48 | Dec 2029 | Thesis draft for MS18 |

- **No target date for paper 1** is set.
- **The secondment total is five months, not seven.** Annex 1 requires one visit of at least three months; Sterpin raised the deviation and it was accepted, so no visit needs extending.
- **Secondment 1 scope: photon plan evaluation**, agreed with Sterpin and the OpenTPS team in August 2026; the four-option assessment is in `dc18_timeline.docx` §8.3. Since all dose is imported from RayStation, the case for the host rests on the evaluation work, and the MS17 report needs a statement of what made the two months specific to Ljubljana. With the D4.1 freeze before departure, the visit contributes to paper 1 rather than to D4.1, an accepted consequence.
- The obligations after M42, including the M48 thesis draft, are conditional on the fourth year being in place.

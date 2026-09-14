# Evaluation Module

Version 6.4. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

The **evaluator** turns per-block dose into per-strategy utility and admissibility. It sits between the extractor and the allocator and is the only component that touches a dose grid on a per-strategy basis.

Division of responsibility across the three modules:

| Module    | Owns                                                                                                                                                           | Does not own                                                            |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| Extractor | Ingest, registration, per-block physical dose, per-block target metrics, plan complexity descriptors, facility data                                            | Any conversion to EQD2, any NTCP evaluation, any admissibility decision |
| Evaluator | Strategy construction, composition of blocks into strategies, EQD2 conversion, DVH reduction, NTCP evaluation, both admissibility screens, NTCP model registry | Any allocation decision, any knowledge of capacity                      |
| Allocator | The multiple-choice knapsack over utilities and occupancies, the shadow price, the policy comparison                                                           | Any contact with a dose grid                                            |

### 1.1 Why a third component is required

Two constraints stated in the companion documents are individually correct and jointly force the split.

- The extractor stores **block-level** distributions rather than strategy-level accumulated ones. At version 5 the argument was a counting one: the accumulated form required 2^B distributions where 2B sufficed. At version 6 there are four strategies per schedule rather than 2^B, so the saving is smaller, but the rule stands on two grounds that do not depend on the strategy count: composition at evaluation time is a weighted sum of arrays already held, and the conversion to EQD2 depends on the fractionation scheme, which is a decision variable.

- The allocator **never touches a dose grid**, so that it is unit-testable against synthetic tables and developable before data access.

Composition is the only operation in the pipeline that depends simultaneously on the strategy and on the voxel grid. It therefore belongs to neither. A third component is not an added layer but the recognition of a boundary that was already implied.

A second reason is that the conversion to EQD2 depends on the fractionation scheme, which is a decision variable. Conversion must therefore happen at composition time and its result must not be stored. Locating conversion inside the extractor would freeze one fractionation choice in the stored data and silently invalidate every alternative schedule.

## 2. Strategy construction

The evaluator is the component that builds each patient’s strategy space, and construction precedes every screen. Strategies that violate the planning workflow are not generated and then removed; they are never generated.

**Margin is a property of the arm.** Following the version 6 supervisory decision, the workflow is chosen at prescription and adaptation is a course-level property. The construction rule is therefore a mapping from the arm rather than from a per-block indicator:

- A **non-adapted arm** carries the clinical-margin plan generated on the pCT. Its dose on blocks after the first is that plan recomputed on the block’s repeat image, **unless the recomputed plan fails the coverage screen on that block**, in which case the arm carries a replan generated on that repeat image at unchanged margin, which then carries forward to later blocks and is screened again on each of them. This is the version 7 supervisory decision, A24 and A28 to A30 of the allocator document. "Non-adapted" therefore means reactively adapted at clinical margin, not zero replans.

- An **adapted arm** carries the reduced-margin plan generated on the pCT for the first block, and the reduced-margin replan generated on each subsequent block’s repeat image.

**The rule applies to both modalities.** An adapted photon arm carries the reduced-margin photon plan on the same footing as the proton arm. Neither modality carries an adaptation vector.

Robustness contributes no independent index to the strategy tuple, as in version 5, but because it is fixed by the arm rather than derived from a vector. A free crossing of margin with adaptation would generate plans that could not be delivered.

**What this implies for the option set.** A patient holds **seven** strategies, independently of the number of blocks. XT-A, PT-NA and PT-A each carry both fractionation schemes; XT-NA carries one, fixed exogenously by clinical eligibility under A32 of the allocator document, because it represents the treatment the patient would receive under current practice. Version 5 built 2^B adaptation schedules per group and collapsed them to B + 1; both the construction and the collapse are removed. The number of blocks continues to govern how many dose fields must be composed per strategy, and no longer governs how many strategies exist.

**The first block is evaluated on the planning anatomy.** Its contribution to every strategy is the nominal planned dose on the pCT. This is the reference study’s convention and preserves comparability with its decomposition. Its consequence is not symmetric across arms and is declared as A23 in the allocator document; whether to also report the first block evaluated on the first repeat image, as a conservative bound, is open decision 21 there. The evaluator must therefore keep the first block’s dose source configurable rather than hard-wired.

**Mixed strategies are computable and are not options.** A reduced-margin pCT plan recomputed on the repeat images is a valid composition that requires no new plan. It is not a member of the option set presented to the allocator. Whether it is computed as a reported diagnostic, which would separate the margin-reduction benefit from the adaptation benefit within the study, is open decision 22 in the allocator document. The evaluator should be able to compose it on request without that composition entering the option set.

**Consequence for admissibility.** Version 2 recorded the clinical-margin adaptive plan as the fallback when the coverage screen removes the reduced-margin plan on a block; versions 5 and 6 recorded that no fallback existed. At version 7 the fallback exists for every arm and is rescue at unchanged margin, so nothing is removed and no option set can empty. The count of blocks on which the **reduced-margin** plan failed is still emitted, but it now reads as a diagnostic on scripted replanning rather than on margin deliverability: under A1 and A4 an adapted arm's block plan is optimised on the anatomy it is evaluated on, so the count is zero by construction and a non-zero entry means the objective template failed to produce an acceptable plan. See open decision 26 of the allocator document. The case where a reduced-margin plan cannot be made acceptable at all is A31 there: the adapted arm is absent from that patient's option set from the start.

## 3. Interface contract

**Consumes, per patient:** block-level physical dose per candidate plan, masked to the ROI union; deformation vector fields keyed by image pair and DIR settings hash; per-block target metrics, nominal and worst-case; ROI masks and grid geometry under canonical names; clinical covariates required by the active NTCP models; plan complexity descriptors.

**Dose provenance (E16).** This physical dose is computed in RayStation for both modalities and imported; OpenTPS performs no dose calculation for this study, including no use of its own photon CCC implementation. See Section 10.

**Emits, per (patient, strategy):**

| Field       | Meaning                                                                                                                                 |
|-------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| u           | Utility. Union ΔNTCP against the locked baseline                                                                                        |
| dntcp_k     | Per-endpoint ΔNTCP, for reporting                                                                                                       |
| ntcp_k      | Absolute per-endpoint NTCP, for reporting and for the internal solve                                                                    |
| tau_pt      | Proton machine occupancy per fraction, minutes. Zero for photon strategies                                                              |
| tau_xt      | Photon adaptation time per fraction, minutes. Zero for proton strategies and for XT-NA. Charged on every fraction of an adapted arm, since an adapted arm adapts at every block |
| n_fx        | Fraction count                                                                                                                          |
| admissible  | Boolean                                                                                                                                 |
| reason      | Which screen removed the strategy, if any                                                                                               |
| eqd2_target | Descriptive target EQD2 at the declared tumor α/β                                                                                       |
| dvh         | Cached reduced dose, per ROI, retained for parameter propagation                                                                        |

The allocator consumes the first seven fields and nothing else. It sees a callable returning utility and admissibility for a (patient, strategy) pair, and no dose object of any kind.

**Why occupancy is emitted per resource.** The two costs are consumed by disjoint groups of arms, so a single occupancy field would have to be read together with the modality to know which budget it draws on. Two fields make the resource explicit and let the allocator treat the option set as two chains without inspecting the modality string. The photon field carries the adaptation increment only, since photon delivery is not a constrained resource; the allocator document states the reason at its Section 5.1.

**Internal representation of utility.** Each patient receives exactly one strategy, so the sum of baseline NTCP over the cohort is a constant. Maximizing the sum of ΔNTCP and minimizing the sum of absolute NTCP are therefore the same problem. The evaluator emits both, the allocator solves on absolute NTCP, and ΔNTCP is used for reporting and for the no-harm diagnostic. This removes a class of sign and baseline errors.

## 4. Accumulation ordering

### 4.1 The choice

Two operations must be applied to each block dose: deformation onto the planning CT frame, which is an interpolation, and conversion from physical dose to equivalent dose in 2 Gy fractions, which is nonlinear. They do not commute.

**Adopted ordering.** For each block b, on its native geometry and inside each ROI mask, compute the biologically effective dose field at that ROI’s α/β:

BED_b(x) = n_b · d_b(x) · (1 + d_b(x)/(α/β)), with d_b(x) = D_b(x)/n_b

then deform BED_b onto the planning CT, then sum over blocks, then convert the total once:

EQD2(x) = BED_total(x) / (1 + 2/(α/β))

BED is additive over segments because the underlying model is multiplicative in survival, so summation after deformation is exact. Conversion precedes interpolation, so the commutation error is not incurred.

### 4.2 Why the ordering matters quantitatively

The conversion is convex in dose, so interpolating before converting **underestimates** systematically. The error is zero where dose is uniform and largest where the gradient is steep.

Illustration with α/β of 3 Gy, one fraction, two adjacent voxels at 1 Gy and 5 Gy, and a target voxel falling midway:

| Ordering             | Intermediate         | Result  |
|----------------------|----------------------|---------|
| Deform, then convert | (1 + 5)/2 = 3.00 Gy  | 3.60 Gy |
| Convert, then deform | 0.80 Gy and 8.00 Gy  | 4.40 Gy |

The example is extreme by construction and is included to make the mechanism visible, not to quantify the expected effect. What makes it relevant here rather than generic is the volume parameter. For a serial-like organ with a small volume parameter, such as rectum at n = 0.09, the generalised equivalent uniform dose approaches maximum dose and therefore draws its weight from the high-gradient region, which is exactly where the error lives. For an endpoint driven by mean dose the error would average out.

**Corrected 14 September 2026.** The second row's 5 Gy figure was 10.00 Gy; it is 8.00 Gy, D·(d+α/β)/(2+α/β) = 5·8/5, confirmed by two further independent routes: BED then conversion by hand, and `ntcp.bed`/`ntcp.eqd2_from_bed` run directly, both giving 8.00 Gy exactly, and the row's result changes from 5.40 to 4.40 Gy accordingly. The first row was already correct and is unchanged. The likely origin of the error: 5×8/**4** = 10.00 exactly, consistent with the denominator having used α/β = 2, the value in the Section 7.2 example elsewhere in this document, rather than the α/β = 3 this illustration states throughout. A plausible transcription, not confirmed as such. `evaluator/compose.py`'s tests do not depend on this row regardless of the mechanism: they are built on independently derived numbers, detailed in Section 11.5.

### 4.3 What the ordering costs

BED_b depends on n_b, which follows from the fractionation scheme, and on α/β, which follows from the structure. The deformed field is therefore not unique: one exists per (block, scheme, α/β) combination. With two schemes and two distinct α/β values in the registry this is four warped fields per block per arm rather than one.

These are four **applications** of a cached deformation field, not four registrations. Registration is performed once per image pair and cached as a first-class artefact. Applying a field to an array is an interpolation and is cheap. The registration cost, which dominates, is unchanged.

### 4.4 Sensitivity measurement rather than assumption

The alternative ordering is computed once on a real case and the difference in gEUD is reported for the organs driving the NTCP. This converts an assumption into a measurement at negligible cost and pre-empts the question rather than inviting it. If the difference is negligible the sentence is short; if it is not, the adopted ordering is justified by evidence rather than by argument.

## 5. Composition of strategies

### 5.1 Structure

A strategy is the tuple (modality, adaptation, fractionation, technique). The robustness setting is not a component: it is determined by the arm, as specified in Section 2. Adaptation is a boolean scalar rather than a vector over blocks, so each (modality, fractionation) group holds two strategies; with the XT-NA schedule fixed exogenously, each patient holds seven. Rescue is not a component of the tuple either: it is a deterministic consequence of the screen given the anatomy, not a choice, so it changes the dose composed for a strategy without adding strategies.

Composition of a strategy is a weighted sum of cached warped BED fields, with block weights given by the fraction counts. It is an array operation over the masked ROI union and is cheap relative to registration. The number of fields summed is the number of blocks; the number of compositions is the number of strategies, which no longer grows with the number of blocks.

### 5.2 Collapse by dominance, retired

**Void at version 6.** The collapse existed because occupancy depended only on the number of adapted blocks while utility depended on which blocks were adapted, so all but the best schedule at each count were strictly dominated. With adaptation reduced to a scalar there are no schedules sharing an occupancy and nothing to collapse. The evaluator presents the constructed strategies directly.

Two things that the collapse carried are lost with it and are recorded so that they are not silently missed. The reportable answer to whether early or late adaptation carries more benefit, which was read off which schedule won at each count. And the 2^B compositions per group, which were the evaluator’s dominant cost at large B and are now four compositions per scheme regardless of B. The second is a saving; the first is a loss, and it belongs to the second publication together with the per-block option set.

**What survives from this section.** The Pareto reduction itself remains valid and is still applied: among options of equal cost only the best utility survives, and an option that costs more without buying more is dropped. With four options per scheme it will rarely bind, but it is what removes strategies of negative utility from the chains, which test T10 in the allocator document depends on. Dominance is not compared across modalities at this stage, and the allocator does not take a hull across the two chains either. The further hull reduction used by the allocator’s LP path is applied there, not here, since it is valid only for the relaxation.

## 6. Admissibility

Admissibility rests on one enforced screen and one reported diagnostic. They differ in basis, in cost, and in what they do with a failing strategy. At version 7 neither removes anything.

| Stage           | Basis                           | Requires registration and accumulation? | Granularity | Effect on a failing strategy |
|-----------------|---------------------------------|-----------------------------------------|-------------|------------------------------|
| Target coverage | Per-block dose on its own image | No                                      | Per plan    | A rescue plan at unchanged margin is substituted from that block onward; the arm is retained |
| No harm         | Accumulated EQD2, then NTCP     | Yes                                     | Per strategy | Counted and reported; the strategy is retained |

### 6.1 Coverage, judged per block, and rescue

Target coverage is a property of a plan delivered on a given anatomy. If the plan an arm would deliver on rCT*j* falls below the acceptance criterion, that plan would not be delivered, and the judgement requires no accumulation.

**What follows is a substitution.** The arm acquires a replan generated on that image at unchanged margin and unchanged setup error, which carries forward and is screened again on each later block. The evaluator's composition for a non-adapted arm is therefore a piecewise sequence of clinical-margin plans rather than one plan recomputed throughout, and the sequence is determined by the screen rather than chosen. This is the version 7 supervisory decision; Sections 8.1 to 8.6 of the allocator document carry the argument and A24 and A28 to A31 carry the assumptions.

**Consequences.**

- The screen removes nothing, so no option set can empty and the strategy count is independent of the anatomy. Version 6 removed a failing arm for the whole course, per schedule; that behaviour is withdrawn.

- **Screen every arm; expect rescues only on the non-adapted ones.** Under A1 and A4 an adapted arm's block plan is optimised on the anatomy it is then evaluated on, so nominal coverage holds by construction. The screen is still run on PT-A and XT-A and the count reported per arm, because A4 requires the property to be demonstrated rather than asserted and a non-zero count there is a scripted-replanning failure, which is open decision 26 of the allocator document. The implementation must not special-case the adapted arms out of the screen.

- The number of coverage evaluations equals the number of plans, rescue plans included, rather than the number of strategies.

- **The screen no longer prunes before composition.** Versions 2 to 6 justified keeping the two stages separate by the ordering saving: coverage ran first and accumulation was performed only for survivors. There are no survivors to select now, since nothing is removed, and the screen instead determines *which* plan each block contributes. The stages stay separate for a different reason: the screen decides the composition, so it must run before it, and it still requires no registration or accumulation.

- Accumulated coverage is not retained, in any role.

- **The criterion is the plan acceptance protocol used at treatment planning.** The screen takes a list of criteria of which all must pass, and the count is emitted per criterion, so instantiating the list is a configuration change. Which metrics instantiate it is open decision 7b of the allocator document, now a question for the clinical partners and the RTTs, with target metrics and OAR metrics kept apart because only the second changes what the primary endpoint means.

- **Rescue frequency is a first-class emitted quantity**, per arm, per schedule and per block. It replaces the removal count of earlier versions, and it is the diagnostic that has to exist before the manuscript rests on the no-harm property, since the count of patients with no free option is now zero by construction.

### 6.2 Worst-case coverage

Worst-case metrics are evaluated **per block and not accumulated**. Retained as a sensitivity analysis. It is expected not to fire on the adapted arms, since robust evaluation at the reduced margin is part of plan acceptance; where a reduced-margin plan cannot pass it at plan generation, the arm is absent from that patient's option set rather than removed later, which is A31 of the allocator document.

### 6.3 No harm

A strategy whose union ΔNTCP against the locked baseline is negative is **counted and reported, not removed**. This revises versions 1 to 4, in which it was removed on the same footing as a coverage failure. The requirement it serves is unchanged: maximising a cohort mean must not make an individual worse than current standard care. What changed is the recognition that removal is not what secures it. The argument is given in Section 8.3 of the allocator design and is not repeated here; the evaluator's part is that the no-harm computation does not touch the admissibility flag.

**The diagnostic is computed on the union scalar only.** A strategy that worsens one endpoint while improving the others can still be the right choice, and excluding it on a single endpoint would be stricter than the selection rule used everywhere else in the design. Per-endpoint sign violations are counted and reported explicitly, so the cost of the convention is visible rather than hidden.

**Structural consequence, unconditional at version 7.** No harm removes nothing and coverage removes nothing, so neither can contribute to an empty option set. Version 6 could establish this only where XT-NA was assignable, and identified the patients whose XT-NA the screen had removed as the exception. There is no such patient now: XT-NA is rescued like any other arm, every patient holds a free assignable option of zero utility, and the dominance argument holds cohort-wide.

**What is emitted.** The count of strategies whose union ΔNTCP is not positive, excluding the reference arm, whose zero is definitional. It measures how often adaptation or a changed schedule fails to reduce the union probability, which is of independent interest and is distinct from how often such a strategy is selected.

**The baseline's two roles no longer separate.** XT-NA serves as the ΔNTCP reference and as an assignable option. The coverage screen could previously remove the second role while leaving the first; it now rescues instead, so both roles hold for every patient. The reference is redefined accordingly as the photon treatment the patient would receive under current practice: clinical margin throughout, at the schedule clinical eligibility assigns them under A32, with offline rescue where coverage fails. One consequence must be carried into reporting: a rescue improves the reference NTCP, so the zero point of that patient's ΔNTCP moves with the acceptance criterion. The shift is a per-patient constant applied to all seven of their options, so the intra-patient ordering is unaffected and only the level moves.

### 6.4 Empty option sets

**Unreachable.** Neither screen removes a strategy, so the multiple-choice constraint is always satisfiable. The only way an option set can shrink is A31, an adapted arm not generated because its reduced-margin plan could not be made robustly acceptable, which is an absence recorded at construction with its reason and cannot remove XT-NA.

The infeasibility raise is retained as a defensive check on the evaluator's own construction. If it fires it indicates a defect, not a patient.

## 7. Caching

### 7.1 Stages

| Stage                             | Cost     | Cached                                                              | Invalidated by                 |
|-----------------------------------|----------|---------------------------------------------------------------------|--------------------------------|
| Warp BED per (block, scheme, α/β) | Moderate | Yes                                                                 | Deformation field, α/β, scheme |
| Sum over blocks                   | Low      | Yes, per strategy                                                   | Block weights, warped fields   |
| Convert to EQD2                   | Low      | No                                                                  | Recompute                      |
| Reduce to DVH                     | Low      | **Yes. This is** the cache** boundary** | Accumulated field, ROI mask    |
| gEUD                              | Very low | No                                                                  | Recompute from DVH             |
| NTCP                              | Very low | Never                                                               | Recompute                      |

### 7.2 Why the boundary is the DVH and not the gEUD

The Monte Carlo propagation of NTCP parameter uncertainty requires thousands of re-evaluations with perturbed parameters. The three LKB parameters do not enter at the same stage. TD50 and m enter only at the final evaluation. The volume parameter n enters earlier, through the gEUD exponent a = 1/n:

gEUD = (Σ_i v_i · D_ia)(1/a)

A cached gEUD scalar cannot be recomputed at a perturbed a. A cached DVH can, because it contains exactly the (v_i, D_i) pairs the power mean requires. Caching at the DVH therefore makes the propagation a sum over a few hundred bins per sample, which is microseconds, and thousands of samples become free.

**Declared approximation.** A gEUD recomputed from a binned DVH is not identical to one computed voxel by voxel. The difference is controlled by bin width, provisionally 0.1 Gy, and is verified once on a real case by comparing the two routes rather than assumed.

**The DVH dose axis must be set, not defaulted.** `DVH.computeDVH(maxDVH=100.0)` truncates the dose axis at 100 Gy **absolute**, not at a multiple of the prescription. Verified in the installed environment on 11 September 2026: a uniform 150 Gy field on a 60 Gy prescription returns Dmax 150 and D2 99.99, since Dmax reads the dose array while D2 reads the histogram.

The truncation is harmless for physical dose and is not harmless here, because the DVH this section caches is taken on **accumulated EQD2**. EQD2 passes 100 Gy at prescription level in hypofractionated schedules at the low α/β of late-responding organs: 5 × 8 Gy at α/β = 2 is 100 Gy EQD2, 5 × 10 Gy at α/β = 3 is 130 Gy, before any hot spot. A target at α/β = 10 stays below. Truncation would therefore fall asymmetrically, on the hypofractionated arms and on the OAR endpoints, which is one of the two structural liberations of this work; it would bias a small-volume-parameter gEUD downward by removing exactly the upper tail the power mean weights; and it would be silent, since Dmax continues to report correctly.

`maxDVH` is therefore set from the actual maximum of the field with margin, and the value used is recorded. At 4096 bins a 200 Gy axis still gives a step near 0.05 Gy, so the declared approximation above is unaffected. This is an instance of the general rule in extractor Section 3.4 that nothing is called with its defaults. Recorded here because the constraint bites where the DVH meets EQD2, which is this document's territory rather than the extractor's.

**α/β is outside the cache.** It enters before the DVH, so perturbing it invalidates the accumulated field. A sensitivity analysis on α/β therefore requires recomposition rather than re-evaluation and is structurally more expensive than the LKB propagation. This is consistent with treating α/β as a separate sensitivity axis rather than as a parameter propagated in bulk.

## 8. NTCP model registry

Relocated from the extractor, since the evaluator is now the component that evaluates NTCP.

Models are declarative records rather than classes. What varies between sites is which structures matter, which endpoints are modelled and which parameters those models use. None of that is code.

Model ( name = ‘rectum_bleeding_g2’, site = ‘pelvis’, kind = ‘lkb’, roi = ‘Rectum’, metric = (‘gEUD’, 0.09), \# a = 1/n alpha_beta = 3.0, params = {‘td50’: 76.9, ‘m’: 0.13, ‘n’: 0.09}, covariates = \[\], source = ‘Michalski 2010 QUANTEC’, fitted_on = ‘solid rectum, photon, 1.8-2.0 Gy/fx’)

Three functional forms cover nearly everything: LKB on a gEUD input, logistic on a linear predictor over dose metrics and clinical covariates as used by the Dutch protocols, and relative seriality. Each is one function and kind selects it. Adding a site means adding records.

**Engine contract.** Given a cohort and a list of models, the engine collects the union of required ROIs, metrics, covariates and α/β values, validates the cohort against that union **before any dose work**, then evaluates. A missing covariate surfaces at cohort assembly, not after hours of accumulation. The union of α/β values also determines how many warped fields per block are required, so the registry is what sizes the composition workload.

**Endpoint composition is declared, not assumed.** The active endpoint list and the composition rule belong to the site configuration. Otherwise changing site silently changes the meaning of the selection scalar.

**fitted_on is not documentation.** The QUANTEC rectum parameters were fitted on a particular delineation convention, on photon data, at conventional fractionation. Each is an assumption when the parameters are applied to a proton adaptive workflow with hypofractionation in the design. Recording it as a field makes the mismatch visible and lets the assumptions register be generated from the registry rather than maintained by hand.

**Scope.** The mechanism is built now, since retrofitting it is painful, but populated only for the site in use.

## 9. Utility and reporting outputs

**Selection scalar.** The union probability over the active endpoints:

NTCP_total = 1 − Π_k (1 − NTCP_k)

The independence assumption is false, since toxicities in a shared anatomical region are correlated, so the composite overestimates the probability of at least one event. This is inherited from the reference study and accepted as the best available treatment. The direction of the bias is stated in the manuscript rather than left implicit.

**Per-endpoint values are emitted on the same call**, since reporting requires them and the no-harm violation count requires them.

**Target EQD2 is a first-class output.** Schedule equivalence rests on clinical consensus rather than on a linear quadratic conversion, so target EQD2 is reported for completeness rather than to assert equivalence: it makes any residual mismatch in tumour effect between fractionation arms visible. It uses the same machinery applied to the CTV with a different α/β. It belongs in the evaluator’s output record rather than being computed ad hoc at figure time.

**Per-endpoint weights.** The interface carries per-endpoint weights defaulting to the union form, so that severity-weighted utilities can be substituted later without structural change.

**Dominance inputs.** The evaluator does not compute dominance, which belongs to the allocator, but its emitted option sets are what the allocator’s two dominance counts, Pareto and LP, are computed on; the per-block coverage-fallback count of Section 6.1 is emitted here because only the evaluator sees the per-block screen outcomes.

## 10. Assumptions register

| ID  | Assumption                                                                                                                                                               | Status                                                                                                                                                                                                     | Risk                                                                                                                                                                      |
|-----|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| E1  | BED is additive over blocks, so deformation may follow conversion and precede summation                                                                                  | Exact under the linear quadratic model                                                                                                                                                                     | None beyond the validity of the model itself                                                                                                                              |
| E2  | Conversion before deformation is preferable to the reverse                                                                                                               | Adopted; the reverse is computed once and the difference reported                                                                                                                                          | Low. Measured rather than assumed                                                                                                                                         |
| E3  | gEUD recomputed from a binned DVH approximates the voxel-wise value                                                                                                      | To be verified on the first real case at the chosen bin width                                                                                                                                              | Low, controlled by bin width                                                                                                                                              |
| E4  | Target coverage is judged per block on the plan delivered in that block                                                                                                  | Corrects the earlier accumulated criterion                                                                                                                                                                 | Stricter than the accumulated form, which is the intended direction                                                                                                       |
| E5  | Worst-case coverage is a per-plan property and is not accumulated                                                                                                        | Adopted; per-block worst cases correspond to no physical scenario                                                                                                                                          | The nominal and worst-case screens answer slightly different questions, which must be stated                                                                              |
| E6  | No harm is judged on the union scalar, and is **reported rather than enforced**                                                                                          | Consistent with the selection rule; per-endpoint violations counted. Enforcement removed by decision of the doctoral candidate, pending supervisory confirmation; open decision 16 of the allocator design | A strategy worsening one endpoint may be selected. Harmful strategies remain in the option set and are declined by dominance in the allocator rather than by removal here |
| E7  | Occupancy depends only on the number of adapted blocks, not on which. Stated per resource                                                                                | Follows from the time model. Applies within each modality, since each modality draws on one budget                                                                                                         | If block-dependent, the dominance collapse of Section 5.2 does not hold                                                                                                   |
| E8  | The linear quadratic model is valid for OAR EQD2 conversion over the fraction sizes considered                                                                           | To be checked against real cases                                                                                                                                                                           | Applies to OARs only, not to any tumour claim                                                                                                                             |
| E9  | Margin level is determined by the adaptation vector: adapted blocks carry the reduced-margin plan on their repeat image, non-adapted blocks the clinical-margin pCT plan | Construction rule of Section 2, mirroring A14 of the allocator document. Single adaptive margin level adopted at supervision                                                                               | A free crossing would generate undeliverable plans and an inflated strategy count. Removes the conservative fallback under coverage failure                               |
| E10 | The DVH is computed by OpenTPS and consumed in its cumulative form, with `maxDVH` set from the field rather than left at its default                                     | Adopted; a separate implementation was removed. Binning error and re-evaluation cost measured, both negligible. `maxDVH` amended at version 6.1 after verification in the installed environment             | Notation differs: OpenTPS writes the power-mean exponent as EUDa where this document writes 1/n. The default `maxDVH=100.0` truncates at 100 Gy absolute and would silently clip accumulated EQD2 on the hypofractionated arms: Section 7.2 |

| ID  | Assumption                                                                                                         | Status                                                                      | Risk                                                                                                                                                                                                                                                                                                                                  |
|-----|--------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| E11 | Photon adaptation is decided per block, on the same block structure as protons                                     | Design decision of version 5 of the allocator document, mirroring A18 there | If photon adaptation is in practice course-level, the photon group has two members rather than B + 1 and the intermediate photon options are unreachable                                                                                                                                                                              |
| E12 | The photon adapted arm carries the reduced-margin plan on the block’s repeat image, as the proton adapted arm does | Extends the construction rule of Section 2 to photons                       | If the photon margin reduction is not deliverable on a block, the coverage screen removes it and no conservative adaptive photon plan remains, exactly as for protons                                                                                                                                                                 |
| E13 | Only the adaptation increment is charged to the photon budget                                                      | Follows from A17 of the allocator document                                  | If photon delivery is binding at the partner centre, the emitted tau_xt understates photon demand                                                                                                                                                                                                                                     |
| E14 | The photon adapted arm adapts on the block repeat images, the same rCTs the proton arm uses                        | Design decision. The rCTs are the images that exist in the data             | The modelled photon adaptation is a per-block surrogate of the online ART workflow, which adapts on daily CBCT or MR. The surrogate understates adaptation frequency and uses a different image; the direction of the net bias on the photon adaptation benefit is not known. This is the photon twin of A1 of the allocator document |
| E16 | All dose for paper 1 is computed in RayStation and imported, for both modalities; OpenTPS performs no dose calculation, including no use of its photon CCC implementation | Design decision, following the Secondment 1 scope confirmation | The engine choice and cross-modality reporting conventions, RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin, remain open: decision 25 of the allocator document. Bears on the study's premise, since analytical proton dose is least reliable in a heterogeneous abdomen and the resulting error is systematic rather than random, falling on the arm whose anatomical degradation the study measures |

### 10.1 Amendments at version 5

The rows below are superseded, amended or added by the version 6 decision of the allocator document that modality, adaptation and fractionation are all chosen at prescription on the planning CT. The original rows are left in place above so that the change is visible; where the two conflict, this subsection governs. The version numbers differ because this document is one version behind the allocator; the decision is the same one.

| ID  | Status |
|-----|--------|
| E7  | **Retired.** Occupancy no longer depends on a count of adapted blocks, because there is no adaptation vector. It is a per-course quantity taking two values per modality per schedule. Mirrors A13. The risk column referred to the dominance collapse of Section 5.2, which is itself retired |
| E9  | **Superseded by E15.** Margin is a property of the arm, not of the block. Mirrors A14, superseded by A25 |
| E11 | **Superseded.** Photon adaptation is a course-level decision, symmetric with the proton arm. The risk column of the original row anticipated this outcome and it has occurred. Mirrors A18 |
| E12 | **Amended.** The photon adapted arm carries the reduced-margin plan from the first fraction, on the pCT plan, and its dose is recomputed on each repeat image. The construction is per arm rather than per block, symmetric with the proton adapted arm |
| E15 | **New.** The reduced margin is a property of the adapted arm and applies from the first fraction, on the pCT plan. Construction rule of Section 2, mirroring A25 of the allocator document. Single adaptive margin level adopted at supervision. Risk: a free crossing would generate undeliverable plans and an inflated strategy count, and no conservative fallback remains under coverage failure |

E13 is unaffected: A17, which it follows, is retained.

### 10.2 Amendments at version 6

The rows below are superseded, amended or added by the version 7 supervisory decision of the allocator document that an arm which loses target coverage is rescued by offline replanning at unchanged margin, and by the decision that the fractionation schedule of XT-NA is fixed by clinical eligibility. The version numbers differ because this document is one version behind the allocator on the major number; the decision is the same one.

| ID  | Status |
|-----|--------|
| E4  | **Retained, with its effect changed.** Coverage is still judged per block on the plan delivered in that block. What follows a failure is a substitution rather than a removal |
| E6  | **Retained, and its qualification removed.** No-harm enforcement is redundant for every patient, not only where XT-NA is assignable. Open decision 16 of the allocator document is resolved in the affirmative |
| E12 | **Amended again.** Its risk column stated that a photon reduced-margin plan failing on a block would be removed with no conservative photon plan remaining. Neither half survives: the adapted arms do not fail the nominal screen by construction, and where a reduced-margin plan cannot be made acceptable the arm is absent from the option set at construction, which is A31 of the allocator document |
| E15 | **Amended.** The reduced margin remains a property of the adapted arm and applies from the first fraction. The clause "no conservative fallback remains under coverage failure" is void: the fallback is rescue at unchanged margin and it applies to every arm |

| ID  | Assumption | Status | Risk |
|-----|------------|--------|------|
| E17 | A non-adapted arm's dose on a block is the pCT plan recomputed on that block's image, or, where that fails the screen, a replan generated on that image at unchanged margin which carries forward and is re-screened | Construction rule of Section 2, mirroring A24, A29 and A30 of the allocator document, all confirmed at supervision | The composition for a non-adapted arm is a piecewise sequence of plans whose breakpoints depend on the acceptance criterion. Changing the criterion changes the dose composed, not only which strategies pass, so the criterion must be recorded with every result |
| E18 | Rescue is a deterministic consequence of the screen and not a component of the strategy tuple | Follows from E17: the screen is applied to the anatomy in hand and admits no choice | The strategy count is independent of the anatomy, which is what keeps the option set fixed at seven and the MCKP structure intact |
| E19 | A rescue is unpriced on both budgets, so the emitted per-fraction occupancies are unchanged by it | Mirrors A28 of the allocator document, confirmed at supervision and inherited from the reference study | If a rescue were priced, the emitted cost of a non-adapted arm would become anatomy-dependent. The formulation would still hold, since costs are per patient per option, but XT-NA would cease to be free and the no-harm property would revert to empirical |
| E20 | XT-NA carries one fractionation schedule per patient, supplied as an eligibility flag in the patient record | Mirrors A32 of the allocator document | The flag is required input. Where it is hypofractionated, the numeraire for that patient is a hypofractionated arm and every ΔNTCP they carry is referred to it |

E13 is unaffected: A17, which it follows, is retained and is part of the argument for E19.

## 11. Implementation strategy

New at version 6.2. Sections 4 to 7 specify the composition machinery; nothing implementing them exists yet, confirmed against STATE.md's own account of what is built. This section is the design-before-code step for it, on the same footing as extractor 3 was for that module: written and reviewed before the code that follows it, not after.

**Appended rather than inserted.** Extractor 3 sits early in that document because a dedicated renumbering round put it there. No such round has been done here, and doing one now would cost more than it returns: STATE.md and other documents already point at "evaluator 10, 10.1, 10.2" for the assumptions register, and those pointers stay valid only if existing numbers are not moved. This section is therefore 11, not slotted in earlier, following the same numbering-preservation rule CHANGELOG.md states for every document.

### 11.1 Module and scope, revised after `ntcp.py` and `registry.py` were read

The 6.2 draft of this section stated that `evaluator/ntcp.py` and `evaluator/registry.py` were recorded as already implemented but not read, and that `compose.py` would therefore stop at a DVH and invent nothing about what consumes it. Reading them on 14 September 2026, once Tommaso supplied the files, found more overlap than that boundary anticipated: `ntcp.py` already has `bed`, `eqd2_from_bed` and `geud_from_cumulative_dvh`, the same three pieces of arithmetic `compose.py`'s first draft had independently written. `ntcp.py`'s own docstring states the reason this is a problem, not a redundancy to shrug at: *"Keeping both here and there invites a parameter to be changed in one and not the other, so that a result depends on which module was imported."*

**Revised scope.** `compose.py` does not compute BED, EQD2 or gEUD itself. It calls `ntcp.py` for all three and confines itself to what `ntcp.py`'s own docstring says it deliberately does not do: OpenTPS-geometry-aware operations, warping a field, summing fields on a shared grid, and constructing the DVH, which `ntcp.py` states it takes as given rather than computing. `ntcp.py` is "pure functions only", plain arrays, no OpenTPS objects; `compose.py` is the geometry-aware layer around it.

    compute_bed(dose_per_fraction, n_fx, alpha_beta) -> BED array          # via ntcp.bed
    warp_bed(bed_field, dvf) -> BED array, on the fixed image's grid       # no ntcp.py involvement
    sum_bed(bed_fields: list) -> total BED array                          # no ntcp.py involvement
    bed_to_eqd2(bed_total, alpha_beta) -> EQD2 array                      # via ntcp.eqd2_from_bed
    reduce_to_dvh(eqd2_field, roi_mask, *, max_dvh=None) -> DVH           # no ntcp.py involvement
    geud_from_dvh(dvh, n) -> float                                        # via ntcp.geud_from_cumulative_dvh

**The dose convention had to be bridged, not just confirmed.** Section 4.1 defines `d_b(x) = D_b(x)/n_b`, and extractor design 5 stores physical dose per fraction, so the 6.2 draft concluded no conversion was needed at the boundary. That conclusion assumed `compute_bed` would implement the formula itself. `ntcp.bed(dose, n_fx, ab)` takes `dose` as a segment's **total** physical dose and derives the per-fraction value internally; calling it with the extractor's per-fraction dose directly would silently divide by `n_fx` a second time. `compute_bed` now multiplies by `n_fx` before calling `ntcp.bed`, which divides by `n_fx` again inside: an exact round trip, not an approximation, and it is what lets the module keep the extractor's native per-fraction dose as its own public input while still calling the one place the LQ formula is written down.

**`geud_from_dvh` took `a = 1/n` in the first draft**, a second convention invented before `ntcp.py` had been read. It now takes `n`, matching `ntcp.py` and `registry.py`'s `Model.params['n']` for the `'lkb'` kind, and is a direct unpack-and-delegate to `ntcp.geud_from_cumulative_dvh`, which additionally normalises the volume fractions and raises on an empty DVH, robustness the first draft's own arithmetic lacked.

**`warp_bed` takes an already-computed field, and does not call `get_dvf` itself.** Registration, `extractor.adapters.get_dvf`, is performed once per image pair and cached (extractor design 6); applying a cached field to an array is cheap and repeated once per (block, scheme, α/β) combination (evaluator design 4.3, "four applications... not four registrations"). Keeping the two calls apart, rather than having `warp_bed` reach for `get_dvf` on every call, is what makes that sentence true of the code rather than only of the design. The registration's `moving` and `fixed` are the block's repeat image and the planning CT respectively, per extractor 6.2 and X3; the BED field is a separate array living on that same repeat-image grid, and it is what gets passed to the already-obtained field's `deformImage`, not a parameter of the registration itself.

**Where compose.py's output actually goes**, now visible from `registry.py`: `evaluate()` for the `'lkb'` and `'rseriality'` kinds takes `eqd2_dose` as a plain voxel array and calls `geud()` on it directly, not through a DVH at all. The DVH `reduce_to_dvh` builds is for the cached, repeated-re-evaluation path Section 7.2 describes, perturbing `n` many times without recomputing the accumulated field; the primary, single nominal NTCP evaluation for a strategy takes `bed_to_eqd2`'s array output directly, via `.imageArray`, into `registry.evaluate`. Both paths exist and are both this module's concern to feed correctly, not only the DVH one the 6.2 draft assumed was the sole consumer.

### 11.2 What is deferred and stated as such

**Caching**, Section 7.1's table, is not implemented this round. `compute_bed`, `sum_bed` and `bed_to_eqd2` are pure functions of hashable inputs by construction, so a content-hash-keyed cache in the style of `DIRSettings.content_hash()` can wrap them later without changing their signatures; deferring the cache is a sequencing choice, not a design gap. `warp_bed` is the expensive stage and is exactly the one the extractor's own DVF cache, keyed by (moving, fixed, settings hash), already covers, so caching at that layer is largely inherited rather than new.

**The Section 7.2 declared approximation**, that a gEUD from a binned DVH differs from a voxel-wise one by an amount controlled by bin width, is stated in the design and is not measured in this round: it requires a real case, per that section's own text, and does not block writing or testing `geud_from_dvh` against synthetic and hand-computed cases. `ntcp.py`'s own `geud()`, the direct voxel-wise route, and `geud_from_cumulative_dvh`, now confirmed as the two routes this approximation compares, are both already implemented; only the real-case comparison itself remains open.

**The Section 4.4 sensitivity measurement**, the alternative ordering computed once on a real case, is unaffected by this round for the same reason: no real case exists yet to compute it on.

**Wiring `compose.py`'s output into `registry.evaluate` end to end**, beyond confirming the interface shape above, is not done this round either: it requires a cohort object with the `.rois`/`.covariates` shape `validate_cohort` expects, which belongs with the ingest work of extractor items 5 and 6, not with this round.

### 11.3 What is testable now, and what is not

Testable now, and where Sections 11.4 and 11.5 record what was exercised: `compute_bed` and `bed_to_eqd2` against hand-computable values; `sum_bed` against a synthetic multi-block case; `reduce_to_dvh`'s `maxDVH` handling against the exact hypofractionated numbers Section 7.2 already states, 5 × 8 Gy at α/β = 2 giving 100 Gy EQD2 and 5 × 10 Gy at α/β = 3 giving 130 Gy, reproduced as fixtures rather than paraphrased; `geud_from_dvh` against a uniform-dose case, where gEUD equals the dose regardless of the volume parameter, and against a two-value case computable by hand. `warp_bed` reduces to the extractor's own registration test, extractor 3.3, since it adds no new deformation logic.

Not testable now: whether the composed EQD2 field is correct on real anatomy, which needs real dose and real deformation fields rather than synthetic ones; and the Section 4.4 and 7.2 measurements stated above as deferred.

### 11.4 The Section 4.2 illustration, and why it is not the golden test regardless

Section 4.2 stated a worked example: α/β = 3 Gy, one fraction, two adjacent voxels at 1 Gy and 5 Gy, a target voxel midway. The plan was to reproduce it verbatim as a test fixture. Recomputing it while writing the test found that the second row did not check out; corrected in place at 4.2, confirmed independently via `ntcp.bed`/`ntcp.eqd2_from_bed` once those became available. Even corrected, it is not adopted as the golden test: the test suite is built on numbers derived and checked independently of the design document's prose throughout, named in 11.5, which is the more conservative choice given one number in this document has already needed correcting once.

### 11.5 Implemented at version 6.3, tested on both environments, reconciled with `ntcp.py`

`evaluator/compose.py`: `compute_bed`, `warp_bed`, `sum_bed`, `bed_to_eqd2`, `reduce_to_dvh`, `geud_from_dvh`, matching Section 11.1's revised signatures. 21 tests in `tests/test_compose.py`, passing against both the public OpenTPS release and the project's own checkout, 14 September 2026.

**Delegation is tested directly, not only by matching numbers.** Four tests call `ntcp.bed`, `ntcp.eqd2_from_bed` and `ntcp.geud_from_cumulative_dvh` alongside the corresponding `compose.py` function and assert the results agree, rather than only checking `compose.py`'s output against a hand-computed value that could coincidentally match a second, independent formula.

**One thing found writing `geud_from_dvh`'s first draft, before `ntcp.py` was available to compare against.** `DVH.histogram` is **cumulative**, confirmed by reading `computeDVH`'s source directly: volume in percent, "volume receiving at least this dose", the same convention `computeVx` and `computeDx` already rely on. `ntcp.geud_from_cumulative_dvh`, now known to already exist, recovers the differential form the same way this section's first draft independently derived, `v_i = volume[i] - volume[i+1]`, confirming the derivation rather than replacing it, and adds normalisation and an empty-DVH check the first draft lacked.

**Verified by construction rather than only by test.** `bed_to_eqd2`, via `ntcp.eqd2_from_bed`, reproduces the algebraic identity that at exactly 2 Gy per fraction, EQD2 equals total physical dose for any α/β, since the α/β-dependent terms in BED and in the EQD2 denominator cancel; checked algebraically before being written as a test rather than the reverse. The Section 7.2 hypofractionated numbers, 5 × 8 Gy at α/β = 2 giving 100 Gy and 5 × 10 Gy at α/β = 3 giving 130 Gy, were independently recomputed before use as fixtures and matched exactly, unlike the 4.2 illustration, which `ntcp.bed`/`ntcp.eqd2_from_bed` also confirmed independently once available: Section 4.2.

**`warp_bed` is tested as the thin delegation it is stated to be**, against a synthetic zero-displacement field, checking it returns exactly what `Deformation3D.deformImage` returns: the deformation logic itself is extractor 3.3's registration test, not re-tested here.

**Not yet done.** Caching, per 11.2. Wiring `compose.py`'s EQD2 output into `registry.evaluate` end to end against a real cohort object, per 11.2. The Section 4.4 sensitivity measurement and the Section 7.2 declared gEUD-binning approximation, both requiring a real case.

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.7 there.

Sections 11 to 14: version history, moved to `CHANGELOG.md`.

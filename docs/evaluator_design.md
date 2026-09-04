# Evaluation Module

Version 5.2. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

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

- A **non-adapted arm** carries the clinical-margin plan generated on the pCT, for every block. Its dose on blocks after the first is that plan recomputed on the block’s repeat image.

- An **adapted arm** carries the reduced-margin plan generated on the pCT for the first block, and the reduced-margin replan generated on each subsequent block’s repeat image.

**The rule applies to both modalities.** An adapted photon arm carries the reduced-margin photon plan on the same footing as the proton arm. Neither modality carries an adaptation vector.

Robustness contributes no independent index to the strategy tuple, as in version 5, but because it is fixed by the arm rather than derived from a vector. A free crossing of margin with adaptation would generate plans that could not be delivered.

**What this implies for the option set.** A patient holds four strategies per fractionation scheme and eight over the two schemes, independently of the number of blocks. Version 5 built 2^B adaptation schedules per group and collapsed them to B + 1; both the construction and the collapse are removed. The number of blocks continues to govern how many dose fields must be composed per strategy, and no longer governs how many strategies exist.

**The first block is evaluated on the planning anatomy.** Its contribution to every strategy is the nominal planned dose on the pCT. This is the reference study’s convention and preserves comparability with its decomposition. Its consequence is not symmetric across arms and is declared as A23 in the allocator document; whether to also report the first block evaluated on the first repeat image, as a conservative bound, is open decision 21 there. The evaluator must therefore keep the first block’s dose source configurable rather than hard-wired.

**Mixed strategies are computable and are not options.** A reduced-margin pCT plan recomputed on the repeat images is a valid composition that requires no new plan. It is not a member of the option set presented to the allocator. Whether it is computed as a reported diagnostic, which would separate the margin-reduction benefit from the adaptation benefit within the study, is open decision 22 in the allocator document. The evaluator should be able to compose it on request without that composition entering the option set.

**Consequence for admissibility.** Version 2 recorded the clinical-margin adaptive plan as the fallback when the coverage screen removes the reduced-margin plan on a block. That fallback no longer exists. A block on which the reduced-margin plan fails coverage leaves the non-adapted plan, which may fail for the same anatomical reason, or the photon arms. The count of blocks on which the reduced-margin plan failed is emitted, since it measures how often the licensed margin reduction is not in fact deliverable.

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
| Convert, then deform | 0.80 Gy and 10.00 Gy | 5.40 Gy |

The example is extreme by construction and is included to make the mechanism visible, not to quantify the expected effect. What makes it relevant here rather than generic is the volume parameter. For a serial-like organ with a small volume parameter, such as rectum at n = 0.09, the generalised equivalent uniform dose approaches maximum dose and therefore draws its weight from the high-gradient region, which is exactly where the error lives. For an endpoint driven by mean dose the error would average out.

### 4.3 What the ordering costs

BED_b depends on n_b, which follows from the fractionation scheme, and on α/β, which follows from the structure. The deformed field is therefore not unique: one exists per (block, scheme, α/β) combination. With two schemes and two distinct α/β values in the registry this is four warped fields per block per arm rather than one.

These are four **applications** of a cached deformation field, not four registrations. Registration is performed once per image pair and cached as a first-class artefact. Applying a field to an array is an interpolation and is cheap. The registration cost, which dominates, is unchanged.

### 4.4 Sensitivity measurement rather than assumption

The alternative ordering is computed once on a real case and the difference in gEUD is reported for the organs driving the NTCP. This converts an assumption into a measurement at negligible cost and pre-empts the question rather than inviting it. If the difference is negligible the sentence is short; if it is not, the adopted ordering is justified by evidence rather than by argument.

## 5. Composition of strategies

### 5.1 Structure

A strategy is the tuple (modality, adaptation, fractionation, technique). The robustness setting is not a component: it is determined by the arm, as specified in Section 2. Adaptation is a boolean scalar rather than a vector over blocks, so each (modality, fractionation) group holds two strategies and each patient holds eight.

Composition of a strategy is a weighted sum of cached warped BED fields, with block weights given by the fraction counts. It is an array operation over the masked ROI union and is cheap relative to registration. The number of fields summed is the number of blocks; the number of compositions is the number of strategies, which no longer grows with the number of blocks.

### 5.2 Collapse by dominance, retired

**Void at version 6.** The collapse existed because occupancy depended only on the number of adapted blocks while utility depended on which blocks were adapted, so all but the best schedule at each count were strictly dominated. With adaptation reduced to a scalar there are no schedules sharing an occupancy and nothing to collapse. The evaluator presents the constructed strategies directly.

Two things that the collapse carried are lost with it and are recorded so that they are not silently missed. The reportable answer to whether early or late adaptation carries more benefit, which was read off which schedule won at each count. And the 2^B compositions per group, which were the evaluator’s dominant cost at large B and are now four compositions per scheme regardless of B. The second is a saving; the first is a loss, and it belongs to the second publication together with the per-block option set.

**What survives from this section.** The Pareto reduction itself remains valid and is still applied: among options of equal cost only the best utility survives, and an option that costs more without buying more is dropped. With four options per scheme it will rarely bind, but it is what removes strategies of negative utility from the chains, which test T10 in the allocator document depends on. Dominance is not compared across modalities at this stage, and the allocator does not take a hull across the two chains either. The further hull reduction used by the allocator’s LP path is applied there, not here, since it is valid only for the relaxation.

## 6. Admissibility

Admissibility rests on one enforced screen and one reported diagnostic. They differ in basis, in cost, and in what they do with a failing strategy.

| Stage           | Basis                           | Requires registration and accumulation? | Granularity                              | Effect on a failing strategy                   |
|-----------------|---------------------------------|-----------------------------------------|------------------------------------------|------------------------------------------------|
| Target coverage | Per-block dose on its own image | No                                      | Per plan, removes families of strategies | Removed: `admissible` set false                |
| No harm         | Accumulated EQD2, then NTCP     | Yes                                     | Per strategy                             | Counted and reported; the strategy is retained |

### 6.1 Coverage, judged per block

Target coverage is a property of a plan delivered on a given anatomy. If the non-adapted plan evaluated on rCT1 falls below the acceptance criterion, that plan would not be delivered for that block, and the judgement requires no accumulation.

**Consequences.**

- The screen acts on arms, not on individual strategies. A failure of the non-adapted plan at block b removes the non-adapted arm of that modality for the whole course, per schedule. Version 5 stated this as the removal of every strategy whose adaptation vector was false at b; with adaptation reduced to a scalar the family is a single arm. See open decision 24 of the allocator document.

- The number of coverage evaluations equals the number of plans rather than the number of strategies.

- The screen runs **before** any composition, so accumulation is performed only for surviving strategies. This is a real ordering saving and is the reason the two stages are kept separate rather than merged.

- Accumulated coverage is not retained, in any role.

- The criterion is V95% below 95 per cent, and the screen takes a **list** of criteria of which all must pass, since further criteria may be added. The count of strategies removed is emitted per criterion, so that adding one later is a configuration change and its effect is visible separately.

- Where the reduced-margin plan fails on a block, no conservative adaptive plan remains for that block. The count of such blocks is emitted, since it quantifies how often the licensed margin reduction is undeliverable.

### 6.2 Worst-case coverage

Worst-case metrics are evaluated **per block and not accumulated**.

### 6.3 No harm

A strategy whose union ΔNTCP against the locked baseline is negative is **counted and reported, not removed**. This revises versions 1 to 4, in which it was removed on the same footing as a coverage failure. The requirement it serves is unchanged: maximising a cohort mean must not make an individual worse than current standard care. What changed is the recognition that removal is not what secures it, and that where removal would change the answer it does harm. The argument is given in Section 8.3 of the allocator design and is not repeated here; the evaluator’s part is that the no-harm computation no longer touches the admissibility flag.

**The diagnostic is computed on the union scalar only.** A strategy that worsens one endpoint while improving the others can still be the right choice, and excluding it on a single endpoint would be stricter than the selection rule used everywhere else in the design. Per-endpoint sign violations are counted and reported explicitly, so the cost of the convention is visible rather than hidden.

**Structural consequence.** No harm removes nothing, so it cannot contribute to an empty option set under any circumstances, and coverage is the only route to infeasibility. Version 4 asserted that conclusion while still enforcing the screen, where it did not hold: coverage could remove XT-NA, no harm could then remove every remaining strategy that was worse than an arm the patient could not receive, and Section 6.4 would raise for a patient with a deliverable plan. The conclusion now follows from the design rather than being asserted against it.

**What is emitted.** The count of strategies whose union ΔNTCP is not positive, excluding the reference arm, whose zero is definitional. Under the previous design this count was identically zero by construction. It now measures how often adaptation or a changed schedule fails to reduce the union probability, which is a quantity of independent interest.

**The baseline’s two roles are separated.** XT-NA serves as the ΔNTCP reference and as an assignable option, and the coverage screen applies only to the second role: the baseline retains its reference role regardless of its own admissibility, so every ΔNTCP in the study remains referenced to the same arm on every patient. The case is expected to be rare in practice, since photon dose is comparatively insensitive to anatomical change in the absence of range error, and the screen is expected to do its real work on the non-adapted proton arm, whose fragility under anatomical change is the premise of the project. The rule is stated so that, should the rare case occur on a real patient, its handling is a recorded design decision rather than a choice made after seeing the result.

### 6.4 Empty option sets

If every strategy for a patient fails the screens, the multiple-choice constraint cannot be satisfied and the problem is infeasible. The evaluator raises and names the patient and the failing screen.

No fallback is provided.

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
| E10 | The DVH is computed by OpenTPS and consumed in its cumulative form                                                                                                       | Adopted; a separate implementation was removed. Binning error and re-evaluation cost measured, both negligible                                                                                             | Notation differs: OpenTPS writes the power-mean exponent as EUDa where this document writes 1/n                                                                           |

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

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.7 there.

Sections 11 to 14: version history, moved to `CHANGELOG.md`.

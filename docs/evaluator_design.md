# Evaluation Module

Version 6.9. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

The **evaluator** turns per-block dose into per-strategy utility and the admissibility diagnostics. It sits between the extractor and the allocator, and it is the only component that touches a dose grid on a per-strategy basis.

Division of responsibility across the three modules:

| Module    | Owns | Does not own |
|-----------|------|--------------|
| Extractor | Ingest, registration, per-block physical dose, per-block target metrics, plan complexity descriptors, the export manifest, facility data | Any conversion to EQD2, any NTCP evaluation, any admissibility judgement |
| Evaluator | Strategy construction, composition of blocks into strategies, EQD2 conversion, DVH reduction, NTCP evaluation, the coverage verification and the no-harm diagnostic, the NTCP model registry | Any allocation decision, any knowledge of capacity |
| Allocator | The multiple-choice knapsack over utilities and occupancies, the shadow prices, the policy comparison | Any contact with a dose grid |

### 1.1 Why a third component is required

Two constraints stated in the companion documents are individually correct and jointly force the split.

- The extractor stores **block-level** distributions rather than strategy-level accumulated ones. Composition at evaluation time is a sum of arrays already held, and the conversion to EQD2 depends on the fractionation schedule, which is a decision variable. Converting inside the extractor would freeze one schedule in the stored data and silently invalidate every alternative, so conversion happens at composition time and its result is not stored.
- The allocator **never touches a dose grid**, so that it is unit-testable against synthetic tables and developable before data access.

Composition is the only operation in the pipeline that depends simultaneously on the strategy and on the voxel grid. It therefore belongs to neither, and the third component is the recognition of a boundary that was already implied.

### 1.2 What the dose model does not represent

Each block contributes the nominal dose of the plan delivered in it, computed on the block's image (Section 2). The model contains no per-fraction setup error and no intrafraction motion. Worst-case metrics are evaluated per plan and per block and are descriptive (Section 6.2). Two effects of fraction number on robustness are therefore absent: the reduced averaging of random setup error over fewer fractions, whose realised mean has standard deviation σ/√n, and intrafraction drift during longer fractions. Omitting them favours hypofractionation. This is a limitation of the study (E22; road 3.4).

## 2. Strategy construction

The evaluator builds each patient's strategy space, and construction precedes every diagnostic. Strategies that violate the planning workflow are never generated.

**Margin is a property of the arm.** The workflow is chosen at prescription, and adaptation is a property of the course (allocator A24). The construction rule is therefore a mapping from the arm:

- A **non-adapted arm** carries the clinical-margin plan generated on the pCT. Its dose on each later block is that plan recomputed on the block's image. Where the recomputed plan fails the acceptance criterion, the arm carries a replan generated on that image at unchanged margin and unchanged setup error, which carries forward to later blocks and is judged again on each of them (E17). "Non-adapted" therefore means reactively adapted at clinical margin.
- An **adapted arm** carries the reduced-margin plan generated on the pCT for the first block, and the reduced-margin replan generated on each later block's image.

**The rule applies to both modalities.** The adapted photon arm is constructed as the adapted proton arm (E12). Neither modality carries an adaptation vector, and robustness contributes no independent index to the strategy tuple, since the arm fixes it. A free crossing of margin with adaptation would generate plans that could not be delivered.

**Where the plan sequence comes from.** The acceptance judgement is made in RayStation during plan generation, and every rescue is generated there (allocator 8.2). The plan each arm delivers on each block, rescue plans included, is therefore read from the export manifest (extractor 4) rather than decided by the evaluator. The evaluator verifies the judgement (Section 6.1).

**Option set.** A patient holds **seven** strategies, independently of the number of blocks. XT-A, PT-NA and PT-A each carry both schedules; XT-NA carries the one schedule clinical eligibility assigns (allocator A32; E20). The number of blocks governs how many dose fields are composed per strategy, not how many strategies exist. An adapted arm whose reduced-margin plan could not be made robustly acceptable at plan generation is absent from that patient's option set, and the absence is recorded with its reason (allocator A31).

**The first block is evaluated on the planning anatomy.** Its contribution to every strategy is the nominal planned dose on the pCT, as in the reference study (allocator A23). This favours the non-adapted arms, which would already degrade during the first block; allocator 4 states the limitation. The block weights of a composition are configurable, so the investigation described there, assigning the first block the dose of the second, is a recomposition from doses already held and needs no new plan or recomputation.

**Fractions per block.** The fraction count n_b of each block is derived from the acquisition dates of the repeat images relative to the start of treatment, and set by hand where the dates do not determine it (E21).

## 3. Interface contract

**Consumes, per patient:**

- block-level physical dose per plan, masked to the ROI union;
- the export manifest: arm, block, role (planned or rescue), schedule, the image each plan was generated on and the image its dose is computed on, and the RayStation acceptance judgement, which together fix each arm's plan sequence (extractor 4);
- deformation vector fields keyed by image pair, DIR settings hash and working grid;
- per-block target metrics per plan, and the outcome of robust evaluation per plan and block as recorded at plan generation;
- ROI masks and grid geometry under canonical names;
- clinical covariates required by the active NTCP models, and the XT-NA eligibility flag;
- plan complexity descriptors;
- the identifier of the acceptance criterion in force.

**Dose provenance (E16).** Physical dose is computed in RayStation for both modalities and imported; OpenTPS performs no dose calculation for this study, including no use of its own photon CCC implementation.

**Emits, per (patient, strategy):**

| Field | Meaning |
|---|---|
| u | Utility. Union ΔNTCP against XT-NA |
| dntcp_k | Per-endpoint ΔNTCP, for reporting |
| ntcp_k | Absolute per-endpoint NTCP, for reporting and for the allocator's dynamic-program cross-check |
| tau_pt | Proton machine occupancy per fraction, minutes. Zero for photon strategies |
| tau_xt | Photon adaptation time per fraction, minutes. Zero for proton strategies and for XT-NA. Charged on every fraction of an adapted arm |
| n_fx | Fraction count |
| admissible | Boolean. True for every emitted strategy, since nothing is removed; kept as a defensive flag, and no solver or policy assigns a strategy for which it is false (allocator T11) |
| plan_sequence | The plan delivered on each block, with its role, as read from the manifest |
| eqd2_target | Descriptive target EQD2 at the declared tumour α/β |
| dvh | Cached reduced dose, per ROI, retained for parameter propagation |

**Emits, per patient and per cohort:** rescue counts by arm, schedule and block; disagreements between the RayStation acceptance judgement and the evaluator's verification, by arm and block; robust-evaluation failure counts by arm; the count of assignable strategies whose union ΔNTCP is not positive, and the per-endpoint sign violations; absent adapted arms with their reason (A31); the acceptance criterion identifier.

The allocator consumes u, ntcp_k, tau_pt, tau_xt, n_fx and admissible per (patient, strategy), and the counts for reporting. It sees no dose object of any kind.

**Why occupancy is emitted per resource.** The two costs are consumed by disjoint groups of arms, so a single occupancy field would have to be read together with the modality to know which budget it draws on. Two fields make the resource explicit and let the allocator treat the option set as two chains without inspecting the modality string. The photon field carries the adaptation increment only, since photon delivery is not a constrained resource (allocator 5.1).

**Internal representation of utility.** Each patient receives exactly one strategy, so the sum of reference NTCP over the cohort is a constant. Maximising the sum of ΔNTCP and minimising the sum of absolute NTCP are therefore the same problem. The evaluator emits both. The allocator's integer, linear and greedy solvers maximise the sum of ΔNTCP, and its dynamic-program cross-check minimises the sum of absolute NTCP; allocator T5 asserts that the two give identical allocations. ΔNTCP is also used for reporting and for the no-harm diagnostic.

## 4. Accumulation ordering

### 4.1 The choice

Two operations are applied to each block dose: deformation onto the planning CT frame, which is an interpolation, and conversion from physical dose to equivalent dose in 2 Gy fractions, which is nonlinear. They do not commute.

**Adopted ordering.** For each block b, on its native geometry and inside each ROI mask, compute the biologically effective dose field at that ROI's α/β:

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

The example is extreme by construction and makes the mechanism visible; it does not quantify the expected effect. What makes it relevant here is the volume parameter. For a serial-like organ with a small volume parameter, n = 0.09 for instance, the generalised equivalent uniform dose approaches the maximum dose and therefore draws its weight from the high-gradient region, which is exactly where the error lives. For an endpoint driven by mean dose the error would average out.

### 4.3 What the ordering costs

BED_b depends on n_b, which follows from the schedule and the block, and on α/β, which follows from the structure. The deformed field is therefore not unique: one exists per (block, schedule, α/β) combination. With two schedules and two distinct α/β values in the registry, this is four warped fields per block per arm rather than one.

These are four **applications** of a cached deformation field, not four registrations. Registration is performed once per image pair and cached. Applying a field to an array is an interpolation and is cheap. The registration cost, which dominates, is unchanged.

### 4.4 Sensitivity measurement rather than assumption

The alternative ordering is computed once on a real case, and the difference in gEUD is reported for the organs driving the NTCP. If the difference is negligible the statement is short; if it is not, the adopted ordering is justified by evidence rather than by argument.

## 5. Composition of strategies

### 5.1 Structure

A strategy is the tuple (modality, adaptation, fractionation, technique). Robustness is not a component: the arm determines it (Section 2). Adaptation is a boolean scalar, so each (modality, fractionation) group holds two strategies; with the XT-NA schedule fixed by eligibility, each patient holds seven. Rescue is not a component of the tuple either. It is a consequence of the acceptance judgement given the anatomy, not a choice, so it changes the dose composed for a strategy without adding strategies (E18).

Composition of a strategy is the sum of its cached warped BED fields over blocks. The fraction count of each block enters through BED_b (Section 4.1), so the sum carries no further weights.

### 5.2 Pareto reduction

The evaluator emits every constructed strategy, seven per patient, including strategies of negative utility, since the no-harm count of Section 6.3 is computed on them. The Pareto reduction is applied by the allocator (`dominance.py`): among options of equal cost only the best utility survives, and an option that costs more without buying more is dropped. It is valid for both the integer problem and the relaxation, and it removes strategies of negative utility from the chains, since XT-NA dominates them at zero cost (allocator T10). The hull reduction used for the LP is applied there as well, and only there.

## 6. Admissibility

Admissibility rests on one enforced criterion and one reported diagnostic. Neither removes a strategy.

| Stage | Basis | Requires registration and accumulation? | Granularity | Effect on a failure |
|---|---|---|---|---|
| Target coverage | Per-block dose on its own image | No | Per plan | A rescue plan at unchanged margin is delivered from that block onward, as recorded in the manifest; the arm is retained |
| No harm | Accumulated EQD2, then NTCP | Yes | Per strategy | Counted and reported; the strategy is retained |

### 6.1 Coverage, judged per block, and rescue

Target coverage is a property of a plan delivered on a given anatomy. If the plan an arm would deliver on rCT_j falls below the acceptance criterion, that plan would not be delivered, and the judgement requires no accumulation (E4).

**The judgement is made in RayStation; the evaluator verifies it.** During plan generation, each non-adapted plan is recomputed on each new image and judged against the acceptance criterion, and a rescue is generated at once where it fails (allocator 8.2). The composition of a non-adapted arm is therefore a piecewise sequence of clinical-margin plans, read from the manifest. The evaluator re-applies the same criterion to the exported dose of every plan on every block. Where its result differs from the RayStation judgement, for instance through differences in structure rasterisation or DVH binning, **RayStation governs** (E23), and the disagreement is reported per arm and per block. A disagreement indicates a difference between the two computations, not a change in the composition.

**Consequences.**

- Nothing is removed, so no option set can empty and the strategy count is independent of the anatomy.
- **Every arm is verified; rescues are expected only on the non-adapted arms.** Under allocator A1 and A4, an adapted arm's block plan is optimised on the anatomy it is then evaluated on, so nominal coverage holds by construction. The verification still runs on PT-A and XT-A, and the count is reported per arm, because A4 requires the property to be demonstrated rather than asserted. A non-zero count there is a replanning failure (allocator decision 26). The implementation does not special-case the adapted arms out of the verification.
- The number of coverage evaluations equals the number of plans, rescue plans included, rather than the number of strategies.
- The verification precedes composition, since it checks the plan sequence the composition uses, and it requires no registration or accumulation.
- Accumulated coverage is not used in any role.
- **The criterion is the plan acceptance protocol used at treatment planning.** It is a list of criteria of which all must pass, and the count is emitted per criterion, so instantiating the list is a configuration change. Which metrics instantiate it is allocator decision 7b. The criterion is fixed before plan generation and recorded with every result.
- **Rescue frequency is emitted per arm, per schedule and per block.** It is the empirical check on the plausibility of a non-adapted arm, in particular of a five-fraction course without systematic adaptation.

### 6.2 Worst-case coverage

Worst-case metrics are evaluated **per plan and per block and not accumulated**, since the worst scenario in one block need not be the worst in another, and a sum of per-block worst cases corresponds to no physical scenario (E5). Whether each plan passes robust evaluation on each block is recorded at plan generation, alongside the nominal judgement, and the evaluator reports the failure counts per arm. Worst-case failure does not trigger rescue. The adapted arms are expected not to fail, since robust evaluation at the reduced margin is part of plan acceptance; where a reduced-margin plan cannot pass it, the arm is absent from that patient's option set (allocator A31).

### 6.3 No harm

A strategy whose union ΔNTCP against the reference is negative is **counted and reported, not removed** (E6). The requirement it serves is that maximising a cohort mean must not make an individual worse than current standard care. The argument that the option set already secures it, since XT-NA is free, never removed and dominates every strategy of negative utility, is given in allocator 8.3. The evaluator's part is that the no-harm computation removes nothing.

**The diagnostic is computed on the union scalar.** A strategy that worsens one endpoint while improving the others can still be the right choice, and excluding it on a single endpoint would be stricter than the selection rule used everywhere else in the design. Per-endpoint sign violations are counted and reported explicitly, so the cost of the convention stays visible.

**What is emitted.** The count of strategies whose union ΔNTCP is not positive, excluding the reference arm, whose zero is definitional. It measures how often adaptation or a changed schedule fails to reduce the union probability, which is of independent interest and is distinct from how often such a strategy is selected.

**The reference includes rescue, so results are conditional on the acceptance criterion.** XT-NA is defined as current practice: the clinical-margin plan, replanned offline wherever it fails the acceptance criterion on a repeat image. A plan below the criterion would not be delivered, so a reference without rescue would not represent current practice; rescue restores the reference rather than improving it. The reference NTCP, and with it every ΔNTCP, therefore depends on which criterion defines acceptability (allocator decision 7b). PT-NA is rescued on the same criterion, so the modality step, the photon outside option and the step-ratio threshold Δτ\* are conditional on the criterion as well. Two quantities do not depend on the rescue of XT-NA: the ordering among a patient's other six options, and pen\*, which compares two adapted proton arms.

### 6.4 Empty option sets

**Unreachable.** Neither stage removes a strategy, so the multiple-choice constraint is always satisfiable. The only way an option set can shrink is an adapted arm not generated under allocator A31, which is an absence recorded at construction with its reason and cannot remove XT-NA.

The infeasibility raise is retained as a defensive check on the evaluator's own construction. If it fires, it indicates a defect, not a patient.

## 7. Caching

### 7.1 Stages

| Stage | Cost | Cached | Invalidated by |
|---|---|---|---|
| Warp BED per (block, schedule, α/β) | Moderate | Yes | Deformation field, α/β, schedule, n_b |
| Sum over blocks | Low | Yes, per strategy | Plan sequence, warped fields |
| Convert to EQD2 | Low | No | Recompute |
| Reduce to DVH | Low | **Yes. This is the cache boundary** | Accumulated field, ROI mask |
| gEUD | Very low | No | Recompute from DVH |
| NTCP | Very low | Never | Recompute |

### 7.2 Why the boundary is the DVH and not the gEUD

The Monte Carlo propagation of NTCP parameter uncertainty requires thousands of re-evaluations with perturbed parameters. The three LKB parameters do not enter at the same stage. TD50 and m enter only at the final evaluation. The volume parameter n enters earlier, through the gEUD exponent a = 1/n:

gEUD = (Σ_i v_i · D_i^a)^(1/a)

A cached gEUD scalar cannot be recomputed at a perturbed a. A cached DVH can, because it contains exactly the (v_i, D_i) pairs the power mean requires. Caching at the DVH therefore makes the propagation a sum over a few hundred bins per sample, which takes microseconds, so thousands of samples cost nothing.

**Declared approximation.** A gEUD recomputed from a binned DVH is not identical to one computed voxel by voxel. The difference is controlled by the bin width, provisionally 0.1 Gy, and is verified once on a real case by comparing the two routes rather than assumed (E3).

**The DVH dose axis is set, not defaulted.** `DVH.computeDVH(maxDVH=100.0)` truncates the dose axis at 100 Gy **absolute**, not at a multiple of the prescription. In the installed OpenTPS, a uniform 150 Gy field on a 60 Gy prescription returns Dmax 150 and D2 99.99, since Dmax reads the dose array while D2 reads the histogram.

The truncation is harmless for physical dose and is not harmless here, because the DVH this section caches is taken on **accumulated EQD2**. EQD2 passes 100 Gy at prescription level in hypofractionated schedules at the low α/β of late-responding organs: 5 × 8 Gy at α/β = 2 is 100 Gy EQD2, and 5 × 10 Gy at α/β = 3 is 130 Gy, before any hot spot. A target at α/β = 10 stays below. Truncation would therefore fall asymmetrically, on the hypofractionated arms and on the OAR endpoints, which is exactly where the study's comparisons are made. It would bias a small-volume-parameter gEUD downward by removing the upper tail the power mean weights, and it would be silent, since Dmax continues to report correctly.

`maxDVH` is therefore set from the actual maximum of the field with a margin, and the value used is recorded (E10). At 4096 bins a 200 Gy axis still gives a step near 0.05 Gy, so the declared approximation above is unaffected. This is an instance of the rule of extractor 3.4 that nothing is called with its defaults.

**α/β is outside the cache.** It enters before the DVH, so perturbing it invalidates the accumulated field. A sensitivity analysis on α/β therefore requires recomposition rather than re-evaluation and is structurally more expensive than the LKB propagation. α/β is treated as a separate sensitivity axis rather than propagated in bulk.

## 8. NTCP model registry

Models are declarative records rather than classes. What varies between sites is which structures matter, which endpoints are modelled and which parameters those models use. None of that is code.

```
Model(
    name       = 'rectum_bleeding_g2',
    site       = 'pelvis',
    kind       = 'lkb',
    roi        = 'Rectum',
    alpha_beta = 3.0,
    params     = {'td50': 76.9, 'm': 0.13, 'n': 0.09},
    covariates = [],
    source     = 'Michalski 2010 QUANTEC',
    fitted_on  = 'solid rectum, photon, 1.8-2.0 Gy/fx',
)
```

This is the one populated record: a pelvic model used to exercise the mechanism. The volume parameter n is held once, in `params`, and the power-mean exponent is a = 1/n. A record is validated at construction: the parameters its kind needs are present, the LKB and relative-seriality parameters are positive, and α/β is positive where a voxel-based form uses it. The abdominal endpoint models depend on the site (allocator decision 19) and on the model family (allocator decision 10).

Three functional forms cover nearly everything: LKB on a gEUD input; logistic on a linear predictor over dose metrics and clinical covariates, as used by the Dutch protocols; and relative seriality. Each is one function, and `kind` selects it. Adding a site means adding records. A logistic model on mean dose without a fractionation term is evaluated on mean EQD2 at a declared α/β, never on physical dose across schedules (allocator decision 10).

**Engine contract.** Given a cohort and a list of models, the engine collects the union of required ROIs, metrics, covariates and α/β values, validates the cohort against that union **before any dose work**, then evaluates. A missing covariate surfaces at cohort assembly, not after hours of accumulation. The union of α/β values also determines how many warped fields per block are required, so the registry sizes the composition workload.

**Endpoint composition is declared, not assumed.** The active endpoint list and the composition rule belong to the site configuration. Otherwise changing the site silently changes the meaning of the selection scalar.

**`fitted_on` is not documentation.** The QUANTEC rectum parameters were fitted on a particular delineation convention, on photon data, at conventional fractionation. Each is an assumption when the parameters are applied to an adaptive proton workflow with hypofractionation in the design. Recording it as a field makes the mismatch visible and lets the assumptions register be generated from the registry rather than maintained by hand.

**Scope.** The mechanism is built now, since retrofitting it is painful, and populated only for the site in use.

## 9. Utility and reporting outputs

**Selection scalar.** The union probability over the active endpoints:

NTCP_total = 1 − Π_k (1 − NTCP_k)

The independence assumption is false, since toxicities in a shared anatomical region are correlated, so the composite overestimates the probability of at least one event under positive dependence. This is inherited from the reference study and accepted as the best available treatment. The direction of the bias is stated in the manuscript.

**Per-endpoint values are emitted on the same call**, since reporting requires them and the per-endpoint violation count requires them.

**Target EQD2 is a first-class output.** Schedule equivalence rests on clinical consensus for the photon arms and on assumption for the proton hypofractionated arm (allocator A5), so target EQD2 is reported for completeness, not to assert equivalence: it makes any residual mismatch in tumour effect between arms visible. It uses the same machinery applied to the CTV with a different α/β, and belongs in the evaluator's output record rather than being computed at figure time.

**Per-endpoint weights.** The interface carries per-endpoint weights defaulting to the union form, so that severity-weighted utilities could be substituted later without structural change.

**Dominance inputs.** The evaluator does not compute dominance, which belongs to the allocator, but its emitted option sets are what the allocator's two dominance counts, Pareto and LP, are computed on. The per-block rescue and verification counts of Section 6.1 are emitted here because only the evaluator sees the per-block outcomes.

## 10. Assumptions register

| ID | Assumption | Status | Risk |
|---|---|---|---|
| E1 | BED is additive over blocks, so deformation may follow conversion and precede summation | Exact under the linear quadratic model | None beyond the validity of the model itself |
| E2 | Conversion before deformation is preferable to the reverse | Adopted; the reverse is computed once and the difference reported | Low. Measured rather than assumed |
| E3 | gEUD recomputed from a binned DVH approximates the voxel-wise value | To be verified on the first real case at the chosen bin width | Low, controlled by bin width |
| E4 | Target coverage is judged per block on the plan delivered in that block | Adopted; the accumulated criterion is rejected as permissive in the wrong direction | Stricter than an accumulated criterion, which is the intended direction |
| E5 | Worst-case coverage is a per-plan property, not accumulated, and descriptive | Adopted; per-block worst cases correspond to no physical scenario | The nominal criterion and the worst-case count answer different questions, which must be stated |
| E6 | No harm is judged on the union scalar and is **reported rather than enforced** | Confirmed at supervision (allocator A12); per-endpoint violations counted | A strategy worsening one endpoint may be selected. Harmful strategies remain in the option set and are declined by dominance in the allocator |
| E8 | The linear quadratic model is valid for OAR EQD2 conversion over the fraction sizes considered | To be checked against real cases | Applies to OARs only, not to any tumour claim |
| E10 | The DVH is computed by OpenTPS and consumed in cumulative form, with `maxDVH` set from the field | Adopted. Binning error and re-evaluation cost measured, both negligible | OpenTPS writes the power-mean exponent as EUDa where this document writes 1/n. The default `maxDVH` would silently clip accumulated EQD2 on the hypofractionated arms (Section 7.2) |
| E12 | The adapted photon arm is constructed as the adapted proton arm: the reduced-margin plan on the pCT for the first block, and a reduced-margin replan on each later block's image | Construction rule of Section 2 | As E15 |
| E13 | Only the adaptation increment is charged to the photon budget | Follows from allocator A17 | If photon delivery is binding at the partner centre, the emitted tau_xt understates photon demand |
| E14 | The adapted photon arm adapts on the block images, the same rCTs the proton arm uses | Design decision. The rCTs are the images that exist in the data | The modelled photon adaptation is a per-block surrogate of the online workflow, which adapts on daily CBCT or MR. The surrogate uses a different image; the direction of the net bias on the photon adaptation benefit is not known. The photon twin of allocator A1 |
| E15 | The reduced margin is a property of the adapted arm and applies from the first fraction, on the pCT plan | Construction rule of Section 2, mirroring allocator A25 | A free crossing of margin with adaptation would generate undeliverable plans and an inflated strategy count |
| E16 | All dose for paper 1 is computed in RayStation and imported, for both modalities; OpenTPS performs no dose calculation, including no use of its photon CCC implementation | Design decision | The engine and the cross-modality reporting conventions (RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin) remain open: allocator decision 25. Analytical proton dose is least reliable in a heterogeneous abdomen, and the error is systematic, falling on the arm whose anatomical degradation the study measures |
| E17 | A non-adapted arm's dose on a block is the pCT plan recomputed on that block's image or, where that fails the acceptance criterion, a replan on that image at unchanged margin, which carries forward and is judged again | Construction rule of Section 2, mirroring allocator A24, A29 and A30, confirmed at supervision. The sequence is decided in RayStation and read from the manifest | The composition is a piecewise sequence of plans whose breakpoints depend on the acceptance criterion. Changing the criterion changes which plans exist, so it is fixed before plan generation and recorded with every result |
| E18 | Rescue is a consequence of the acceptance judgement and not a component of the strategy tuple | Follows from E17 | The strategy count is independent of the anatomy, which keeps the option set fixed at seven and the MCKP structure intact |
| E19 | A rescue is unpriced on both budgets, so the emitted per-fraction occupancies are unchanged by it | Mirrors allocator A28, confirmed at supervision | If a rescue were priced, the emitted cost of a non-adapted arm would become anatomy-dependent and XT-NA would cease to be free, so the no-harm property would revert to empirical |
| E20 | XT-NA carries one fractionation schedule per patient, supplied as an eligibility flag in the patient record | Mirrors allocator A32 | The flag is required input. Where it is hypofractionated, every ΔNTCP of that patient is referred to a hypofractionated arm |
| E21 | The fraction count n_b of each block is derived from the acquisition dates of the repeat images relative to the start of treatment | Adopted. Where the dates do not determine it unambiguously, it is set by hand and tagged `assumed` in the provenance table (extractor 12) | n_b enters every accumulated EQD2. A hand-set value is a declared assumption, not a measurement |
| E22 | The dose model contains no per-fraction setup error and no intrafraction motion | Adopted scope (Section 1.2) | The robustness effects of fraction number are absent, which favours hypofractionation. Stated as a limitation |
| E23 | The RayStation acceptance judgement governs; the evaluator's re-application of the criterion is a verification | Adopted | Differences in rasterisation or binning can make the two disagree. Disagreements are reported and do not change the composition |

Retired: E7, E9, E11. Their content is in `CHANGELOG.md`.

## 11. Implementation

### 11.1 The composition module

`evaluator/compose.py` implements Sections 4 and 7. It is the geometry-aware layer around `evaluator/ntcp.py`, which holds the linear quadratic and gEUD arithmetic as pure functions on plain arrays. `compose.py` does not compute BED, EQD2 or gEUD itself; it calls `ntcp.py` for all three, so the formulas are written in one place and a parameter cannot change in one copy and not another. What `compose.py` adds is what `ntcp.py` deliberately does not do: warping a field, summing fields on a shared grid, and constructing the DVH.

```
compute_bed(dose_per_fraction, n_b, alpha_beta) -> BED array           # via ntcp.bed
warp_bed(bed_field, dvf, *, rois, fill_value = 0) -> BED array, on the fixed image's grid   # no ntcp.py involvement
sum_bed(bed_fields: list) -> total BED array                           # no ntcp.py involvement
bed_to_eqd2(bed_total, alpha_beta) -> EQD2 array                       # via ntcp.eqd2_from_bed
reduce_to_dvh(eqd2_field, roi_mask, *, max_dvh=None) -> DVH            # no ntcp.py involvement
geud_from_dvh(dvh, n) -> float                                         # via ntcp.geud_from_cumulative_dvh
```

Four conventions are fixed by this interface.

- **Dose per fraction in, total dose to `ntcp.bed`.** The extractor stores physical dose per fraction. `ntcp.bed(dose, n_fx, ab)` takes a segment's total physical dose and derives the per-fraction value internally. `compute_bed` therefore multiplies by `n_b` before the call, a round trip exact to floating-point rounding, so the module keeps the extractor's per-fraction dose as its public input while the LQ formula stays in one place. The argument is the block's fraction count n_b (E21), held in the extractor's `BlockFractions` record, and not the course's fraction count.
- **The volume parameter is n.** `geud_from_dvh` takes n, matching `ntcp.py` and the registry's `params['n']`, and delegates to `ntcp.geud_from_cumulative_dvh`, which normalises the volume fractions and raises on an empty DVH. `DVH.histogram` in OpenTPS is cumulative (volume receiving at least a given dose, in per cent); the differential fractions are recovered as its first difference. Both gEUD functions of `ntcp.py` evaluate the power mean scaled by the maximum dose, in float64, since the direct power mean overflows a float32 field for n of 0.05 or below at the EQD2 values of the hypofractionated arms (Section 7.2). Both raise on an empty or non-finite input.
- **`warp_bed` takes a field already computed.** Registration (`extractor.adapters.get_dvf`) is performed once per image pair and cached (extractor 6). Applying a cached field is cheap and is repeated once per (block, schedule, α/β) combination (Section 4.3). The registration's moving and fixed images are the block's repeat image and the planning CT (extractor 6.2); the BED field is passed to the field's `deformImage`. Every argument that changes a result is explicit (extractor 3.4): a voxel whose source lies outside the BED field's grid is filled with 0, which shows as a hole in a DVH and not as a replicated edge value. `warp_bed` raises if the BED field and the field are not on one grid, or if any voxel of the ROI masks it is given (`rois`, the masks the warped field will be read on) is filled and not sampled, since a DVH over a partly filled ROI describes a different volume.
- **`reduce_to_dvh` sets `maxDVH` from the field** with a 5 per cent margin when it is not given explicitly (Section 7.2). It raises if the ROI mask is not on the field's grid, since the OpenTPS DVH would resample the mask by interpolation and dilate it, or if the mask is empty.

**Two consumers of the composed field.** `registry.evaluate()` for the `'lkb'` and `'rseriality'` kinds takes the EQD2 voxel array directly and computes gEUD from it: this is the primary, single nominal NTCP evaluation of a strategy. The DVH built by `reduce_to_dvh` serves the cached re-evaluation path of Section 7.2, in which n is perturbed many times without recomputing the accumulated field. Both paths are fed from `bed_to_eqd2`.

### 11.2 What is tested

| File | Covers |
|---|---|
| `tests/test_compose.py` | Each function of Section 11.1 against independently derived values: the identity that EQD2 equals total physical dose at exactly 2 Gy per fraction for any α/β; the hypofractionated values of Section 7.2 (100 and 130 Gy EQD2); gEUD on a uniform dose (equal to the dose for any n) and on a hand-computed two-value case; `warp_bed` as a delegation to `deformImage` on a zero-displacement field, and its refusal of a ROI whose voxels map outside the field; `reduce_to_dvh` on a mask off the field's grid or empty. Delegation to `ntcp.py` is tested directly, by calling both and asserting agreement |
| `tests/test_end_to_end.py` | The seams between modules: DICOM ingest of CT and dose, real Morphons registration, `compute_bed`, `warp_bed`, `sum_bed`, `bed_to_eqd2`, `reduce_to_dvh`, into `registry.evaluate` with `rectum_bleeding_g2`. Two blocks of uniform dose, n_fx = 25 per block at 2.0 and 1.8 Gy per fraction, α/β = 3. Expected values computed by hand beforehand: EQD2 = 93.2 Gy, NTCP = 0.948501; reproduced to five and six significant figures, the residual consistent with registration interpolation. The cached DVH path and the direct voxel path agree within the binning error of Section 7.2 |
| `tests/test_cohort_validation.py` | `validate_cohort` against the real registry: raises on a missing ROI and on a missing covariate, naming the patient; a cohort with one invalid patient stops before any patient reaches `evaluate()`. The covariate path uses a locally constructed logistic model, since the registry holds none with covariates |

All three run against OpenTPS 3.0.1.

### 11.3 What is not built, and why

| Item | Reason |
|---|---|
| Composition of a non-adapted arm from the manifest's plan sequence, rescue plans included, and the verification of the RayStation acceptance judgement (Section 6.1) | Needs the first exported case, since the manifest's real content is what it reads |
| Caching (Section 7.1) | Sequencing, not design. `compute_bed`, `sum_bed` and `bed_to_eqd2` are pure functions of hashable inputs, so a content-hash cache can wrap them without a signature change. The expensive stage, warping, is covered by the extractor's DVF cache |
| A production cohort loader | `validate_cohort` needs only objects with `.pid`, `.rois` and `.covariates`. Choosing a class is left to the loader written once ingest runs over many real patients |
| The Section 4.4 ordering measurement and the Section 7.2 binning comparison | Each requires a real case |

### 11.4 A risk for real data

`readDicomCT` transposes DICOM's (rows, columns, slices) into the internal axis order of OpenTPS. The end-to-end phantom is not spatially uniform, so a DICOM writer that ignores which axis DICOM calls a row does not round-trip; the test is unaffected, because pCT and repeat CTs pass through the same writer and reader. On real data, CT, dose, structure masks and deformation fields come through different readers, and all must share one axis convention. This is checked on the first real export, by overlaying a known structure on its CT and dose, before any composition is trusted.

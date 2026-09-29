# Road to Paper 1

Version 7.1. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 0. Document set and division of labour

Four documents describe this work, and each owns a distinct subject.

| Document | Owns |
|---|---|
| **Road to paper 1** | Scientific question, hypothesis, arm set, uncertainty budget, plan budget, endpoint policy, what the paper claims, declared limitations |
| **Allocator design** | The optimisation problem, the algorithm, the shadow prices, the step-ratio threshold, the policy comparison, the capacity accounting, the synthetic cohorts |
| **Evaluator design** | Strategy construction, dose composition, accumulation ordering, EQD2 conversion, NTCP evaluation, the coverage verification and the no-harm diagnostic, the NTCP model registry |
| **Extractor design** | Ingest, the export manifest, registration, storage, target metrics, plan complexity, ROI naming, provenance |

Section 5 of this document summarises the software architecture at the level a reader of the paper plan needs, and defers every algorithmic detail to the module documents.

## 1. Background

The reference study (Borderías-Villarroel et al., Radiother Oncol 198 (2024) 110389) established that the normal tissue complication probability (NTCP) benefit of online adaptive proton therapy decays with the time required to adapt, because adaptation consumes machine capacity and displaces patients to photon therapy. The analysis held the number of fractions constant at 30, which made time per fraction and time per treatment course interchangeable. It also held the photon arm non-adapted and named the integration of online adaptation into the photon branch as future work.

This project releases both constraints. When fractionation becomes a degree of freedom the two time quantities separate, the resource consumed by a patient becomes machine time per course, and adaptation and fractionation compete for a single budget. When the photon comparator is itself allowed to adapt, the reference point against which the proton advantage is measured moves, which is the more demanding test of whether that advantage survives.

**Photon adaptation is a rationed resource, not a free one.** A department that can adapt some photon patients cannot in general adapt all of them, and the arm every patient is entitled to is the non-adapted one. The design therefore carries two budgets: proton machine time, and photon adaptation time (allocator A3, confirmed at supervision). Non-adapted photon treatment consumes neither and remains the reference arm, so every ΔNTCP keeps the zero point of the reference study and the comparison with its decomposition stays valid. Adaptation is the scarce quantity on both modalities, and patients compete for it through the ΔNTCP it buys them. Each budget carries its own shadow price, λ_PT and λ_XT, and their ratio states where a department gains more from the next unit of investment. The allocator document specifies the formulation.

**The two levers act on opposite terms of the cohort mean.** Hypofractionation improves cohort composition by freeing capacity. For late-responding organs at risk it plausibly degrades per-patient NTCP through the increased biological effect of larger fractions. Adaptation improves per-patient NTCP and consumes capacity.

**Central hypothesis.** The effect of hypofractionation on cohort ΔNTCP depends on the adaptation strategy, so the two levers are not additive. Section 3.4 states the mechanism and what the model does not represent.

**Principal new deliverable.** An OpenTPS plugin that allocates a capacity-constrained proton resource across a cohort whose members no longer consume equal machine time. Its decision rule generalises the model-based selection logic of the Dutch national protocol, in which patients are referred to protons on a clinically meaningful ΔNTCP threshold, to the case where the candidate workflows differ in machine cost.

**A structural result sits alongside the hypothesis.** Within one fractionation schedule, whether the non-adapted proton arm carries any allocative value is governed by a threshold in the extra time per adapted fraction, with the closed form Δτ\* = τ_0 · (a/m), where a/m is the ratio of adaptation benefit to modality benefit measured on the cohort. Below the threshold PT-NA lies under the segment joining photons to adapted protons: a patient who enters the proton chain enters it adapted, and the problem reduces to the reference study's structure. Above it, PT-NA is a live rung and the cohort can split three ways.

- **It is a per-schedule statement.** Each schedule carries its own (τ_0, a, m) and therefore its own Δτ\*. The competition between schedules, in which the biological penalty of larger fractions trades against the capacity they free, is not captured by the formula; that cross-schedule interaction is the subject of the study and is resolved by the allocator.
- **It depends on the photon adaptation budget.** The bottom rung of a patient's proton chain is whichever photon arm that patient would otherwise hold. A patient receiving adapted photons measures the modality step against a stronger comparator, which shrinks it and raises the threshold. Δτ\* is therefore reported as a function of the photon budget, on the same sweep that produces λ_XT.
- **It is conditional on the acceptance criterion**, since m and a are evaluated on post-rescue utilities (Section 5.10).

No clinical on-couch adaptive proton workflow exists for the abdomen, so the extra time per adapted fraction is the study's independent variable, as in the reference study, and the per-schedule thresholds are the deliverable at this level. The derivation is in allocator 6.2.

## 2. Scope of the publication

| | **In scope** | **Out of scope** |
|---|---|---|
| Scientific content | Joint effect of adaptation strategy and fractionation on cohort NTCP under machine capacity constraints. Allocation of a capacity-constrained proton resource and a rationed photon adaptation resource across a cohort whose members no longer consume equal machine time. The step-ratio threshold governing whether non-adapted proton therapy carries allocative value alongside adapted proton therapy. The relative price of the two resources | Reinforcement learning formulation. Prospective validation. Functional imaging biomarkers. Queueing dynamics, arrival processes and waiting-list policy. Scheduling, in the sense of which fraction occupies which slot on which day. Photon delivery capacity, modelled as unconstrained. A change of schedule during the course, and reallocation during the course. Tumour control modelling |
| Modalities | Proton therapy against a photon comparator, following the model-based selection logic that motivates the ΔNTCP metric. The photon comparator includes an adapted variant, the extension the reference study named as future work | Comparison across proton delivery techniques. Comparison across photon delivery platforms. Mixing of modalities within a course |

## 3. Scientific rationale

### 3.1 What changes when fractionation is released

In the reference study the machine resource consumed by a patient was proportional to the extra time per fraction alone. Once the fraction count varies, the relevant quantity is total course time:

T_course = n_fx · (t_fixed + t_delivery(d) + t_adaptation)

Two consequences follow. Capacity must be counted over a horizon rather than within a day, because a patient with fewer fractions occupies the machine on fewer days rather than for a shorter slot. And the gain from reducing the fraction count is smaller than it first appears, because delivery time grows with dose per fraction.

**Where the freed capacity goes.** The cohort is closed, so capacity released by hypofractionation cannot admit new patients. It can be spent in exactly two ways: upgrading an existing patient to adaptation, or moving a patient off the photon arm onto protons. The second is the displacement mechanism of the reference study running in reverse, and it exists only because the photon strategy is inside each patient's option set at zero proton cost. Without that, hypofractionation would carry no capacity value in this formulation. This is the mechanism that makes the cohort-composition channel representable, and the manuscript states it.

### 3.2 Two channels acting in opposite directions

The cohort mean ΔNTCP contains two channels. The first is cohort composition: how many patients receive protons, and with which workflow, under the capacity constraints. The second is the per-patient NTCP of each patient who does receive protons. The levers load onto these channels in opposite senses, which is the principal justification for studying them jointly rather than in sequence.

| Lever | Channel A: cohort composition | Channel B: per-patient NTCP |
|---|---|---|
| Faster adaptation | Improves | Neutral |
| More adaptation | Degrades through capacity loss | Improves through dosimetry |
| Hypofractionation | Improves through capacity gain | Uncertain, plausibly degrades |
| Photon adaptation | Improves, by releasing proton slots. Consumes the photon adaptation budget rather than the proton machine | Improves the comparator, therefore reduces the measured proton advantage |

### 3.3 The four competing effects

| Effect | Direction | Mechanism and confidence |
|---|---|---|
| Capacity | Positive | Shorter courses free machine time, so fewer patients are displaced to photons |
| Radiobiology at isoeffective prescription | Likely negative | At tumour-isoeffective dose, the differential between organ α/β near 3 Gy and tumour α/β near 10 Gy raises normal tissue biologically effective dose when fractions are enlarged. Direction follows from the linear quadratic model. Physical dose falls, per-fraction weighting rises |
| Robustness | Mixed | Reduced averaging of random setup error over fewer fractions, substantially absorbed when daily imaging and correction are in place. Longer delivery accumulates baseline drift and organ filling, which are systematic within the fraction. Partly offset by more breathing cycles per fraction. **Not modelled in this study** (Section 3.4) |
| Adaptation economics | Positive | Fewer fractions mean fewer adaptation events per course, so a given per-fraction adaptation cost is cheaper over the course |

### 3.4 Central hypothesis and its mechanism

**Hypothesis.** The effect of hypofractionation on cohort ΔNTCP depends on the adaptation strategy. Hypofractionation frees capacity, which improves cohort composition. It also raises the biologically effective dose to late-responding organs near the target, which degrades per-patient NTCP. Adaptation changes the dose distribution on which the second effect acts, and it consumes the capacity on which the first depends, so the two levers are not additive.

**What the model represents.** The dose-redistribution channel, through voxel-wise linear quadratic conversion of per-block dose (Section 6), and the capacity channel, through the two budgets. Differences between the schedules in block structure and in rescue frequency enter as well. The interaction is an output of the allocation, not an input to it.

**What the model does not represent: the robustness effects of fraction number.** The van Herk formulation separates systematic from random geometric uncertainty. The fraction count enters only the random term, since the realised mean displacement over n fractions has standard deviation σ/√n; at five fractions this is 0.45 σ. In a workflow with daily imaging and correction, σ is the residual after correction (intrafraction motion, delineation, isocentre reproducibility), which corresponds to the 2 mm setup-error scenario of the reference study, so the √n penalty acts on an already small residual. Intrafraction drift during longer fractions is the second effect. The dose model composes the nominal dose of each block's plan on the block's image, with no per-fraction setup error and no intrafraction motion (evaluator 1.2, E22), so neither effect is represented. Omitting them favours hypofractionation. The argument above suggests the omitted term is small wherever daily imaging leaves a small random residual; its size is not measured. Stated as a limitation (Section 7.2).

### 3.5 Predicted site dependence

The inflation of equivalent dose in 2 Gy fractions scales with the local dose per fraction. Voxels in the high-dose region adjacent to the target are strongly affected, whereas the low-dose bath is nearly insensitive to fraction size. Hypofractionation therefore shifts the weight of the organ dose response towards the high-dose region, which is where the proton advantage over photons is smallest.

The magnitude of this redistribution is governed by the volume parameter of the dose-response model. For serial-like organs with a small volume parameter, such as rectum, the generalised equivalent uniform dose approaches the maximum dose, making the endpoint strongly fractionation sensitive and weakly proton favourable. For parallel organs with a volume parameter near unity, such as liver, the endpoint approaches the mean dose, making it less fractionation sensitive and more proton favourable. The sign and size of the effect are therefore expected to depend on which organ drives the NTCP, which makes the choice of anatomical site a design input rather than an incidental detail.

The same volume parameter determines how sensitive the result is to the ordering of dose accumulation and biological conversion (Section 6).

### 3.6 Controlling tumour effect across fractionation schedules

**The issue.** NTCP is a monotone function of biologically effective dose to the organ. Adaptation and margin reduction lower organ dose at fixed target dose, so a ΔNTCP comparison isolates their value cleanly. Fractionation does not have this property. If two arms deliver different biologically effective dose to the target, part of the NTCP difference between them is bought by treating the tumour differently rather than by sparing normal tissue better. A ΔNTCP ranking is then not a valid ranking of workflows.

The following illustration uses a conventional 28-fraction prescription and an arbitrary five-fraction schedule chosen to be isoeffective on the target at α/β of 10 Gy. It is arithmetic, not a proposed prescription.

| Schedule | Dose per fraction | Target EQD2, α/β 10 Gy | Organ EQD2 at full dose, α/β 3 Gy |
|---|---|---|---|
| 50.4 Gy in 28 fractions | 1.8 Gy | 49.6 Gy | 48.4 Gy |
| 35 Gy in 5 fractions | 7.0 Gy | 49.6 Gy | 70.0 Gy |

At matched tumour effect the hypofractionated schedule costs roughly 22 Gy of equivalent dose in the high-dose organ region. That is the expected direction, and it is what makes the capacity trade-off a genuine tension rather than a foregone conclusion. Conversely, if the hypofractionated arm sat below the standard arm in target EQD2, its NTCP would fall for a reason unrelated to workflow quality.

**Route: clinical equivalence by convention.** Isoeffectiveness is asserted by clinical consensus rather than derived from a linear quadratic calculation. This is the logic the Dutch protocol uses when comparing modalities, in which the prescription is fixed by guideline and only NTCP is compared. It holds differently for the two modalities (allocator A5, 10.1).

- **Photon arms.** Both schedules are protocol-sanctioned for the indication, which the clinical partners confirm, and the schedule of XT-NA is set per patient by the protocol's eligibility criteria (allocator A32). Equivalence rests on the protocol.
- **Proton arms.** No protocol exists for hypofractionated proton treatment at the candidate sites; it is an investigational workflow, planned with the clinicians and simulated for every patient, with the prescription agreed with them. Its equivalence for tumour control is an assumption of the study.

**Safeguard.** Target EQD2 per arm is reported as a descriptive row in the results table, at a declared tumour α/β. It is produced by the evaluator as a first-class output rather than computed at figure time, so that any residual mismatch in tumour effect between arms is visible.

## 4. Study design

### 4.1 Arm set

The arm set is symmetric across modalities: per modality, a non-adapted arm at clinical margin and a systematically adapted arm at reduced margin. The adapted arm at unchanged margin is not carried, by supervisory decision, since the reference study characterises it as OAPT-Clinic.

**"Non-adapted" means reactively adapted at clinical margin.** An arm whose plan fails the acceptance criterion on a repeat image is rescued by an offline replan at unchanged margin and continues; nothing is removed (allocator A24, A30). The two arm families are therefore distinguished by margin and by adaptation frequency, not by the presence or absence of replanning. The label is kept for continuity with the reference study, which rescued in the same way as standard clinical practice (allocator 2), and it is defined on first use in the manuscript, since a reader would otherwise take it to mean zero replans.

**The workflow is chosen at prescription, on the planning CT.** Modality, adaptation and fractionation are all fixed before the first fraction and none is revisited during the course (supervisory decision). A rescue is not a decision: it follows from the acceptance criterion given the anatomy, so each arm remains a fully specified prescription-time workflow and the allocation remains a choice among a fixed option set.

**Each patient carries seven options.** XT-A, PT-NA and PT-A each carry both fractionation schedules. XT-NA carries one, fixed per patient by clinical eligibility, because it represents the treatment the patient would receive under current practice, and current practice chooses the schedule on protocol criteria rather than on ΔNTCP (allocator A32). Which schedules the photon protocols sanction, for which patients and on which photon arm, is refined once the clinicians answer for the chosen site (allocator decision 31).

**Margin is a property of the arm, not of the block.** An adapted arm carries a reduced-margin plan from the first fraction, generated on the pCT, and a reduced-margin replan on each repeat image thereafter. A non-adapted arm carries the clinical-margin pCT plan, with its dose recomputed on each repeat image and rescued where it fails. This is what the reference study does, where the reduced-setup-error plans are generated on the pCT and the first block of every adaptive workflow is delivered with them. It is coherent because the modelled workflow is systematic online adaptation, in which one replan per block stands for the daily replans (allocator 4, A25). Robustness therefore contributes no independent factor. The design is modality (2) by adaptation (2) by fractionation (2), less one cell: XT-NA carries only the schedule clinical eligibility assigns, so each patient holds seven options.

**Adapted means adapted at every block.** There is no partial adaptation. The study therefore cannot report whether early or late adaptation carries more benefit, nor whether a partially adapted course is ever the price-efficient choice (allocator A24).

**The first block carries no modelled anatomical degradation.** Its dose is the planned dose on the pCT, for every arm, as in the reference study (allocator A23). Under the online reading the adapted arms would adapt during the first block as well, while the non-adapted arms would already meet anatomical change there. The convention therefore favours the non-adapted arms and understates the benefit of adaptation, by an amount that scales with the first block's share of the course. It is a declared limitation; it can be investigated without new plans by recomposing every arm with the first block assigned the dose of the second (allocator 4).

| Arm | Configuration | Role |
|---|---|---|
| XT-NA | Photon, clinical margin, rescued where coverage fails, at the schedule clinical eligibility assigns | Reference arm. All ΔNTCP values are referred to it. Free on both budgets and assignable for every patient, which is what makes the no-harm property structural |
| XT-A | Photon, adapted at every block, reduced margin from the matched uncertainty budget. Consumes the photon adaptation budget | Primary comparator. Tests whether the proton advantage survives when the alternative also improves. Named as future work by the reference study. Rationed, so not every patient receives it |
| PT-NA | Proton, clinical robustness settings, rescued where coverage fails | Reproduces the NA-Clinic arm of the reference study |
| PT-A | Proton, adapted at every block, reduced setup error from the matched uncertainty budget | Matched counterpart to XT-A. Corresponds to the reference study's OAPT-2mm |

**What dropping the unchanged-margin adaptive arms costs.** The study cannot separate the benefit of adaptation from the benefit of the margin reduction it licenses, since the two travel together by construction. The separation is available from the reference study for lung and is not re-derived here.

**What rescue gives back, and what it does not.** Where a non-adapted arm is rescued at every block, it becomes clinical-margin systematic adaptation, and its contrast with the adapted arm of the same modality is then a pure margin contrast. That estimate costs nothing, since both compositions exist, but it is conditional on a subgroup selected for maximal anatomical change and is not a cohort estimate. It is reported with the number of patients it rests on, and where that number is small only the count is reported. The cell that would make the separation clean, clinical margin with systematic adaptation, is not added: it would cost one replan per block per patient, and it could never be selected, since it costs what the adapted arm costs and is worth less.

**Arms and strategies.** An arm is a plan configuration. A strategy, in the allocator's sense, is an arm together with a fractionation schedule. Three of the four arms generate two strategies each and XT-NA generates one, so each patient's option set holds seven. Rescue does not add strategies; it changes the dose composed for one.

**Both adapted arms adapt on the same images.** XT-A adapts on the block repeat images, the same rCTs the proton arm uses, because those are the images that exist in the data. The modelled photon adaptation is therefore a per-block surrogate of the online workflow, which adapts on daily CBCT or MR; the direction of the net bias on the photon adaptation benefit is not known (evaluator E14).

### 4.2 Matched uncertainty budget across modalities

Introducing an adapted photon arm creates a fairness problem the reference study did not face. If the adapted proton arm is optimised at a reduced setup error while the adapted photon arm keeps clinical margins, part of the measured proton advantage is an artefact of an inconsistent uncertainty budget rather than a property of the modality. The reference study was internally consistent because its photon arm was not adapted, so full margins were correct there. That consistency does not survive the introduction of XT-A.

The photon equivalent of reducing the robust-optimisation setup error is reducing the CTV-to-PTV margin. The reference study performed this translation in one direction: it converted the van Herk margin of its photon plans into a non-isotropic setup error for robust IMPT optimisation, capping robust optimisation at 5 mm and applying the remainder as a CTV expansion, so that the two modalities carried a comparable uncertainty budget. The same translation, or its reverse, gives the adapted margin of the other modality.

**The budget.** Rather than asserting margin values per arm, both are derived from a single explicit budget of geometric uncertainty terms, each flagged for whether the adaptive workflow removes it. The clinicians supply the clinical and reduced settings for one modality; the other follows by conversion. The values are open decision 28 of the allocator document.

| Uncertainty term | Type | Removed by online adaptation? |
|---|---|---|
| Baseline setup and isocentre localisation | Systematic and random | Largely, given daily imaging and correction |
| Interfractional anatomical change, organ filling, weight loss | Mostly systematic | Yes. This is what adaptation is for |
| Delineation uncertainty on the planning image | Systematic | Only if re-contouring is performed and verified (allocator decision 29) |
| Intrafraction motion, breathing, drift | Random | No |
| Residual isocentre reproducibility | Random | No |

From that budget the photon margin follows from van Herk and the proton setup error from the published robustness recipes, so both arms are traceable to the same numbers, and the methods can show the derivation rather than assert two round figures.

Two properties of the budget are stated in advance. First, the van Herk recipe weights the systematic term at 2.5 and the random term at 0.7. Adaptation acts mainly on the systematic term, the heavily weighted one, so the margin reduction adaptation justifies for photons is proportionally large, against the intuition that photon adaptation is a marginal improvement. Second, the residual after adaptation is dominated by intrafraction motion, delineation and isocentre reproducibility, which are largely independent of beam physics. The two modalities therefore converge towards a similar residual geometric uncertainty at the adaptive limit, and the remaining difference between them is driven by dose-distribution physics rather than by the uncertainty budget, which is arguably the cleanest available statement of what proton therapy buys.

**Where the symmetry breaks.**

- For photons the dominant uncertainty is geometric, and the static dose cloud approximation holds reasonably well, so re-targeting onto the current anatomy captures most of the available benefit.
- For protons, adaptation recovers the geometric component and the interfractional density component of range error, since dose is recomputed on current anatomy. It does not touch the intrinsic CT-to-stopping-power calibration uncertainty, conventionally carried as 3 per cent, which has no photon analogue and is irreducible by adaptation.

Setup error is therefore a shared parameter that moves together across modalities, while range robustness is a proton-only parameter held fixed across all proton arms. Both facts are stated explicitly, since a reader will otherwise wonder whether range robustness was reduced as well.

A second asymmetry works in the opposite direction. The photon penumbra is broader, so a millimetre of margin reduction removes less normal-tissue dose in photons than the equivalent setup-error reduction removes in protons. In the limit, the photon margin reduction may bring little or no reduction in organ dose. The margin translation is therefore an equivalence of uncertainty accounting, not a guarantee of equivalent dosimetric payoff, and the size of the photon payoff is one of the empirical questions the symmetric arm set exists to answer.

**The allocation is referred to XT-NA throughout.** The objective, every policy ranking and every threshold use ΔNTCP against XT-NA, the arm every patient is entitled to. The comparison of PT-A with XT-A below is reported for every patient but is not a criterion in the allocation.

**Reporting.** Two differences are reported.

- ΔNTCP of PT-A against XT-NA, directly comparable with the published result.
- ΔNTCP of PT-A against XT-A, the current-technology comparison and the quantity that should drive a referral decision.

The gap between them quantifies how much of the published proton advantage is attributable to the photon arm not having been adapted. Both quantities come from the same computation.

**A qualification from rationing.** The second comparison is evaluated for every patient, but XT-A is not delivered to every patient, since the photon budget is finite. It is therefore a per-patient counterfactual, namely what the comparison would be if that patient's photon treatment were adapted, and is reported as such. Which patients actually hold XT-A is a separate and equally reportable output of the allocation.

### 4.3 Plan budget

Plans are generated in RayStation, which is faster and more reliable than OpenTPS for this purpose. The cost is that each plan is a manual act, so the size of the design is bounded by planning effort rather than by computation. With two repeat CTs, an adapted arm requires one plan on the planning CT plus one replan per repeat CT.

| Arm | Plans per patient per schedule | Schedules carried | Plans per patient |
|---|---|---|---|
| XT-NA | 1 | 1 | 1 |
| XT-A | 3 | 2 | 6 |
| PT-NA | 1 | 2 | 2 |
| PT-A | 3 | 2 | 6 |
| Total | | | **15, plus rescues** |

**Rescues are additional plans.** A non-adapted arm whose plan fails the acceptance criterion on a block acquires a replan on that image, which carries forward and is judged again on later blocks. The upper bound is one rescue per block from the second on, which would bring a non-adapted arm to the plan count of an adapted one; the expected number is much smaller and is not predictable before the data. The realised count is a study output, and planning-hour estimates carry the bound alongside the nominal count.

For comparison, the reference study used twelve dose distributions per patient across fourteen patients. Fifteen per patient before rescues is a comparable load. Dropping the unchanged-margin adaptive arms saves eight to twelve plans per patient, depending on whether their pCT plan would be shared with the non-adapted arm, and that saving buys cohort size. Since the cohort must also be enriched for cases in which the choice of schedule is genuinely in doubt, the budget is confirmed against planning-hour availability before the case matrix is fixed.

**The hypofractionated schedule may cost more.** The table assumes two repeat images per schedule. If the hypofractionated schedule is adapted per fraction, with the first fraction delivered on the pCT plan like every first block (Section 4.1), an adapted arm needs five plans on a five-fraction course, the schedule alone needs eleven or twelve depending on the XT-NA flag, and a patient needs nineteen over both schedules before rescues. Which images represent the hypofractionated blocks, and hence the block count, is open decision 23. The images available may come from conventionally fractionated courses, which span more anatomical change than a one-to-two-week course experiences; the images are then assigned to blocks by elapsed time from the start of treatment, and the resulting bias, which overstates the benefit of adapting a short course, is declared (Section 7.2).

**The plan count is linear in the number of blocks, and the strategy count does not depend on it.** Each block contributes one replan per adapted arm and, where the acceptance criterion fails, one rescue per non-adapted arm, so planning cost grows linearly in B while the option set stays at seven. What B governs downstream is the number of dose fields composed per strategy, also linear. The number of repeat CTs is therefore a data-availability parameter, not a design constraint.

**Levers for reducing the budget**, in order of scientific cost:

- Script the replanning from a fixed objective template (allocator decision 26), which reduces planning hours without changing the design.
- Coarsen the block structure of the hypofractionated schedule (decision 23), at the cost of modelling less than daily adaptation where the photon literature reports adaptation in nearly every fraction.
- Drop the adapted photon arm. Listed for completeness only: it would revert the comparator to the reference study's and forfeit the extension this study exists to make.

### 4.4 Prescription-time choice and the oracle framing

Modality, adaptation and fractionation are decided at prescription, as they are in clinics, and no schedule is changed during the course. The hypofractionated course is evaluated as prescribed from the first fraction. This is a property of the question the study asks, not a simplification made for cost.

Retrospective observation, such as the degradation visible on a repeat image, is used only to label which patients would have been selected for which workflow, not to design their plans. The question the study answers is: if patient selection were perfect, how much cohort-level benefit would the prescribed workflows deliver under two capacity constraints?

**The oracle is a ceiling and is reported as one.** The allocation uses information that is not available at prescription time, so the population benefit it reports is an upper bound on what any prospective rule could achieve, the same status the reference study's ideal scenario has. It defines a ceiling for any predictive model developed later in WP2 or WP3, and makes the prospective version, in which the workflow is chosen from planning-time features alone, the natural object of a later publication.

Paper 1 answers which patient receives which workflow. When to act within a course, and the right-time framing of the work package, belong to a later publication.

### 4.5 Endpoint models and the fractionation correction

Fractionation is a degree of freedom only if the endpoint is evaluated on a dose quantity that carries the fraction size. The endpoint models are therefore evaluated on EQD2, converted voxel-wise at a declared α/β (Section 6), and the model family is open decision 10.

- **A model with a fractionation term**, such as an LKB model on gEUD of EQD2 with a declared α/β, is used as fitted.
- **A model without one**, such as a multivariable logistic fit on mean dose plus clinical covariates, as used in the reference study and in the Dutch protocols, is evaluated on mean EQD2 at a declared α/β. The approximation is that the model was fitted on physical dose at conventional fraction size; it is stated as a limitation and bounded by the α/β sensitivity (Section 7).
- **No model is evaluated on physical dose across schedules.** A five-fraction plan delivers lower physical dose for the same biological effect, so a physical-dose evaluation would make hypofractionation look beneficial by construction.

Better-fitted fractionation-aware models would strengthen the result; their absence limits it without invalidating the design.

### 4.6 Anatomical site: two candidates

The indication is abdominal. The site is not fixed, and two candidates are carried: pancreas and adrenal (allocator decision 19, comparison table in allocator 10.4). The criteria, in order of weight:

1. **Clinical doubt between the two schedules, and plans generated with the clinicians.** The study needs a site where clinicians genuinely hesitate between standard and hypofractionated treatment; without that doubt the fractionation axis has no clinical question to answer.
2. **Repeat imaging in the cohort**, without which no block beyond the first exists.
3. **Endpoint models**, used as Section 4.5 describes.

**Pancreas.** The current guideline recommends, for locally advanced disease, both conventionally fractionated chemoradiation and five-fraction stereotactic treatment, and recommends adaptation for dose-escalated stereotactic delivery. Two schedules recommended for the same clinical setting is the condition on which photon schedule equivalence rests (Section 3.6). One confounder follows. Conventional treatment includes elective coverage of regions at risk of microscopic disease and stereotactic treatment does not, so comparing the two protocol schedules confounds fraction size with target volume. If pancreas is chosen, the target volume is fixed explicitly: either held constant across schedules and declared as a deviation from protocol, or kept per protocol with target volume and target EQD2 reported as descriptive rows.

**Adrenal.** There is no guideline pair of the same standing, the setting is oligometastatic, and the clinical rationale for a proton arm is weak. The empirical case for adaptation is very strong: a published MR-guided series reports adaptation in essentially every fraction. That leaves the adaptation decision with almost no variance for the allocation to inform.

**A dilemma common to both.** Adaptation is recommended where the delivered dose is escalated, and escalation is the point at which the two schedules stop being isoeffective on the target. The non-escalated schedule preserves schedule equivalence and weakens the clinical rationale for adaptation; the escalated one strengthens the rationale and forfeits equivalence, which without a TCP model cannot be repaired. The choice is made explicitly and declared.

## 5. Software architecture

Three modules, specified in their own documents. This section states only what the paper needs to assert.

### 5.1 Module split

| Module | Role in the paper |
|---|---|
| Extractor | Produces per-block physical dose, per-block target metrics, registrations and plan complexity descriptors, and reads the export manifest that records each arm's plan sequence. Emits dose-derived quantities rather than precomputed NTCP |
| Evaluator | Constructs the seven strategies, composes each from its plan sequence, converts to EQD2, evaluates NTCP, verifies the acceptance judgement and computes the no-harm diagnostic, hosts the NTCP model registry |
| Allocator | Solves the capacity-constrained allocation and produces the shadow prices, the step-ratio threshold and the policy comparison. Never touches a dose grid |

The dose-metric interface between extraction and evaluation is required for three reasons: NTCP models will be replaced, and precomputed scalars would force re-extraction each time; the parameter propagation of Section 5.9 requires thousands of re-evaluations with perturbed parameters, which a stored scalar cannot support; and NTCP is nonlinear, so the NTCP of a course whose plan changes between blocks cannot be composed from per-block values.

The allocator's independence from dose objects is what made it developable and testable on synthetic cohorts before data authorisation. Its algorithmic layer is complete and tested: the exact solve reproduces the reference study as the two-option special case, the linear relaxation is verified against an independent solver, and the six policies of Section 5.6 run end to end on synthetic cohorts.

### 5.2 Occupancy and the budget

Proton machine time, consumed by the proton arms:

occupancy_PT = n_fx · (τ_0 + Δτ_PT) for PT-A, n_fx · τ_0 for PT-NA

Photon adaptation time, consumed by the adapted photon arm:

occupancy_XT = n_fx · Δτ_XT for XT-A, zero for XT-NA

Occupancy is per course, because adaptation is a property of the course; this is the reference study's own accounting. The proton arms are charged the whole session, because the proton machine is binding for delivery as well as for adaptation. The adapted photon arm is charged only the increment, because photon delivery is not binding, so no photon baseline session length enters the design. A rescue is an offline replan and charges neither budget (allocator A28).

Both budgets are counted over a horizon rather than within a day. Under stationary operation with staggered starts, the horizon total is the mean of the daily load, and heterogeneous fraction counts across strategies do not break this. There is **one shadow price per resource**, reportable per day or over the horizon.

**Stated limitation.** The horizon constraint is exact for the mean load and relaxes daily feasibility: between-patient heterogeneity and discrete starts make the daily load fluctuate about its mean, and a patient's fractions must fall on consecutive working days. The allocation is therefore an upper bound on achievable throughput, not a schedule (allocator 10.2, A2). Daily feasibility could be checked without changing the allocation, by simulating staggered starts under the optimal allocation and reporting the fraction of days over capacity; the check is not planned.

### 5.3 The allocation problem

Each patient receives exactly one strategy, subject to a proton capacity constraint and a photon adaptation constraint, maximising cohort ΔNTCP against XT-NA. This is a multiple-choice knapsack problem with two resources.

Because no strategy consumes both budgets, each patient's option set is two chains meeting at XT-NA: a photon chain and a proton chain. XT-NA consumes neither budget and is assignable for every patient, since it is rescued rather than removed, so the allocation is always feasible. The model therefore cannot represent a department stressed to the point where a patient receives no treatment. That is the correct behaviour for a referral question, and it is stated so that the word capacity does not import the other connotation.

### 5.4 Why ranking by ΔNTCP is not sufficient

The Dutch protocol ranks patients by ΔNTCP and refers those above a threshold. The reference study did the same when choosing which patients to displace to photons. That ranking is optimal only when every candidate consumes the same capacity, which was true there and is false as soon as adaptation and fractionation vary.

The demonstration for the paper is a three-way comparison: the ΔNTCP ranking of current practice, the benefit-density ranking that would be the natural first correction, and the allocation that is optimal or near-optimal.

**Ranking with two budgets.** A benefit density, ΔNTCP per minute, is defined on one budget at a time. Ranking proton and photon upgrades in one list would need an exchange rate between proton minutes and photon adaptation minutes. That rate is λ_XT / λ_PT, an output of the LP, and it cannot be an input to heuristics meant to approximate it. The heuristic policies therefore rank proton upgrades only, and spend the photon adaptation budget by a separate rule: photon patients are adapted in decreasing ΔNTCP until the budget is exhausted. At zero photon budget this is the single-resource ranking (allocator 5.3).

**Magnitudes.** How far the naive ranking falls short of the optimum is measured on the seven-option sets, first on synthetic cohorts and then on the cohort. The expected result, stated as a hypothesis, is that the naive rule is near-optimal within one schedule, and that the gap opens when both schedules compete on the proton axis, where the best upgrade can skip a rung.

**The shadow prices.** The same relaxation yields one multiplier per constraint. λ_PT is the cohort benefit bought by one additional proton machine-minute and inherits the reference study's interpretation. λ_XT is the cohort benefit bought by one additional minute of photon adaptation, and no comparable quantity exists in the reference literature as far as is currently known. No threshold is supplied as an input; it is induced by the allocation. This gives the ΔNTCP referral threshold of the Dutch protocol a facility-specific interpretation, and it answers whether a workflow change costing additional minutes per fraction is worthwhile without enumerating scenarios.

**λ_XT is reported as a curve.** Its magnitude depends on the photon adaptation budget, which has no measured anchor for this indication, so a single value would report an assumed number. The budget is swept instead. At zero budget the comparator is the reference study's non-adapted photon arm, and at a budget covering the cohort's demand every patient not on protons receives adapted photons. The ratio λ_XT / λ_PT across the sweep states where the next unit of investment buys more, which is a departmental result rather than a per-patient one.

### 5.5 Scalar endpoint for the allocation decision

The reference study reported three NTCPs separately but needed a scalar to decide which patients to displace, and used the probability of at least one complication. The same convention is adopted, and severity weighting is not applied: a composite for the decision, individual endpoints for reporting.

NTCP_total = 1 − Π_k (1 − NTCP_k)

The independence assumption is false, since toxicities in a shared anatomical region are correlated; under positive dependence the composite overestimates the probability of at least one event. The direction of that bias is stated in the manuscript.

### 5.6 Compare policies rather than reporting a single optimum

An optimum on its own is not a clinically useful output, because no clinic implements an integer program. The informative output is the gap between what simple rules achieve and what is achievable at all.

| Policy | Definition | What it represents |
|---|---|---|
| P0 | Threshold-based referral, fixed standard schedule, no adaptation | Current practice. The baseline policy |
| P1 | Threshold-based referral, adaptation for all proton patients, fixed schedule | Essentially the reference study |
| P1x | As P1, then photon adaptation in decreasing ΔNTCP until the photon budget is exhausted | Separates the value of the adapted photon arm's existence from the value of optimising over it |
| P2a | Greedy by benefit density over patients | The natural but generally suboptimal capacity-aware rule |
| P2b | Greedy by best available upgrade over Pareto-reduced option sets | The correct heuristic |
| P3 | Exact multiple-choice knapsack optimum | Upper bound on what any allocation can achieve |

Under two resources the heuristics rank proton upgrades only, and the photon budget is spent by the separate rule of Section 5.4 (allocator 5.3). All conventions coincide at zero photon budget, so the single-resource behaviour is recovered by construction.

Cohort ΔNTCP is reported for each policy as a function of adaptation time. P3 − P0 is the total headroom; P2b − P0 is what a correct implementable rule captures; P3 − P2b indicates whether exact optimisation is worth anything; P2b − P2a is the methodological result of Section 5.4; and P3 − P1x separates the gain of optimising the allocation from the gain of the adapted photon arm merely existing, which P3 − P1 confounds. If P2b recovers most of P3, that is a useful clinical message and the natural performance baseline for a later WP3 agent.

**The policy comparison is a secondary output.** The primary result is the parametric behaviour of the optimal allocation itself under the two constraints; the policies read that result against implementable rules (Section 5.12).

### 5.7 Two-dimensional adaptation-time output

The central result of the reference study was a threshold in adaptation time. That structure is preserved and extended at three levels.

With adaptation available on both modalities there are two adaptation times, one per modality, and the natural output is a contour of cohort ΔNTCP over the (Δτ_PT, Δτ_XT) plane, with the iso-benefit line separating the region in which adaptive proton therapy remains worthwhile from the region in which it does not. The symmetric arm set of Section 4.1 is what makes the two axes commensurable.

Beneath that surface sits the step-ratio threshold of the allocator document, which partitions the proton axis into the regime where non-adapted protons are a live option and the regime where a patient who enters the proton chain enters it adapted, and the problem collapses to the reference structure.

The third level is the photon adaptation budget, a parameter rather than an axis of the plane. Sweeping it produces λ_XT as a curve and moves the step-ratio threshold, since a larger budget puts more patients on the stronger comparator and shrinks their modality step. One sweep yields both.

**The plane is evaluated at a reference budget.** A single reference value C_XT^ref, in absolute minutes and fixed with the clinical partners and the supervisor (allocator decision 13), plays for the photon budget the role the 480 minutes play for the proton budget in the reference study. The (Δτ_PT, Δτ_XT) plane is computed there. The budget sweep is reported on a normalised axis, the photon budget as a fraction of the cohort's photon adaptation demand (allocator 5.2), with minutes secondary, so that its endpoints are the reference study's comparator and the unconstrained case by construction.

### 5.8 Cohort size

The cohort has not been assembled, and its size and composition are not known. If it proves small, the output of the capacity model becomes a step function in the number of patients. With eight patients, each moves the cohort mean by an eighth, and a threshold read from the curves reflects granularity as much as physics. One possible response is to use the cohort to estimate the joint distribution of benefit and occupancy per patient per strategy, resample synthetic populations of realistic size, and report thresholds with confidence intervals. This assumes the cohort represents the referral stream. A cohort enriched for schedule-equivocal cases does not, so the resampled population would be described as enriched. Whether any such step is needed is decided once the data are in hand; if the cohort is large enough, the allocation is run on it directly.

### 5.9 Propagating NTCP parameter uncertainty through the decision

NTCP model support in the abdomen is thin, and there is no equivalent of the Dutch protocol model set for these sites. The registry currently holds one populated model, a pelvic test model (QUANTEC rectum) used to exercise the mechanism; the abdominal endpoint models depend on the site (decision 19) and the model family (decision 10). The proposed handling converts the vulnerability into a result: sample the NTCP model parameters from their published confidence intervals, propagate each sample through the allocator, and report the fraction of samples in which the allocation itself changes. This measures decision robustness rather than dose robustness, which is the quantity that matters for a referral rule, and no comparable analysis exists in the reference literature as far as is currently known.

The evaluator caches the reduced dose at the dose-volume histogram rather than at the gEUD scalar, so the volume parameter can be perturbed without recomputing the accumulated dose, which makes the propagation computationally cheap. Perturbing α/β is structurally more expensive, since it enters before the accumulation, so it is treated as a separate sensitivity axis rather than propagated in bulk.

### 5.10 Admissibility

ΔNTCP ranks strategies on organ dose alone and carries no information about the target. Two conditions are checked, and neither removes a strategy from the option set.

**Target coverage, judged per block, enforced by rescue.** A plan delivered on a changed anatomy can lose target coverage, and if the target has moved away from the driving organ at risk it can lose coverage while its NTCP improves, so a ranking on ΔNTCP alone would prefer the arm that undertreats the tumour. Coverage is a property of a plan delivered on a given anatomy, so the criterion is applied to each block's plan on its own image and not to the accumulated dose, which is permissive in the wrong direction. An arm whose plan fails is **rescued**: it acquires a replan generated on that image at unchanged margin and unchanged setup error, which carries forward and is judged again on later blocks. This is a supervisory decision, and it is standard clinical practice, as in the reference study (allocator 2). The criterion applies symmetrically to the photon arms, whose dose is recomputed on the repeat images; screening protons while exempting photons would bias the measured proton advantage.

**The judgement is made at plan generation.** The criterion is the plan acceptance protocol used at treatment planning (decision 7b), fixed before plan generation starts. Each non-adapted plan is recomputed on each new image in RayStation and judged there, and a rescue is generated at once where it fails; the plan sequence is recorded in the export manifest. The evaluator re-applies the criterion as a verification, and where the two disagree RayStation governs and the disagreement is reported (allocator 8.2, evaluator 6.1). Changing the criterion afterwards changes which plans exist, so a sensitivity analysis on it costs planning effort, not computation. Worst-case evaluation is recorded per plan and per block and reported as counts; it does not trigger rescue.

**Rescue is a phenomenon of the non-adapted arms.** An adapted arm's block plan is optimised on the anatomy it is then evaluated on, so nominal coverage holds by construction. The criterion is nonetheless verified on every arm and the count reported per arm, because that property must be demonstrated rather than asserted, and a non-zero count on an adapted arm means the replanning failed (decision 26). Where a reduced-margin plan cannot be made robustly acceptable at plan generation, that patient has no adapted arm of that modality (allocator A31).

**No harm, reported rather than enforced.** A strategy whose union ΔNTCP against XT-NA is negative is counted and reported, not removed. The requirement is that maximising a cohort mean must not make any individual worse than current standard care; removal is not what delivers it. The count is computed on the union scalar, consistent with the selection rule, and per-endpoint sign violations are counted separately.

**What protects the individual is structural.** The allocator imposes no constraint on the sign of ΔNTCP. Protection comes from the option set: XT-NA costs nothing on either budget, has ΔNTCP identically zero, and is never removed, so it dominates every strategy of negative benefit, and substituting it both raises the objective and frees capacity. No optimal allocation contains a harmful strategy. The property is a consequence of the formulation, not an empirical finding, and the manuscript argues it as such. The count of patients with no free assignable option is retained as a regression check on the construction, expected to be zero.

**Rescue frequency is the diagnostic to produce**, by arm, by schedule and by block. It measures how often the standard-of-care workflow itself requires offline replanning, a clinically citable number in its own right, and it is the empirical check on whether a non-adapted arm, in particular a five-fraction course without systematic adaptation, is plausible.

**The reference includes rescue, so results are conditional on the acceptance criterion.** XT-NA is defined as current practice: the clinical-margin plan, replanned offline wherever it fails the acceptance criterion on a repeat image. A plan below the criterion would not be delivered, so a reference without rescue would not represent current practice; rescue restores the reference rather than improving it. The reference NTCP, and with it every ΔNTCP, therefore depends on which criterion defines acceptability (decision 7b). PT-NA is rescued on the same criterion, so the modality step, the photon outside option and the step-ratio threshold Δτ\* are conditional on the criterion as well. Two quantities do not depend on the rescue of XT-NA: the ordering among a patient's other six options, and pen\*, which compares two adapted proton arms. The criterion is recorded with every result.

### 5.11 Photon adaptation as capacity relief

A stronger adapted photon arm reduces the number of patients whose ΔNTCP justifies a proton slot, so photon adaptation functions as a capacity-relief mechanism for the proton facility and not only as a tougher comparator. The allocator quantifies this directly, since the proton slots released per unit of photon adaptation capability are an output of the same optimisation that produces the cohort mean. This framing does not appear in the reference literature as far as is currently known, and it is the clearest argument for having the adapted photon arm in the design rather than naming it as future work.

With photon adaptation rationed, the relief is the exchange rate between the two budgets: the proton minutes released per photon adaptation minute purchased, governed in price terms by λ_XT / λ_PT and read off the same budget sweep. The relief with unlimited photon adaptation is the limit of that sweep and is reported as the limit, not as the estimate. The interior of the sweep is what a centre would obtain, conditional on the assumed extra time per adapted photon fraction.

### 5.12 Candidate outputs, in order of relevance (provisional)

The ordering is provisional and is revisited once real cases are in hand, since the relative interest of the outputs depends on what the data show. It exists now for a structural reason: the sweep and reporting machinery must produce every entry without deciding internally which one is the result, so the hierarchy is a property of the manuscript, not of the code.

| Rank | Output | Nature |
|---|---|---|
| 1 | The parametric allocation study: how the optimal assignment of the cohort moves across the (Δτ_PT, Δτ_XT) plane at C_XT^ref, with the iso-benefit line, and along the normalised photon budget axis. Composition by arm and by schedule, and cohort ΔNTCP | Primary |
| 2 | The two shadow prices: λ_PT at the reference configuration, λ_XT as a curve over the normalised budget, and their ratio as the departmental investment signal | Primary, derived from 1 |
| 3 | The step-ratio regime boundary Δτ\*(C_XT): where the non-adapted proton arm carries value at all | Structural, derived from 1 |
| 4 | Policy gaps: P3 − P0, P2b − P0, P3 − P2b, P2b − P2a, P3 − P1x | Secondary |
| 5 | Per-endpoint ΔNTCP against XT-NA, and the per-patient PT-A versus XT-A counterfactual | Secondary, reporting |
| 6 | Robustness of the conclusions: Monte Carlo parameter propagation at the decision level, α/β sensitivity, accumulation-ordering sensitivity | Supporting |
| 7 | Option-set diagnostics: rescue frequency by arm, schedule and block; disagreements between the acceptance judgement and its verification; robust-evaluation failures by arm; assignable strategies of non-positive ΔNTCP; patients with no free assignable option, expected zero; patients for whom an adapted arm could not be generated | Supporting, reporting |

Entries 1 to 3 come from one computation and constitute the finding; entries 4 and 5 read the finding against practice; entries 6 and 7 defend it. Entry 7 is a table rather than a figure and belongs with the methods, since it describes what the allocator was given rather than what it produced. A figure that does not serve one of the first six does not enter the manuscript.

## 6. Dose accumulation and biological conversion

Biologically effective dose accumulates over blocks, with the local dose per fraction obtained from the block's physical dose D_b and its fraction count n_b:

BED_b(x) = n_b · d_b(x) · (1 + d_b(x)/(α/β)), with d_b(x) = D_b(x)/n_b

EQD2(x) = BED_total(x) / (1 + 2/(α/β))

n_b is derived from the acquisition dates of the repeat images relative to the start of treatment, and set by hand where the dates do not determine it (evaluator E21). The conversion is voxel-wise and precedes any dose-volume histogram reduction, since the generalised equivalent uniform dose does not commute with the EQD2 transform.

**Ordering with respect to deformation.** Conversion also precedes deformation. The transform is convex in dose, so interpolating physical dose and converting afterwards underestimates systematically, with the error concentrated in the high-gradient region. For a serial-like organ with a small volume parameter the gEUD draws its weight from precisely that region, so the error does not average out. The adopted sequence is therefore: compute the BED field per block on its own geometry, deform, sum over blocks, and convert the total to EQD2 once. Summation after deformation is exact because BED is additive over segments.

The cost is that the deformed field is not unique, since it depends on the schedule, the block's fraction count and the structure's α/β. These are repeated applications of a cached deformation field rather than repeated registrations, so the dominant cost is unchanged. The alternative ordering is computed once on a real case and the difference in gEUD reported in the methods, which converts an assumption into a measurement.

## 7. Where the conclusion could be conditional

### 7.1 α/β ratio

Any comparison between fraction sizes routes through the linear quadratic conversion, which is governed by α/β. That parameter is weakly constrained by the data underlying conventionally fractionated dose-response models. The strength of the conclusion therefore depends on the endpoint chosen, and in the worst case a result could reflect a parameter choice as much as a workflow finding.

What is in place against this exposure: an α/β sensitivity analysis, reported alongside the main result; endpoint models evaluated on EQD2 at a declared α/β, with the approximation stated where the model carries no fractionation term (Section 4.5); cross-checking of organ tolerance at large fraction size against the hypofractionation literature; and the Monte Carlo parameter propagation, which addresses the same exposure at the level of the decision rather than the dose.

**Residual exposure.** If the sensitivity analysis shows that the spread from α/β exceeds the spread from workflow variation, the manuscript reports a conclusion conditional on that parameter and states what evidence would resolve it. This is a weaker headline but an honest and citable contribution. The decision-robustness result partially insulates the paper against this outcome, since a demonstration that the allocation is stable under parameter uncertainty is informative even when the absolute NTCP values are not.

### 7.2 Current limitations

Each is stated in the manuscript with its direction where known.

| Limitation | Direction | Where |
|---|---|---|
| Robustness effects of fraction number (random-error averaging, intrafraction drift) are not modelled | Favours hypofractionation; size not measured | Section 3.4; evaluator E22 |
| The first block carries no modelled anatomical degradation | Favours the non-adapted arms; understates adaptation benefit | Section 4.1; allocator A23 |
| Every ΔNTCP, and Δτ\*, is conditional on the acceptance criterion | Level of ΔNTCP and the step-ratio threshold move with the criterion; pen\* and the ordering among non-reference options do not | Section 5.10 |
| One replan per block stands for daily online adaptation, for both modalities | Not signed for photons (evaluator E14); for protons, variation within a block is not represented (allocator A1) | Section 4.1 |
| Hypofractionated blocks may be represented by images from conventionally fractionated courses | Overstates anatomical change for the short course, hence the benefit of adapting it and its rescue frequency | Section 4.3; decision 23 |
| Proton hypofractionation is assumed isoeffective on the tumour | Not signed; target EQD2 reported descriptively | Section 3.6; allocator A5 |
| Endpoint models without a fractionation term are evaluated on mean EQD2 | Not signed; bounded by the α/β sensitivity | Section 4.5 |
| Planning and physics labour is unpriced | Favours adaptation | allocator A28 |
| Toxicities are treated as independent in the union probability | Overestimates the probability of at least one event | Section 5.5 |
| The horizon constraint relaxes daily feasibility | Allocation is an upper bound on throughput | Section 5.2 |
| The oracle allocation uses information unavailable at prescription | Upper bound on any prospective rule | Section 4.4 |

# Road to Paper 1

Version 6.1. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 0. Document set and division of labour

Four documents describe this work, and each owns a distinct subject.

| Document             | Owns                                                                                                                                             |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| **Road to paper 1**  | Scientific question, hypothesis, arm set, uncertainty budget, plan budget, endpoint policy, what the paper claims                                |
| **Allocator design** | The optimization problem, the algorithm, the shadow price, the step-ratio threshold, the policy comparison, the capacity accounting              |
| **Evaluator design** | Dose composition, accumulation ordering, EQD2 conversion, NTCP evaluation, admissibility screens, strategy construction, the NTCP model registry |
| **Extractor design** | Ingest, registration, storage, target metrics, plan complexity, ROI naming, provenance                                                           |

Section 5 of this document therefore summarises the software architecture at the level a reader of the paper plan needs and defers every algorithmic detail to the module documents.

## 1. Background

The reference study established that the normal tissue complication probability (NTCP) benefit of online adaptive proton therapy decays with the time required to adapt, because adaptation consumes machine capacity and displaces patients to photon therapy. The analysis held the number of fractions constant at 30, which made time per fraction and time per treatment course interchangeable. It also held the photon arm non-adapted and named the integration of online adaptation into the photon branch as future work.

This project proposes to release both constraints. When fractionation becomes a degree of freedom the two time quantities separate, the resource consumed by a patient becomes machine time per course, and adaptation and fractionation compete for a single budget. When the photon comparator is itself allowed to adapt, the reference point against which the proton advantage is measured moves, which is the more demanding test of whether that advantage survives.

**Photon adaptation is a rationed resource, not a free one.** A department that can adapt some photon patients cannot in general adapt all of them, and the arm that every patient is entitled to is the non-adapted one. The design therefore carries two budgets: proton machine time, and photon adaptation time. Non-adapted photon treatment consumes neither and remains the locked reference, so the zero point of every ΔNTCP value is unchanged and the comparison with the reference study’s decomposition stays valid. Adaptation is the scarce quantity on both modalities, and patients compete for it through the ΔNTCP it buys them. Each budget carries its own shadow price, λ_PT and λ_XT, and their ratio states where a department gains more from the next unit of investment. The allocator document specifies the formulation.

The two levers act on opposite terms of the cohort mean. Hypofractionation improves cohort composition by freeing capacity, while for late-responding organs at risk it plausibly degrades the per-patient NTCP through the increased biological effect of larger fractions: higher dose per fraction at lower integral dose, longer individual fractions with more exposure to intrafraction motion, and reduced averaging of random setup error over fewer fractions.

**Central hypothesis.** Adaptation and fractionation are not additive. Adaptation could therefore be what makes hypofractionation robust enough to be clinically worthwhile.

**Principal new deliverable.** An OpenTPS plugin that allocates a capacity-constrained proton resource across a cohort whose members no longer consume equal machine time. Its decision rule generalises the model-based selection logic of the Dutch national protocol, in which patients are referred to protons on a clinically meaningful ΔNTCP threshold, to the case where the candidate workflows differ in machine cost.

**A structural result now sits alongside the hypothesis.** At a fixed fractionation scheme, whether the non-adapted proton arm carries any allocative value is governed by a threshold in the extra time per adapted fraction, with the closed form Δτ\* = τ_0 · (a/m), where a/m is the ratio of adaptation benefit to modality benefit measured on the cohort. Below the threshold PT-NA lies under the segment joining photons to fully adapted protons: a patient who enters the proton chain enters it adapted, and the problem reduces to the reference study’s structure. Above it, PT-NA is a live rung and the cohort can split three ways. The threshold is a per-scheme statement: each fractionation scheme carries its own (τ_0, a, m) and therefore its own Δτ\*, and the competition between schemes, in which the biological penalty of larger fractions trades against the capacity they free, is not captured by the formula. That cross-scheme interaction is the subject of the study and is resolved by the allocator, not by a closed form. The threshold also depends on the photon adaptation budget, because the bottom rung of a patient’s proton ladder is whichever photon arm that patient would otherwise hold. A patient receiving adapted photons measures the modality step against a stronger comparator, which shrinks it and raises the threshold; a patient receiving non-adapted photons measures it against the locked baseline. Δτ\* is therefore reported as a function of the photon budget rather than as a number, on the same sweep that produces λ_XT. Since no clinical on-couch adaptive proton workflow exists for the abdomen, the extra time per adapted fraction is the study’s independent variable, exactly as in the reference study, and the per-scheme thresholds are the deliverable at this level. The derivation is in the allocator document, Section 6.5.

## 2. Scope of the publication

|                    | **In scope**                                                                                                                                                                                                                                                                                                                                                                                                | **Out of scope**                                                                                                                                                                                                                                                                           |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Scientific content | Joint effect of adaptation strategy and fractionation on cohort NTCP under machine capacity constraints. Allocation of a capacity-constrained proton resource and a rationed photon adaptation resource across a cohort whose members no longer consume equal machine time. The step-ratio threshold governing when per-block adaptation allocation carries value. The relative price of the two resources. | Reinforcement learning formulation. Prospective validation. Functional imaging biomarkers. Queueing dynamics, arrival processes and waiting-list policy. Scheduling, in the sense of which fraction occupies which slot on which day. Photon delivery capacity, modelled as unconstrained. |
| Modalities         | Proton therapy against a photon comparator, following the model-based selection logic that motivates the ΔNTCP metric. The photon comparator now includes an adapted variant, which is the extension the reference study named as future work.                                                                                                                                                              | Comparison across proton delivery techniques. Comparison across photon delivery platforms. Fraction-level mixing of modalities within a course.                                                                                                                                            |

## 3. Scientific rationale

### 3.1 What changes when fractionation is released

In the reference study the machine resource consumed by a patient was proportional to the extra time per fraction alone. Once the fraction count varies, the relevant quantity becomes total course time:

T_course = n_fx · (t_fixed + t_delivery(d) + t_adaptation)

Two consequences follow. Capacity must be counted over a horizon rather than within a day, because a patient with fewer fractions occupies the machine on fewer days rather than for a shorter slot. And the gain from reducing the fraction count is smaller than it first appears, because delivery time grows sub-linearly with dose per fraction.

**Where the freed capacity goes.** The cohort is closed, so capacity released by hypofractionation cannot admit new patients. It can be spent in exactly two ways: upgrading an existing patient to more adaptation or moving a patient off the photon arm onto protons. The second is the displacement mechanism of the reference study running in reverse, and it exists only because the photon strategy is inside each patient’s option set at zero proton cost. Without that, hypofractionation would carry no capacity value in this formulation at all. This is the mechanism that makes the cohort-composition channel representable, and it should be stated in the manuscript rather than left to emerge.

### 3.2 Two channels acting in opposite directions

The cohort mean ΔNTCP contains two channels. The first is cohort composition, meaning how many patients receive protons at all under the capacity constraint. The second is the per-patient NTCP of each patient who does receive protons. The two levers load onto these channels in opposite senses, which is the principal justification for studying them jointly rather than in sequence.

| **Lever**         | **Channel A: cohort** composition**                                                         | **Channel B:** per-patient NTCP**                          |
|-------------------|-----------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| Faster adaptation | Improves                                                                                                  | Neutral                                                                  |
| More adaptation   | Degrades through capacity loss                                                                            | Improves through dosimetry                                               |
| Hypofractionation | Improves through capacity gain                                                                            | Uncertain, plausibly degrades                                            |
| Photon adaptation | Improves, by releasing proton slots. Consumes the photon adaptation budget rather than the proton machine | Improves the comparator, therefore reduces the measured proton advantage |

### 3.3 The four competing effects

| **Effect**                                | **Direction**   | **Mechanism and confidence**                                                                                                                                                                                                                                                     |
|-------------------------------------------|-----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Capacity                                  | Positive        | Shorter courses free machine time, so fewer patients are displaced to photons                                                                                                                                                                                                                    |
| Radiobiology at isoeffective prescription | Likely negative | At tumor-isoeffective dose, the differential between organ α/β near 3 and tumor near 10 raises normal tissue biologically effective dose when fractions are enlarged. Direction follows from the linear quadratic model. Physical dose falls, per-fraction weighting rises                       |
| Robustness                                | Mixed           | Reduced averaging of random setup error over fewer fractions, substantially absorbed when daily imaging and correction are in place. Longer delivery accumulates baseline drift and organ filling, which are systematic within the fraction. Partly offset by more breathing cycles per fraction |
| Adaptation economics                      | Positive        | Fewer fractions mean fewer adaptation events per course, so a given per-fraction adaptation cost is cheaper over the course                                                                                                                                                                      |

### 3.4 Central hypothesis and its mechanism

The van Herk formulation separates systematic from random geometric uncertainty. The fraction count enters only the random term, since the realised mean displacement over n fractions has standard deviation sigma divided by the square root of n. At five fractions this residual is approximately 0.45 sigma, which is not negligible in the abstract.

However, sigma in an adaptive workflow is the residual after daily imaging and correction, comprising intrafraction motion, delineation uncertainty and isocentre reproducibility. This corresponds to the 2 mm setup error scenario of the reference study. A square-root-of-n penalty applied to an already small residual is minor. The robustness cost of hypofractionation is therefore conditional on the adaptation strategy, and the design measures that conditionality directly through the interaction term.

### 3.5 Predicted site dependence

The inflation of equivalent dose in 2 Gy fractions scales with the local dose per fraction. Voxels in the high-dose region adjacent to the target are strongly affected, whereas the low-dose bath is nearly insensitive to fraction size. Hypofractionation therefore shifts the weight of the organ dose response towards the high-dose region, which is where the proton advantage over photons is smallest.

The magnitude of this redistribution is governed by the volume parameter of the dose response model. For serial-like organs with a small volume parameter, such as rectum, the generalised equivalent uniform dose approaches maximum dose, making the endpoint strongly fractionation sensitive and weakly proton favourable. For parallel organs with a volume parameter near unity, such as liver, the endpoint approaches mean dose, making it less fractionation sensitive and more proton favourable. The sign and size of the effect are therefore expected to depend on which organ drives the NTCP, which makes the choice of anatomical site a design input rather than an incidental detail.

The same volume parameter has a second, computational consequence: it determines how sensitive the result is to the ordering of dose accumulation and biological conversion. See Section 6.

### 3.6 Controlling tumor effect across fractionation schemes

**The issue.** NTCP is a monotone function of biologically effective dose to the organ. Adaptation and margin reduction lower organ dose at fixed target dose, so a ΔNTCP comparison isolates their value cleanly. Fractionation does not have this property. If two arms deliver different biologically effective dose to the target, part of the NTCP difference between them is bought by treating the tumor differently rather than by sparing normal tissue better. A ΔNTCP ranking is then not a valid ranking of workflows, and a reviewer will say so.

The following illustration uses the current single-case prescription and an arbitrary five-fraction schedule chosen to be isoeffective on the target at α/β of 10 Gy. It is arithmetic, not a proposed prescription.

| **Schedule**            | **Dose per** fraction** | **Target EQD2,** α/β 10 Gy** | **Organ EQD2 at** full dose, α/β 3** Gy** |
|-------------------------|---------------------------------------|--------------------------------------------|-----------------------------------------------------------------------|
| 50.4 Gy in 28 fractions | 1.8 Gy                                | 49.6 Gy                                    | 48.4 Gy                                                               |
| 35 Gy in 5 fractions    | 7.0 Gy                                | 49.6 Gy                                    | 70.0 Gy                                                               |

At matched tumor effect the hypofractionated schedule costs roughly 22 Gy of equivalent dose in the high-dose organ region. That is the honest expected direction, and it is what makes the capacity trade-off a genuine tension rather than a foregone conclusion. Conversely, if the hypofractionated arm were to sit below the standard arm in target EQD2, its NTCP would fall for a reason that has nothing to do with workflow quality.

**Route chosen, and confirmed.** Clinical equivalence by convention. The clinical partners confirm that sanctioned protocols are available and that the candidate schedules are clinically equivalent for tumour control, so isoeffectiveness is asserted by clinical consensus rather than derived from a linear quadratic calculation. This is the logic the Dutch protocol uses when comparing modalities, in which the prescription is fixed by guideline and only NTCP is compared.

**The condition on which this route depended is met**, namely that both schedules be guideline-accepted for the same indication rather than chosen by us.

**Safeguard adopted regardless of route.** Target EQD2 per arm is reported as a descriptive row in the results table, at a declared tumor α/β. It is produced by the evaluator as a first-class output rather than computed ad hoc at figure time, so that any residual mismatch in tumor effect between arms is visible.

## 4. Study design

### 4.1 Arm set

The arm set is symmetric across modalities: a non-adapted arm at clinical margins and an adapted arm at reduced margin, per modality. The adaptive arm at unchanged margins is not carried, following the supervisory decision, since the reference study already characterises it as OAPT-Clinic. Each arm is evaluated under both fractionation schedules.

**The workflow is chosen at prescription, on the planning CT.** Following the version 6 supervisory decision, modality, adaptation and fractionation are all fixed before the first fraction and none of them is revisited during the course. Each patient therefore carries four workflows per fractionation schedule and eight in total.

**Margin is a property of the arm, not of the block.** An adapted arm carries a reduced-margin plan from the first fraction, generated on the pCT, and a reduced-margin replan on each repeat image thereafter. A non-adapted arm carries the clinical-margin pCT plan for the whole course, with its dose recomputed on each repeat image. This is what the reference study does, where the reduced setup error plans are planning-stage plans and the first block of every adaptive workflow is delivered with them. Robustness therefore contributes no independent factor to the design, which is modality (2) by adaptation (2) by fractionation (2), and the factorial is now the whole design rather than the arm set alone.

**Adapted means adapted at every block.** There is no partial adaptation and no adaptation vector. The design consequence is recorded in the allocator document as A24: the study cannot report whether early or late adaptation carries more benefit, and it cannot report whether a partially adapted course is ever the price-efficient choice. Both were properties of a per-block option set and neither survives.

**The first block carries no modelled anatomical degradation.** Its dose is the nominal planned dose on the planning anatomy, for every arm. The consequence is not symmetric: the reduced-margin arms bank organ sparing over that block at zero modelled coverage risk, so the distortion favours margin reduction, which in the reference study is the larger of the two benefit terms. It scales as one over the number of blocks. Declared as A23 in the allocator document, with a bounding computation recorded as an open decision there.

| **Arm** | **Configuration**                                                                                                         | **Role**                                                                                                                                                                                    |
|---------|---------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| XT-NA   | Photon, no adaptation, clinical margins                                                                                   | Locked baseline. All ΔNTCP values are referred to this arm at the standard schedule                                                                                                         |
| XT-A    | Photon, adapted at every block, margin derived from the adapted uncertainty budget. Consumes the photon adaptation budget | Primary comparator. Tests whether the proton advantage survives when the alternative also improves. Named as future work by the reference study. Rationed, so not every patient receives it |
| PT-NA   | Proton, no adaptation, clinical robustness settings                                                                       | Reproduces the NA-Clinic arm of the reference study                                                                                                                                         |
| PT-A    | Proton, adapted, setup error derived from the adapted uncertainty budget                                                  | Matched counterpart to XT-A. Corresponds to the reference study’s OAPT-2mm                                                                                                                  |

**What dropping the unchanged-margin adaptive arms costs.** Two things, both stated rather than absorbed. The study can no longer decompose the benefit of adaptation from the benefit of the margin reduction it licenses, since the two now travel together by construction; the decomposition is available from the reference study for lung and is not re-derived here. And there is no conservative adaptive plan to fall back on when the coverage screen removes the reduced-margin plan on a block, which makes an empty option set marginally more reachable, as Section 5.10 records.

**Arms and strategies are almost the same object at version 6.** An arm is a plan configuration. A strategy, in the allocator’s sense, is an arm together with a fractionation scheme. Each arm therefore generates exactly two strategies, one per schedule, and each patient’s option set holds eight. Version 5 generated several strategies per arm through the adaptation vector; that multiplicity is gone, and with it the growth of the option set with the number of repeat images.

**Both adapted arms adapt on the same images.** XT-A adapts on the block repeat images, the same rCTs the proton arm uses, because those are the images that exist in the data. The modelled photon adaptation is therefore a per-block surrogate of the online ART workflow, which adapts on daily CBCT or MR; the direction of the net bias on the photon adaptation benefit is not known. Recorded as E14 in the evaluator document. The plan budget below counts plans, not strategies; no additional planning is required to populate the strategy space, since a strategy is a combination of plans already generated.

### 4.2 Matched uncertainty budget across modalities

Introducing an adapted photon arm creates a fairness problem that the reference study did not face. If the adapted proton arm is optimized at a reduced setup error while the adapted photon arm retains clinical margins, part of the measured proton advantage is an artefact of an inconsistent uncertainty budget rather than a property of the modality. The reference study was internally consistent because its photon arm was not adapted, so retaining full margins there was correct. That consistency does not survive the introduction of XT-A.

The photon equivalent of reducing the robust-optimization setup error is reducing the CTV-to-PTV margin. The reference study already performed this translation in one direction, converting the van Herk margin used for the tomotherapy plans into a non-isotropic setup error for robust IMPT optimization, precisely so that the two modalities carried a comparable uncertainty budget. Running the same translation in reverse gives the adapted photon margin.

**Proposal.** Rather than asserting margin values per arm, derive both from a single explicit budget of geometric uncertainty terms, with each term flagged for whether the adaptive workflow removes it.

| **Uncertainty term**                                          | **Type**              | **Removed by online adaptation?** |
|---------------------------------------------------------------|-----------------------|---------------------------------------------------|
| Baseline setup and isocentre localisation                     | Systematic and random | Largely, given daily imaging and correction       |
| Interfractional anatomical change, organ filling, weight loss | Mostly systematic     | Yes. This is what adaptation is for               |
| Delineation uncertainty on the planning image                 | Systematic            | Only if re-contouring is performed and verified   |
| Intrafraction motion, breathing, drift                        | Random                | No                                                |
| Residual isocentre reproducibility                            | Random                | No                                                |

From that budget the photon margin follows from van Herk and the proton setup error follows from the published robustness recipes, so both arms are traceable to the same numbers, and the methods section can show the derivation rather than assert two round figures.

Two properties of the budget are worth stating in advance. The van Herk recipe weights the systematic term at 2.5 and the random term at 0.7. Adaptation acts mainly on the systematic term, which is the heavily weighted one, so the margin reduction that adaptation justifies for photons is proportionally large. This runs against the intuition that photon adaptation is a marginal improvement.

The residual after adaptation is dominated by intrafraction motion, delineation and isocentre reproducibility, and these are largely independent of beam physics. The two modalities therefore converge towards a similar residual geometric uncertainty at the adaptive limit. If that holds, the remaining difference between them is driven by dose distribution physics rather than by uncertainty budget, which is arguably the cleanest available statement of what proton therapy buys.

**Where the symmetry breaks.** Adaptation does not act identically on the two modalities.

- For photons the dominant uncertainty is geometric, and the static dose cloud approximation holds reasonably well, so re-targeting onto the current anatomy captures most of the available benefit.

- For protons, adaptation recovers the geometric component and the interfractional density component of range error, since dose is recomputed on current anatomy. It does not touch the intrinsic CT-to-stopping-power calibration uncertainty, conventionally carried as 3 per cent. That term has no photon analogue and is irreducible by adaptation.

Setup error is therefore a shared parameter that must move together across modalities, while range robustness is a proton-only parameter held fixed across all proton arms. Both facts should be stated explicitly, since a reader will otherwise wonder whether range robustness was reduced as well.

A second asymmetry works in the opposite direction, and it cuts deeper than penumbra width alone. The photon penumbra is broader, so a millimetre of margin reduction removes less normal tissue dose in photons than the equivalent setup error reduction removes in protons. In the limit, the photon equivalent of margin reduction may not exist as a dosimetric benefit at all: even with adaptation, the delivery physics may translate a formally reduced PTV into little or no reduction in organ dose. The margin translation of the matched budget is therefore an equivalence of uncertainty accounting, not a guarantee of equivalent dosimetric payoff, and the size of the photon payoff is one of the empirical questions the symmetric arm set exists to answer. Whether that payoff outweighs the erosion of the baseline is likewise empirical.

**Reporting.** Two differences are reported rather than one.

- ΔNTCP of PT-A against XT-NA, which is directly comparable with the published result and preserves continuity with the reference study.

- ΔNTCP of PT-A against XT-A, which is the honest current-technology comparison and is the quantity that should drive a referral decision.

The gap between them quantifies how much of the published proton advantage is attributable to the photon arm not having been adapted. Since the locked baseline is XT-NA, both quantities fall out of the same computation at no additional cost.

**One qualification follows from rationing photon adaptation.** The second comparison is evaluated for every patient, but XT-A is not delivered to every patient, since the photon budget is finite. The quantity is therefore a per-patient counterfactual, namely what the comparison would be if that patient’s photon treatment were adapted, and it should be reported as such. The allocation outcome, meaning which patients actually hold XT-A, is a separate and equally reportable quantity.

### 4.3 Plan budget

Plan generation is performed in RayStation, which is faster and more reliable than generating plans in OpenTPS for this purpose. The cost is that each plan is a manual act, so the factorial size is bounded by planning effort rather than by computation. Assuming two repeat CTs, an adaptive arm requires one plan on the planning CT plus one replan per repeat CT.

| **Arm** | **Plans per patient per schedule** | **Both schedules** |
|---------|----------------------------------------------------|--------------------|
| XT-NA   | 1                                                  | 2                  |
| XT-A    | 3                                                  | 6                  |
| PT-NA   | 1                                                  | 2                  |
| PT-A    | 3                                                  | 6                  |
| Total   | 8                                                  | 16                 |

For comparison, the reference study used twelve dose distributions per patient across fourteen patients. Sixteen per patient is a comparable load, which is what makes a cohort of similar order feasible. Dropping the unchanged-margin adaptive arms removed six plans per patient, a 43 per cent reduction against the symmetric two-level design, and that saving buys cohort size, which was the binding constraint. Since the cohort must in addition be enriched for cases in which the choice of schedule is genuinely in doubt, the budget should still be confirmed against planning-hour availability before the case matrix is fixed.

**The hypofractionated schedule may not cost two plans per adapted arm.** The table above assumes two repeat images and therefore two replans per adapted arm, which is the standard schedule. If a hypofractionated arm is adapted on in-room imaging with a block equal to a fraction, an adapted arm requires one replan per fraction: on a five-fraction schedule that is six plans per adapted arm, fourteen for the hypofractionated schedule alone and twenty-two per patient over both. The lever is the block granularity of the hypofractionated schedule, which can be set coarser at the cost of modelling less than daily adaptation in a setting where the photon literature reports adaptation in nearly every fraction. This is recorded as open decision 23 in the allocator document and it determines whether the fractionation axis is affordable in planning hours.

**The plan count is linear in the number of blocks and the strategy count does not depend on it at all.** Each block contributes one adapted and one non-adapted plan per arm, so planning cost grows linearly in B, while the option set is fixed at four strategies per schedule whatever B is. At version 5 the strategy count was 2^B and the evaluation cost grew with it; with adaptation reduced to a scalar that growth is gone, and what B still governs is the number of dose fields composed per strategy, which is also linear. This is why the number of repeat CTs is not fixed at two by the design, even though two is expected: it is a data-availability parameter, not a design constraint.

Levers available for reducing the budget, in order of what they cost scientifically:

- Generate hypofractionated plans only for patients labelled as candidates under the trigger rule, rather than for the whole cohort. Under the oracle-selection framing this is not an approximation, because a non-candidate patient never receives that arm. Largest saving, no scientific cost.

- Reduce the number of adaptation points, which is in any case a design parameter that must be stated explicitly rather than left implicit.

- Break the modality symmetry by dropping the adapted photon arm. Listed for completeness only: it would revert the comparator to the reference study’s and forfeit the extension this study exists to make.

### 4.4 No mid-course change of schedule, by design

**What the design does.** A mid-course change of schedule is not evaluated. The hypofractionated course is evaluated as if it had been prescribed from the first fraction, because under the version 6 decision that is what prescription means: the schedule is fixed on the planning CT and is not revisited.

**This is no longer a simplification.** Versions 2 to 5 presented it as a pragmatic concession whose blocking cost was plan generation, since a switch at fraction k requires a plan designed for the remaining fractions at the new dose per fraction, on the anatomy at the switch point, and generating those plans for every candidate k is not affordable. That argument remains true and is now redundant: the design contains no switch to evaluate. The distinction matters for how the limitation is written. It should be stated as a property of the question the study asks, not as a corner cut for cost.

**The asymmetry that motivated the open item is void.** Hypofractionation from the first fraction was proposed as a worst case, and was found to be conservative on NTCP, since it maximises organ EQD2 among all switch times at tumour isoeffect with organ α/β below tumour α/β, while optimistic on capacity, since it releases the most machine time. That tension only arises when the first-fraction case is standing in for a family of switch times. With no switch axis there is nothing for it to stand in for, and item 2 of the open problems register closes. The switch-time question moves to the second publication together with receding-horizon reallocation.

### 4.5 The oracle-selection framing

The framing is now the design rather than a choice among framings, and it extends to the whole strategy tuple. Modality, adaptation and fractionation are decided at prescription, as they are in real clinics. The retrospective observation, such as tumour regression or the degradation visible on a repeat image, is used only to label which patients would have been selected for which workflow, not to design their plan. The question the study answers is: if patient selection were perfect, how much cohort-level benefit would the prescribed workflows deliver under two capacity constraints?

**The oracle is a ceiling and must be reported as one.** The allocation uses information that is not available at prescription time, so the population benefit it reports is an upper bound on what any prospective rule could achieve. This is the same status the reference study’s ideal scenario has, one level up. Stating it plainly is what makes the prospective version, in which the workflow is chosen from planning-time features alone, the natural object of the second publication rather than an afterthought.

Three properties make this attractive. Nothing is approximated, so nothing needs to be argued conservative. It matches how prescription works, since clinics fix the schedule before treatment starts. And it defines a ceiling on what any predictive model developed in WP2 or WP3 could achieve.

The cost is that the switch-time axis disappears from paper 1.

**Note on scope.** The allocator document specifies adaptive fractionation through receding-horizon reallocation, and that section is marked out of scope at version 6. The specification exists so that the formalism does not have to change later, not because the capability is used now. Paper 1 answers which patient receives which workflow; when within a course to act belongs to the second publication, and the right-time framing of the work package belongs there with it. That division should be confirmed at supervision rather than left implicit.

### 4.6 Control arms, if the switch axis is retained

A switch at fraction k bundles two changes: the schedule changes and the plan is re-optimized on updated anatomy. Two control arms are required to separate them, namely adaptation at fraction k without a schedule change, and a schedule change at fraction k without adaptation. Without these the two effects are confounded, and the interaction term cannot be attributed. These arms are required only if item 2 of the open problems register resolves in favour of retaining the switch axis.

### 4.7 Information revelation

If capacity were the only driver, the fractionation decision would belong at planning time, and the study would be a scheduling problem rather than an adaptive one. A mid-course switch is scientifically motivated only if information arrives during treatment that was unavailable at planning. The resulting tension, in which the value of information rises with switch time while the value of acting falls, is the natural successor to the timing axis of the reference study and is also the state definition that WP3 will later require.

Candidate signals are filtered by four criteria: observable before the decision point, predictive of the endpoint, actionable within the remaining fractions, and reconstructible retrospectively from the available cohort. The fourth criterion is decisive and eliminates any signal requiring prospective biological sampling.

| **Candidate signal**                                          | **Retrospectively available** | **Disposition**                                                                                       |
|---------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Accumulated organ biologically effective dose against planned | Yes, once accumulation is implemented         | Primary state variable                                                                                |
| Plan degradation, loss of target coverage                     | Yes, per block, without accumulation          | Primary state variable. Already produced for the admissibility screen, so it costs nothing additional |
| Anatomical drift, organ filling, weight loss                  | Yes                                           | Primary state variable                                                                                |
| Tumor volume regression                                       | Yes                                           | Secondary. Weak predictor in abdomen. Currently the presumed trigger, pending item 12                 |
| Mid-treatment PET or diffusion weighted MRI                   | Only if present in the cohort                 | Stated extension                                                                                      |
| Circulating biomarkers                                        | No                                            | Future work by construction                                                                           |

### 4.8 Can a mid-course change of schedule be evaluated?

This question was raised as an objection to the design and was found to contain three distinct claims with different consequences. Separating them is what identified the actual constraint.

| **Claim**                                                        | **Status**                                    | **Consequence**                                                                                                                                                                                                                                                                                                                                                                                                                                          |
|------------------------------------------------------------------|-----------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| The linear quadratic formalism cannot represent a mixed schedule | Not correct                                   | Biologically effective dose is additive over segments, because the model is multiplicative in survival. No global fraction count is required: the fraction count enters only through the local dose per fraction. A course of ten fractions at one dose followed by five at another has a well-defined biologically effective dose field                                                                                                                 |
| The second segment cannot be computed in practice                | Correct, and it is the binding constraint     | It requires a plan re-optimized on the anatomy at the switch point, plus deformable mapping and accumulation to sum the segments. This is a workflow cost, not a radiobiological obstacle, and it is the reason the pragmatic simplification is attractive. A possible partial escape, uniform rescaling of a reference hypofractionated plan over the remaining fractions at preserved target EQD2, is recorded as item 2 of the open problems register |
| The NTCP model may not admit a fractionation correction          | Correct, and it constrains endpoint selection | The endpoint models used in the reference study are multivariable logistic fits on mean dose plus clinical covariates. They contain no α/β and no fractionation term of any kind and were validated only at conventional fraction size. There is no principled correction available for them                                                                                                                                                             |

**Consequence for the design.** Fractionation can be included as a degree of freedom only if the endpoints are expressed with models that admit an explicit dose-per-fraction correction, meaning gEUD or LKB-type models evaluated on a voxel-wise EQD2 distribution with a declared α/β. Endpoint selection is therefore constrained by fractionation-correctability, and the lung endpoint set of the reference study cannot simply be reused. This is item 3 of the open problems register.

### 4.9 Anatomical site: two candidates

The indication is abdominal. The site is not fixed, and two candidates are carried. Neither is adopted; the purpose of this subsection is to record what each choice would imply, so that the decision can be taken on its consequences rather than on availability alone. The comparison table sits in the allocator document, Section 10.6; what follows is what the choice does to this document.

**Pancreas.** The current guideline recommends, for locally advanced disease, both conventionally fractionated chemoradiation and five-fraction stereotactic treatment, and recommends adaptation for dose-escalated stereotactic delivery. Two consequences. First, A5 gains the anchor it has so far lacked: two schedules recommended for the same clinical setting is exactly the condition on which schedule equivalence by convention rests, and it is now a citable condition rather than an asserted one. Second, a confounder appears that is larger than the one the design was built to control. Conventional treatment includes elective coverage of regions at risk of microscopic disease and stereotactic treatment does not, so a comparison of the two protocol schedules confounds fraction size with target volume. Three responses exist: fix the target volume across schedules and declare the deviation from protocol, which makes the comparison controlled and weakens A5; keep the protocol pair and report target volume and target EQD2 as descriptive rows, which keeps A5 and leaves the confounder in the discussion; or drop the fractionation axis. The first is the cleanest scientifically and the second is the cheapest.

**Adrenal.** There is no guideline pair of the same standing, the setting is oligometastatic rather than curative, and the clinical rationale for a proton arm is weak. The empirical case for adaptation is very strong: a published magnetic-resonance-guided series reports adaptation in essentially every fraction. That strength is double-edged for this study, because a decision with almost no variance is not a decision the allocation can inform, and the contribution would shift entirely onto the pricing side.

**A dilemma common to both.** Adaptation is recommended where the delivered dose is escalated, and escalation is the point at which the two schedules stop being isoeffective on the target. The non-escalated schedule preserves A5 and weakens the clinical rationale for adaptation; the escalated one strengthens the rationale and forfeits A5, which without a TCP model cannot be repaired. The choice must be made explicitly.

**The criterion that should carry the most weight.** Section 4.8 records that fractionation can be included as a degree of freedom only if the endpoints admit an explicit dose-per-fraction correction. That is usually read as a constraint that follows from the site. It runs the other way as well: if the organs driving the endpoint at a candidate site have no model evaluable on voxel-wise EQD2 with a declared α/β, the fractionation axis does not exist at that site. Fractionation-correctability is therefore a criterion for choosing the site, not only a consequence of having chosen it.

## 5. Software architecture

Three modules, specified in their own documents. This section states only what the paper needs to assert.

### 5.1 Module split

| Module    | Role in the paper                                                                                                                                                                                        |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Extractor | Produces per-block physical dose, per-block target metrics, registrations and plan complexity descriptors. Emits dose-derived quantities rather than precomputed NTCP                                    |
| Evaluator | Constructs the strategy space under the margin-adaptation coupling, composes blocks into strategies, converts to EQD2, evaluates NTCP, applies both admissibility screens, hosts the NTCP model registry |
| Allocator | Solves the capacity-constrained allocation and produces the shadow price, the step-ratio threshold and the policy comparison. Never touches a dose grid                                                  |

The dose-metric interface between extraction and evaluation is required for three reasons: NTCP models will be replaced, and precomputed scalars would force re-extraction each time; the parameter propagation of Section 5.9 requires thousands of re-evaluations with perturbed parameters, which a stored scalar cannot support; and NTCP is nonlinear, so the value for a partially adapted course cannot be composed from the adapted and non-adapted values.

The allocator’s independence from dose objects is what makes it developable and unit-testable against synthetic cohorts before data authorisation, which is the reason it was the first component implemented. Its algorithmic layer is complete and tested: the exact solve reproduces the reference study as the two-option special case, the linear relaxation is verified against an independent solver, and the five policies of Section 5.6 run end to end on synthetic cohorts.

### 5.2 Occupancy and the budget

Proton machine time, consumed by the proton arms:

occupancy_PT = n_fx · (τ_0 + Δτ_PT) for PT-A, n_fx · τ_0 for PT-NA

Photon adaptation time, consumed by the adapted photon arm:

occupancy_XT = n_fx · Δτ_XT for XT-A, zero for XT-NA

Occupancy is per course, because adaptation is a course-level property at version 6. This is the reference study’s own accounting recovered exactly; version 5 wrote it per block to accommodate an adaptation vector. The proton arms are charged the whole session, because the proton machine is binding for delivery as well as for adaptation. The photon adapted arm is charged only the increment, because photon delivery is not binding. No photon baseline session length therefore enters the design.

Both budgets are counted over a horizon rather than within a day. Under stationary operation with staggered starts the daily and horizon accountings are the same constraint expressed in different units, and heterogeneous fraction counts across strategies do not break the equivalence. Consequently there is **one shadow price per resource**, each reportable in two units.

**Stated limitation.** A total-minutes budget ignores the constraint that a patient’s fractions fall on consecutive working days, so it is an upper bound on achievable throughput rather than a schedule. The assumption that a patient’s varying session lengths may enter the constraint at their course average is checked by re-solving under a peak-occupancy constraint, which is a genuinely different feasible set; the allocator document specifies this.

### 5.3 The allocation problem

Each patient receives exactly one strategy, subject to a proton capacity constraint and a photon adaptation constraint, maximizing cohort ΔNTCP against the locked baseline. This is a multiple-choice knapsack problem with two resources.

Because no strategy consumes both budgets, each patient’s option set is two chains meeting at the non-adapted photon arm: a photon chain and a proton chain. Non-adapted photon treatment consumes neither budget and is admissible for every patient, so the allocation is always feasible. The model therefore cannot represent a department stressed to the point where a patient receives no treatment, which is the correct behaviour for a referral question and should be stated so that the word capacity does not import the other connotation.

### 5.4 Why ranking by ΔNTCP is not sufficient

The Dutch protocol ranks patients by ΔNTCP and refers those above a threshold. The reference study did the same when choosing which patients to displace to photons. That ranking is optimal only when every candidate consumes the same capacity, which was true there and is false as soon as adaptation and fractionation vary.

The demonstration for the paper is a three-way comparison: the ΔNTCP ranking of current practice, the benefit-density ranking that would be the natural first correction, and the ladder-based allocation that is actually optimal or near-optimal.

**Measured magnitudes temper the claim.** On synthetic cohorts spanning concave to convex adaptation-benefit profiles, the correct heuristic outperformed the naive density ranking in 11 per cent of instances, by 0.16 percentage points of cohort headroom on average; both landed within one per cent of the exact optimum on average. The honest statement is therefore that the naive rule is near-optimal in most regimes, which is a reassuring message for current practice, and that the regimes in which the ranking statistic matters are identifiable in advance through the dominance structure. The cohort values are what the paper reports; if they disagree materially with the synthetic ones, that is itself informative.

The same relaxation yields one multiplier per constraint. λ_PT is the cohort benefit bought by one additional proton machine-minute and is the quantity that inherits the reference study’s interpretation. λ_XT is the cohort benefit bought by one additional minute of photon adaptation capability, and no comparable quantity exists in the reference literature as far as is currently known. No threshold is supplied as an input: it is induced by the allocation rather than imposed on it. This gives the ΔNTCP referral threshold of the Dutch protocol a facility-specific interpretation, and it answers whether a workflow change costing additional minutes per fraction is worthwhile without enumerating scenarios.

**λ_XT is reported as a curve.** Its magnitude depends on the photon adaptation budget, which has no measured anchor for this indication, so reporting a single value would report an assumed number. The budget is swept instead. The two limits are interpretable: at zero budget the comparator reduces to the reference study’s non-adapted photon arm, and at a budget exceeding cohort demand every displaced patient receives adapted photons. The ratio λ_XT / λ_PT across the sweep states where the next unit of investment buys more, which is a departmental result rather than a per-patient one.

**One methodological consequence is recorded rather than resolved.** A benefit density is not defined when an upgrade may consume either of two budgets, so the ranking statistic used by the heuristic policies of Section 5.6 requires a stated convention. The allocator document records the options; the choice changes what those policies represent and is not yet made.

### 5.5 Scalar endpoint for the allocation decision

The reference study reported three NTCPs separately but needed a scalar to decide which patients to displace and used the probability of at least one complication. The same convention is adopted, and severity weighting is not applied: a composite for the decision, individual endpoints for reporting.

NTCP_total = 1 − Π_k (1 − NTCP_k)

The independence assumption is false, since toxicities in a shared anatomical region are correlated, and the composite therefore overestimates the probability of at least one event. The direction of that bias is stated in one sentence in the manuscript rather than left implicit.

### 5.6 Compare policies rather than reporting a single optimum

An optimum on its own is not a clinically useful output, because no clinic implements an integer program. The informative output is the gap between what simple rules achieve and what is achievable at all.

| **Policy** | **Definition**                                                                         | **What it represents**                                                                        |
|------------|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P0         | Threshold-based referral, fixed standard schedule, no adaptation                       | Current practice. The locked baseline                                                         |
| P1         | Threshold-based referral, adaptation for all proton patients, fixed schedule           | Essentially the reference study                                                               |
| P1x        | As P1, then photon adaptation in decreasing ΔNTCP until the photon budget is exhausted | Isolates the value of the adapted photon arm’s existence from the value of optimising over it |
| P2a        | Greedy by benefit density over patients                                                | The natural but generally suboptimal capacity-aware rule                                      |
| P2b        | Greedy by best available upgrade over Pareto-reduced ladders                           | The correct heuristic                                                                         |
| P3         | Exact multiple-choice knapsack optimum                                                 | Upper bound on what any allocation could achieve                                              |

Under two resources, the heuristics rank proton upgrades only and the photon budget is spent by a separate rule, adapting photon patients in decreasing ΔNTCP until it is exhausted; the reasons are recorded in the allocator document at Section 5.3. All conventions coincide at zero photon budget, so the version 4 behaviour is recovered by construction.

Report cohort ΔNTCP for each policy as a function of adaptation time. P3 minus P0 is the total headroom, P2b minus P0 is what a correct implementable rule captures, P3 minus P2b indicates whether exact optimization is worth anything at all, P2b minus P2a is the methodological result of Section 5.4, and P3 minus P1x separates the gain of optimising the allocation from the gain of the adapted photon arm merely existing, which P3 minus P1 confounds. If P2b recovers most of P3, that is a useful clinical message and also the natural performance baseline against which a WP3 agent would later have to justify itself.

**The policy comparison is a secondary output.** The primary result of the study is the parametric behaviour of the optimal allocation itself under the two constraints; the policies read that result against implementable rules. Section 5.12 records the provisional ordering.

### 5.7 Two-dimensional adaptation-time output

The central result of the reference study was a threshold in adaptation time. That structure is preserved and extended at three levels.

With adaptation available on both modalities there are two adaptation times, one per modality, and the natural output is a contour of cohort ΔNTCP over the (Δτ_PT, Δτ_XT) plane, with the iso-benefit line separating the region in which adaptive proton therapy remains worthwhile from the region in which it does not. The symmetric arm set of Section 4.1 is what makes the two axes commensurable.

Beneath that surface sits the step-ratio threshold of the allocator document, which partitions the proton axis into the regime where per-block adaptation allocation carries value and the regime where the problem collapses to the reference structure.

The third level is the photon adaptation budget, which is a parameter rather than an axis of the plane. Sweeping it produces λ_XT as a curve and moves the step-ratio threshold, since a larger budget puts more patients on the stronger comparator and shrinks their modality step. The sweep is one computation and yields both.

**The plane is evaluated at a reference budget.** A single reference value C_XT^ref, to be fixed with the clinical partners and the supervisor, plays for the photon budget the role the 480 minutes play for the proton budget in the reference study. The (Δτ_PT, Δτ_XT) plane is computed there; the budget sweep is reported on a normalised axis, fraction of cohort photon adaptation demand, with minutes secondary, so that its endpoints are the reference study’s comparator and the free case by construction.

### 5.8 Small cohort, and decoupling the cohort from the clinic

The cohort is expected to be smaller than the reference study, because it must be enriched for cases in which the choice of schedule is genuinely in doubt. This creates a specific problem: the output of a capacity model is a step function in the number of patients, so with eight patients each individual is one eighth of the cohort mean, the ΔNTCP curves become jagged, and any threshold extracted from them reflects cohort granularity as much as physics.

**Proposed handling.** Stop treating the cohort as the clinic. Use the cohort to estimate the joint distribution of benefit and occupancy per patient per strategy, resample from it to construct synthetic clinic populations of realistic size, and run the allocator on those. The reported output is then a threshold with a confidence interval rather than a single jagged curve.

**Assumption incurred.** That the cohort is representative of the referral stream. This is questionable precisely because the cohort is deliberately enriched for borderline cases, so the synthetic population must be described as a borderline-enriched population and interpreted accordingly. The enrichment has a second, positive role: the step-ratio threshold is patient-wise, so a borderline-enriched cohort is exactly the population in which ladders of both shapes coexist and the heterogeneous cohort is observable.

### 5.9 Propagating NTCP parameter uncertainty through the decision

NTCP model support in abdomen and pelvis is thin. There is no equivalent of the Dutch protocol model set for these sites, and the parameters currently in use, rectum from QUANTEC and a labelled placeholder for bowel, are of uneven quality. The proposed handling converts the vulnerability into a result: sample the NTCP model parameters from their published confidence intervals, propagate each sample through the allocator, and report the fraction of samples in which the allocation itself changes. This measures decision robustness rather than dose robustness, which is the quantity that actually matters for a referral rule, and no comparable analysis exists in the reference literature as far as is currently known.

The evaluator caches the reduced dose at the dose volume histogram rather than at the gEUD scalar, so that the volume parameter can be perturbed without recomputing the accumulated dose. This makes the propagation computationally free. Perturbing α/β is structurally more expensive, since it enters before the accumulation, and it is therefore treated as a separate sensitivity axis rather than propagated in bulk.

### 5.10 Admissibility

ΔNTCP ranks strategies on organ dose alone and carries no information about the target. Two screens are applied before allocation, and both remove strategies from the option set rather than ranking them with degraded benefit.

**Target coverage, judged per block.** A plan delivered on a changed anatomy can lose target coverage, and if the target has moved away from the driving organ at risk it can lose coverage while its NTCP improves, so a ranking on ΔNTCP alone would prefer the arm that undertreats the tumor. Coverage is a property of a plan delivered on a given anatomy, so the criterion is applied to each block’s plan on its own image and not to the accumulated dose. The accumulated form is permissive in the wrong direction, since a block delivered with unacceptable coverage can be offset by later blocks. The screen is applied symmetrically to the photon arms, which are recomputed on the repeat images rather than represented by planned dose; screening protons while exempting photons would bias the measured proton advantage downwards. The worst-case variant, also per block, is retained as a sensitivity analysis, and the number of strategies removed under each criterion is reported. The criterion is V95% below 95 per cent, with the possibility of further criteria added later, so the screen takes a list of criteria of which all must pass. With a single adaptive margin level there is no conservative adaptive plan to fall back on when the reduced-margin plan fails a block, so an empty option set is marginally more reachable than it would otherwise be. The response remains an error rather than a fallback, since with clinical plans in a retrospective study an empty set indicates a misconfigured criterion rather than an untreatable patient.

**No harm, reported rather than enforced.** A strategy whose union ΔNTCP against the locked baseline is negative is counted and reported, not removed. Earlier versions removed it, on the reasoning that maximising a cohort mean must not make any individual worse than current standard care. That requirement stands; removal is not what delivers it. The count is computed on the union scalar rather than per endpoint, consistent with the selection rule, and per-endpoint sign violations are counted separately.

**What actually protects the individual.** The screen is not what does the work, and the manuscript should not claim that it is. The allocator imposes no constraint on the sign of ΔNTCP anywhere. Protection comes from the structure of the option set: XT-NA costs nothing on either budget and has ΔNTCP identically zero, so it dominates every strategy of negative benefit, and substituting it both raises the objective and frees capacity. No optimal allocation contains a harmful strategy, whether or not harmful strategies are present in the option set, so removing them changes nothing wherever that structure holds. Where it does not hold, removal deletes deliverable options from a patient who has no free arm to fall back on, which is why the screen was converted to a diagnostic.

The structure does not hold everywhere. The coverage screen applies symmetrically to the photon arms, so it can remove XT-NA for an individual patient, in which case that patient has no free arm to fall back on and an optimal allocation may assign them a strategy worse than the reference. XT-NA remains the reference for their ΔNTCP either way, so the zero point of the decomposition does not move. Three counts are therefore reported with every allocation: strategies removed by the screens, assignable strategies whose ΔNTCP is not positive, and patients with no free assignable option. The last of these is what licenses the claim that no patient was made worse off, and where it is zero the claim is a property of the formulation rather than a result, and must be written as such.

Removing a strategy does not force a modality switch. Adaptation exists to restore coverage, so the surviving options are typically the adapted proton arm and the photon arms, and the allocation decides between them on cost. The effect is to raise the price of keeping that patient on protons, which may move them to photons at the margin, and that is an outcome of the optimization rather than a forced switch.

### 5.11 Photon adaptation as capacity relief

A stronger adapted photon arm reduces the number of patients whose ΔNTCP justifies a proton slot, which means photon adaptation functions as a capacity-relief mechanism for the proton facility rather than only as a tougher comparator. The allocation module quantifies this directly, since the number of proton slots released per unit of photon adaptation capability is an output of the same optimization that produces the cohort mean. This framing does not appear in the reference literature as far as is currently known, and it is the clearest argument for having the adapted photon arm in the design rather than naming it as future work.

With photon adaptation rationed, the relief is not a single number. It is the exchange rate between the two budgets, measured as the proton minutes released per photon adaptation minute purchased, and in price terms it is governed by the ratio λ_XT / λ_PT. It is read off the same budget sweep that produces λ_XT. The version 4 treatment, in which photon adaptation was free and the relief was an upper bound, is the limiting case of that sweep as the budget grows without bound, and it should be reported as the limit rather than as the estimate. The interior of the sweep is what a centre would obtain, conditional on the assumed extra time per adapted photon fraction.

### 5.12 Candidate outputs, in order of relevance (provisional)

The ordering below is provisional and will be revisited once real cases are in hand, since the relative interest of the outputs depends on what the data show. It exists now for a structural reason: the sweep and reporting machinery must be able to produce every entry without deciding internally which one is the result, so the hierarchy is a property of the manuscript, not of the code.

| Rank | Output                                                                                                                                                                                                                                                       | Nature                     |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------|
| 1    | The parametric allocation study: how the optimal assignment of the cohort moves across the (Δτ_PT, Δτ_XT) plane at C_XT^ref, with the iso-benefit line, and along the normalised photon budget axis. Composition by arm and by schedule, and cohort ΔNTCP | Primary                    |
| 2    | The two shadow prices: λ_PT at the reference configuration, λ_XT as a curve over the normalised budget, and their ratio as the departmental investment signal                                                                                                | Primary, derived from 1    |
| 3    | The step-ratio regime boundary Δτ\*(C_XT): where the non-adapted proton arm carries value at all                                                                                                                                                                   | Structural, derived from 1 |
| 4    | Policy gaps: P3 − P0, P2b − P0, P3 − P2b, P2b − P2a, P3 − P1x                                                                                                                                                                                                | Secondary                  |
| 5    | Per-endpoint ΔNTCP decomposition against the locked baseline, and the per-patient PT-A versus XT-A counterfactual                                                                                                                                            | Secondary, reporting       |
| 6    | Robustness of the conclusions: Monte Carlo parameter propagation at the decision level, peak-occupancy re-solve of A2, α/β sensitivity                                                                                                                       | Supporting                 |
| 7    | Option-set diagnostics: strategies removed per screen, assignable strategies of non-positive ΔNTCP, and patients with no free assignable option                                                                                                              | Supporting, reporting      |

The rule of use: entries 1 to 3 come from one computation and constitute the finding; entries 4 and 5 read the finding against practice; entries 6 and 7 defend it. Entry 7 is a table rather than a figure and belongs with the methods, since it describes what the allocator was given rather than what it produced. A figure that does not serve one of the first six does not enter the manuscript.

## 6. Dose accumulation and biological conversion

The governing expressions are as follows. Biologically effective dose accumulates over segments, with the local dose per fraction obtained from the segment total and its fraction count:

BED_b(x) = n_b · d_b(x) · (1 + d_b(x)/(α/β)), with d_b(x) = D_b(x)/n_b

EQD2(x) = BED_total(x) / (1 + 2/(α/β))

The isoeffect solver, used if a second segment must be prescribed to match a target biologically effective dose deficit over n_2 remaining fractions, follows from inverting the same expression:

d_2 = ((α/β)\_T / 2) · (√(1 + 4·dBED_T/(n_2·(α/β)\_T)) − 1)

The conversion is voxel-wise and must precede any dose volume histogram reduction, since the generalised equivalent uniform dose does not commute with the EQD2 transform.

**Ordering with respect to deformation.** Conversion also precedes deformation. The transform is convex in dose, so interpolating physical dose and converting afterwards underestimates systematically, with the error concentrated in the high-gradient region. For a serial-like organ with a small volume parameter the gEUD draws its weight from precisely that region, so the error does not average out. The adopted sequence is therefore: compute the biologically effective dose field per block on its own geometry, deform, sum over blocks, convert the total to EQD2 once. Summation after deformation is exact because biologically effective dose is additive over segments.

The cost is that the deformed field is not unique, since it depends on the fractionation scheme and on the structure’s α/β. These are repeated applications of a cached deformation field rather than repeated registrations, so the dominant cost is unchanged. The alternative ordering is computed once on a real case and the difference in gEUD reported in the methods, which converts an assumption into a measurement.

## 7. Where the conclusion could be conditional

Any comparison between fraction sizes routes through the linear quadratic conversion, which is governed by α/β. That parameter is weakly constrained by the data underlying conventionally fractionated dose response models. It follows that the strength of the conclusion depends on the endpoint chosen, and in the worst case a result could reflect a parameter choice as much as a workflow finding.

What remains in place against this exposure: an α/β sensitivity analysis within the cohort phase, reported alongside the main result; endpoint selection constrained to models that admit a fractionation correction; cross-checking of organ tolerance at large fraction size against the hypofractionated-era literature; and the Monte Carlo parameter propagation, which addresses the same exposure at the level of the decision rather than the dose.

**Residual exposure.** If the sensitivity analysis shows that the spread from α/β exceeds the spread from workflow variation, the manuscript reports a conclusion conditional on that parameter and states what evidence would resolve it. This is a weaker headline but remains an honest and citable contribution. The decision-robustness result partially insulates the paper against this outcome, since a demonstration that the allocation is stable under parameter uncertainty is informative even when the absolute NTCP values are not.

## Appendix F. The fractionation dimension: consolidated summary

Collected here so that the fractionation design can be revised as a block. The material is not removed from the sections that own it; this appendix is a digest with pointers. This is the single copy: F.1 to F.5 cover the study level and F.6 to F.8 the module level. The module documents point here.

Rewritten at version 6. Statements that referred to an adaptation vector, to a schedule space of size 2^B or to a collapse to B + 1 options have been restated rather than annotated, so that no cell of this appendix has to be mentally corrected while it is read.

### F.1 What the fractionation axis is for

| Aspect | Where | Statement |
| --- | --- | --- |
| Central hypothesis | Road 1, 3.4 | Adaptation and fractionation are not additive. Adaptation could be what makes hypofractionation robust enough to be clinically worthwhile |
| What changes when fractionation is released | Road 3.1 | The resource consumed by a patient becomes machine time per course rather than per fraction, so capacity must be counted over a horizon |
| Where freed capacity goes | Road 3.1, 5.2 | In a closed cohort, only two destinations: moving a patient from the non-adapted to the adapted arm, or moving a patient from photons to protons. The second is the reference study's displacement mechanism in reverse, and it exists only because a photon option sits in the option set at zero proton cost |
| Two channels | Road 3.2 | Hypofractionation improves cohort composition through capacity and plausibly degrades per-patient NTCP through fraction size. The opposition of the two is the reason for studying the levers jointly |
| Four competing effects | Road 3.3 | Capacity positive; radiobiology at isoeffective prescription likely negative; robustness mixed; adaptation economics positive |
| Site dependence | Road 3.5, allocator 10.6, road 4.9 | The effect is governed by the volume parameter of the dose response. Serial-like organs are fractionation sensitive and weakly proton favourable; parallel organs the reverse. The site is a design input and is not yet fixed |

### F.2 Design decisions on the axis

| Decision | Where | Statement |
| --- | --- | --- |
| Schedule equivalence | Road 3.6, 4.1 | Clinical equivalence by convention, restricted to protocol-sanctioned schedules. Confirmed available. Isoeffectiveness is asserted by clinical consensus, not derived from a linear quadratic calculation |
| Safeguard | Road 3.6 | Target EQD2 per arm reported as a descriptive row at a declared tumour α/β, produced by the evaluator as a first-class output rather than computed at figure time |
| Plan budget | Road 4.3 | Each arm planned under both schedules: 8 plans per patient per schedule, 16 over both, on the assumption of two repeat images per schedule. If the hypofractionated schedule is adapted per fraction the hypofractionated half rises to 14 and the total to 22. The granularity is open decision 23 |
| No mid-course change of schedule | Road 4.4 | Not a simplification at version 6 but a property of the design: the schedule is fixed at prescription and is not revisited, so there is no switch to evaluate |
| Oracle framing | Road 4.5 | Modality, adaptation and fractionation all decided at prescription; retrospective observation used only to label which patients would have been selected. The reported benefit is a ceiling on what any prospective rule could achieve |
| Adaptive fractionation | Road 4.5, allocator 10.5 | Out of scope for paper 1. The receding-horizon specification is retained so the formalism need not change later, and moves to the reinforcement learning publication |
| Control arms | Road 4.6 | Required only if the switch axis is retained. It is not, so they are not required |

### F.3 Known weaknesses on the axis

These are the items most likely to attract reviewer attention and are the reason the axis is expected to keep moving.

- **Endpoint selection is constrained by fractionation-correctability and is unresolved.** Multivariable logistic fits on mean dose plus covariates, as used in the reference study, contain no α/β term and admit no principled correction. Only gEUD or LKB-type models evaluated on a voxel-wise EQD2 distribution at a declared α/β can carry the axis. Road 4.8, allocator open decision 10. This blocks everything downstream on the axis, and at version 6 it is itself downstream of the site, open decision 19.

- **α/β is weakly constrained and the conclusion may be conditional on it.** Road 7 states the exposure and the four defences: an α/β sensitivity analysis, constrained endpoint selection, cross-checking against the hypofractionated-era literature, and the Monte Carlo parameter propagation that addresses the exposure at the level of the decision rather than the dose.

- **The threshold is a within-scheme statement.** Each scheme carries its own (τ_0, a, m, x) and therefore its own Δτ\*. Competition between schemes, in which the biological penalty of larger fractions trades against the capacity they free, is resolved by the allocator and not by any closed form.

- **The two cost distortions run in opposite directions and do not cancel.** The per-fraction charge of A16 and A19 overstates the replanning effort by the number of fractions per block, which biases in favour of hypofractionation; the first-block convention of A23 banks organ sparing at zero modelled coverage risk over a block whose weight is one over the number of blocks, which biases in favour of margin reduction and therefore more strongly for the standard schedule. Allocator 9 and 4. Open decisions 20 and 21 record the bounding computations.

- **A free hypofractionated photon arm enters the population mean at zero capacity cost.** XT-NA is free on both budgets under either schedule, so if its hypofractionated variant carries positive utility it is selected without consuming anything, and that component of the population benefit is not a result about capacity. Allocator A27 and open decision 18. Whether the case arises at all depends on the sign of the utility, which is organ-dependent and cannot be predicted before the site and the endpoints are fixed.

*Item retired at version 6.* The asymmetry of hypofractionation from the first fraction, conservative on NTCP and optimistic on capacity, was a weakness only while that case stood in for a family of switch times. With no switch axis it stands in for nothing, and item 2 of the open problems register closes. Road 4.4.

### F.4 Interaction with the second resource

Both occupancies scale with the fraction count, so a scheme that shortens the course reduces demand on the proton budget and on the photon adaptation budget alike. No additional machinery is required. The one point worth stating is that the photon adaptation budget gives hypofractionation a second destination for freed capacity on the photon side, which did not exist in version 4 because photon adaptation was free.

### F.5 What would change if the schedule set changes

Nothing structural. Schedules enter as additional members of the strategy tuple, and the constraints and the multipliers are indifferent to how many there are. What scales is the plan budget, linear in the number of schedules, and the number of warped BED fields the evaluator caches, also linear.

### F.6 Consequences in the allocator

Pointers in the *Where* column are to sections and assumptions of the allocator document.

**What fractionation is, in that document.** A component of the strategy tuple, alongside modality and adaptation. The MCKP absorbs it without modification. Its consequences are in what it does to u and τ.

| Aspect | Where | Statement |
| --- | --- | --- |
| Position in the strategy tuple | 4 | s = (modality, adaptation, fractionation, technique). Robustness is determined by the arm, so each (modality, fractionation) group holds two options and each patient holds eight |
| Capacity accounting | 10.1, 10.2 | Cost is total occupancy over the course, not per day. Under stationary operation with staggered starts the daily and horizon constraints are the same statement, so heterogeneous fraction counts do not break the equivalence |
| Where freed capacity goes | 10.1 | In a closed cohort, only two destinations: moving a patient from the non-adapted to the adapted arm, or moving a patient from photons to protons. The second exists only because a photon option sits in the option set at zero proton cost |
| Mean-field assumption | 10.3, A2 | Course-averaged occupancy, checked by a peak-occupancy re-solve rather than by simulation |
| Schedule equivalence | 10.4, A5 | Restricted to protocol-sanctioned schedules. Equivalence rests on clinical consensus, not on a linear quadratic conversion of the tumour prescription. Tumour α/β is not required; OAR α/β is |
| Repopulation | 10.4, A6 | Neglected, consistent with modelling no TCP. Lengthened schedules are not penalised |
| Adaptive fractionation | 10.5 | Out of scope for paper 1. The receding-horizon specification is retained and moves to the second publication |
| Relation to the step-ratio threshold | 6.5 | Δτ\* = τ_0 · (a / m) at zero photon outside option, the version 4 and version 5 form evaluated at B = 1. It is a **within-scheme** statement: each scheme carries its own (τ_0, a, m, x) and therefore its own threshold. Competition between schemes is resolved by the allocator, not by the closed form |
| Site | 10.6, A26 | Two candidates carried, pancreas and adrenal. Fractionation-correctability of the endpoint models at a candidate site is a criterion for choosing it, not only a consequence of having chosen it |

**Interaction with the second resource.** The photon adaptation cost n_fx · Δτ_XT scales with the fraction count in the same way the proton cost does, so a scheme that shortens the course reduces demand on both budgets. This is handled by the formulation without additional machinery.

**What would change if the schedule set changes.** Nothing structural. The candidate schedules enter as additional members of the strategy tuple, and the constraint and the multipliers are indifferent to how many there are. What changes is the plan budget, which is linear in the number of schedules, and the number of warped BED fields the evaluator must cache, which is also linear.

**Open items touching fractionation.** Open decision 19, the anatomical site, sits upstream of everything else on the axis. Open decision 10, endpoint selection constrained to models admitting a dose-per-fraction correction, blocks the axis and is itself gated on 19. Open decisions 18, 20, 21 and 23 each touch the axis without blocking it.

### F.7 Consequences in the evaluator

Pointers in the *Where* column are to sections and assumption identifiers of the evaluator document.

**What fractionation is, in that document.** The quantity that fixes the dose per fraction, and therefore the only reason the conversion to biologically effective dose cannot be performed upstream and stored.

| Aspect | Where | Statement |
| --- | --- | --- |
| Why the evaluator exists at all | 1.1 | Conversion to EQD2 depends on the fractionation scheme, which is a decision variable, so conversion must happen at composition time and its result must not be stored. Locating it in the extractor would freeze one schedule in the data |
| Conversion | 4.1 | BED_b(x) = n_b · d_b(x) · (1 + d_b(x)/(α/β)) with d_b(x) = D_b(x)/n_b, then EQD2(x) = BED_total(x) / (1 + 2/(α/β)) |
| Ordering | 4.1, 4.2, E1, E2 | Convert per block on native geometry, deform, sum over blocks, convert the total once. BED is additive over segments, so summation after deformation is exact. Converting after interpolation underestimates systematically, and the error concentrates where a small volume parameter draws its weight |
| Cost of the ordering | 4.3 | The deformed field is not unique: one per (block, scheme, α/β). With two schemes and two α/β values this is four warped fields per block per arm. These are applications of a cached deformation field, not registrations |
| Cache invalidation | 7.1 | Warped BED is keyed by (block, scheme, α/β) and invalidated by any of them. α/β sits outside the cache boundary, so a sensitivity analysis on it requires recomposition rather than re-evaluation |
| Target EQD2 | 9 | A first-class output at a declared tumour α/β, reported per arm for completeness rather than to assert equivalence, since schedule equivalence rests on clinical consensus |
| Model validity | E8 | The linear quadratic model is assumed valid for OAR EQD2 conversion over the fraction sizes considered. To be checked against real cases. Applies to OARs only, not to any tumour claim |
| Registry constraint | 8 | Each model declares its α/β, and the union of declared α/β values sizes the composition workload. Models with no α/β term cannot be fractionation-corrected, which constrains endpoint selection upstream |

**Interaction with the second resource.** Both occupancies scale with the fraction count, tau_pt through the full session and tau_xt through the adaptation increment. The evaluator emits both per fraction together with the fraction count, so a change of scheme changes the emitted fraction count and the allocator applies it to both budgets. No additional machinery is required here.

**What would change if the schedule set changes.** The number of warped BED fields per block, linear in the number of schemes. Nothing else in the evaluator is sensitive to how many schedules exist.

**Open item touching fractionation.** Endpoint selection is constrained to models admitting an explicit dose-per-fraction correction, meaning gEUD or LKB-type models evaluated on a voxel-wise EQD2 distribution at a declared α/β. Multivariable logistic fits on mean dose plus covariates, as used in the reference study, contain no α/β term and admit no principled correction. This is unresolved and blocks the fractionation axis.

### F.8 Consequences in the extractor

Pointers in the *Where* column are to sections of the extractor document unless stated otherwise.

**What fractionation is, in that document.** A label on a plan, and the reason two storage rules take the form they do.

| Aspect | Where | Statement |
| --- | --- | --- |
| Storage rule | 3 | Store physical dose per block on native geometry. Do not store EQD2: it depends on dose per fraction, and fractionation is a decision variable, so storing it would fix one schedule in the data and silently invalidate every alternative |
| Second storage rule | 3 | Do not store warped dose either. The warped object is a BED field, which depends on both the scheme and the structure's α/β, so it is a derived product belonging to the evaluator's cache |
| What is stored instead | 3 | Physical dose per block on its own image, the fraction count, and the deformation fields. Everything downstream is recomputable |
| Schema field | 10 | `fx_scheme` records (n, d) and the protocol identifier, per (patient, block, plan) |
| Workload sizing | 8 | The union of distinct α/β values in the registry determines how many warped fields per block the evaluator will require, and the extractor reports that union so the estimate exists before the pipeline runs |
| Plan budget | Road 4.3, extractor 15 | Each arm is planned under both schedules, so the plan count is linear in the number of schedules. If the hypofractionated schedule is adapted per fraction, an adapted arm requires six plans rather than three. This is the binding cost of the fractionation axis and it is not an extraction cost |

**Interaction with the second resource.** None at the extractor. The photon adaptation budget is charged an increment that the study sweeps, so no additional per-plan quantity is extracted for it under either fractionation scheme.

**What would change if the schedule set changes.** The number of plans per patient, linear in the number of schedules, and therefore the ingest and registration workload. No schema change and no new field.

Sections 8 to 11: version history, moved to `CHANGELOG.md`.

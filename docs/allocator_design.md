# Capacity and Allocation Module

Version 6.4. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

This document specifies the design of the **allocator**, which assigns treatment strategies to patients under a machine capacity constraint.

Two companion documents specify the components it depends on. The **extractor** gathers per-patient, per-plan and per-facility quantities. The **evaluator** composes block-level dose into per-strategy accumulated dose, evaluates NTCP, and applies the admissibility screens. The allocator consumes utilities, occupancies and admissibility flags, and never touches a dose grid.

The allocator answers two of the three questions that “capacity and allocation” can denote:

- **Strategy assignment.** Given a cohort and a capacity, which patient receives which strategy?

- **Capacity design.** What is a machine-minute worth, in outcome units, at a given load? Two resources are priced, proton machine time and photon adaptation time, so this question has two answers.

The third question, **scheduling** (which fraction occupies which slot on which day), is deliberately out of scope for now.

## 2. Relation to the reference study

Borderías-Villarroel et al. quantifies how the extra time per fraction required by online adaptive proton therapy (OAPT) erodes the NTCP benefit of protons, because a capacity-limited center can treat fewer patients when sessions lengthen. Their method:

- A cohort of 14 lung patients, one XT plan and three IMPT plans per patient (clinical robustness, 4 mm and 2 mm setup error), with adaptation simulated on two repeat CTs and dose accumulated on the planning CT;

- A single-room center with 480 min/day and a baseline of 14 patients, giving 34.2 min per fraction;

- Seven scenarios indexed by the extra time per adapted fraction, from instantaneous to +25.7 min. In scenario Si, i patients are displaced to photons;

- Displaced patients are chosen as those with the lowest ΔNTCP over the union of the three modeled complications;

- The outcome is the cohort-mean ΔNTCP per endpoint against a non-adaptive XT reference.

**What to keep.** The cohort-level ΔNTCP currency; the XT non-adaptive reference; the coupling between adaptation time and machine capacity; the accumulated-dose basis for NTCP; the treatment of the extra time per adapted fraction as the independent variable of the study.

**What we change.** Three structural rigidities in their formulation limit what it can express:

- **R1.** One workflow is applied to the entire selected subset. The cohort cannot contain both adapted and non-adapted proton patients simultaneously.

- **R2.** Adaptation is all-or-nothing over the whole course. A patient is either adapted at every opportunity or at none.

- **R3.** Time cost per patient is uniform, so ranking by ΔNTCP is optimal within their assumptions but not in general.

Relaxing R1 and R2 is the substantive contribution of the allocator. Relaxing R3 follows from the formulation. Whether the relaxation of R2 carries value is itself governed by a threshold in adaptation time, derived in Section 6.5; this is a result rather than an embarrassment, and it is the same kind of result the reference study reports one level down.

**R4.** The photon comparator is non-adapted and costs nothing. The formulation cannot express a centre that can adapt some photon patients but not all, which is the situation any real department faces.

Relaxing R4 is what introduces the second resource. The photon arm is split into a non-adapted arm that consumes nothing and an adapted arm that consumes a rationed photon adaptation budget, so that photon patients compete for adaptation on the same logic as proton patients compete for machine time.

A fifth difference concerns plan admissibility. Suppose anatomical change brings target coverage below the acceptance criterion in the non-adapted arm. Any ranking based only on NTCP is then unphysical, since that plan could never be delivered in a real clinic.

**Adaptation model.** As in the reference study, the workflow being simulated is on-couch adaptation. The clinical model is that adaptation lengthens the treatment session and therefore consumes machine capacity.

## 3. Related work and positioning

Three largely disjoint literatures bear on this problem.

**Model-based selection.** The Dutch national indication protocols select patients by comparing photon and proton NTCP profiles against **fixed** per-endpoint ΔNTCP thresholds. This is a per-patient rule with no capacity term, and the thresholds are set by national policy rather than derived from a facility’s load. We adopt the NTCP-comparison logic but not the fixed threshold.

**Capacity-aware allocation.** Loizeau et al. allocate proton *fractions* rather than patients, exploiting the nonlinearity of NTCP so that early proton fractions carry more benefit than later ones. Papp and Unkelbach make selection dynamic under stochastic arrivals and derive facility-state-dependent ΔNTCP thresholds. In each, a proton slot is a fixed, homogeneous unit; its *duration* is not a decision variable.

**Throughput and workflow timing.** Session and delivery times are measurable and patient-dependent. Spot-scanning delivery time increases with total target volume and accounts for roughly 30 to 40 per cent of total treatment time for targets above 200 cm³. Clinical daily adaptive proton therapy at PSI averaged about 23 min per session (range 15 to 30), of which adaptation including QA and plan assessment averaged just under 7. McComas et al. reported roughly 16 additional minutes per adaptive pelvic photon fraction. No clinical on-couch adaptive proton workflow exists for the abdomen, so no measured value of the extra time per adapted fraction is available for the site of this study; the quantity is treated as the independent variable throughout.

**Robustness and adaptation rate.** Badiu et al. established that increased plan robustness reduces the adaptation rate at the cost of higher OAR dose. This is the mechanism that makes robustness setting a genuine decision variable rather than a fixed parameter.

## 4. Notation and definitions

| Symbol  | Meaning                                                                                |
|---------|----------------------------------------------------------------------------------------|
| p       | patient index, p = 1, …, P                                                             |
| s       | strategy index, s ∈ Sp                                                                 |
| k       | toxicity endpoint index                                                                |
| u_ps    | utility of strategy s for patient p                                                    |
| τ^PT_ps | proton machine occupancy per fraction, minutes. Zero for photon strategies             |
| τ^XT_ps | photon adaptation time per fraction, minutes. Zero for proton strategies and for XT-NA |
| Δτ_PT   | extra proton machine time per adapted fraction, minutes                                |
| Δτ_XT   | extra photon linac time per adapted fraction, minutes                                  |
| n_ps    | number of fractions                                                                    |
| C_PT    | available proton machine minutes                                                       |
| C_XT    | available photon adaptation minutes                                                    |
| x_ps    | binary decision, 1 if patient p receives strategy s                                    |
| λ_PT    | shadow price of proton machine capacity, in utility per minute                         |
| λ_XT    | shadow price of photon adaptation capacity, in utility per minute                      |

A **strategy** is the tuple:

s = (modality, adaptation, fractionation, technique)

with the parameter technique that could be used in the future to extend (VMAT, IMRT, ARC, …).

**Block.** The interval of a course over which one plan is delivered, delimited by the images available: the pCT for the first block and each repeat image thereafter. With two repeat images a standard course has three blocks. The number of blocks B is a property of the imaging available under a schedule, not a decision variable, and its value for the hypofractionated schedule is open decision 23. B governs the extractor, the evaluator and the plan budget; at version 6 it does not govern the allocator.

**Adaptation is a course-level property, not a per-block one.** Following the supervisory decision of version 6, the workflow is chosen once, on the planning CT, and holds for the whole course. An adapted arm adapts at every block: it carries a reduced-margin plan generated on the pCT for the first block, and a reduced-margin replan generated on each repeat image thereafter. A non-adapted arm carries the clinical-margin plan generated on the pCT and delivers it for the whole course, with its dose recomputed on each repeat image. There is no adaptation vector, no intermediate adaptation count, and no decision taken during the course.

**Mixed strategies are computable but are not options.** Delivering a reduced-margin plan on a block without a replan is representable in the data, since it needs a dose recomputation and no new plan. It is not a member of the option set. Whether it is nonetheless computed as a reported diagnostic is open decision 22.

**Margin follows the arm, not the block.** Version 5 tied the margin level to the adaptation indicator of each block, so that a non-adapted block of an adapted arm reverted to the clinical-margin plan. That coupling is removed: the reduced margin is a property of the adapted arm from the first fraction. This is what the reference study does, where the reduced setup error plans are planning-stage plans and the first ten of thirty fractions of every OAPT workflow are delivered with them. Robustness contributes no independent degree of freedom to the strategy tuple, as in version 5, but for a simpler reason: it is now determined by the arm rather than by a vector.

**The first block carries no modelled anatomical degradation.** The dose of the first block is the nominal planned dose on the pCT, evaluated on the anatomy the plan was made on. This holds for every arm, but its consequence is not symmetric. The reduced-margin arms bank their organ sparing over that block at a modelled coverage risk of zero, while the clinical-margin arms bank a higher organ dose over the same block, also at zero modelled risk. The distortion therefore favours margin reduction, which in the reference study is the larger of the two benefit terms: at the 2 mm setting and for two-year mortality, the modality step is worth 6.9 per cent and the further step to full adaptation with reduced margins 3.8 per cent, of which the margin component is the larger part. It scales as one over the number of blocks, so it is stronger for a schedule adapted at coarse granularity than for one adapted at fine granularity, and therefore stronger for the standard schedule than for a hypofractionated schedule adapted per fraction. It is recorded as A23 and its bounding is open decision 21.

The adaptive arm at unchanged margins is dropped. It is characterised by the reference study, which reports it as OAPT-Clinic, so retaining it would spend planning effort re-deriving a published result. What is lost is the within-study decomposition of the adaptation benefit from the margin-reduction benefit, and the fallback option when the coverage screen removes the reduced-margin plan; both consequences are recorded in Section 8.2. The reference study supplies the decomposition externally, for lung under mean-dose logistic endpoints, and that is the only source of it available to this study unless open decision 22 is resolved in favour of computing the diagnostic.

## 5. The allocation problem

### 5.1 Formulation

Each patient receives exactly one strategy. Total machine occupancy must not exceed capacity.

max Σ_p Σ_s u_ps · x_ps

subject to:

Σ_p Σ_s n_ps · τ^PT_ps · x_ps ≤ C_PT

Σ_p Σ_s n_ps · τ^XT_ps · x_ps ≤ C_XT

Σ_s x_ps = 1 ∀p ; x_ps ∈ {0, 1}

This is a **multiple-choice knapsack problem** (MCKP) with two resources.

**Photon delivery is unconstrained; photon adaptation is not.** A department does not run out of conventional photon capacity in any sense that changes a referral decision, so the non-adapted photon arm is available to every patient at no modelled cost. Adaptation is the scarce quantity on both modalities, and it is what the two constraints price. This revises the version 4 statement that photon capacity is unconstrained: unconstrained delivery is retained, rationed adaptation is added. The revision is recorded as a design decision pending supervisory confirmation, since the version 4 wording was adopted at supervision.

**What each arm consumes.** Occupancy is per course, since adaptation is a course-level property.

| Arm   | Proton machine time      | Photon adaptation time |
|-------|--------------------------|------------------------|
| XT-NA | none                     | none                   |
| XT-A  | none                     | Δτ_XT per fraction     |
| PT-NA | τ_0 per fraction         | none                   |
| PT-A  | τ_0 + Δτ_PT per fraction | none                   |

The proton arms are charged the whole session, because the proton machine is binding for delivery as well as for adaptation. The photon adapted arm is charged only the increment, because photon delivery is not binding. This asymmetry is a direct consequence of the modelling decision above rather than an additional assumption, and it is why no photon baseline session length is required anywhere in the design.

**Structure of a patient’s option set.** Each patient holds four strategies per fractionation scheme and eight in total over the two schemes. Because the two resources are consumed by disjoint groups of arms, the options form two chains meeting at XT-NA: a photon chain of one rung above the base along the C_XT axis, and a proton chain of two rungs along the C_PT axis. Nothing in the option set consumes both. Section 5.2 uses this structure.

**The option set no longer grows with the number of blocks.** Under version 5 it held B + 1 entries per chain and the number of repeat images was a design parameter of the allocation. It is now fixed at four per scheme regardless of B. The number of blocks continues to govern the extractor, the evaluator and the plan budget, and it no longer governs the allocator.

**Scope limitation.** XT-NA consumes neither budget, and wherever it is assignable the allocation is feasible and no patient is left without a strategy. This is the correct representation of a referral question, in which the standard of care is an entitlement rather than a rationed good. It also means the model cannot represent a department stressed to the point where a patient receives no treatment at all. The word capacity carries the second connotation in the reference study and should not be allowed to import it here.

The entitlement is not unconditional. The coverage screen of Section 8.2 applies symmetrically to the photon arms (A10), so it can remove XT-NA for an individual patient, and the evaluator design already separates the two roles XT-NA plays in that event: the arm remains the ΔNTCP reference and stops being an assignable option (evaluator design, Section 6.3). Feasibility is therefore conditional on the reference arm surviving coverage, and Section 8.6 states what follows when it does not. The version 5 wording asserted the entitlement unconditionally and is corrected here.

**Order of operations.**

- The extractor produces per-block dose and per-block target metrics.

- The evaluator constructs the four strategies per scheme under the arm-level margin rule of Section 4, applies the coverage screen per block, which removes strategies before any accumulation is performed, composes the surviving strategies, evaluates NTCP, and computes the no-harm diagnostic of Section 8.3.

- The allocator solves the MCKP on the surviving option sets. No dominance collapse step is required, since strategies are no longer generated by an adaptation vector and none of them share an occupancy by construction.

**Two distinct reductions are called dominance and only one is retired.** The *collapse by dominance* of the evaluator picked the best schedule at each adaptation count and discarded the rest; it existed only because an adaptation vector generated many strategies of equal occupancy, and it is void at version 6. The *hull reduction* of Section 5.2 removes options lying below the upper convex hull of a patient's chain, and it is what makes the incremental-efficiency ordering valid for the linear relaxation. That argument is indifferent to how the points were generated, so the hull reduction is retained unchanged and is required for T2 and T8. Reading the sentence above as retiring both is an error, and one worth guarding against because the implementation carries a single module named for the word.

Infeasibility is therefore handled by set construction, not by a penalty inside the objective. This keeps the optimization clean and makes the clinical rules explicit rather than implicit in a weighting.

**Internal solve on absolute NTCP.** Since each patient receives exactly one strategy, the sum of baseline NTCP over the cohort is a constant, and maximizing the sum of ΔNTCP is identical to minimizing the sum of absolute NTCP. The allocator solves for absolute NTCP; ΔNTCP is used for reporting and for the no-harm diagnostic.

**No sign constraint is imposed on the objective.** The formulation contains no row of the form u_ps ≥ 0, and none is required. Where a patient holds an assignable option that is free on both budgets and has utility zero, which is XT-NA in the normal case, that option dominates every option of negative utility: substituting it raises the objective and relaxes both capacity rows simultaneously, so no optimal solution of either the integer problem or its relaxation contains a strategy that harms a patient. The sign is enforced by the structure of the option set rather than by a constraint. Imposing it explicitly would be redundant, and it would corrupt the reading of the two shadow prices by introducing rows whose multipliers mix into the duals of the capacity rows.

Two consequences follow, and both are reported rather than assumed. First, the statement that no patient is worse off than the reference is true by construction whenever every patient retains a free assignable reference arm; it is a property of the formulation and must be presented as such rather than as a finding. Second, where a patient has no free assignable option, the condition of the previous paragraph fails and an optimal allocation may assign a strategy of negative utility to that patient. That is the correct answer to the question of what to do with a patient who must be treated and whose reference plan is not deliverable. The count of such patients is reported alongside the allocation.

**Discretisation.** The exact solver runs by dynamic programming over machine time discretised at 0.1 min. The resolution is not innocuous: at 1 min, an occupancy of 36.9 min rounds to 37 and thirteen patients no longer fit in 480 min, which changes the answer and breaks the reproduction of the reference study for a purely numerical reason. Costs round up, so the capacity constraint is never violated by rounding. The resolution is a named constant, not a buried literal.

### 5.2 Algorithm and the shadow price

No threshold is supplied as input. A threshold is *induced* by the allocation and reading it off is the point of the following derivation.

Relax integrality and attach a multiplier to each capacity constraint, λ_PT ≥ 0 and λ_XT ≥ 0:

L(x, λ) = Σ_p Σ_s (u_ps − λ_PT · n_ps · τ^PT_ps − λ_XT · n_ps · τ^XT_ps) · x_ps + λ_PT · C_PT + λ_XT · C_XT

The coupling between patients is replaced by two prices, so the problem still separates. For fixed prices, each patient independently selects the strategy maximizing its priced utility. Since no strategy consumes both resources, that selection reduces to taking the better of two independent chain maxima, one priced at λ_PT and one at λ_XT.

**This is not the same as ranking patients by u/τ.** Version 1 of this document stated that the correct greedy ordering is by benefit density, ΔNTCP divided by occupancy. That statement is correct for a 0-1 knapsack, in which each patient has a single proton option and the decision is to buy or not to buy. It is not correct for the MCKP, in which every patient already holds a baseline option, non-adapted photon treatment at zero cost in both budgets, and the decision is how far up that patient’s chains to climb.

**The single-resource procedure, which remains the building block.** With one resource the LP relaxation of an MCKP is solved as follows.

- Within each patient’s option set, sort options by occupancy.

- Discard **LP-dominated** options, meaning those lying strictly below the upper convex hull of the (τ, u) points for that patient. An option can be undominated in the ordinary sense, that is have higher utility than every cheaper option, and still never be selected by the LP, because a convex combination of its neighbors beats it. Options lying exactly on the segment joining their neighbours are removed as well: they are alternative optima, not additional ones.

- Compute **incremental efficiencies** between consecutive surviving options within each patient: (u_j − u\_(j−1)) / (τ_j − τ\_(j−1)).

- Start every patient at their cheapest surviving option and greedily spend capacity on the pooled incremental efficiencies in decreasing order.

λ\* is the incremental efficiency at the break item: the marginal cohort utility bought by one additional machine-minute spent **upgrading one patient by one rung**.

**What survives with two resources, and what does not.** The hull reduction survives, applied **chain by chain**. Since each chain lies on a single cost axis, the (τ, u) hull of the photon chain and of the proton chain are each ordinary one-dimensional hulls, and the argument for discarding LP-dominated options is unchanged within a chain. No hull is taken across chains.

The pooled greedy does **not** survive. With one resource the greedy is valid because spending is monotone: capacity is consumed and never released. With two resources, moving a patient from the photon chain to the proton chain releases photon adaptation minutes while consuming proton minutes, so the exchange is not monotone in either budget and a single ordering of upgrades does not exist. The LP must therefore be solved either by an explicit solver or by a search over the price pair (λ_PT, λ_XT), with the per-patient chain maxima evaluated at each candidate pair. This is an implementation item rather than a formulation change, and it is recorded in Section 12.

λ_PT retains its previous meaning, the marginal cohort utility bought by one additional proton machine-minute. λ_XT is new: the marginal cohort utility bought by one additional minute of photon adaptation capability. Their ratio states where a department gains more from the next unit of investment, which is a result the reference study cannot produce.

**λ_XT is reported as a curve, not as a point.** Its magnitude depends on C_XT, and C_XT has no measured anchor for this indication. Reporting a single value would report an assumed number. The budget is therefore swept and λ_XT(C_XT) is reported, with the two limits carrying interpretable meaning: at C_XT = 0 the photon comparator reduces to the reference study’s non-adapted arm, and as C_XT grows without bound the version 4 free-photon-adaptation case is recovered.

**The sweep axis is normalised.** C_XT is reported as a fraction of the cohort’s total photon adaptation demand, so that 0 is the reference study’s comparator and 1 is the version 4 free case by construction, making T8 and T9 the endpoints of the axis. This makes the curves invariant to cohort size and to the resampling procedure. Absolute minutes are carried as a secondary axis. A single **reference value** C_XT^ref will additionally be fixed with the clinical partners and the supervisor, playing the role the 480 minutes play for the proton budget in the reference study: results that need one photon budget rather than a sweep, in particular the (Δτ_PT, Δτ_XT) plane, are evaluated there.

**The hull reduction is a property of the linear relaxation only.** An option below the hull is never bought by the LP, which can split its budget between the neighbours; the integer problem cannot split, and an LP-dominated option can appear in the integer optimum. The hull reduction must therefore never be applied before an integer solve or inside an integer heuristic. Version 2 of this document stated the reduction without this scoping, and the integer greedy was implemented on the reduced set, which is an error; Section 13 records it. What is valid for both problems is the **Pareto reduction**: among options of equal cost only the best utility survives, and an option that costs more without buying more is dropped.

**Two kinds of dominance, reported separately.** Pareto dominance says two arms are not in genuine competition, for instance a strategy that costs more without buying more; it is structural and largely uninformative. LP-dominance says a rung is one the relaxation would never buy at any capacity, which is the clinically informative statement. Folding both into one count would let the first swamp the second, so the two are counted and reported as distinct quantities.

**Under version 6 the LP-dominance question has exactly one instance per patient per scheme.** Within a single scheme, the photon chain holds one rung above the base and cannot be LP-dominated; the proton chain holds two, so the only rung that can fall below the hull is PT-NA, and it does so when the price-efficient route into the proton chain is to enter directly at PT-A. That single question, at single-scheme scope, is what Section 6.5 answers and what test T14 checks.

Pooled across two schemes, both axes carry two rungs above the free base rather than one, and both can be LP-dominated by the identical geometric argument: nothing in it is specific to the proton axis. `report.dominance_counts` anchors each axis at its own free point before reducing, so the pooled count it reports is correct on both axes, but no closed form covers this case. Section 6.5 states why, and it is not a gap left for later: the cross-scheme interaction is the subject the allocator resolves directly, not a case the threshold was meant to reach (road 1).

**NB.** Each multiplier compresses a scenario ladder into one number with a clear operational meaning. A proposed proton workflow change costing an extra Δτ_PT per fraction is worthwhile for patient p if and only if the incremental utility it buys exceeds λ_PT · Δτ_PT, and the same statement holds on the photon side with λ_XT. This answers the reference study’s central question without enumerating scenarios and gives “Time is NTCP” a quantitative exchange rate on each modality. It also makes the comparison with national model-based selection precise: λ_PT · τ is what a referral threshold *should* be given a particular centre’s capacity and case mix.

**Integrality gap.** In a single-resource MCKP the LP optimum has at most one fractional class, so the gap is bounded by the utility difference between the two straddling options **within that single patient’s set**, not by a whole patient’s utility. With two constraints the bound weakens to at most two fractional classes, one per binding constraint, by the standard argument on the number of basic variables. The bound is therefore stated per resource rather than globally.

The recommendation is unchanged: solve the integer problem exactly and use the LP relaxation only to extract the multipliers and the dominance structure. With four options per patient per scheme the exact solve is computationally trivial at any cohort size the study can reach, so the state-space concern recorded in version 5 lapses. The integer linear program of open decision 15 is retained as the reference solver, because it states the two-resource problem in the form hardest to get wrong and supplies the duals directly.

### 5.3 Policies to compare

An optimum alone is not a clinically useful output, because no clinic implements an integer program. The informative output is the gap between what simple rules achieve and what is achievable at all.

| Policy | Definition                                                                             | What it represents                                                                                                                   |
|--------|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| P0     | Threshold-based referral, fixed standard schedule, no adaptation                       | Current practice. The locked baseline                                                                                                |
| P1     | Threshold-based referral, adaptation for all proton patients, fixed schedule           | Essentially the reference study                                                                                                      |
| P1x    | As P1, then photon adaptation in decreasing ΔNTCP until the photon budget is exhausted | Isolates the value of the adapted photon arm’s existence from the value of optimising over it. Without it, P3 − P1 confounds the two |
| P2a    | Greedy by benefit density u/τ over patients                                            | The naive capacity-aware rule, implementable by hand                                                                                 |
| P2b    | Greedy by best available upgrade over Pareto-reduced ladders                           | The correct heuristic                                                                                                                |
| P3     | Exact multiple-choice knapsack optimum                                                 | Upper bound on what any allocation could achieve                                                                                     |

**P2b, defined precisely.** Every patient starts on their cheapest option. At each step the upgrade with the highest ratio of utility gained to minutes spent is taken, over all patients and over **every** option above the one currently held, not only the next rung; on a non-concave chain the best available upgrade can skip rungs, and a rank-by-rank scan never reaches it. The procedure runs on the Pareto-reduced option sets, not the hull-reduced ones, for the reason given in Section 5.2. It stops when no upgrade fits.

P2a and P2b are separated deliberately. Merging them would confound two different costs: the cost of using a heuristic instead of an exact solve, and the cost of using the wrong ranking statistic.

**Ranking statistic under two resources: resolved.** A benefit density u/τ is not defined when an upgrade may consume either of two budgets, because the two efficiencies are in different units and comparing them assumes an exchange rate between the budgets, which is exactly the quantity the LP computes as λ_XT / λ_PT. Three conventions were considered: rank within each resource and interleave by a fixed priority; scalarise costs with the current price pair, which makes the heuristic depend on the LP it is supposed to approximate; or restrict the heuristics to the proton chain and assign the photon chain by a separate rule. The **third is adopted**: P2a and P2b rank proton upgrades only, in their version 4 form, and the photon budget is spent by a separate rule, adapting photon patients in decreasing ΔNTCP until it is exhausted, the same rule P1x uses. Two reasons. It is what a clinic would implement, since the two capacities are managed by different services and no clinic would order a mixed list. And it preserves comparability with the synthetic magnitudes below, which were measured under the single-resource form. All three conventions coincide at C_XT = 0, so recoverability of the version 4 behaviour did not discriminate between them; the choice matters only in the interior, where both budgets bind.

**Policies are secondary outputs.** The primary result of the study is the parametric behaviour of the optimal allocation itself, how the cohort’s assignment moves across the (Δτ_PT, Δτ_XT) plane and along the photon budget axis under the two constraints. The policy comparison reads that result against implementable rules and is reported after it.

**P2a and P2b coincide only within a single fractionation scheme.** With two rungs on one scheme's proton chain, the only way the best available upgrade differs from the next rung is when a patient is moved directly from the photon base to PT-A, skipping PT-NA, which is precisely the case in which PT-NA falls below the hull: the separation between the two heuristics collapses onto the same single question as the LP-dominance count, at that scope. Pooled across two schemes the separation is no longer marginal, because a best-available upgrade can now also skip from the photon base past PT-NA-hyp to PT-A-std or the reverse, a jump the single-scheme argument does not describe. On a synthetic illustration spanning both schemes, P2a fell short of the exact optimum by 6.6 per cent on average against 3.4 per cent for P2b; restricted to one scheme the gap was 1.3 per cent for both (synthetic cohort, not a magnitude for the study). The two policies are retained, because the case is real and its frequency is a reportable quantity, but the design should not promise coincidence once the fractionation axis is active.

**Measured magnitudes on synthetic cohorts, superseded.** On 1800 synthetic instances spanning concave, linear and convex adaptation-benefit profiles, P2b fell short of the exact optimum by 0.51 per cent of the optimum on average (maximum 8.1), P2a by 0.67 per cent (maximum 10.1), and P2b was strictly better than P2a in 11 per cent of instances. Those instances carried ladders with several adapted rungs and therefore do not describe the version 6 option set. They are retained here as the measurement that motivated separating the two heuristics, and they must be re-measured on four-option ladders before any magnitude is quoted in the manuscript. The direction of the expected change is known: with fewer rungs, both heuristics move closer to the optimum and closer to each other.

### 5.4 Algorithmic claims to be tested

The following are assertions about the formulation, and each is implemented as a failing-by-default test rather than left in prose.

| ID  | Claim                                                                                                                                                                                                                                                                                                     | Status  |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|
| T1  | With │Sp│ = 2, τ constant across patients, and one shared adaptation policy, the allocator reproduces the reference study’s scenario ladder                                                                                                                                                               | Passing |
| T2  | Incremental-efficiency greedy after hull removal attains the LP optimum, checked against an independent LP solver                                                                                                                                                                                         | Passing |
| T3  | The integer optimum lies below the LP optimum by at most one within-patient upgrade step. As implemented the bound used is the largest upgrade step within the fractional patient’s chain, which is weaker than the straddling-pair statement; the discrepancy is noted here so the test is not over-read | Passing |
| T4  | λ extracted from the LP equals the finite difference of optimal utility with respect to capacity                                                                                                                                                                                                          | Passing |
| T5  | Solving on absolute NTCP and on ΔNTCP produce identical allocations                                                                                                                                                                                                                                       | Passing |
| T6  | **Void at version 6.** The claim concerned the dominance collapse over adaptation counts, which no longer exists                                                                                                                                                                                        | Void    |

Three further claims follow from the second resource and are not yet implemented.

| ID  | Claim                                                                                                                                                                                         | Status       |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| T7  | Each multiplier equals the finite difference of optimal utility with respect to its own budget, holding the other fixed. This is T4 stated per resource                                       | Passing |
| T8  | At C_XT = 0 the two-resource solve reproduces the version 4 single-resource result exactly, and therefore still reproduces the reference study through T1                                     | Passing |
| T9  | As C_XT grows beyond the cohort’s total photon adaptation demand, λ_XT falls to zero and every patient not receiving protons holds XT-A, recovering the version 4 free-photon-adaptation case | Passing |
| T15 | Relabelling the two resources onto each other and swapping the budgets reproduces the mirrored problem exactly, in optimal value and in both duals                                            | Passing |

T8 and T9 are the two limits of the C_XT sweep and are what make the sweep interpretable. They also serve as regression tests against the existing implementation, since the version 4 behaviour must survive as a boundary case rather than be replaced.

Two further claims concern the sign of the utility and the separation of the two roles XT-NA plays. They are implemented.

| ID  | Claim                                                                                                                                                                                                                                                                                                 | Status  |
|-----|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|
| T10 | While every patient retains a free assignable reference arm, no policy assigns a strategy of negative utility, and no sign constraint is present anywhere in the code that achieves it. The Pareto reduction of Section 5.2 is what removes such strategies from the chains                           | Passing |
| T11 | Where the reference arm is not assignable and nothing free replaces it, the exact optimum assigns the least harmful surviving strategy rather than raising, an inadmissible strategy is never assigned by any solver or policy, and an option set emptied by the screens raises and names the patient | Passing |

Three claims follow from the version 6 option set and were added here at version 6.1.

| ID  | Claim                                                                                                                                                                                                                                                    | Status       |
|-----|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| T12 | **Void at 6.2.** Asserted that no selected strategy varies modality, adaptation or fractionation across blocks. The record already makes a mixed course unrepresentable rather than merely disallowed, so the claim held by construction and no test could fail it | Void |
| T13 | **Absorbed into T1 at 6.2.** With the option set restricted to one scheme and Δτ_XT set so that C_XT does not bind, the per-course occupancy of Section 9 was to be checked against the version 5 per-block occupancy on a fully adapted arm; no version 5 implementation survives to check it against. The reference-study ladder, the only half with a live referent, is T1 | Absorbed |
| T14 | The number of patients for whom PT-NA falls below the upper hull of their proton chain, augmented with the photon outside option, equals the number for whom Δτ_PT is below the closed-form threshold of Section 6.5, to solver tolerance. Scoped to a single fractionation scheme, matching the scope of the closed form itself (road 1) | Passing |

T14 is the test that keeps the closed form honest, since Section 6.5 is now a statement about one rung rather than about a family of intermediate counts and can be checked patient by patient. It is deliberately not run on a cohort spanning both schemes: pooled on the shared proton axis, the augmented hull answers the cross-scheme question Section 6.5 states the formula does not cover, so the two would be checked against a claim the design never made. `test_t14_hull_membership_matches_the_closed_form` (`test_threshold.py`) sweeps Δτ_PT, the presence and price of photon coupling, and the photon budget as a fraction of cohort demand, rather than a cohort constructed to straddle the threshold, so the crossing is shown as a property of the formulation rather than of the construction.

## 6. Configuration space

Four configurations were considered. **Config 0e is adopted**, following the version 6 supervisory decision. Each is illustrated with an **invented four-patient example** (three CTs, three blocks of ten fractions, τ_0 = 30 min, Δτ = 30 min, C = 130 min). The numbers demonstrate structure only, and for Config 2 they now illustrate a configuration that has been deferred.

| Config | Modality              | Adaptation                  | Fractionation             | Verdict                   |
|--------|-----------------------|-----------------------------|---------------------------|---------------------------|
| 0      | binary, whole course  | one policy for whole cohort | fixed                     | reference study; baseline |
| 0e     | binary, whole course  | per patient, whole course   | per patient, whole course | **adopted**               |
| 1      | fraction-level mixing | none                        | fixed                     | rejected                  |
| 2      | binary, whole course  | per patient, per block      | per patient               | deferred to paper 2       |
| 3      | fraction-level mixing | per patient, per block      | per patient               | deferred                  |

**Config 0e is what version 6 defines.** It releases the reference study’s first rigidity, one workflow for the whole cohort, by letting the adaptation decision and the fractionation decision be taken per patient. It does not release the decision to the block level. What separates it from Config 0 is therefore the per-patient granularity and the second degree of freedom, not the timing.

### 6.1 Config 0: reference-study structure

One workflow for all selected patients. In the illustration, the non-adaptive arm fits four patients (mean ΔNTCP 0.055) and the adaptive arm fits two (mean 0.0575). The two are near-equivalent, which reproduces the reference study’s central finding: at large Δτ the adaptive workflow sits on or below the non-adaptive line.

In the adaptive arm 100 of 130 minutes are used and 30 are idle. The scenario structure cannot spend the remainder, because it admits no mixed cohort. This is rigidity R1.

### 6.2 Config 1: fraction-level proton-photon mixing

Two variants must be distinguished.

*Naive mixing* plans a full proton course and a full photon course independently and delivers k fractions of one and N − k of the other. Each plan was optimised assuming it would deliver the whole treatment, so neither exploits the other. Utility is close to linear in k and the optimum collapses to k = 0 or k = N. This recovers patient selection with extra work.

*Joint optimization* optimizes both fluence sets simultaneously against a shared BED objective (Fabiano et al.). This is the version with real content, and it introduces a genuine technical obstacle: physical doses cannot be summed across modalities, because the quadratic term of the linear quadratic model depends on the dose per fraction each modality delivers to each specific voxel, and these differ voxel by voxel. The objective becomes quadratic in the fluence and the problem nonconvex. The optimal split depends on alpha over beta per structure, which for abdomen is poorly constrained.

**Expected gain.** Entirely from the curvature of u(k). Loizeau et al. found the population-level gain over patient selection to be small in head and neck when both modalities deliver the same dose per fraction. A substantial advantage appeared only when proton and photon fractions were allowed different doses per fraction, which is a hypofractionation argument and does not apply to a 28 by 1.8 Gy pelvic prescription.

**Additional objections specific to this study.**

- The photon arm defines the ΔNTCP reference. Making it also a within-course resource entangles the baseline with the decision variable.

- It requires a second capacity constraint and therefore a second multiplier, doubling the interpretive load of every result.

- It requires a photon planning engine capable of joint optimization with the proton engine. Given the unresolved maturity of photon planning in OpenTPS, this is the binding infrastructural constraint.

- Combining RBE-weighted proton dose with photon physical dose in one BED expression carries an RBE assumption that is usually left silent and becomes considerably worse under variable RBE.

**Decision:** rejected for this study.

*One variant worth a cheap test.* Protons are sensitive to anatomical change; photons degrade more gracefully. This suggests allocating modality **by anatomical stability over time**: deliver blocks where anatomy is drifting with photons, and stable blocks with protons. The rationale is robustness complementarity rather than NTCP curvature, and it interacts directly with the adaptation decision, since a photon block is an alternative to adapting a proton block. This is speculation; no formulation of it is known to the author of this document. It may fail trivially if an offline-replanned proton block dominates a photon block on both robustness and dose. It is testable against the Config 2 data at no additional planning cost, and merits one paragraph in the eventual discussion, not a workstream.

### 6.3 Config 2: adaptation-level allocation, deferred

**Deferred by supervisory decision, version 6.** Modality stays binary and whole course, and what becomes divisible is the adaptation, decided per patient and per block. Each patient’s option set would then hold B + 1 entries per chain rather than two, and intermediate adaptation counts would be selectable. This is the configuration versions 2 to 5 of this document recommended. It is not what the study does.

**What is lost, stated plainly.** Three reportable quantities disappear with it. Whether adaptation early in the course carries more benefit than adaptation late, which the per-block option set answered directly. Whether a partially adapted course is ever the price-efficient choice, which is the heterogeneous-cohort mechanism the illustration below shows. And the interpretation of the closed form as a statement about intermediate counts, which Section 6.5 replaces with a statement about one rung.

**What survives.** The heterogeneity of the cohort survives, because it never depended on the per-block decision alone. Patients still differ in which rung of which chain is price-efficient for them, and the mixed cohort in the illustration below is reachable through modality and schedule rather than through adaptation count. The two-resource structure survives unchanged. The closed-form threshold survives, with a different and arguably clearer reading.

**The illustration, retained for the record.** In the invented example the Config 2 optimum is a heterogeneous cohort: two patients fully adapted, one on protons without adaptation, one on photons, giving mean ΔNTCP 0.0675 against 0.0575 for the best Config 0 arm. That configuration is unreachable in the reference study’s framework. Under Config 0e the same cohort is reachable in composition but not through intermediate adaptation counts.

**Where it goes.** Config 2 is the natural first extension of the reinforcement learning publication, together with the receding-horizon reallocation of Section 10.5, since both concern when to act within a course rather than what to assign at its start.

### 6.4 Config 3: layered

Both decisions are active. Structurally, this is Config 2 with a finer partition of each patient’s course. In the illustration it adds approximately the Config 1 gain on top of Config 2, which is to say little, for a large increase in machinery. **Deferred.**

### 6.5 The step-ratio threshold

Since no clinical on-couch adaptive proton workflow exists for the abdomen, the extra time per adapted fraction is not a measurable input; as in the reference study it is the independent variable, and the deliverable is a threshold on it. Under version 6 the threshold answers a different question from the one version 5 posed, and it answers it in the same closed form.

**The question.** With two rungs on the proton chain, the only structural question the hull can pose is whether PT-NA survives it. Below the threshold, PT-NA lies under the segment joining the photon base to PT-A: non-adapted protons are never the price-efficient way to spend proton capacity, and a patient who enters the proton chain at all enters it adapted. Above the threshold, PT-NA is a live rung and the cohort can split three ways rather than two. This is a more direct clinical question than the version 5 one, and it is patient-wise.

**Derivation.** Let m be the ΔNTCP of the modality step, photons to non-adapted protons, and a the further ΔNTCP of adaptation together with the margin reduction it licenses, so that PT-A is worth m + a. Let τ_0 be the baseline session length and n_fx the fraction count. Occupancies are per course, n_fx · τ_0 for PT-NA and n_fx · (τ_0 + Δτ) for PT-A. The efficiency of the entry step and of the adaptation step are:

e_mod = m / (n_fx · τ_0)

e_ada = a / (n_fx · Δτ)

PT-NA survives the hull when e_mod ≥ e_ada, that is when the step ratio ρ = e_mod / e_ada ≥ 1, which solves to:

**Δτ\* = τ_0 · (a / m)**

This is the version 4 and version 5 closed form evaluated at B = 1. The block count and the concavity exponent p, which entered only through the factor B^(1−p), drop out because there are no intermediate counts whose spacing they described. Nothing else in the derivation changes.

Three properties are worth stating.

- **The threshold is a fraction of the baseline session length**, governed by the benefit ratio a/m. In adimensional form Δτ\*/τ_0 = a/m, so it transfers across sites and does not depend on the particular 34.2 min of the reference setting.

- **a/m is an output of the cohort, not an input.** The study measures both numerators; the threshold then follows, and is compared against the workflow-time envelope constructed from the components of Section 9.

- **It is patient-wise.** Each patient carries their own (m_p, a_p) and therefore their own threshold, so a cohort spanning both sides of it produces a mixed allocation at a single Δτ. This is the design argument for enriching the cohort with borderline cases, and it is what T14 checks.

**The closed form coincides with the reference study’s break-even.** The reference study asks at what Δτ adapting every patient, and losing capacity for it, ceases to beat adapting none. Under a uniform cohort and continuous capacity that condition is written as follows. With i patients displaced to photons, capacity gives (P − i)(τ_0 + Δτ) = P · τ_0, and equality of the two cohort means gives (P − i)(m + a)/P = m. Eliminating i:

τ_0 · (m + a) / (τ_0 + Δτ) = m, hence Δτ = τ_0 · (a / m)

which is Δτ\*. **The hull condition and the reference study’s break-even are the same condition.** They coincide because at LP prices the optimum spends capacity on the more efficient step first, so the point at which two pure policies break even is the point at which their two steps have equal efficiency. The reference study’s headline number is therefore available in closed form rather than read from a scenario ladder.

**Numerical check against the published values, as illustration and not as reanalysis.** For two-year mortality at the 2 mm setting, m = 6.9 and m + a = 10.7, so a = 3.8 and with τ_0 = 34.2 min the threshold is 18.8 min, against the 19 min at which the reference study reports the gain ceasing to be significant against the non-adapted arm. For dysphagia, a = 7.5 and the threshold is 42.1 min, consistent with the published curve not crossing within a sweep that stops at 25.7 min. For pneumonitis the threshold is 20.9 min while the published crossing falls near 13.7 min, and the discrepancy is informative rather than a failure.

**The closed form is a benchmark and the discrepancies are the result.** Three mechanisms separate the analytical value from the observed crossing, and each is measurable as a departure from it.

- **Discreteness.** Patients are integers and capacity moves in steps. For the non-reduced-margin setting on two-year mortality the closed form gives 4.5 min while the published crossing falls between the 2.7 min and 5.9 min scenarios, so the analytical value sits inside the discrete interval rather than at a point.

- **Heterogeneity with selection.** The displaced patients are not average patients but the ones the displacement rule selects, which moves the crossing away from the uniform-cohort value.

- **Disalignment of the ranking statistic.** In the reference study the displacement is decided on the union probability computed under the unchanged-margin adapted arm, while the curve being read is a single endpoint under a reduced-margin arm. The subset displaced is therefore not the subset that a ranking coherent with the evaluated strategy would displace. For pneumonitis this appears to be the dominant term.

Reporting the observed allocation against the closed form decomposes the gap between the exact optimum and current practice by mechanism, rather than as a single unattributed difference. With the fractionation axis a fourth term is added, since n_fx enters the two schemes differently, and that term is not captured by a threshold derived at fixed schedule.

**The budget acts on the threshold through one scalar.** At LP prices the patient’s photon chain enters the proton competition only through its best priced value, the **photon outside-option value**

w(λ_XT) = max( 0, x − λ_XT · n_fx · Δτ_XT )

with x the photon adaptation benefit. The reduction is exact, not an approximation, because the two chains share no cost axis: a proton rung is LP-selectable if and only if it lies on the upper hull of the proton points augmented with the point (0, w). Version 5 wrote w as a maximum over adaptation counts; with a single photon rung the maximum is over two terms.

The adaptation increment does not involve w; only the entry step does, whose efficiency becomes (m − w) / (n_fx · τ_0). The threshold follows:

**Δτ\*(w) = τ_0 · a / (m − w), valid for w \< m**

At w = 0 this is the closed form above; the dependence on the budget enters only through the denominator.

**Monotonicity is proved, not asserted.** The LP value is concave in the right-hand side, so λ_XT is non-increasing in C_XT; w is a maximum of affine non-increasing functions of λ_XT, hence non-decreasing in C_XT; and Δτ\*(w) is increasing in w below m. Therefore Δτ\*(C_XT) is non-decreasing, piecewise smooth, with interpretable limits: τ_0 · a / m at C_XT = 0 (T8) and τ_0 · a / (m − x) at saturation (T9). The closed form was verified numerically against the hull implementation to a relative 1e-6 across the w range under the version 5 parametrisation (test_threshold.py); the version 6 form is the same expression at B = 1 and the test is retained with the concavity cases removed.

**The regime w ≥ m.** If a patient’s photon outside option is worth more than the bare modality step, the formula is void and the correct statement is stronger: PT-NA is never LP-selected for that patient at any proton price, and the patient enters the proton chain, if at all, directly at PT-A. This is an interpretable finding rather than a pathology: a sufficiently funded photon adaptation programme removes non-adapted protons from the efficient frontier patient-wise, and the boundary w = m is itself a reportable transition. Whether any real patient sits there depends on x against m, which the study measures.

**Cohort coupling.** w depends on λ_XT, an equilibrium scalar of the whole allocation, so the per-patient thresholds form a family Δτ\*\_p(C_XT) driven by one cohort-level price: heterogeneity at fixed budget comes from (m_p, a_p, x_p) only, and the family costs nothing beyond the λ_XT(C_XT) sweep already planned.

The direction of the budget effect is known in advance and should be stated, because it acts against the mechanism that motivates spending proton capacity on adaptation and a reader will otherwise suspect it was noticed only after the fact. The magnitude is the size of the photon adaptation benefit, which the study measures rather than assumes. As in version 4, the threshold does not capture competition between fractionation schemes: each scheme carries its own (τ_0, a, m, x) and therefore its own surface.

**One point of that competition has a closed form.** The standard adapted arm, PT-A under the standard schedule, is the highest-cost point of a patient's pooled proton frontier at every reachable parameter setting: the hypofractionated schedule is cheaper on both its rungs by construction of Section 9, and charging the adaptation increment per fraction only widens that gap under the standard schedule's larger fraction count. A point at maximum cost survives Pareto, and therefore sits on the hull, exactly when it also carries the maximum utility of the whole set: anything that beat it in utility at equal or lower cost would dominate it outright, its own cost ranking aside. Writing m and a for the standard schedule's own modality and adaptation benefit, pen for the biological penalty applied to the hypofractionated modality benefit, and a_mult for the ratio of the hypofractionated to the standard adaptation benefit (`generator/synth.py`, `scripts/two_scheme_check.py`), the binding comparison is against the hypofractionated adapted arm's utility, m − pen + a·a_mult, and reduces to

**pen\* = a · (a_mult − 1)**

PT-A standard survives the pooled hull when pen > pen\*, is dropped when pen < pen\*, and at exact equality is resolved by the tie-break in `pareto()`, which keeps the cheaper of two equal-utility points: at a_mult = 1 this gives pen\* = 0 for any a, so that boundary is a coincidence of the tie-break rather than an economically meaningful transition. Neither Δτ nor any occupancy parameter enters, since the comparison is between utilities alone; the geometry only used cost to establish which point was rightmost to begin with. At the reference-study magnitude already used above, a = 3.8 percentage points, so pen\* = 3.8 · (a_mult − 1): a hypofractionated adaptation benefit 1.5 times the standard one requires a biological penalty above 1.9 points before the standard adapted arm is displaced, 2.5 times requires above 5.7. This does not extend to the other three points of the pooled frontier, whose hull membership is still resolved by the allocator directly and not by any closed form.

**Per-replan accounting (open decision 20).** Section 9 charges the adaptation increment on every fraction of an adapted course, n_fx · Δτ in total. Charging it once per block instead, B · Δτ in total, replaces the entry step's competitor and rescales the threshold:

**Δτ\*_replan(w) = (n_fx / B) · τ_0 · a / (m − w)**

the closed form above with the same w, scaled by n_fx / B > 1: per-replan accounting always raises the single-scheme threshold, since the same physical Δτ now buys a cheaper-looking adaptation on the entry step's terms. At the reference-study magnitudes already used above (τ_0 = 34.2 min, m = 6.9 per cent, a = 3.8 per cent) and B = 3 (ten fractions per block, Section 9), the threshold moves from 18.8 to 188 min: under this convention PT-NA standard is essentially never displaced by its own adaptation step. This is an illustration at published magnitudes, not a new measurement, on the same footing as the numerical check earlier in this section.

The formula is silent on the question decision 20 actually turns on, which schedule's adaptation looks cheaper against the other once both are charged per replan rather than per fraction, because that is a comparison between two schemes' (τ_0, a, m, B) tuples and is resolved by the allocator on the pooled proton axis, not by either scheme's threshold alone, for the same reason given above for the LP-dominance question. Evaluating it needs B for both schedules; the standard schedule's is fixed by Section 9, the hypofractionated schedule's is not, pending decision 23.

**Where a non-concave profile now comes from.** At version 5 a patient's proton chain could be non-concave through the curvature of the benefit in the adaptation count, and the exponent p described that curvature. With two rungs per scheme there is no curvature to describe, but the chain is not thereby concave: both schemes lie on the same proton cost axis, so a patient's frontier holds four proton points and the standard arms compete against the hypofractionated ones on price. Whether an arm falls below the hull is then governed by the biological penalty of hypofractionation against the adaptation benefit it licenses, not by any within-chain curvature, quantified above for the standard adapted arm specifically. The hull reduction is what handles this, which is the second reason it is retained. The synthetic generator exposes the three reachable configurations, both schemes represented on the hull, one arm below it, and the standard chain entirely below it, so that the greedy is exercised on all three.

## 7. Utility currency

ΔNTCP against a locked non-adaptive photon baseline, with the baseline fractionation scheme and margin fixed before any computation. As in the reference study, selection is made on the union probability, with per-endpoint ΔNTCP reported separately. Two consequences must be stated explicitly:

- The union probability assumes independence between toxicities, which is false, since they share dose drivers and patient-level frailty. This is accepted as the best treatment available and matches the reference study.

- Selection on a single scalar with reporting on several means that no per-endpoint curve is the optimum for its own endpoint. The single-endpoint optima are a natural benchmark and should be computed as a secondary analysis.

**Severity weighting is not applied.** The union probability weights all endpoints equally, including endpoints of very different severity, and this is accepted following the supervisory decision, for continuity with the reference study and with the model-based selection logic. The interface retains per-endpoint weights defaulting to the union form, so that a severity-weighted utility could be substituted later without structural change, but no such weighting is exercised in this study.

## 8. Admissibility

Comparing arms on NTCP alone is legitimate only where every arm delivers the prescribed dose to the target and no arm is worse than the baseline. The two conditions are handled differently, and the asymmetry is deliberate. Target coverage is **enforced** by a screen, because nothing in the objective penalises an underdosed target. No harm is **reported** rather than enforced, because the structure of the option set already guarantees it wherever it can be guaranteed at all, as Section 5.1 shows. Both are computed by the evaluator; the allocator receives the filtered option sets, the admissibility flags, and the counts.

### 8.1 What is assumed and what is not

Every arm is **engineered** to treat the tumor adequately: each plan is generated to protocol on the image available at the time of planning, with the robustness settings appropriate to its arm. This is a design constraint on plan generation.

What is **not** assumed is that adequacy persists. A plan built on the pCT and delivered without adaptation to a changed anatomy may lose target coverage as well as OAR sparing. Anatomical change that could not be anticipated at planning is precisely the failure mode that motivates adaptation, and it acts on the target, not only on normal tissue.

Coverage degradation is therefore an **independent trigger for adaptation**, alongside NTCP benefit. A patient may require adaptation not because it improves the toxicity profile but because the non-adapted plan no longer treats the tumor adequately.

If the target shifts away from an OAR between pCT and rCT, the non-adapted plan underdoses the CTV while the OAR dose falls, so coverage fails and NTCP *improves*. An allocator ranking on ΔNTCP alone would rate that plan as the better option. NTCP is a function of OAR dose only and carries no information about the target, so coverage must be tested explicitly rather than inferred.

### 8.2 Coverage, judged per block

Target coverage is a property of a plan delivered on a given anatomy. If the non-adapted plan evaluated on rCT1 falls below the acceptance criterion, that plan would not be delivered for that block, and no accumulation is required to reach that judgement.

Three consequences:

- The screen acts on **arms**, not on individual strategies. Failure of the non-adapted plan at block b removes the non-adapted arm of that modality, for the whole course, since the arm is a course-level commitment taken at prescription. The removal is **per schedule**: the two schedules carry different block structures, so failure under one does not imply failure under the other. Version 5 stated this as the removal of every strategy whose adaptation vector was false at b; with adaptation reduced to a scalar the family is a single arm. What should follow once an arm is removed is open decision 24.

- The number of coverage evaluations equals the number of plans rather than the number of strategies.

- The screen runs before composition, so accumulation is performed only for surviving strategies.

Accumulated coverage is not retained in any role.

**No conservative fallback exists.** With a single adaptive margin level, a block on which the reduced-margin plan fails coverage leaves only the non-adapted plan for that block, which may well fail for the same anatomical reason, or the photon arms. The empty-option-set path of Section 8.4 is therefore marginally more reachable than it would be with two adaptive margin levels. This remains unlikely with clinical plans in a retrospective study, and the response is an error rather than a fallback, but the count of blocks on which the reduced-margin plan failed the screen is reported, since it measures how often the licensed margin reduction is not in fact deliverable.

**Worst-case variant.** Worst-case metrics are evaluated per block and not accumulated, since the worst scenario in one block need not be the worst in another and a sum of per-block worst cases corresponds to no physical scenario. The worst-case screen is the statement that no block’s plan fails robust coverage evaluation, which is the per-plan property robustness evaluation conventionally asserts. It is retained as a sensitivity analysis, and the count of strategies removed under each criterion is reported.

**Symmetry.** The screen applies to the photon arm as well.

**The criterion is V95% below 95 per cent**, following the supervisory decision. Additional criteria may be added, so the screen takes a list of criteria of which all must pass rather than a single test, and the count of strategies removed is reported per criterion. This keeps a later addition a configuration change rather than a code change.

### 8.3 No harm

A strategy whose union ΔNTCP against the locked baseline is negative is **counted and reported, not removed**. This revises the previous design, in which it was removed on the same footing as a coverage failure. The ethical requirement is unchanged: maximising a cohort mean must not make an individual worse than current standard care. What changed is the recognition that removal is not what secures it.

**Why removal is not what secures it.** XT-NA costs nothing on either budget and has ΔNTCP identically zero, so it dominates every strategy of negative utility: substituting it raises the objective and frees capacity at the same time. No optimal allocation of either the integer problem or its relaxation contains a harmful strategy, whether or not such strategies are present in the option set. Removal is therefore redundant wherever XT-NA is assignable.

**Where removal is not redundant it is wrong.** The only patients for whom it changes the answer are those whose XT-NA the coverage screen has already removed. For them, removal deletes every remaining option that is worse than an arm they cannot receive, which can empty the option set and raise under Section 8.4 for a patient who has a deliverable, merely suboptimal, plan. Reporting instead of removing leaves them with their least harmful deliverable option, which is what a clinic would give them.

**What is reported.** The count of assignable strategies whose union ΔNTCP is not positive, excluding the reference arm, whose zero is definitional. Under the previous design this count was identically zero and carried no information; it now measures how often adaptation or a changed schedule fails to help, which is a quantity of independent interest and is distinct from how often such a strategy is selected. The latter is also reported per allocation and is expected to be zero.

**The union scalar only.** A strategy that worsens one endpoint while improving the others can still be the right choice, and judging it on a single endpoint would be stricter than the selection rule used everywhere else. Per-endpoint sign violations are counted separately, so the cost of the convention stays visible.

**Consequence for feasibility.** No harm no longer removes anything, so it cannot contribute to an empty option set under any circumstances. Infeasibility can originate only from coverage, which is the statement the previous design asserted without it being true.

### 8.4 Empty option sets

If every strategy for a patient fails the coverage screen, the multiple-choice constraint cannot be satisfied and the problem is infeasible. The evaluator raises and names the patient and the failing criterion. No fallback is provided. Coverage is the only screen that removes anything, following Section 8.3, so this is the only route to infeasibility.

Given clinical plans and a retrospective study, an empty set indicates a misconfigured acceptance criterion rather than an untreatable patient, and an error is the response that surfaces that.

### 8.5 Photon adaptation as capacity relief

A stronger adapted photon comparator lowers the number of patients whose delta NTCP justifies a proton slot, so photon adaptation acts as a capacity-relief mechanism for the proton facility and not only as a tougher comparator. The allocator quantifies it directly, since the proton minutes released fall out of the same optimisation that produces the cohort mean.

With photon adaptation rationed, the relief is no longer a single number. It is the **exchange rate between the two budgets**, measured as the proton minutes released per photon adaptation minute purchased, and it is read off the same C_XT sweep that produces λ_XT. In price terms the relief is governed by the ratio λ_XT / λ_PT: a department gains more from the next photon adaptation minute than from the next proton minute exactly when that ratio exceeds one.

Version 4 reported this quantity as an upper bound, because photon adaptation was free by assumption and every displaced patient received XT-A. That bound is now the limiting case of the sweep as C_XT grows without bound, and it should be reported as the limit rather than as the estimate. The interior of the sweep is the quantity a centre would actually obtain, conditional on the assumed Δτ_XT.

### 8.6 Reference arm and default arm

XT-NA carries two roles that the design has so far treated as one. They are separated here, following the evaluator design, Section 6.3.

| Role                                                                       | What it must satisfy                                                                                   | Consequence of losing it                                                                                            |
|----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| **Reference arm**, the numeraire of ΔNTCP                                  | Identical across every patient, every policy and every configuration                                   | The zero point of every ΔNTCP value moves and continuity with the reference study’s published decomposition is lost |
| **Default arm**, what a patient receives when no capacity is spent on them | Assignable, and free on both budgets if the allocation is to be guaranteed no worse than the reference | Feasibility becomes conditional and a negative assignment becomes possible                                          |

The two coincide for almost every patient. They separate when the coverage screen removes a patient’s non-adapted photon plan, which A10 requires the screen to be capable of doing. The reference arm then retains the first role and loses the second: ΔNTCP for that patient is still measured against XT-NA, and XT-NA is still not something the patient can receive.

Three things follow.

- **The dominance argument of Section 5.1 lapses for that patient.** With no free assignable option, an optimal allocation may assign a strategy of negative utility. This is a correct answer, not a solver defect, and it is the only circumstance in which a negative utility can appear in a reported allocation.

- **The heuristic policies need a starting point.** P0, P1, P2a and P2b place unreferred patients on their default arm, defined as the cheapest assignable option with ties broken on utility, rather than on the reference arm. Where the reference arm is assignable the two definitions coincide and the policies are unchanged, which is verified by regression rather than asserted.

- **Nothing further is removed from their option set.** Under the no-harm decision of Section 8.3 the patient keeps every deliverable strategy and receives the least harmful of them. The alternative, enforcing no harm, would have deleted all of them and raised under Section 8.4 for a patient who has a deliverable plan.

**Reported quantities.** Three counts are emitted with every allocation, so that the option sets the allocator worked on are visible to a reader who cannot inspect them: strategies removed by the coverage screen, assignable strategies whose ΔNTCP is not positive, and patients with no free assignable option. The second is the diagnostic of how often adaptation or a changed schedule fails to help, which is distinct from how often it is selected. The third is what licenses or withdraws the statement that no patient is worse off than the reference.

## 9. Time model

Only Δτ, the difference in machine occupancy between an adapted and a non-adapted fraction, enters the capacity constraint. Components are therefore classified by whether they survive the difference. The classification below is written for protons; Section 9.1 states what carries over to photons.

| Component          | Enters Δτ?    |
|--------------------|---------------|
| Setup              | No            |
| Contouring         | Yes (+)       |
| Re-optimization    | Yes (+)       |
| Plan QA and checks | Yes (+)       |
| Beam delivery      | Yes (+ and −) |

Contouring and QA appear in both workflows but not in both daily budgets. Patient-specific QA is performed per plan. Both arms carry an initial plan of record generated on the pCT, verified once before treatment starts; that verification is common to both and cancels in the difference. In the adaptive arm a new plan exists at each adapted fraction, and its verification necessarily falls inside the session. The same holds for contouring. Both therefore enter Δτ with a positive sign rather than cancelling.

**The verification of an adapted plan is a computation, not a measurement.** Measurement-based patient-specific QA cannot be performed on a plan generated while the patient is on the couch, so online adaptive workflows verify through an independent secondary dose calculation. The clinical figure of just under 7 min for the adaptation step, including QA and plan assessment, is consistent only with that. The adaptation cost therefore remains inside the treatment session, τ captures all of it, and the single-constraint structure of Section 5.1 survives. This resolves the open item previously recorded here. Confirmation with the PARTICLE physicists is still worth obtaining, since the argument is structural rather than local.

Delivery time carries two effects of opposite sign that must be kept separate. Margin reduction shortens delivery, through fewer energy layers and spots. Hypofractionation lengthens the individual fraction, through higher MU, while shortening the course.

Decomposing τ rather than sweeping it as a scenario parameter is what allows the module to answer where engineering effort should be invested, which the reference study cannot. Since no measured Δτ exists for abdominal OAPT, the decomposition serves a second purpose: it is how a defensible envelope of plausible Δτ values is constructed, component by component with declared provenance, against which the threshold of Section 6.5 is compared. Which components are extractable from RayStation plan data and which must be modelled with clinical input is a question for the clinical supervisor.

**Cost is per fraction, plans are per block.** An adapted patient pays Δτ on every fraction of the course, while only one replan is performed per block, on that block’s repeat image. The reference study makes exactly the same choice, charging the adaptation time of one replan to all ten fractions of the block, and does not comment on it. It is stated here because a reader will otherwise ask. The fractions after the first in a block would in reality cost less, since the plan already exists, so charging all of them at Δτ is conservative in the direction of overstating the cost of adaptation. Since an adapted arm adapts every block, the occupancy of a strategy is:

occupancy = n_fx · (τ_0 + Δτ) for an adapted arm, n_fx · τ_0 otherwise

which is the reference study’s own accounting, recovered exactly. Version 5 wrote the occupancy per block to accommodate an adaptation vector; with the vector removed the per-block and per-course forms coincide and the per-course form is used.

**The conservatism is not symmetric between the two schedules.** The factor by which the per-fraction charge overstates the true replanning effort is the number of fractions per block. A standard schedule with two repeat images has ten fractions per block; a hypofractionated schedule adapted on in-room imaging has one. The per-fraction convention therefore overcharges the standard schedule relative to the hypofractionated one by roughly that factor, which biases the fractionation axis in favour of hypofractionation for a reason internal to the cost model. This runs against the first-block distortion of Section 4, which biases in the opposite direction. The two do not cancel in any controlled way and both are declared: A16 and A23 respectively. A per-replan accounting is required as a sensitivity bound, recorded as open decision 20.

### 9.1 The photon side

**The two cost distortions run in opposite directions and do not cancel.** The per-fraction charge of A16 and A19 overstates the replanning effort by the number of fractions per block, which biases in favour of the schedule with fewer fractions. The first-block convention of A23 banks organ sparing at zero modelled coverage risk over a block whose weight is one over the number of blocks, which biases in favour of margin reduction and therefore more strongly for the schedule with more blocks. The two act on different quantities, one on cost and one on utility, so no cancellation should be assumed. Open decisions 20 and 21 record the bounding computations; until both are run the net direction is unknown.

The photon adapted arm consumes photon adaptation minutes with the same per-course structure:

occupancy_XT = n_fx · Δτ_XT for XT-A, zero for XT-NA

Three differences from the proton expression are deliberate.

- **The baseline session does not appear.** Photon delivery is unconstrained, so only the increment is charged. No photon baseline session length is required by the design, which is why the extractor is unchanged on this point.

- **Δτ_XT is an independent variable, as Δτ_PT is.** No clinical on-couch adaptive proton workflow exists for the abdomen, and the photon literature offers one anchor of the right order, roughly 16 additional minutes per adaptive pelvic photon fraction reported by McComas et al. That anchor places the sweep range; it is not adopted as a measured value for this indication.

- **The component decomposition of Section 9 is not repeated.** For photons the adaptation step is re-contouring, re-optimisation and verification, and the arguments about which components survive the difference are the same in structure. Whether measurement-based verification is feasible within a photon session, which A15 answers negatively for protons, is a question for the clinical partners and is recorded in Section 12.

The two adaptation times are separate axes of the study rather than one. Section 5.7 of the road document describes the resulting plane.

## 10. Fractionation

### 10.1 Formulation

Fractionation enters as an additional component of the strategy tuple. The MCKP absorbs it without modification. The difficulty is in what it does to u and τ.

**Biological side.** Changing (n, d) changes tumor and OAR EQD2 differently, because alpha over beta differs.

**Capacity side.** Under a closed cohort with a fixed patient list, shortening a course frees capacity that has no new claimant, since no additional patient can be admitted. Making the capacity dimension meaningful requires replacing the per-day constraint by a horizon-total one:

Σ_p Σ_s n_ps · τ^PT_ps · x_ps ≤ C_PT,horizon

and likewise for the photon adaptation budget. The cost of a strategy becomes total occupancy over the course rather than per day, so hypofractionation and adaptation compete on equal terms within each resource, and each multiplier prices them in the same units.

**Where the freed capacity goes.** In a closed cohort the capacity released by hypofractionation can be spent in exactly two ways: upgrading an existing patient to more adaptation, on either modality, or moving a patient off the photon arms onto protons. The second is the displacement channel of the reference study running in reverse, and it exists only because a photon strategy sits inside Sp at zero proton cost. Without a photon option inside the option set, hypofractionation would carry no capacity value at all in this model. This mechanism is what makes the cohort-composition channel representable in a fixed-cohort formulation and should be stated rather than left to emerge.

### 10.2 The daily and horizon constraints are one constraint

Under stationary operation with staggered starts, daily and horizon accounting are the same statement. Modelling the number of patients concurrently under treatment as L = r · W, with r the start rate and W the course duration in days, and one fraction per patient per day, the daily load is L · τ averaged over the mix, and the horizon total is that quantity multiplied by the horizon length. Little’s law is class-agnostic, so heterogeneous fraction counts across strategies do not break this: with classes indexed by strategy, the concurrent load is the sum over classes of r_s n_s, and nothing requires n to be common.

What remains is **one shadow price per resource**, each reportable in two units. Utility per machine-minute per day answers whether a workflow change costing Δτ per fraction is worth it. Utility per machine-minute over the horizon answers whether a schedule is worth its total occupancy. Both are reported; for a given resource they are not independent quantities. λ_PT and λ_XT are independent quantities, since they price different machines.

The argument of this section applies unchanged to the photon adaptation budget, since Little’s law is class-agnostic and the photon adapted patients are simply another class.

### 10.3 The diagnostic that does exist

**Retired at version 6.2.** This section checked the mean-field constraint of Section 10.2 against a peak-occupancy re-solve, on the grounds that a patient adapted in some blocks and not others occupies a short session on some days and a long one on others within the same course. A24 makes that situation unrepresentable: a course is adapted throughout or never, so occupancy is constant per day within a given patient's own course under a given scheme, and no within-course variation remains for a peak-occupancy bound to catch. What survives, patients on different schemes or different adaptation decisions mixed in the same day's census, is population heterogeneity of exactly the kind Section 10.2 already handles by class, so no separate check is needed for it either. The mechanism this section tested no longer exists in the version 6 formulation; see A2, Section 11.

### 10.4 Schedule equivalence without a TCP model

Candidate schedules are restricted to those **sanctioned by clinical protocol** for the indication. Equivalence between schedules therefore rests on trial evidence, not on a linear quadratic conversion of the tumor prescription.

Three consequences:

- Tumor alpha over beta is **not** required, since no conversion between tumor prescriptions is needed. It is nonetheless declared and used to report target EQD2 per arm as a descriptive safeguard.

- OAR alpha over beta **is** required, since NTCP models are fitted at 2 Gy per fraction and any cross-schedule comparison requires conversion of OAR dose to EQD2.

- Repopulation is neglected, which is internally consistent with not modelling TCP. The model will not penalize a schedule that lengthens overall treatment time.

**Sanctioned schedules are available**, following the supervisory decision, so the fractionation dimension is clinically live and equivalence rests on clinical consensus rather than on a linear quadratic conversion of the tumour prescription. Target EQD2 is reported per arm at a declared tumour alpha over beta as a descriptive safeguard, so that any residual mismatch in tumour effect between arms is visible; it is reported for completeness and not used to assert equivalence.

### 10.5 Adaptive fractionation, deferred

**Out of scope for paper 1.** Under the version 6 decision the schedule, like the modality and the adaptation workflow, is fixed at prescription on the planning CT and is not revisited during the course. The material below described a design in which the compression decision is re-asked at every repeat image, and it describes something this study does not do. It is retained as the specification of the natural continuation and moves to the reinforcement learning publication, where receding-horizon reallocation is the object rather than an extension.

Two consequences for the present document. The pragmatic simplification of the road document, Section 4.4, stops being a simplification and becomes a property of the design: a mid-course change of schedule is not evaluated because the design does not contain one. And paper 1 answers which patient receives which workflow, not when within a course to act, so the right-time framing of the work package belongs to the second publication. That division should be confirmed at supervision rather than left implicit.

The retained specification follows.

The pCT verdict on whether compression is achievable need not be final, because the geometry that blocks it may not persist. Tumor regression or a different bowel configuration at rCT1 may open a window that was closed at planning. The natural response is to re-ask the question at every rCT, in both directions, with dose accumulated continuously. The tractable implementation is receding-horizon reallocation: re-solve the same MCKP at each rCT, with each patient’s remaining course as the decision and accumulated voxel-wise BED as carried state. Completed patients drop out; committed patients have reduced option sets. This preserves the entire formalism and adds a loop, not new mathematics. It is not optimal in the dynamic-programming sense, since it does not anticipate future options, but it is transparent and is what a clinic could implement.

Four structural consequences, which the second publication inherits: costs are no longer known at time zero, since a patient’s total occupancy depends on whether compression becomes available at a future rCT; sunk fractions constrain the future, since the dose already deposited is not reversible and every remaining option must respect the residual OAR budget; adaptation and compression may be complements or substitutes, since compression shortens the window for further degradation while carrying more dose per fraction and therefore a higher cost of residual geometric error; and the timing of compression trades capacity against flexibility, since compressing early frees more machine time while compressing late preserves more fractions with which to respond to a later change.

### 10.6 Anatomical site: two candidates

Recorded as options with their consequences. Neither is adopted, and nothing in this document depends on the choice being made yet.

| Criterion                                              | Pancreas                                                                                                                                                                                                                          | Adrenal                                                                                                                                                                                                                               |
|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Two schedules sanctioned for the same clinical setting | Present. In locally advanced disease both conventionally fractionated chemoradiation and five-fraction stereotactic treatment are recommended, which is the condition A5 requires                                                 | Not equivalent. The setting is oligometastatic and the schedule set is institutional rather than guideline-fixed                                                                                                                      |
| Clinical rationale for adaptation                      | Adaptation is recommended for dose-escalated stereotactic treatment in the current guideline                                                                                                                                      | Very strong empirically. A published magnetic-resonance-guided series reports adaptation in essentially every fraction, which is an argument for adaptation and simultaneously leaves the adaptation decision with almost no variance |
| Clinical rationale for a proton arm                    | Present in the literature                                                                                                                                                                                                         | Weak. Proton treatment of adrenal lesions is rare                                                                                                                                                                                     |
| Cohort with protons and repeat imaging                 | To be verified with the clinical partner                                                                                                                                                                                          | Unlikely                                                                                                                                                                                                                              |
| Endpoint models                                        | Duodenum, stomach and bowel. Evaluable on voxel-wise EQD2 with a declared α/β, therefore fractionation-correctable, but on a thin empirical base                                                                                  | Thinner still                                                                                                                                                                                                                         |
| Target volume comparability across schedules           | Weak. Conventional treatment includes elective coverage of regions at risk of microscopic disease while stereotactic treatment does not, so a comparison of the two protocol schedules confounds fraction size with target volume | Not applicable in the same form                                                                                                                                                                                                       |
| Intent                                                 | Curative or near-curative                                                                                                                                                                                                         | Oligometastatic, with competing mortality                                                                                                                                                                                             |

**The consequence that reaches furthest.** Fractionation-correctability of the endpoint models is not only a constraint that follows from the site; it is a criterion for choosing it. If the organs that drive the endpoint at a candidate site have no model evaluable on voxel-wise EQD2 with a declared α/β, the fractionation axis does not exist at that site.

**A dilemma that does not resolve itself at either site.** Adaptation is recommended for dose-escalated stereotactic treatment, and dose escalation is the point at which the two schedules stop being isoeffective on the target. Choosing the non-escalated schedule preserves A5 and weakens the clinical rationale for adaptation; choosing the escalated one strengthens the rationale and forfeits A5, which without a TCP model cannot be repaired. The choice must be made explicitly and declared.

## 11. Assumptions register

| ID  | Assumption                                                                                                                                                                  | Status                                                                                                                                                                   | Risk                                                                                                                                                                                                                  |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A1  | Anatomy on rCTj represents the whole block of fractions following it                                                                                                        | Inherited from reference study                                                                                                                                           | Makes the problem combinatorial rather than continuous                                                                                                                                                                |
| A2  | Course-averaged occupancy is a valid conversion from per-fraction time to daily load                                                                                        | **Retired as a distinct check at 6.2** (10.3, void). Exact under Little's law for heterogeneous classes in steady state (10.2); A24 leaves no within-course variation for a separate peak-occupancy bound to test                                                                                        | —                                                                                                                                                                       |
| A3  | Photon **delivery** is unconstrained; photon **adaptation** is constrained by a budget C_XT                                                                                 | Revises the version 4 decision. Taken as a design decision, pending supervisory confirmation                                                                             | Every patient is entitled to XT-NA, so the allocation is always feasible. Introduces a second shadow price and makes the relief of Section 8.5 a function of C_XT rather than an upper bound                          |
| A4  | Every arm is generated to protocol on the image available at planning time                                                                                                  | Design constraint on plan generation                                                                                                                                     | Must be demonstrated per arm, not asserted                                                                                                                                                                            |
| A5  | Protocol-sanctioned schedules are clinically equivalent for tumor control                                                                                                   | Confirmed available at supervision. Rests on clinical consensus, not on the linear quadratic model                                                                       | Limits the admissible set to sanctioned schedules. Target EQD2 reported descriptively                                                                                                                                 |
| A6  | Repopulation neglected                                                                                                                                                      | Accepted, consistent with no TCP model                                                                                                                                   | Model will not penalize lengthened schedules                                                                                                                                                                          |
| A7  | Linear quadratic model valid for OAR EQD2 conversion over the fraction sizes considered                                                                                     | To be checked against real cases                                                                                                                                         | Applies to OARs only, not to the tumor claim                                                                                                                                                                          |
| A8  | Toxicity endpoints independent in the union probability                                                                                                                     | Inherited from reference study                                                                                                                                           | False; accepted as best available                                                                                                                                                                                     |
| A9  | Adapted plans generated offline are equivalent in quality to those an online workflow would produce                                                                         | Inherited from reference study                                                                                                                                           | Acknowledged there as requiring further investigation                                                                                                                                                                 |
| A10 | Photon dose is recomputed on the rCTs and screened on the same criterion as the proton arms                                                                                 | Amends the reference study, which assumes planned photon dose represents delivered dose                                                                                  | Asymmetric screening would bias ΔNTCP against protons                                                                                                                                                                 |
| A11 | Coverage is judged **per block** on the nominal dose of the plan delivered in that block                                                                                    | The accumulated criterion is rejected as permissive in the wrong direction                                                                                               | Stricter criterion than previous one                                                                                                                                                                                  |
| A12 | No harm is judged on the union scalar rather than per endpoint, and is **reported rather than enforced**                                                                    | Decision of the doctoral candidate, pending supervisory confirmation. Enforcement is redundant wherever XT-NA is assignable and harmful where it is not, per Section 8.3 | A strategy worsening one endpoint may be selected. Harmful strategies remain in the option set and are declined by dominance rather than by removal, which must be stated in the manuscript rather than left implicit |
| A13 | Occupancy depends only on the number of adapted blocks, not on which blocks                                                                                                 | Follows from the time model                                                                                                                                              | If false, the dominance collapse in Section 6.3 does not hold                                                                                                                                                         |
| A14 | Margin level is determined by the adaptation vector: an adapted block carries the reduced-margin plan on its repeat image, a non-adapted block the clinical-margin pCT plan | Follows from the planning workflow, with a single adaptive margin level adopted at supervision                                                                           | Robustness contributes no independent degree of freedom. Removes the conservative fallback under coverage failure                                                                                                     |
| A15 | Patient-specific QA of an adapted plan is an independent secondary dose calculation and consumes no beam time                                                               | Structural argument, consistent with reported adaptation times. Confirmation with PARTICLE physicists outstanding                                                        | If false, part of the adaptation cost lands outside the session and τ alone no longer captures it                                                                                                                     |
| A16 | Every fraction of an adapted block carries the full Δτ, though only one replan is performed per block                                                                       | Inherited from the reference study                                                                                                                                       | Conservative: overstates the cost of adaptation                                                                                                                                                                       |

| ID  | Assumption                                                                                                                                                                                             | Status                                                                                                                                                                                                                                | Risk                                                                                                                                                                                                                                                                                                                             |
|-----|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A17 | The photon adapted arm is charged only the adaptation increment Δτ_XT, not a baseline session                                                                                                          | Follows from A3. Photon delivery is not binding, so charging the session would price a resource declared unconstrained                                                                                                                | If photon delivery is in fact binding at the partner centre, C_XT understates photon demand and λ_XT is too low                                                                                                                                                                                                                  |
| A18 | Photon adaptation is decided per block, on the same block structure as protons                                                                                                                         | Design decision, symmetric with the proton arm                                                                                                                                                                                        | If photon adaptation is in practice an all-or-nothing course-level decision, the photon chain has two rungs rather than B + 1 and intermediate photon options are not reachable                                                                                                                                                  |
| A19 | Every fraction of an adapted photon block carries the full Δτ_XT, as A16 assumes for protons                                                                                                           | Symmetric with A16                                                                                                                                                                                                                    | Conservative in the same direction: overstates the cost of photon adaptation, therefore understates the relief of Section 8.5                                                                                                                                                                                                    |
| A20 | C_XT is a policy parameter of the study rather than a measured facility quantity                                                                                                                       | No measured anchor exists for this indication                                                                                                                                                                                         | Handled by reporting λ_XT and Δτ\* as functions of C_XT rather than at a single value. A single reported value would be a function of an assumption                                                                                                                                                                              |
| A21 | Every patient retains an assignable option that is free on both budgets, normally XT-NA                                                                                                                | Expected to hold for the whole cohort, since XT-NA is not expected to fail the coverage screen in this indication. Not guaranteed, since A10 requires the screen to apply to the photon arms. Reported per cohort rather than assumed | Where it holds, no allocation can make a patient worse than the reference and the statement is a property of the formulation, not a finding. Where it fails for a patient, feasibility is conditional and a negative ΔNTCP assignment becomes possible for that patient                                                          |
| A22 | A patient whose reference arm is not assignable receives their cheapest assignable option under the heuristic policies, and the referral threshold is still applied to ΔNTCP against the reference arm | Decision of the doctoral candidate, pending supervisory confirmation: the published referral rule is retained unmodified. The exact solvers are unaffected, since they optimise over the assignable set directly                      | The heuristics are approximate for such patients: one whose default arm is worse than the reference is not referred on that account alone. Under A21 the case is not expected to occur, so the choice is not expected to affect any reported quantity. If a real case appears, the rule is revisited before the results are read |

### 11.1 Amendments at version 6

The rows below are superseded or added by the decision that modality, adaptation and fractionation are all chosen at prescription on the planning CT. The original rows are left in place above so that the change is visible; where the two conflict, this subsection governs.

| ID  | Status at version 6                                                                                                                                                                                                  |
|-----|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A13 | **Retired.** Occupancy no longer depends on an adaptation count, because there is no adaptation vector. Occupancy is per course and takes two values per modality per scheme                                         |
| A14 | **Superseded by A25.** Margin is a property of the arm, not of the block                                                                                                                                             |
| A16 | **Retained**, with its asymmetry between schedules now declared in Section 9. The per-fraction charge overstates the replanning effort by the number of fractions per block, which differs between the two schedules |
| A18 | **Superseded.** Photon adaptation is a course-level decision, symmetric with the proton arm as before. The risk column of the original row anticipated this outcome and it has occurred                              |
| A19 | **Retained**, symmetric with A16                                                                                                                                                                                     |
| A21 | **Amended.** The guarantee is that every patient retains at least one assignable option free on both budgets. Under two fractionation schemes there may be two, since XT-NA is free under either schedule. See A27   |

| ID  | Assumption                                                                                                                                               | Status                                                                                                                                                                           | Risk                                                                                                                                                                                                                                                                                                                                                                                                 |
|-----|----------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A23 | The first block is evaluated on the planning anatomy, so its dose is the nominal planned dose and no arm carries modelled anatomical degradation over it | Inherited from the reference study, whose accumulation weights the pCT dose by the first ten of thirty fractions                                                                 | Not symmetric in effect. The reduced-margin arms bank organ sparing over that block at zero modelled coverage risk, so the distortion favours margin reduction, which is the larger of the two benefit terms. It scales as one over the number of blocks and is therefore stronger for the standard schedule than for a hypofractionated schedule adapted per fraction. Bounding is open decision 21 |
| A24 | An adapted arm adapts at every block and a non-adapted arm never adapts                                                                                  | Supervisory decision, version 6                                                                                                                                                  | Partial adaptation is not representable, so the study cannot report whether early or late adaptation carries more benefit, and the closed form of Section 6.5 speaks about the survival of one rung rather than about intermediate counts                                                                                                                                                            |
| A25 | The reduced margin is a property of the adapted arm and applies from the first fraction, on the pCT plan                                                 | Supervisory decision, version 6. Matches the reference study, whose reduced setup error plans are planning-stage plans delivered over the first block of every adaptive workflow | Defensible only under A9, in which the modelled workflow is systematic online adaptation and the block structure is an artefact of imaging availability rather than of the workflow. Under a literal offline reading, the first block of an adapted arm is delivered at reduced margin with no imaging, which no centre would do                                                                     |
| A26 | The indication is abdominal and the anatomical site is not yet fixed                                                                                     | Two candidates carried, pancreas and adrenal. Open decision 19                                                                                                                   | The endpoint set, the availability of fractionation-correctable models, the cohort size and the clinical rationale for a proton arm all depend on it. Nothing downstream of endpoint selection can be fixed before it is resolved                                                                                                                                                                    |
| A27 | XT-NA is free on both budgets under either fractionation schedule, so a patient may hold two zero-cost options                                           | Follows from A3 and from the fractionation axis                                                                                                                                  | Any positive utility on a free arm enters the population mean at zero capacity cost, and that component is not a result about capacity. It must be reported separately from the capacity-constrained component. If the utility of the hypofractionated free arm is non-positive for every patient, the arm is strictly dominated and the issue is empty; that is what open decision 18 turns on      |

## 12. Open decisions

Items 1, 2, 7, 8 and 9 of version 3 are closed by the supervisory decisions recorded in Section 13. What remains:

| ID  | Question                                                                                                                                                                     | Blocks                                                |
|-----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------|
| 3   | PARTICLE operating model: hours per day, rooms, beam sharing, clinical slot length. Which Δτ components are extractable from RayStation plan data and which must be modelled | The plausible Δτ envelope, not the formulation        |
| 7b  | Whether criteria beyond V95% below 95 per cent are added to the coverage screen                                                                                              | Nothing structurally; the screen already takes a list |
| 10  | Endpoint selection, constrained to models admitting a dose-per-fraction correction                                                                                           | The entire fractionation axis                         |

Five items are opened by the second resource.

| ID  | Question                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Blocks                                                                                              |
|-----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| 11  | Supervisory confirmation that photon adaptation may be rationed, revising the version 4 decision that photon capacity is unconstrained                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Nothing immediately; the formulation degrades gracefully to version 4 at C_XT growing without bound |
| 12  | Plausible range for Δτ_XT, and whether photon plan verification is measurement-based or computational within a session                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | The sweep range, not the formulation. The analogue of A15 on the photon side                        |
| 13  | The reference value C_XT^ref, to be fixed with the clinical partners and the supervisor, analogous to the 480 proton minutes of the reference study. The sweep axis itself is settled: normalised to cohort photon adaptation demand, minutes secondary                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | The plane of Section 6.5 of the road document is evaluated at C_XT^ref                              |
| 14  | **Resolved.** Convention 3 of Section 5.3: heuristics rank proton upgrades only; the photon budget is spent by ΔNTCP order. See Section 5.3 for the reasons                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |                                                                                                     |
| 15  | **Resolved.** The exact two-resource solve uses an integer linear program (scipy.optimize.milp, HiGHS backend) as the reference solver, and the LP relaxation is obtained from the same model with integrality dropped, whose duals supply (λ_PT, λ_XT) for T7 directly. The 1D dynamic program and the greedy LP are retained unchanged as the independent cross-check at C_XT = 0, which is test T8. Reasons: with two constraints an ILP is simpler to state correctly than a 2D dynamic program, so the reference implementation should be the one hardest to get wrong; the duals arrive from the solver rather than from bespoke bookkeeping; and the option-count structure that made the 1D DP attractive remains available as a later optimisation if solve time ever matters, which at cohort scale it will not. The structure is simpler at version 6 than the reasoning above assumed: the photon axis takes two values per patient per schedule rather than B + 1, which strengthens the conclusion without changing it |                                                                                                     |

Two items were opened by the separation of the reference arm from the default arm in Section 8.6. Both are closed by decision of the doctoral candidate, **pending supervisory confirmation**, and are retained here with their reasoning. Item 16 revises a convention present since version 1 of the evaluator design and carries an ethical framing, so it is flagged for confirmation on the same footing as A3.

| ID  | Question                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Blocks |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| 16  | **Resolved by the doctoral candidate, pending supervisory confirmation.** The no-harm screen becomes a **reported diagnostic** rather than an enforced removal. Enforcement is redundant wherever XT-NA is assignable, since a free zero-utility arm already dominates every strategy of negative utility in both the integer problem and its relaxation, and it changes the answer only for patients whose XT-NA the coverage screen has removed, where it deletes deliverable options and can strand a patient who has a treatable plan. See Section 8.3. Consequence for the manuscript: the protection of the individual is a property of the option set and must be argued, not asserted as a screen |        |
| 17  | **Resolved by the doctoral candidate, pending supervisory confirmation.** The published referral rule is retained unmodified: the threshold is applied to ΔNTCP against the reference arm, including for a patient whose reference arm is not deliverable. P0 and P1 remain faithful reproductions of current practice and of the reference study, which matters because P0 anchors the P3 − P0 headroom. Under A21 the case is not expected to occur on any patient in this cohort. See A22                                                                                                                                                                                                              |        |

**Resolved by the doctoral candidate.** Displaced patients are retained in the denominator of the cohort mean, contributing their XT NTCP: comparability with the reference study, which divides by 14 throughout. States the mean as an intention-to-treat quantity over the referred population rather than over the treated one.

**Items opened at version 6.**

| ID  | Question                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Blocks                                                                                                   |
|-----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| 18  | **How to treat a free hypofractionated photon arm.** XT-NA under the hypofractionated schedule costs nothing on either budget, so if its utility is positive for a patient it is selected at no capacity cost. Three treatments remain live, since a fourth, a third budget row for photon stereotactic delivery, is excluded: a five-fraction course releases linac time rather than consuming it, so that row would price a resource that is not actually scarce. (A) An eligibility threshold ε on the gain of the hypofractionated arm over the same arm at standard fractionation, applied before the solve as a filter on the option set. (B) A uniform utility penalty π applied to every hypofractionated option, which sits inside the objective and reads as the price of a schedule change, reportable beside λ_PT and λ_XT. (D) Exogenous clinical eligibility, in which the hypofractionated arms exist only for patients meeting the protocol criteria for the indication. None of the three is adopted here, since the choice is for supervision. The trade-offs, and the fact that A/B and D are not mutually exclusive, are recorded in Section 12.1 | The reporting split between the zero-cost and the capacity-constrained components of the population mean |
| 19  | **Anatomical site.** Two candidates are carried, pancreas and adrenal. Section 10.6 records what each implies                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Endpoint selection, cohort size, plan budget, and every quantity downstream of them                      |
| 20  | **Per-replan cost accounting as a sensitivity bound.** A16 and A19 charge Δτ to every fraction of an adapted block, which overstates the replanning effort by the number of fractions per block and therefore by a different factor for each schedule. The single-scheme threshold under this accounting is now in Section 6.5; the cross-schedule comparison it does not resolve needs B for the hypofractionated schedule, pending decision 23                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | The credibility of any cross-schedule comparison of adaptation cost                                      |
| 21  | **Resolved by the doctoral candidate.** First block evaluated on the planning anatomy, for every arm: the convention of the reference study, followed for comparability. The distortion this leaves unmeasured favours the reduced-margin arms and scales as one over the number of blocks; its direction is known, its size is not |  |
| 22  | **Resolved by the doctoral candidate.** The reduced-margin non-adapted diagnostic is not computed: a reduced-margin plan delivered without adaptation is clinically incoherent. The margin-reduction and adaptation components of the benefit are therefore separated by reference to the published lung cohort rather than within this cohort |  |
| 23  | **Block granularity for the hypofractionated schedule, and its plan budget.** If a block is a fraction on a five-fraction schedule, an adapted arm requires five replans, and the plan budget rises from sixteen to twenty-two per patient. Coarser blocks restore parity with the standard schedule at the cost of modelling less than daily adaptation in a setting where the photon literature reports adaptation in nearly every fraction                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Whether the fractionation axis is affordable in planning hours                                           |
| 24  | **Handling of the coverage screen, and the count of patients left with no free option.** The screen removes an arm for the whole course under a schedule when the plan delivered in any block fails coverage (Section 8.2). Three things are unsettled. Whether removal for the whole course is the right consequence of a single-block failure, or whether a per-block fallback should be modelled instead. What the fallback is when XT-NA itself is removed, since A21 guarantees a free option and XT-A is not free, so a commitment on C_XT is incurred before the policy runs. And how often this occurs, measured as the count of patients for whom neither XT-NA under the standard schedule nor XT-NA under the hypofractionated schedule survives the screen. That count is what makes the no-harm property of Section 8.3 an empirical statement rather than a structural one, and it must be computed before any manuscript claim rests on it | Whether the no-harm property holds cohort-wide; the fallback logic; A21 and A27 |
| 25  | **Dose engine and cross-modality reporting conventions.** All dose for paper 1 is computed in RayStation and imported; OpenTPS performs no dose calculation for this study (evaluator design, Section 3, E16). Which RayStation dose algorithm generates the proton plans, analytical pencil beam or Monte Carlo, and the reporting conventions for both modalities, RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin, are not yet fixed | Bears on the study's premise: analytical proton dose is least reliable in the heterogeneous abdomen, and the resulting error is systematic rather than random, falling on the arm whose anatomical degradation the study measures |
| 26  | **Scriptability of adapted-arm replanning.** PT-A and XT-A adapt at every block, so each patient needs one fresh inverse optimisation per block per adapted arm rather than a recomputation of an existing plan on new anatomy. Whether a fixed objective template can be scripted in RayStation and applied without intervention, and whether the resulting plans are clinically plausible, is open. Decision 23 fixes the replan count at sixteen or twenty-two per patient | Whether plan quality becomes a function of operator effort, which is not constant across arms and would enter ΔNTCP as a confounder on the primary endpoint |

### 12.1 The three live treatments of the free hypofractionated arm

Recorded so that the choice can be made at supervision without reconstructing the argument. A fourth treatment, C below, is excluded rather than merely unadopted. None of the three live treatments is adopted.

| Treatment                                             | Where it acts                       | What is reported                                                               | Principal objection                                                                                                                                                                                                                      |
|-------------------------------------------------------|-------------------------------------|--------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A. Eligibility threshold ε                            | On the option set, before the solve | Population mean and eligible count as functions of ε                           | ε is a constant chosen by us, and it turns P3 from the optimum into the optimum of a constrained problem. It reintroduces on the fractionation axis the fixed cohort-level rule that this study exists to replace on the adaptation axis |
| B. Uniform penalty π on every hypofractionated option | Inside the objective                | Population mean and cohort composition as functions of π, beside λ_PT and λ_XT | π is unmeasured. It is preferable to A in that it compares against every alternative rather than against one nominated comparator, and it stays inside the price language                                                                |
| C. Third budget row for photon stereotactic delivery (**excluded**) | On the constraint set               | —                                                        | A five-fraction course releases linac time rather than consuming it, so this row would price a resource that is not actually scarce. Whatever scarcity exists on the photon side lies in the adaptation, already priced by C_XT. Retained here for the record rather than deleted |
| D. Exogenous clinical eligibility                     | On the option set, before the solve | Eligible fraction of the cohort                                                | Requires the protocol criteria for the indication from the clinical partners, and may leave the hypofractionated axis thinly populated                                                                                                   |

**A and D are not mutually exclusive.** D fixes the option set on clinical grounds; A or B can then be applied on top of it, reporting how much of the population mean is fragile to the cost of a schedule change. They answer different questions and can be combined rather than chosen between.

**A prior question that may empty the problem.** If the utility of the free hypofractionated photon arm is non-positive for every patient, it is strictly dominated by XT-NA at standard fractionation, which costs the same and is worth more, and none of the three live treatments is needed. The sign is not predictable in advance: the equivalent dose penalty of a large fraction size falls on the high-dose region, while an endpoint driven by mean dose over a parallel organ may still favour the hypofractionated arm because the irradiated volume is smaller. It is therefore an organ-dependent question and can be answered parametrically, by mapping the sign of the utility over the plausible range of α/β and of the volume parameter for a family of synthetic dose-volume histograms. That computation requires the endpoint models and therefore the site, so it is scheduled immediately after open decision 19 is resolved.

**The same structure appears on the adaptation axis and should be presented with it.** A patient’s photon chain and their proton chain are priced on different budgets, so a strategy that is free on both is always dominant among the zero-cost options. Whichever treatment is chosen for the fractionation axis should be checked against the photon axis before it is adopted.

## Appendix F. Fractionation

Consolidated in the road document, Appendix F. The material specific to this module is subsection F.6 there.

Sections 13 to 16: version history, moved to `CHANGELOG.md`.

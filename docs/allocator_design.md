# Capacity and Allocation Module

Version 7.2. Version history is in `CHANGELOG.md`. Project status and open items are in `STATE.md`.

## 1. Purpose and scope

This document specifies the **allocator**, which assigns a treatment strategy to each patient of a cohort under two capacity constraints: proton machine time and photon adaptation time.

Two companion documents specify its inputs. The **extractor** gathers per-patient, per-plan and per-facility quantities. The **evaluator** composes block-level dose into per-strategy accumulated dose, evaluates NTCP and produces the admissibility diagnostics. The allocator consumes utilities and occupancies per (patient, strategy), together with the diagnostic counts it reports, and never touches a dose grid.

The allocator answers two of the three questions that "capacity and allocation" can denote:

- **Strategy assignment.** Given a cohort and the two capacities, which patient receives which strategy?
- **Capacity design.** What is a minute of each resource worth, in outcome units, at a given load? Two resources are priced, so the question has two answers, λ_PT and λ_XT.

The third question, **scheduling** (which fraction occupies which slot on which day), is out of scope.

## 2. Relation to the reference study

Borderías-Villarroel et al. quantify how the extra time per fraction required by online adaptive proton therapy (OAPT) erodes the NTCP benefit of protons, because a capacity-limited centre can treat fewer patients when sessions lengthen. Their method:

- A cohort of 14 lung patients, one XT plan and three IMPT plans per patient (clinical robustness, 4 mm and 2 mm setup error), with adaptation simulated on two repeat CTs and dose accumulated on the planning CT;
- A single-room centre with 480 min/day and a baseline of 14 patients, giving 34.2 min per fraction;
- Seven scenarios indexed by the extra time per adapted fraction, from instantaneous to +25.7 min. In scenario S_i, i patients are displaced to photons;
- Displaced patients are chosen as those with the lowest ΔNTCP over the union of the three modelled complications;
- The outcome is the cohort-mean ΔNTCP per endpoint against a non-adaptive XT reference.

**What to keep.** The cohort-level ΔNTCP currency; the XT non-adaptive reference; the coupling between adaptation time and machine capacity; the accumulated-dose basis for NTCP; the treatment of the extra time per adapted fraction as the independent variable of the study; and the handling of plan admissibility. An arm that loses target coverage on a repeat image is rescued by offline replanning at unchanged margin rather than abandoned, together with the recomputation of dose on the repeat images that detecting the failure requires.

**What we change.** Three rigidities limit what their formulation can express.

- **R1.** One workflow is applied to the whole selected subset, so the cohort cannot contain adapted and non-adapted proton patients at once.
- **R2.** Time cost per patient is uniform, so ranking by ΔNTCP is optimal within their assumptions but not in general.
- **R3.** The photon comparator is non-adapted and free, so the formulation cannot express a centre that can adapt some photon patients but not all.

This study relaxes each one. R1 is relaxed by letting the workflow differ between patients, and R2 follows from the formulation. R3 introduces the second resource: the photon arm splits into a free non-adapted arm and an adapted arm that consumes a rationed photon adaptation budget. Fractionation, which the reference study held at 30 fractions, becomes a per-patient decision. Whether non-adapted protons carry allocative value alongside adapted protons is governed by a threshold in adaptation time, derived in Section 6.2.

**Plan admissibility is inherited.** The reference study rescues any arm that loses target coverage on a repeat image by offline replanning at unchanged margin, the photon arm included. This requires photon dose to be recomputed on the repeat images (A10), and this study does the same. The paper does not describe the rescue, because it is standard clinical practice, and its statement that planned photon doses were representative of the delivered dose means that no delivery reconstruction (log files, measurements) was performed, not that no rescue was applied. Its corresponding author, the supervisor of this project, confirmed the procedure. The manuscript states it explicitly, since a reader of the paper alone would not infer it. Two consequences follow. A ranking on NTCP alone would be unphysical, since a plan below the acceptance criterion could not be delivered. And the arms on both sides of the step-ratio derivation of Section 6.2 are constructed as in the reference study, which is what lets the derivation recover the reference study's break-even condition.

**Adaptation model.** As in the reference study, the workflow being simulated is on-couch adaptation, and adaptation lengthens the treatment session and therefore consumes machine capacity. Section 4 states what the block structure represents.

## 3. Related work and positioning

Three largely disjoint literatures bear on this problem.

**Model-based selection.** The Dutch national indication protocols select patients by comparing photon and proton NTCP profiles against **fixed** per-endpoint ΔNTCP thresholds. This is a per-patient rule with no capacity term, and the thresholds are set by national policy rather than derived from a facility's load. We adopt the NTCP-comparison logic but not the fixed threshold.

**Capacity-aware allocation.** Loizeau et al. allocate proton *fractions* rather than patients, exploiting the nonlinearity of NTCP so that early proton fractions carry more benefit than later ones. Papp and Unkelbach make selection dynamic under stochastic arrivals and derive facility-state-dependent ΔNTCP thresholds. In each, a proton slot is a fixed, homogeneous unit; its *duration* is not a decision variable.

**Throughput and workflow timing.** Session and delivery times are measurable and patient-dependent. Spot-scanning delivery time increases with total target volume and accounts for roughly 30 to 40 per cent of total treatment time for targets above 200 cm³. Clinical daily adaptive proton therapy at PSI averaged about 23 min per session (range 15 to 30), of which adaptation including QA and plan assessment averaged just under 7. McComas et al. reported roughly 16 additional minutes per adaptive pelvic photon fraction. No clinical on-couch adaptive proton workflow exists for the abdomen, so no measured value of the extra time per adapted fraction is available for the site of this study; the quantity is treated as the independent variable throughout.

**Robustness and adaptation rate.** Badiu et al. showed that increased plan robustness reduces the adaptation rate at the cost of higher OAR dose. The two arm families of this design sit at the two ends of that trade-off: the non-adapted arms carry clinical robustness and replan only when coverage fails, while the adapted arms carry reduced robustness and replan at every block.

## 4. Notation and definitions

| Symbol | Meaning |
|---|---|
| p | patient index, p = 1, …, P |
| s | strategy index, s ∈ S_p |
| k | toxicity endpoint index |
| u_ps | utility of strategy s for patient p: union ΔNTCP against XT-NA |
| n_ps | number of fractions of strategy s |
| τ^PT_ps | proton machine occupancy per fraction, minutes. Zero for photon strategies |
| τ^XT_ps | photon adaptation time per fraction, minutes. Zero for proton strategies and for XT-NA |
| τ_0 | baseline proton session length, minutes, per schedule |
| Δτ_PT | extra proton machine time per adapted fraction, minutes |
| Δτ_XT | photon adaptation time per adapted fraction, minutes |
| C_PT | proton machine minutes available over the horizon (Section 10.2) |
| C_XT | photon adaptation minutes available over the horizon |
| x_ps | binary decision, 1 if patient p receives strategy s |
| λ_PT, λ_XT | shadow prices of the two capacities, utility per minute |
| B | number of blocks of a course |
| n_b | number of fractions in block b |

**Strategy.** A strategy is the tuple

s = (modality, adaptation, fractionation, technique)

Technique has a single value per modality in this study and is kept so that photon techniques can be distinguished later. Margin and robustness are not components of the tuple: the arm determines them (below). Each patient holds seven strategies: XT-A, PT-NA and PT-A under each of the two schedules, and XT-NA under the one schedule clinical eligibility assigns (A32).

**Block.** A block is the interval of a course over which one plan is delivered. Blocks are delimited by the images available: the pCT for the first block, then one block per repeat image. With two repeat images a course has three blocks. B is a property of the imaging available under a schedule, not a decision variable, and its value for the hypofractionated schedule is open decision 23. The fraction count n_b is derived from the acquisition dates of the repeat images relative to the start of treatment. Where the dates do not determine it unambiguously, it is set by hand and recorded as an assumed quantity in the provenance table (extractor 12; evaluator E21). B and n_b govern the extractor, the evaluator and the plan budget. They do not enter the allocator.

**Adaptation is a property of the course.** The workflow is chosen once, on the planning CT, and holds for the whole course (A24, supervisory decision).

- An **adapted arm** adapts at every block. It carries a reduced-margin plan generated on the pCT for the first block, and a reduced-margin replan generated on each repeat image thereafter.
- A **non-adapted arm** carries the clinical-margin plan generated on the pCT, recomputed on each repeat image. On any block where that plan fails the acceptance criterion, it is rescued by an offline replan at clinical margin (Section 8.2). "Non-adapted" therefore means reactively adapted at clinical margin, not never replanned. The manuscript defines the label on first use.

**What the block structure represents.** The modelled workflow is systematic online adaptation. In an adapted arm every fraction is adapted, and one replan per block, on the block's repeat image, stands for the daily replans, because the repeat images are the anatomy available in the data. The reference study did the same: it replanned offline on its repeat CTs to simulate an online workflow, and charged the extra time on every fraction. This reading is also what makes a reduced margin from the first fraction deliverable (A25). Two consequences follow. The adaptation time is incurred on every fraction of an adapted course (Section 9, A16). And the first-block convention below favours the non-adapted arms.

**Margin follows the arm.** The reduced margin is a property of the adapted arm and applies from the first fraction (A25). This matches the reference study, whose reduced-setup-error plans are generated on the pCT and delivered over the first block of every adaptive workflow. A reduced-margin plan delivered without adaptation is not an option and is not computed, since it is clinically incoherent.

**The first block carries no modelled anatomical degradation.** For every arm, the dose of the first block is the planned dose on the pCT, as in the reference study (A23). Under the online reading, the adapted arms would adapt during the first block as well, so their nominal first-block dose is the dose they would deliver. The non-adapted arms would already meet anatomical change during the first block, and the convention omits it. The convention therefore favours the non-adapted arms and understates the benefit of adaptation, by an amount that scales with the first block's share of the course. This is a limitation of the design, not a component of it. It can be investigated without planning or recomputation, by recomposing every arm with the first block assigned the dose of the second block (weights 0, 20, 10 instead of 10, 10, 10 for three blocks of ten fractions); the true value lies between the two compositions.

**Unchanged-margin adaptive arms are not carried.** Adaptation at clinical margin is characterised by the reference study, which reports it as OAPT-Clinic, so carrying it would spend planning effort re-deriving a published result. As a consequence, the benefit of adaptation and the benefit of the margin reduction it licenses cannot be separated within this cohort. The reference study supplies that separation externally, for lung under mean-dose logistic endpoints.

## 5. The allocation problem

### 5.1 Formulation

Each patient receives exactly one strategy, and total occupancy must not exceed either capacity:

max Σ_p Σ_s u_ps · x_ps

subject to:

Σ_p Σ_s n_ps · τ^PT_ps · x_ps ≤ C_PT

Σ_p Σ_s n_ps · τ^XT_ps · x_ps ≤ C_XT

Σ_s x_ps = 1 ∀p ; x_ps ∈ {0, 1}

This is a **multiple-choice knapsack problem** (MCKP) with two resources.

**Photon delivery is unconstrained; photon adaptation is not.** A department does not run out of conventional photon delivery capacity in a way that changes a referral decision, so the non-adapted photon arm is available to every patient at no modelled cost. Adaptation is the scarce quantity on both modalities, and it is what the two constraints price (A3, confirmed at supervision).

**What each arm consumes.** Occupancy is per course, since adaptation is a property of the course.

| Arm   | Proton machine time      | Photon adaptation time |
|-------|--------------------------|------------------------|
| XT-NA | none                     | none                   |
| XT-A  | none                     | Δτ_XT per fraction     |
| PT-NA | τ_0 per fraction         | none                   |
| PT-A  | τ_0 + Δτ_PT per fraction | none                   |

The proton arms are charged the whole session, because the proton machine is binding for delivery as well as for adaptation. The adapted photon arm is charged only the increment, because photon delivery is not binding (A17). No photon baseline session length is therefore required anywhere in the design.

**Structure of a patient's option set.** Each patient holds seven strategies (Section 4). The two resources are consumed by disjoint groups of arms, so the options form two chains meeting at XT-NA. The photon chain runs along the C_XT axis, with one rung above the base per schedule; the proton chain runs along the C_PT axis, with two rungs per schedule. No strategy consumes both resources. The option set does not depend on the number of blocks.

**Scope limitation.** XT-NA consumes neither budget and is assignable for every patient: the coverage screen rescues it rather than removing it (Section 8.2), and A31 applies only to adapted arms. The allocation is therefore always feasible. This is the correct representation of a referral question, in which the standard of care is an entitlement rather than a rationed good. It also means the model cannot represent a department stressed to the point where a patient receives no treatment, which is what the word capacity carries in the reference study.

**Order of operations.**

- The extractor produces per-block dose and per-block target metrics for every plan, rescue plans included.
- The evaluator constructs the seven strategies, composes each from its plan sequence as recorded in the export manifest (including the rescue plans of the non-adapted arms, Section 8.2), evaluates NTCP, and computes the diagnostics of Section 8.
- The allocator reduces each option set (below) and solves the MCKP.

**Dominance reductions.** Two reductions are applied to each patient's option set, both in the allocator (`dominance.py`).

- The **Pareto reduction** drops an option that costs more than another without buying more utility; among options of equal cost, only the best survives. It is valid for both the integer problem and its relaxation. It is also what removes strategies of negative utility from the chains, since XT-NA dominates them at zero cost.
- The **hull reduction** additionally drops options lying on or below the upper convex hull of a chain. It is valid for the LP relaxation only, and it is what makes the incremental-efficiency ordering of Section 5.2 valid there.

Clinical rules act on the option set, never as penalties inside the objective, which keeps the optimisation clean and the rules explicit.

**Objective.** Each patient receives exactly one strategy, so the sum of reference NTCP over the cohort is a constant. Maximising the sum of ΔNTCP is therefore the same problem as minimising the sum of absolute NTCP. The integer, linear and greedy solvers maximise the sum of ΔNTCP, which gives the reference arm a coefficient of exactly zero. The dynamic-program cross-check minimises the sum of absolute NTCP, and T5 asserts that the two give identical allocations. ΔNTCP is also what is reported and what the no-harm diagnostic uses.

**No sign constraint is imposed.** The formulation contains no row of the form u_ps ≥ 0, and none is required. XT-NA is free on both budgets and has utility zero, so it dominates every option of negative utility: substituting it raises the objective and relaxes both capacity rows. No optimal solution of the integer problem or of its relaxation contains a strategy that harms a patient. Imposing the sign explicitly would be redundant, and it would corrupt the reading of the shadow prices by adding rows whose multipliers mix into the duals of the capacity rows. The statement that no patient is worse off than the reference is therefore a property of the formulation, not a finding. The solvers and policies still handle a patient without a free assignable option by assigning the least harmful strategy (T11). That case is unreachable by construction, and the test checks the construction.

**Solver.** The exact solver is an integer linear program (`scipy.optimize.milp`, HiGHS backend), which needs no discretisation. It states the two-resource problem in the form hardest to get wrong, and the LP relaxation of the same model, with integrality dropped, supplies (λ_PT, λ_XT) directly as duals. The integer solve runs to a relative optimality gap of 1e-6 (`mip_rel_gap`, an argument), and the gap the solver reports at termination is returned with the allocation. The HiGHS default of 1e-4 left a shortfall on the cohort sum of up to 3e-4 at P = 200 and 3e-3 at P = 1000 on generated non-concave cohorts. Solve time at P = 1000 depends on the instance: one generated cohort solved in 3 s and another did not finish in 150 s, where the default gap took 0.6 s. A looser gap is passed at that size. A dynamic program over proton machine time is retained as an independent cross-check at C_XT = 0 (T8). It discretises time at 0.1 min, with costs rounded up so that rounding never violates the capacity constraint, and the resolution is a named constant. The resolution matters: at 1 min, an occupancy of 36.9 min rounds to 37 and thirteen patients no longer fit in 480 min. That changes the answer and breaks the reproduction of the reference study for a purely numerical reason.

### 5.2 Algorithm and the shadow prices

No threshold is supplied as input. A threshold is induced by the allocation, and reading it off is the point of what follows.

**Lagrangian relaxation.** Relax integrality and attach a multiplier to each capacity constraint, λ_PT ≥ 0 and λ_XT ≥ 0:

L(x, λ) = Σ_p Σ_s (u_ps − λ_PT · n_ps · τ^PT_ps − λ_XT · n_ps · τ^XT_ps) · x_ps + λ_PT · C_PT + λ_XT · C_XT

The two prices replace the coupling between patients, so the problem separates. At fixed prices, each patient independently selects the strategy that maximises its priced utility. Since no strategy consumes both resources, that selection is the better of two independent chain maxima, one priced at λ_PT and one at λ_XT.

**Why ranking patients by u/τ is not the right rule.** Ranking by benefit density is optimal for a 0-1 knapsack, in which each patient has a single option and the decision is whether to buy it. In the MCKP every patient already holds a free option, XT-NA, and the decision is how far up a chain to climb. That decision turns on incremental efficiencies, not total ones.

**The single-resource procedure.** With one resource, the LP relaxation of an MCKP is solved as follows.

- Within each patient's option set, sort options by occupancy.
- Discard **LP-dominated** options, those lying strictly below the upper convex hull of the patient's (τ, u) points. An option can have higher utility than every cheaper option and still never be selected by the LP, because a convex combination of its neighbours beats it. Options lying exactly on the segment joining their neighbours are removed as well: they are alternative optima, not additional ones.
- Compute **incremental efficiencies** between consecutive surviving options of each patient: (u_j − u_(j−1)) / (τ_j − τ_(j−1)).
- Start every patient at their cheapest surviving option and spend capacity greedily on the pooled incremental efficiencies, in decreasing order.

λ\* is the incremental efficiency at the break item: the marginal cohort utility bought by one additional minute spent **upgrading one patient by one rung**.

**With two resources.** The hull reduction is applied chain by chain. Each chain lies on a single cost axis, so each hull is an ordinary one-dimensional hull, and no hull is taken across chains. The pooled greedy does not extend. Moving a patient from the photon chain to the proton chain releases photon adaptation minutes while consuming proton minutes, so spending is not monotone in either budget and no single ordering of upgrades exists. The LP is therefore solved directly, as the integer program with integrality dropped, and its duals give (λ_PT, λ_XT).

**Reading the prices.** λ_PT is the marginal cohort utility of one additional proton machine-minute; λ_XT is that of one additional minute of photon adaptation. Their ratio states where a department gains more from the next unit of investment. With the prices per course-minute, a workflow change costing an extra Δτ_PT per fraction is worthwhile for patient p if the utility it buys exceeds λ_PT · n_fx · Δτ_PT; the same holds on the photon side with λ_XT. This gives the referral threshold of national model-based selection a facility-specific value: λ_PT multiplied by a patient's course occupancy is the ΔNTCP a proton course must buy at that centre's load.

**λ_XT is reported as a curve.** Its magnitude depends on C_XT, which has no measured anchor for this indication (A20), so a single value would be an assumed number. The budget is therefore swept on a normalised axis, C_XT / D_XT. The normaliser is D_XT, the photon adaptation demand of the cohort: the sum over patients of the largest photon adaptation occupancy among each patient's admissible options, which is the smallest budget at which C_XT cannot bind. Where every patient holds the standard-schedule adapted photon arm, D_XT = Σ_p n_fx,std · Δτ_XT. A patient whose standard-schedule adapted arm is absent under A31 contributes the occupancy of its most demanding remaining option, so D_XT depends on which adapted arms exist. At 0 the photon comparator is the reference study's non-adapted arm (T8); at 1 the photon budget stops binding (T9). The normalisation makes the curves independent of cohort size and of resampling, and minutes are carried as a secondary axis. Results that need one budget rather than a sweep, in particular the (Δτ_PT, Δτ_XT) plane, are evaluated at a reference value C_XT^ref in absolute minutes (open decision 13), the analogue of the 480 proton minutes of the reference study.

**The hull reduction is valid for the relaxation only.** The LP never buys an option below the hull, because it can split a budget between that option's neighbours. The integer problem cannot split, so an LP-dominated option can appear in the integer optimum. The hull reduction is therefore never applied before an integer solve or inside an integer heuristic. The Pareto reduction is valid for both.

**Two dominance counts.** Pareto dominance says two options are not in genuine competition; it is largely uninformative. LP-dominance says the relaxation would never buy an option at any capacity, which is the clinically informative statement. The two are counted and reported separately, so that the first does not swamp the second.

**What LP-dominance can say here.** Within one schedule, the photon chain holds one rung above the free base and cannot be LP-dominated. The proton chain holds two, so the only rung that can fall below the hull is PT-NA, when entering the proton chain directly at PT-A is the more efficient route. Section 6.2 answers that question in closed form, and T14 checks it. Pooled across two schedules, both axes carry two rungs above the free base, and both can be LP-dominated by the same geometric argument. `report.dominance_counts` anchors each axis at its own free point, so the pooled counts are correct, but no closed form covers this case. The competition between schedules is what the allocator resolves directly (road 1).

**Integrality gap.** In a single-resource MCKP the LP optimum has at most one fractional class. The gap is therefore bounded by the utility difference between the two straddling options within that one patient's set, not by a whole patient's utility. With two constraints, the standard argument on the number of basic variables allows at most two fractional classes, one per binding constraint, so the bound is stated per resource.

**Recommendation.** Solve the integer problem exactly, and use the LP relaxation only to extract the multipliers and the dominance structure. With seven options per patient the exact solve is trivial at any cohort size the study can reach.

### 5.3 Policies to compare

An optimum alone is not a clinically useful output, because no clinic implements an integer program. The informative output is the gap between what simple rules achieve and what is achievable at all.

| Policy | Definition | What it represents |
|---|---|---|
| P0 | Threshold-based referral, fixed standard schedule, no adaptation | Current practice. The locked baseline |
| P1 | Threshold-based referral, adaptation for all proton patients, fixed schedule | Essentially the reference study |
| P1x | As P1, then photon adaptation on the standard schedule in decreasing ΔNTCP until the photon budget is exhausted | Separates the value of the adapted photon arm's existence at the schedule P1 holds from the value of the fractionation axis and of optimising over it. Without it, P3 − P1 confounds them |
| P2a | Greedy by benefit density u/τ over patients | The naive capacity-aware rule, implementable by hand |
| P2b | Greedy by best available upgrade over Pareto-reduced option sets | The correct heuristic |
| P3 | Exact multiple-choice knapsack optimum | Upper bound on what any allocation can achieve |

**Referral and P1x.** P0 and P1 refer patients in decreasing ΔNTCP while proton capacity lasts. A patient is referred when ΔNTCP is at least the threshold, whose default is zero, and never at zero or negative benefit. P1x holds the schedule fixed as P1 does, so its photon adaptation is restricted to the standard schedule. P1x − P1 is then what the existence of the adapted photon arm adds at the standard schedule, and P3 − P1x is what the fractionation axis, on both modalities, and the optimisation add. P1x equals P1 for any photon budget below one standard-schedule adapted course, n_fx,std · Δτ_XT minutes (T18).

**P2b, defined precisely.** Every patient starts on their cheapest option. At each step the upgrade with the highest ratio of utility gained to minutes spent is taken, over all patients and over **every** option above the one currently held, not only the next rung. On a non-concave chain the best available upgrade can skip rungs, which a rank-by-rank scan never reaches. The procedure runs on the Pareto-reduced option sets, not the hull-reduced ones (Section 5.2), and stops when no upgrade fits.

P2a and P2b are separated deliberately. Merging them would confound two different costs: using a heuristic instead of an exact solve, and using the wrong ranking statistic.

**Ranking with two budgets.** A benefit density is defined on one budget at a time. Ranking proton and photon upgrades in one list would need an exchange rate between the budgets, and that rate is λ_XT / λ_PT, an output of the LP. The heuristics therefore rank proton upgrades only. The photon budget is spent by a separate rule: photon patients are adapted in decreasing ΔNTCP until the budget is exhausted. P1x, P2a and P2b use it, P1x on the standard schedule only. Ties in ΔNTCP are broken by lower photon occupancy and then by identifier, so that the result does not depend on the order of the option list. This is what a clinic would implement, since the two capacities belong to different services. The alternatives have worse defects. Interleaving the two rankings by a fixed priority imposes an arbitrary exchange rate. Scalarising costs at the current prices makes the heuristic depend on the LP it approximates. All three coincide at C_XT = 0.

**Where P2a and P2b separate.** Within one schedule, the best available upgrade differs from the next rung only when a patient moves from the photon base directly to PT-A, skipping PT-NA. That is exactly the case in which PT-NA falls below the hull, so within one schedule the two heuristics separate only on the question Section 6.2 answers. Across two schedules, a best-available upgrade can also skip from the photon base past one schedule's PT-NA to the other schedule's PT-A, and the separation grows. How much the separation grows depends on the cohort, on the load and on the schedule parameters. It is measured on the study cohort and not stated here.

**Policies are secondary outputs.** The primary result is the parametric behaviour of the optimal allocation itself: how the cohort's assignment moves across the (Δτ_PT, Δτ_XT) plane and along the photon budget axis. The policy comparison reads that result against implementable rules and is reported after it.

### 5.4 Algorithmic claims tested

Each claim is implemented as a test that fails by default.

| ID | Claim | Status |
|---|---|---|
| T1 | With two options per patient, occupancy uniform across patients and one shared adaptation policy, the allocator reproduces the reference study's scenario ladder | Passing |
| T2 | The incremental-efficiency greedy after hull removal attains the LP optimum, checked against an independent LP solver | Passing |
| T3 | The integer optimum lies below the LP optimum by at most one within-patient upgrade step. The test uses the largest step in the fractional patient's chain, a weaker bound than the straddling pair | Passing |
| T4 | λ from the LP equals the finite difference of the optimal value with respect to capacity | Passing |
| T5 | Solving on absolute NTCP and on ΔNTCP gives identical allocations | Passing |
| T7 | Each multiplier equals the finite difference of the optimal value with respect to its own budget, the other held fixed | Passing |
| T8 | At C_XT = 0 the two-resource solve reproduces the single-resource result exactly, and through T1 the reference study | Passing |
| T9 | As C_XT exceeds the cohort's photon adaptation demand, λ_XT falls to zero and every patient not on protons holds XT-A | Passing |
| T10 | No policy assigns a strategy of negative utility, and no sign constraint exists anywhere in the code; the Pareto reduction removes such strategies from the chains | Passing |
| T11 | Where no free option is assignable (unreachable by construction), the exact optimum assigns the least harmful strategy; a strategy flagged inadmissible is never assigned; an empty option set raises and names the patient | Passing |
| T14 | Within one schedule, the patients for whom PT-NA falls below the upper hull of their proton chain, augmented with the photon outside option, are exactly those for whom Δτ_PT is below the closed-form threshold of Section 6.2, to solver tolerance. Swept over Δτ_PT, the photon coupling and the photon budget, rather than run on a cohort built to straddle the threshold | Passing |
| T15 | Swapping the two resources and their budgets reproduces the mirrored problem exactly, in optimal value and in both duals | Passing |
| T16 | Across two schedules, PT-A under the standard schedule is on the pooled hull if and only if pen > pen\* = a · (a_mult − 1), patient-wise and whatever Δτ_PT (Section 6.2). Where it is below the hull, PT-NA under the hypofractionated schedule is on the hull if and only if Δτ_PT reaches that schedule's own threshold, τ_0,hyp · a · a_mult / m. Checked against `dominance.hull` on generated cohorts (`test_threshold.py`) | Passing |
| T17 | On the photon chain of a generated patient, the standard XT-A is Pareto dominated at pen_xt = 0 and on the hull at pen_xt > 0, and the hypofractionated XT-A is on the hull for pen_xt < g · (1 − n_hyp / n_std), g being the patient's XT-A benefit (Section 5.5). Two values of pen_xt are tested (`test_generator.py`) | Passing |
| T18 | P1x equals P1 at any photon budget below one standard-schedule adapted photon course, and does not decrease as the budget grows (`test_allocator_rules.py`) | Passing |

T8 and T9 are the two ends of the C_XT sweep and serve as regression tests for the single-resource behaviour. T14 is not run across two schedules, since its closed form makes no claim there; T16 covers the two-schedule forms of Section 6.2. Retired: T6, T12, T13.

### 5.5 Synthetic cohorts

The allocator is tested on synthetic cohorts before real data exist. The generator (`generator/synth.py`) emits utilities and occupancies directly, not dose, since its purpose is to exercise the allocator; the composition and NTCP path is exercised separately, end to end on synthetic DICOM (evaluator 11).

Each synthetic patient carries the seven options of Section 4. The hypofractionated options are derived from the standard ones through a biological penalty pen on the modality benefit and a ratio a_mult on the adaptation benefit (the parameters of Section 6.2). The XT-NA schedule is set per patient by a synthetic eligibility flag, drawn with probability `hypo_frac`. Three named benefit configurations (`SHAPES`: `both_schemes`, `nonconcave`, `hyp_dominant`) place a patient's pooled proton frontier in each of the reachable regimes of Section 6.2. Percentages of 400 generated patients (`x_gain` = 0.03, seed 11, and the generator's defaults otherwise, including τ0 = 30 min) with each arm on the pooled hull, over the reference-study sweep of Δτ_PT from 2.4 to 25.7 min, as `scripts/shape_fractions.py` prints them:

- `both_schemes`: PT-A under both schedules is on the pooled hull for every patient. PT-NA hypofractionated is on it for none of them at 2.4 min, for 33% at 9.3 min, 60% at 13.7 min and 91% at 25.7 min. PT-NA standard is on it for none.
- `nonconcave`: PT-A standard is on the hull for every patient and PT-A hypofractionated for 96 to 97% of them. PT-NA hypofractionated is on it for none up to 19.0 min and for 3% at 25.7 min, and PT-NA standard for none.
- `hyp_dominant`: PT-A hypofractionated is the only proton arm on the hull at every Δτ_PT. The whole standard chain and PT-NA hypofractionated lie below it.

PT-NA standard is thus below the hull in all three shapes over this sweep. It reaches the hull for a large biological penalty combined with a long adaptation time, which `scripts/two_scheme_check.py` maps. The percentages depend on τ0: at 34.2 min, PT-NA hypofractionated in `both_schemes` is on the hull for 87% at 25.7 min. Together the shapes exercise the hull reduction and the greedy on all three regimes.

The adapted photon arm carries the same benefit under both schedules unless `pen_xt` is set, which subtracts from the benefit of the hypofractionated XT-A as `pen` does for the modality step. At its default of zero the standard XT-A, at six times the cost, is Pareto dominated for every synthetic patient. On the photon chain, anchored at XT-NA, the standard XT-A is on the hull if and only if pen_xt > 0, and the hypofractionated XT-A if and only if pen_xt < g · (1 − n_hyp / n_std), with g the patient's XT-A benefit (T17). The sign of the hypofractionated photon effect depends on organ and α/β (Section 10.1), so `pen_xt` is a sweep variable and carries no reference value.

Every benefit and cost the generator draws is illustrative and none is an estimate for the study cohort. The proton adaptation benefit and the range of the modality benefit are of the order of the reference-study lung values of Section 6.2. The photon adaptation benefit has no source, since the reference study has no adapted photon arm.

Rescue is drawn per block for the non-adapted arms (`_rescue_sequence`): each block fails independently with probability p0 · decay^k, k being the rescues already made on that arm, with p0 = 0.05 and decay = 0.5. Both values are placeholders chosen to exercise the code, not estimates. The adapted arms carry the all-planned sequence, enforced by the schema. The realised rescue frequency is a study output (Section 8.2).

## 6. Configuration and the step-ratio threshold

### 6.1 Adopted configuration

The study adopts Config 0e: modality, adaptation and fractionation are each chosen per patient, once, at prescription, and hold for the whole course (A24, supervisory decision). It releases the reference study's first rigidity, one workflow for the whole cohort, and adds the fractionation decision. It does not release the decision to the block level.

| Config | Modality | Adaptation | Fractionation | Verdict | Reason |
|---|---|---|---|---|---|
| 0 | binary, whole course | one policy for the whole cohort | fixed | reference study | Baseline; reproduced by T1 |
| **0e** | binary, whole course | per patient, whole course | per patient, whole course | **adopted** | Releases the per-patient granularity and the fractionation axis while keeping the option set fixed at seven |
| 1 | fraction-level mixing | none | fixed | rejected | Naive mixing collapses to patient selection. Joint optimisation needs a shared BED objective across modalities, which is nonconvex, depends on a poorly constrained abdominal α/β and carries a silent RBE assumption. Loizeau et al. found the gain over patient selection small at equal dose per fraction. The photon arm is also the reference, and making it a within-course resource entangles the baseline with the decision variable |
| 2 | binary, whole course | per patient, per block | per patient | deferred to a later publication | Belongs with receding-horizon reallocation, which concerns when to act within a course rather than what to assign at its start |
| 3 | fraction-level mixing | per patient, per block | per patient | deferred | Config 2 with a finer partition of each course; adds roughly the small Config 1 gain for a large increase in machinery |

### 6.2 The step-ratio threshold

No clinical on-couch adaptive proton workflow exists for the abdomen, so the extra time per adapted fraction is not a measurable input. As in the reference study, it is the independent variable, and the deliverable is a threshold on it.

**The question.** With two rungs on the proton chain, the only structural question the hull can pose is whether PT-NA survives it. Below the threshold, PT-NA lies under the segment joining the photon base to PT-A: non-adapted protons are never the price-efficient way to spend proton capacity, and a patient who enters the proton chain at all enters it adapted. Above the threshold, PT-NA is a live rung and the cohort can split three ways rather than two. The question is patient-wise.

**Derivation.** Let m be the ΔNTCP of the modality step, photons to non-adapted protons, and a the further ΔNTCP of adaptation together with the margin reduction it licenses, so that PT-A is worth m + a. Let τ_0 be the baseline session length and n_fx the fraction count. Occupancies are per course: n_fx · τ_0 for PT-NA and n_fx · (τ_0 + Δτ) for PT-A. The efficiencies of the entry step and of the adaptation step are:

e_mod = m / (n_fx · τ_0)

e_ada = a / (n_fx · Δτ)

PT-NA survives the hull when e_mod ≥ e_ada, that is when the step ratio ρ = e_mod / e_ada ≥ 1, which solves to:

**Δτ\* = τ_0 · (a / m)**

Three properties are worth stating.

- **The threshold is a fraction of the baseline session length**, governed by the benefit ratio a/m. In adimensional form Δτ\*/τ_0 = a/m, so it transfers across sites and does not depend on the particular 34.2 min of the reference setting.
- **a/m is an output of the cohort, not an input.** The study measures both terms; the threshold then follows, and is compared against the workflow-time envelope constructed from the components of Section 9.
- **It is patient-wise.** Each patient carries their own (m_p, a_p) and therefore their own threshold, so a cohort spanning both sides of it produces a mixed allocation at a single Δτ. This is the design argument for enriching the cohort with borderline cases, and it is what T14 checks.

**The closed form coincides with the reference study's break-even.** The reference study asks at what Δτ adapting every patient, and losing capacity for it, ceases to beat adapting none. Under a uniform cohort and continuous capacity that condition is written as follows. With i patients displaced to photons, capacity gives (P − i)(τ_0 + Δτ) = P · τ_0, and equality of the two cohort means gives (P − i)(m + a)/P = m. Eliminating i:

τ_0 · (m + a) / (τ_0 + Δτ) = m, hence Δτ = τ_0 · (a / m)

which is Δτ\*. **The hull condition and the reference study's break-even are the same condition.** They coincide because at LP prices the optimum spends capacity on the more efficient step first, so the point at which two pure policies break even is the point at which their two steps have equal efficiency. The reference study's headline number is therefore available in closed form rather than read from a scenario ladder.

**Numerical check against the published values, as illustration and not as reanalysis.**

- **Two-year mortality, 2 mm setting.** m = 6.9 and m + a = 10.7, so a = 3.8, and with τ_0 = 34.2 min the threshold is 18.8 min. The published OAPT-2 mm curve meets the non-adapted line at scenario S5, +19 min; the paper describes this as the gain ceasing to be significant, without a statistical test.
- **Dysphagia.** a = 7.5 and the threshold is 42.1 min, consistent with the published curve not crossing within a sweep that stops at 25.7 min.
- **Pneumonitis.** The threshold is 20.9 min, while the published curve meets the non-adapted line near scenario S4, +13.7 min. The discrepancy is informative rather than a failure.

**The closed form is a benchmark and the discrepancies are the result.** Three mechanisms separate the analytical value from the observed crossing, and each is measurable as a departure from it.

- **Discreteness.** Patients are integers and capacity moves in steps. For the unchanged-margin setting on two-year mortality the closed form gives 4.5 min, while the published crossing falls between scenarios S1 (+2.4 min) and S2 (+5.7 min), so the analytical value sits inside the discrete interval rather than at a point.
- **Heterogeneity with selection.** The displaced patients are not average patients but the ones the displacement rule selects, which moves the crossing away from the uniform-cohort value.
- **Disalignment of the ranking statistic.** In the reference study the displacement is decided on the union probability computed under the unchanged-margin adapted arm, while the curve being read is a single endpoint under a reduced-margin arm. The subset displaced is therefore not the subset that a ranking coherent with the evaluated strategy would displace. For pneumonitis this appears to be the dominant term.

Reporting the observed allocation against the closed form decomposes the gap between the exact optimum and current practice by mechanism, rather than as a single unattributed difference. With the fractionation axis a fourth term is added, since n_fx enters the two schedules differently, and that term is not captured by a threshold derived at a fixed schedule.

**Dependence on the acceptance criterion.** m and a are evaluated on post-rescue utilities, and the rescue of XT-NA and PT-NA depends on the acceptance criterion (Section 8.2). Δτ\* is therefore conditional on decision 7b, like every ΔNTCP.

**The photon budget acts on the threshold through one scalar.** At LP prices the patient's photon chain enters the proton competition only through its best priced value, the **photon outside-option value**

w(λ_XT) = max( 0, x − λ_XT · n_fx · Δτ_XT )

with x the photon adaptation benefit. The reduction is exact, not an approximation, because the two chains share no cost axis: a proton rung is LP-selectable if and only if it lies on the upper hull of the proton points augmented with the point (0, w).

The adaptation increment does not involve w; only the entry step does, whose efficiency becomes (m − w) / (n_fx · τ_0). The threshold follows:

**Δτ\*(w) = τ_0 · a / (m − w), valid for w < m**

At w = 0 this is the closed form above; the budget enters only through the denominator.

**Monotonicity is proved, not asserted.** The LP value is concave in the right-hand side, so λ_XT is non-increasing in C_XT; w is a maximum of affine non-increasing functions of λ_XT, hence non-decreasing in C_XT; and Δτ\*(w) is increasing in w below m. Therefore Δτ\*(C_XT) is non-decreasing and piecewise smooth, with interpretable limits: τ_0 · a / m at C_XT = 0 (T8) and τ_0 · a / (m − x) at saturation (T9). The closed form is checked against the hull implementation by T14 (`test_threshold.py`).

**The regime w ≥ m.** If a patient's photon outside option is worth more than the bare modality step, the formula is void and the correct statement is stronger: PT-NA is never LP-selected for that patient at any proton price, and the patient enters the proton chain, if at all, directly at PT-A. This is an interpretable finding rather than a pathology. A sufficiently funded photon adaptation programme removes non-adapted protons from the efficient frontier patient-wise, and the boundary w = m is itself a reportable transition. Whether any real patient sits there depends on x against m, which the study measures.

**Cohort coupling.** w depends on λ_XT, an equilibrium scalar of the whole allocation, so the per-patient thresholds form a family Δτ\*\_p(C_XT) driven by one cohort-level price. Heterogeneity at fixed budget comes from (m_p, a_p, x_p) only, and the family costs nothing beyond the λ_XT(C_XT) sweep.

The direction of the budget effect is known in advance and is stated, because it acts against the mechanism that motivates spending proton capacity on adaptation: funding photon adaptation raises the bar for protons. Its magnitude is the size of the photon adaptation benefit, which the study measures rather than assumes. The threshold does not capture competition between fractionation schedules: each schedule carries its own (τ_0, a, m, x) and therefore its own surface.

**One point of that competition has a closed form.** The standard adapted arm, PT-A under the standard schedule, is the highest-cost point of a patient's pooled proton frontier at every reachable parameter setting. The hypofractionated schedule is cheaper on both its rungs, and charging the adaptation increment per fraction only widens that gap under the standard schedule's larger fraction count. A point at maximum cost survives Pareto, and therefore sits on the hull, exactly when it also carries the maximum utility of the whole set: anything that beat it in utility at equal or lower cost would dominate it outright. Write m and a for the standard schedule's modality and adaptation benefits, pen for the biological penalty applied to the hypofractionated modality benefit, and a_mult for the ratio of the hypofractionated to the standard adaptation benefit (Section 5.5). The binding comparison is against the hypofractionated adapted arm's utility, m − pen + a · a_mult, and reduces to

**pen\* = a · (a_mult − 1)**

PT-A standard survives the pooled hull when pen > pen\* and is dropped when pen < pen\*. At exact equality the tie-break in `pareto()` keeps the cheaper of two equal-utility points, so at a_mult = 1, where pen\* = 0 for any a, the boundary is an artefact of the tie-break rather than an economically meaningful transition. Neither Δτ nor any occupancy parameter enters, since the comparison is between utilities alone; cost only establishes which point is rightmost. pen\* does not depend on rescue, since both arms compared are adapted. At the reference-study magnitude a = 3.8 percentage points, pen\* = 3.8 · (a_mult − 1): with a hypofractionated adaptation benefit 1.5 times the standard one, the standard adapted arm is displaced unless the biological penalty exceeds 1.9 points; at 2.5 times, unless it exceeds 5.7. No closed form covers the other three points of the pooled frontier; the allocator resolves their hull membership directly.

**Where a non-concave profile comes from.** Both schedules lie on the same proton cost axis, so a patient's frontier holds four proton points, and the standard arms compete against the hypofractionated ones on price. Whether an arm falls below the hull is governed by the biological penalty of hypofractionation against the adaptation benefit it licenses, quantified above for the standard adapted arm. The hull reduction handles this, which is the second reason it is retained. The synthetic generator exposes the three reachable configurations (Section 5.5).

## 7. Utility currency

The utility of a strategy is its ΔNTCP against XT-NA: the patient's non-adapted photon treatment, at the schedule clinical eligibility assigns (A32), with offline rescue where coverage fails (Section 8.6). The objective, every policy ranking and every threshold are referred to XT-NA. As in the reference study, selection uses the union probability of the modelled complications, and per-endpoint ΔNTCP is reported separately. Two consequences are stated explicitly:

- The union probability assumes independence between toxicities, which is false, since they share dose drivers and patient-level frailty. It is accepted as the best treatment available and matches the reference study.
- Selecting on one scalar while reporting several means that no per-endpoint curve is the optimum for its own endpoint. The single-endpoint optima are a natural benchmark and are computed as a secondary analysis.

**Severity weighting is not applied.** The union probability weights all endpoints equally, including endpoints of very different severity. This is accepted by supervisory decision, for continuity with the reference study and with the model-based selection logic. The interface retains per-endpoint weights defaulting to the union form, so that a severity-weighted utility could be substituted later without structural change, but no such weighting is exercised in this study.

**The cohort mean is taken over the referred population.** Displaced patients stay in the denominator and contribute their XT-NA NTCP, so the mean is an intention-to-treat quantity over the referred population rather than over the treated one. This matches the reference study, which divides by 14 throughout.

## 8. Admissibility

Comparing arms on NTCP alone is legitimate only where every arm delivers the prescribed dose to the target and no arm is worse than the baseline. The two conditions are handled differently, and the asymmetry is deliberate.

- **Target coverage is enforced by substitution**, because nothing in the objective penalises an underdosed target. An arm whose plan falls below the acceptance criterion on a repeat image is rescued by an offline replan at unchanged margin and continues. No arm is removed.
- **No harm is reported rather than enforced**, because the structure of the option set already guarantees it (Section 5.1).

The evaluator computes both; the allocator receives the option sets, the rescue record and the counts.

### 8.1 What is assumed and what is not

Every arm is **engineered** to treat the tumour adequately: each plan is generated to protocol on the image available at the time of planning, with the robustness settings appropriate to its arm (A4). This is a design constraint on plan generation.

What is **not** assumed is that adequacy persists. A plan built on the pCT and delivered without adaptation to a changed anatomy may lose target coverage as well as OAR sparing. Anatomical change that could not be anticipated at planning is precisely the failure mode that motivates adaptation, and it acts on the target, not only on normal tissue.

Coverage degradation is therefore an **independent trigger for adaptation**, alongside NTCP benefit. A patient may require adaptation not because it improves the toxicity profile but because the non-adapted plan no longer treats the tumour adequately. The adaptation it triggers is a **rescue at clinical margin**, not a promotion to the adapted arm. The margin is what distinguishes the two arm families, and a rescue that reduced it would collapse them (A24, A30).

If the target shifts away from an OAR between pCT and rCT, the non-adapted plan underdoses the CTV while the OAR dose falls, so coverage fails and NTCP *improves*. An allocator ranking on ΔNTCP alone would rate that plan as the better option. NTCP is a function of OAR dose only and carries no information about the target, so coverage must be tested explicitly rather than inferred.

### 8.2 Coverage, judged per block, and rescue

Target coverage is a property of a plan delivered on a given anatomy. If the plan an arm would deliver on rCT_j falls below the acceptance criterion, that plan would not be delivered, and no accumulation is required to reach that judgement (A11).

**What follows is a substitution, not a removal.** The arm acquires a replan generated on rCT_j at **unchanged margin and unchanged setup error**, and continues. The replan carries forward to subsequent blocks and is itself judged on each of them, so an arm that keeps failing is a sequence of clinical-margin plans replanned on demand. This is standard clinical practice, it is what the reference study does, and it is a supervisory decision (A24, A29, A30).

**Where the judgement is made.** The acceptance judgement is made in RayStation, during plan generation. The planner recomputes a non-adapted plan on each new image, judges it against the acceptance criterion, generates the rescue at once where it fails, and records the plan sequence of every arm in the export manifest (extractor 4). Three consequences:

- The acceptance criterion (decision 7b) is fixed before plan generation starts. Changing it afterwards changes which plans must exist, so a sensitivity analysis on the criterion costs planning effort, not computation.
- The evaluator re-applies the same criterion to the exported dose, as a verification. Where the two disagree, for instance through differences in structure rasterisation or DVH binning, **RayStation governs**, since its judgement is the clinical one being modelled; the disagreement is reported per arm and per block (evaluator E23).
- Rescue plans are generated with the same objective template and process as the adapted replans (decision 26), so that plan quality is governed by one rule across all replans.

Six further consequences:

- **"Non-adapted" means reactively adapted at clinical margin**, as against systematically adapted at reduced margin. The two arm families remain distinct on margin and on adaptation frequency. The label is kept for continuity with the reference study and is defined on first use in the manuscript.
- **Rescue is a phenomenon of the non-adapted arms.** Under A1 and A4 an adapted arm's block plan is optimised on the anatomy it is then evaluated on, so nominal coverage holds by construction and the screen cannot fire on PT-A or XT-A. The screen is nonetheless run on every arm and the count reported per arm, because A4 requires the property to be demonstrated rather than asserted. A non-zero entry on an adapted arm is a replanning failure and a diagnostic on decision 26.
- **No arm is ever removed and no option set can empty.** The single exception is not a screen outcome: if a reduced-margin plan cannot be made robustly acceptable at plan generation, that adapted arm is absent from the patient's option set from the start (A31).
- **Rescue is unpriced on both budgets.** An offline replan is performed between fractions and adds no in-room minutes, so it charges nothing to C_PT or C_XT (A28).
- **The number of coverage evaluations equals the number of plans**, rescue plans included, rather than the number of strategies.
- **Rescue changes the plan budget.** Each rescue is an additional plan. The upper bound is one per block per non-adapted arm from the second block on, which would bring a non-adapted arm to the plan count of an adapted one. The realised count is a study output, not a design parameter.

Accumulated coverage is not used in any role.

**Rescue frequency is a reported quantity.** It is reported per arm, per schedule and per block. It is also the empirical check on the plausibility of a non-adapted arm, in particular of a five-fraction course delivered without systematic adaptation: a frequency is more informative than a binary exclusion.

**The reference includes rescue, so results are conditional on the acceptance criterion.** XT-NA is defined as current practice: the clinical-margin plan, replanned offline wherever it fails the acceptance criterion on a repeat image. A plan below the criterion would not be delivered, so a reference without rescue would not represent current practice; rescue restores the reference rather than improving it. The reference NTCP, and with it every ΔNTCP, therefore depends on which criterion defines acceptability (decision 7b). PT-NA is rescued on the same criterion, so the modality step, the photon outside option and the step-ratio threshold Δτ\* are conditional on the criterion as well. Two quantities do not depend on the rescue of XT-NA: the ordering among a patient's other six options, and pen\*, which compares two adapted proton arms. The criterion is recorded with every result.

**Worst-case evaluation is descriptive.** Worst-case metrics are evaluated per plan and per block and never accumulated, since the worst scenario in one block need not be the worst in another, and a sum of per-block worst cases corresponds to no physical scenario. Whether each plan passes robust evaluation on each block is recorded at plan generation, alongside the nominal judgement, and the failure counts are reported per arm. Worst-case failure does not trigger rescue: rescue follows the nominal acceptance criterion only. The adapted arms are expected not to fail, because robust evaluation at the reduced margin is part of plan acceptance and A31 governs the case where it cannot be passed.

**Symmetry.** The screen applies to the photon arms as well as the proton arms. Detecting a coverage failure on a photon arm requires the photon dose to be recomputed on the repeat images (A10).

**The criterion is the plan acceptance protocol used at treatment planning** (supervisory decision). The screen takes a list of criteria of which all must pass, and the count is reported per criterion, so instantiating the list is a configuration change rather than a code change. Which criteria enter the list is open decision 7b, addressed to the clinical partners and the RTTs and gated on decision 19, since the protocol is site-specific.

### 8.3 No harm

A strategy whose union ΔNTCP against the reference is negative is **counted and reported, not removed** (A12, confirmed at supervision). The ethical requirement is that maximising a cohort mean must not make an individual worse than current standard care. Removal is not what secures it.

**Why the option set secures it.** XT-NA costs nothing on either budget and has ΔNTCP identically zero, so it dominates every strategy of negative utility: substituting it raises the objective and frees capacity at the same time. XT-NA is never removed (Section 8.2), so every patient holds it. No optimal allocation of either the integer problem or its relaxation contains a harmful strategy, whether or not such strategies are present in the option set. Removal is therefore redundant, and the protection is structural. The manuscript argues it rather than asserting a screen.

**What is reported.** The count of assignable strategies whose union ΔNTCP is not positive, excluding the reference arm, whose zero is definitional. It measures how often adaptation or a changed schedule fails to help, which is a quantity of independent interest and is distinct from how often such a strategy is selected. The latter is also reported per allocation and is zero by the argument above: in the exact solvers by construction and in the heuristics by verification.

**The union scalar only.** A strategy that worsens one endpoint while improving the others can still be the right choice, and judging it on a single endpoint would be stricter than the selection rule used everywhere else. Per-endpoint sign violations are counted separately, so the cost of the convention stays visible.

### 8.4 Empty option sets

**No screen can empty a patient's option set.** Coverage rescues rather than removes, and no harm reports rather than removes, so the multiple-choice constraint is always satisfiable and the allocation is always feasible.

One route to a smaller option set remains, upstream of the allocator. If a reduced-margin plan cannot be made robustly acceptable at plan generation, the corresponding adapted arm does not exist for that patient (A31). This removes one or two options from a set of seven and cannot empty it, since XT-NA is unaffected. It is recorded as an absence with its reason, not as an error, and the count of patients affected is reported. The case is not expected to arise.

The evaluator retains the infeasibility raise as a defensive check on its own construction. If it ever fires, it indicates a defect rather than a patient.

### 8.5 Photon adaptation as capacity relief

A stronger adapted photon comparator lowers the number of patients whose ΔNTCP justifies a proton slot, so photon adaptation acts as a capacity-relief mechanism for the proton facility and not only as a tougher comparator. The allocator quantifies it directly, since the proton minutes released fall out of the same optimisation that produces the cohort mean.

With photon adaptation rationed, the relief is the **exchange rate between the two budgets**: the proton minutes released per photon adaptation minute purchased, read off the same C_XT sweep that produces λ_XT. In price terms it is governed by λ_XT / λ_PT: a department gains more from the next photon adaptation minute than from the next proton minute exactly when that ratio exceeds one. The relief with unlimited photon adaptation is the limit of the sweep and is reported as such; the interior of the sweep is what a centre would obtain, conditional on the assumed Δτ_XT.

### 8.6 Reference arm and default arm

XT-NA carries two roles: the numeraire of ΔNTCP, and the arm a patient receives when no capacity is spent on them. The two never separate, since XT-NA is rescued rather than removed and every patient therefore holds it as an assignable option free on both budgets. The heuristic policies place unreferred patients on the reference arm, which is also their cheapest assignable option.

**The reference is current practice.** XT-NA is defined as the photon treatment the patient would receive under current practice: clinical margin throughout, at the schedule clinical eligibility assigns, with offline rescue where coverage fails. This is a single definition applied uniformly, so the numeraire is well defined across patients, policies and configurations. Its one cost is the coupling to the acceptance criterion recorded in Section 8.2.

**Reported quantities.** Six counts are emitted with every allocation, so that the option sets the allocator worked on are visible to a reader who cannot inspect them.

| Count | What it licenses |
| --- | --- |
| Rescues, by arm, schedule and block | The plausibility of a non-adapted arm, and the extra plans the study consumed |
| Disagreements between the RayStation acceptance judgement and the evaluator's verification, by arm and block | Whether the verification reproduces the clinical judgement it models (evaluator E23) |
| Robust-evaluation failures, by arm | How often a plan accepted on nominal dose fails its worst-case evaluation; descriptive, never a rescue trigger |
| Assignable strategies whose ΔNTCP is not positive | How often adaptation or a changed schedule fails to help, distinct from how often it is selected |
| Patients with no free assignable option | Zero by construction; a regression check on the construction, not a finding |
| Patients for whom an adapted arm was not generated (A31) | Whether the margin reduction was deliverable at all in this cohort |

## 9. Time model

Only Δτ, the difference in machine occupancy between an adapted and a non-adapted fraction, enters the capacity constraint. Components are therefore classified by whether they survive the difference. The classification below is written for protons; Section 9.1 states what carries over to photons.

| Component          | Enters Δτ?    |
|--------------------|---------------|
| Setup              | No            |
| Contouring         | Yes (+)       |
| Re-optimisation    | Yes (+)       |
| Plan QA and checks | Yes (+)       |
| Beam delivery      | Yes (+ and −) |

Contouring and QA appear in both workflows but not in both daily budgets. Patient-specific QA is performed per plan. Both arms carry an initial plan of record generated on the pCT and verified once before treatment starts; that verification is common to both and cancels in the difference. In the adapted arm a new plan exists at each adapted fraction, and its verification necessarily falls inside the session. The same holds for contouring. Both therefore enter Δτ with a positive sign rather than cancelling.

**The verification of an adapted plan is a computation, not a measurement (A15).** Measurement-based patient-specific QA cannot be performed on a plan generated while the patient is on the couch, so online adaptive workflows verify through an independent secondary dose calculation. The clinical figure of just under 7 min for the adaptation step, including QA and plan assessment, is consistent only with that. The adaptation cost therefore stays inside the treatment session, and τ captures all of it. Confirmation with the PARTICLE physicists is still worth obtaining, since the argument is structural rather than local.

Delivery time carries two effects of opposite sign that are kept separate. Margin reduction shortens delivery, through fewer energy layers and spots. Hypofractionation lengthens the individual fraction, through higher MU, while shortening the course.

Decomposing τ rather than sweeping it as a scenario parameter is what allows the module to answer where engineering effort should be invested, which the reference study cannot. Since no measured Δτ exists for abdominal OAPT, the decomposition serves a second purpose: it is how a defensible envelope of plausible Δτ values is constructed, component by component with declared provenance, against which the threshold of Section 6.2 is compared. Which components are extractable from RayStation plan data and which must be modelled with clinical input is open decision 3.

**Cost is per fraction.** Under the online reading of Section 4, every fraction of an adapted course is adapted and pays Δτ, while one replan per block stands for the daily replans in the dose model. The occupancy of a strategy is therefore:

occupancy = n_fx · (τ_0 + Δτ) for an adapted arm, n_fx · τ_0 otherwise

which is the reference study's own accounting, recovered exactly. For the modelled workflow this charge is exact, not conservative (A16). The approximation lies on the dose side, where one plan per block stands for daily plans (A1). Charging the adaptation once per block instead would price an offline workflow in which the first block is delivered at reduced margin without daily imaging, which A25 excludes, so that accounting is not used, including as a sensitivity bound.

**What the budgets price is online adaptation.** An offline rescue replan is performed between fractions and does not lengthen a session, so it enters neither expression. The same argument already excludes patient-specific QA under A15 and the photon baseline session under A17. The consequence is that λ_PT reads as the price of in-room time rather than of adaptation effort in general, and that the planning and physics labour of rescues and replans is priced nowhere in this model (A28).

### 9.1 The photon side

The adapted photon arm consumes photon adaptation minutes with the same per-course structure:

occupancy_XT = n_fx · Δτ_XT for XT-A, zero for XT-NA

Three differences from the proton expression are deliberate.

- **The baseline session does not appear.** Photon delivery is unconstrained, so only the increment is charged (A17). No photon baseline session length is required by the design.
- **Δτ_XT is an independent variable, as Δτ_PT is.** The photon literature offers one anchor of the right order, roughly 16 additional minutes per adaptive pelvic photon fraction reported by McComas et al. That anchor places the sweep range; it is not adopted as a measured value for this indication (open decision 12).
- **The component decomposition of Section 9 is not repeated.** For photons the adaptation step is re-contouring, re-optimisation and verification, and the arguments about which components survive the difference are the same in structure. Whether measurement-based verification is feasible within a photon session, which A15 answers negatively for protons, is part of open decision 12.

The two adaptation times are separate axes of the study rather than one. Section 5.7 of the road document describes the resulting plane.

## 10. Fractionation

### 10.1 Formulation

Fractionation enters as an additional component of the strategy tuple. The MCKP absorbs it without modification. The difficulty is in what it does to u and τ.

**The schedule is a decision variable for six of the seven options and not for the seventh.** The fractionation schedule of XT-NA is fixed per patient by clinical eligibility, exogenously to the optimisation (A32). XT-NA represents the treatment the patient would receive under current practice, and current practice chooses the schedule on protocol criteria. XT-A, PT-NA and PT-A each carry both schedules. Nothing in the formulation changes: the option set is simply smaller for the arm that carries no choice.

**Proton hypofractionation is an investigational arm.** No protocol exists for hypofractionated proton treatment at the candidate sites. The proton arms therefore carry both schedules for every patient, planned with the clinicians, and their tumour-control equivalence is an assumption of this study rather than a protocol fact (A5). Hypofractionation is valuable on the proton arms through the capacity it frees, whatever its ΔNTCP.

**The photon option set may be refined.** Which schedules the photon protocols sanction, for which patients and on which photon arm, depends on the protocol the clinicians apply at the chosen site: adaptive stereotactic treatment, non-adaptive stereotactic treatment, or conventional fractionation. It is open decision 31, and the photon options are reconstructed from the clinicians' answer.

**Biological side.** Changing (n, d) changes tumour and OAR EQD2 differently, because α/β differs.

**Capacity side.** Under a closed cohort with a fixed patient list, shortening a course frees capacity that has no new claimant, since no additional patient can be admitted. Making the capacity dimension meaningful requires replacing the per-day constraint by a horizon-total one:

Σ_p Σ_s n_ps · τ^PT_ps · x_ps ≤ C_PT,horizon

and likewise for the photon adaptation budget. The cost of a strategy becomes total occupancy over the course rather than per day, so hypofractionation and adaptation compete on equal terms within each resource, and each multiplier prices them in the same units.

**Where the freed capacity goes.** In a closed cohort the capacity released by hypofractionation can be spent in exactly two ways: upgrading an existing patient to adaptation, on either modality, or moving a patient off the photon arms onto protons. The second is the displacement channel of the reference study running in reverse. It exists only because a photon strategy sits inside S_p at zero proton cost; without a photon option inside the option set, hypofractionation would carry no capacity value at all in this model. This mechanism is what makes the cohort-composition channel representable in a fixed-cohort formulation.

**The sign of the hypofractionated reference.** For a patient whose XT-NA is hypofractionated, the numeraire is a hypofractionated arm. The sign of its utility relative to the standard-schedule photon arm therefore moves the zero point of all that patient's ΔNTCP values. That sign is not predictable in advance. The equivalent-dose penalty of a large fraction size falls on the high-dose region, while an endpoint driven by mean dose over a parallel organ may still favour the hypofractionated arm because the irradiated volume is smaller. It is organ-dependent and can be mapped parametrically, over the plausible range of α/β and of the volume parameter, for a family of synthetic dose-volume histograms. The computation needs the endpoint models and therefore the site, so it follows decision 19.

### 10.2 The daily and horizon constraints

Under stationary operation with staggered starts, the horizon constraint is the mean of the daily constraint. Model the number of patients concurrently under treatment as L = r · W, with r the start rate, W the course duration in days and one fraction per patient per day. The mean daily load is then L · τ averaged over the mix, and the horizon total is that quantity multiplied by the horizon length. Little's law is class-agnostic, so heterogeneous fraction counts across strategies do not break this: with classes indexed by strategy, the mean concurrent load is the sum over classes of r_s · n_s.

This equivalence is exact for the **mean** load (A2). It does not guarantee that every day is feasible. Between-patient heterogeneity (five against conventional fraction counts, τ_0 against τ_0 + Δτ) and discrete starts make the daily load fluctuate about its mean, so the horizon constraint is a relaxation of daily feasibility, and the allocation is an upper bound on achievable throughput rather than a schedule. Daily feasibility is a scheduling question and is out of scope (Section 1). It could be checked, without changing the allocation, by simulating staggered starts under the optimal allocation and reporting the fraction of days over capacity; this check is not planned.

What remains is **one shadow price per resource**, each reportable in two units. Utility per machine-minute per day answers whether a workflow change costing Δτ per fraction is worth it. Utility per machine-minute over the horizon answers whether a schedule is worth its total occupancy. For a given resource they are not independent quantities; λ_PT and λ_XT are independent, since they price different machines. The same argument applies unchanged to the photon adaptation budget.

### 10.3 Schedule equivalence without a TCP model

Candidate schedules for the photon arms are restricted to those **sanctioned by clinical protocol** for the indication, so their equivalence rests on trial evidence and clinical consensus, not on a linear quadratic conversion of the tumour prescription. The proton hypofractionated arm is planned with the clinicians, at a prescription agreed with them; its equivalence for tumour control is assumed (A5, Section 10.1).

Three consequences:

- Tumour α/β is **not** required, since no conversion between tumour prescriptions is needed. It is nonetheless declared and used to report target EQD2 per arm as a descriptive safeguard, so that any residual mismatch in tumour effect between arms is visible. Target EQD2 is not used to assert equivalence.
- OAR α/β **is** required, since NTCP models are fitted at conventional fraction size and any cross-schedule comparison requires conversion of OAR dose to EQD2.
- Repopulation is neglected, which is internally consistent with not modelling TCP. The model will not penalise a schedule that lengthens overall treatment time (A6).

### 10.4 Anatomical site: two candidates

Neither candidate is adopted; nothing in this document depends on the choice being made yet (decision 19). The criteria are ordered by weight. The study requires, first, a site where clinicians are genuinely in doubt between the two schedules and where the plans can be generated with them; second, repeat imaging in the cohort; third, endpoint models. A model without a fractionation term is usable, evaluated on mean EQD2 at a declared α/β, with the approximation stated as a limitation (decision 10).

| Criterion | Pancreas | Adrenal |
|---|---|---|
| Clinical doubt between two sanctioned schedules | Present. In locally advanced disease both conventionally fractionated chemoradiation and five-fraction stereotactic treatment are recommended, which is the condition A5 requires | Weak. The setting is oligometastatic and the schedule set is institutional rather than guideline-fixed |
| Cohort with protons and repeat imaging | To be verified with the clinical partner | Unlikely |
| Clinical rationale for adaptation | Adaptation is recommended for dose-escalated stereotactic treatment in the current guideline | Very strong empirically. A published magnetic-resonance-guided series reports adaptation in essentially every fraction, which argues for adaptation and at the same time leaves the adaptation decision with almost no variance |
| Clinical rationale for a proton arm | Present in the literature | Weak. Proton treatment of adrenal lesions is rare |
| Endpoint models | Duodenum, stomach and bowel, on a thin empirical base | Thinner still |
| Target volume comparability across schedules | Weak. Conventional treatment includes elective coverage of regions at risk of microscopic disease while stereotactic treatment does not, so comparing the two protocol schedules confounds fraction size with target volume. If pancreas is chosen, the target volume is fixed explicitly | Not applicable in the same form |
| Intent | Curative or near-curative | Oligometastatic, with competing mortality |

**A dilemma that does not resolve itself at either site.** Adaptation is recommended for dose-escalated stereotactic treatment, and dose escalation is the point at which the two schedules stop being isoeffective on the target. Choosing the non-escalated schedule preserves A5 and weakens the clinical rationale for adaptation. Choosing the escalated one strengthens the rationale and forfeits A5, which without a TCP model cannot be repaired. The choice is made explicitly and declared.

## 11. Assumptions register

| ID | Assumption | Status | Risk |
|---|---|---|---|
| A1 | Anatomy on rCT_j represents the whole block of fractions following it | Inherited from the reference study | Variation within a block is not represented, for any arm |
| A2 | Course-averaged occupancy converts per-fraction time into load | Exact for the mean load under Little's law, for heterogeneous classes in steady state (Section 10.2) | Daily feasibility is not guaranteed; the allocation is an upper bound on throughput, not a schedule |
| A3 | Photon **delivery** is unconstrained; photon **adaptation** is constrained by a budget C_XT | Confirmed at supervision | Introduces a second shadow price and makes the relief of Section 8.5 a function of C_XT |
| A4 | Every arm is generated to protocol on the image available at planning time | Design constraint on plan generation | Must be demonstrated per arm, not asserted |
| A5 | Protocol-sanctioned photon schedules are clinically equivalent for tumour control; the proton hypofractionated arm, planned with the clinicians, is assumed equivalent | Photon schedules: confirmed available at supervision, resting on clinical consensus. Proton hypofractionation: assumption, since no proton protocol exists | Limits the photon arms to sanctioned schedules. The proton equivalence is weakest for patients the photon protocol deems ineligible for hypofractionation. Target EQD2 reported descriptively |
| A6 | Repopulation neglected | Accepted, consistent with no TCP model | The model will not penalise lengthened schedules |
| A7 | Linear quadratic model valid for OAR EQD2 conversion over the fraction sizes considered | To be checked against real cases | Applies to OARs only, not to the tumour claim |
| A8 | Toxicity endpoints independent in the union probability | Inherited from the reference study | False; accepted as best available |
| A9 | Adapted plans generated offline are equivalent in quality to those an online workflow would produce | Inherited from the reference study | Acknowledged there as requiring further investigation |
| A10 | Photon dose is recomputed on the rCTs and judged on the same criterion as the proton arms | Inherited from the reference study, where it is standard clinical practice; not described in the paper, confirmed by its corresponding author (Section 2) | Asymmetric screening would bias ΔNTCP against protons |
| A11 | Coverage is judged **per block** on the nominal dose of the plan delivered in that block | The accumulated criterion is rejected as permissive in the wrong direction | Stricter than an accumulated criterion |
| A12 | No harm is judged on the union scalar rather than per endpoint, and is **reported rather than enforced** | Confirmed at supervision (Section 8.3) | A strategy worsening one endpoint may be selected; per-endpoint violations are counted |
| A15 | Patient-specific QA of an adapted plan is an independent secondary dose calculation and consumes no beam time | Structural argument, consistent with reported adaptation times. Confirmation with the PARTICLE physicists outstanding | If false, part of the adaptation cost lands outside the session and τ alone no longer captures it |
| A16 | Every fraction of an adapted course carries the full Δτ_PT | Exact for the modelled workflow, systematic online adaptation (Section 4); inherited from the reference study | None for the cost model. The approximation is on the dose side (A1) |
| A17 | The adapted photon arm is charged only the adaptation increment Δτ_XT, not a baseline session | Follows from A3 | If photon delivery is in fact binding at the partner centre, C_XT understates photon demand and λ_XT is too low |
| A19 | Every fraction of an adapted photon course carries the full Δτ_XT | As A16 | As A16 |
| A20 | C_XT is a policy parameter of the study rather than a measured facility quantity | No measured anchor exists for this indication | Handled by reporting λ_XT and Δτ\* as functions of C_XT; a single value is reported only at C_XT^ref (decision 13) |
| A21 | Every patient retains an assignable option that is free on both budgets, namely XT-NA | Structural: XT-NA is rescued, never removed | None while rescue is unpriced (A28). If a rescue were priced, XT-NA would cease to be free for the patients who need one |
| A23 | The first block is evaluated on the planning anatomy, for every arm | Inherited from the reference study, whose accumulation weights the pCT dose by the first ten of thirty fractions | Favours the non-adapted arms, which would already degrade during the first block, and understates the benefit of adaptation by an amount scaling with the first block's share of the course. Stated as a limitation; can be investigated by re-weighting (Section 4) |
| A24 | An adapted arm adapts systematically, at every block, at reduced margin; a non-adapted arm adapts reactively, only where coverage fails, at clinical margin | Supervisory decision | Partial adaptation is not representable, so the study cannot report whether early or late adaptation carries more benefit. "Non-adapted" is defined on first use in the manuscript |
| A25 | The reduced margin is a property of the adapted arm and applies from the first fraction, on the pCT plan | Supervisory decision. Matches the reference study | Coherent only under the online reading of Section 4; a reduced margin delivered without daily adaptation is excluded |
| A26 | The indication is abdominal and the anatomical site is not yet fixed | Two candidates, pancreas and adrenal. Decision 19 | The endpoint set, the cohort, the protocol schedules and the clinical rationale for a proton arm all depend on it |
| A28 | Offline rescue replanning is unpriced on both budgets | Confirmed at supervision; the reference study prices rescue the same way. Consistent with A15 and A17 | The planning and physics labour a rescue consumes is priced nowhere in this model, so a department whose bottleneck is dosimetry rather than machine time is outside its scope. The labour of adapted replans is likewise priced only through in-room minutes. If labour were priced, adapted arms, which replan at every block, would carry more of it than non-adapted arms, which replan only on failure; omitting it therefore favours adaptation. Its effect on the proton-versus-photon comparison depends on the relative rescue rates of XT-NA and PT-NA and is not signed. Stated as a limitation |
| A29 | A rescue plan carries forward to subsequent blocks and is judged again on each of them | Confirmed at supervision. Reverting to the pCT plan after the failing block corresponds to no clinical practice | An arm that fails repeatedly becomes a sequence of clinical-margin replans whose plan count approaches that of an adapted arm |
| A30 | A rescue does not change the margin or the setup error | Supervisory decision | Keeps the two arm families distinct. The margin and adaptation components of the benefit remain confounded within this cohort and are separated by reference to the published lung cohort |
| A31 | If a reduced-margin plan cannot be made robustly acceptable at plan generation, the corresponding adapted arm does not exist for that patient | Supervisory decision. Expected not to arise | Removes one or two options from a set of seven and cannot empty it. Enlarging the margin or accepting a degraded plan would break A25 and A4 respectively. The count is reported |
| A32 | The fractionation schedule of XT-NA is fixed per patient by clinical eligibility, exogenously to the optimisation | Supervisory decision. The photon option set may be refined by decision 31 | The eligibility flag is required patient data and depends on the protocol for the site. Where the flag is hypofractionated, the numeraire for that patient is a hypofractionated arm (Section 10.1) |

Retired: A13, A14, A18, A22, A27. Their content is in `CHANGELOG.md`.

## 12. Open decisions

Only open decisions are listed. Closed decisions are stated in the sections they govern; their history is in `CHANGELOG.md`. Identifiers are stable and are not reused.

| ID | Question | Owner | Blocks |
|---|---|---|---|
| 3 | PARTICLE operating model: hours per day, rooms, beam sharing, clinical slot length. Which Δτ components are extractable from RayStation plan data and which must be modelled | Clinical partners | The plausible Δτ envelope, not the formulation |
| 7b | Which metrics instantiate the acceptance criterion (the plan acceptance protocol used at treatment planning). Two directions are not equivalent and are kept apart when the list is requested. **Target metrics**, V95% and D5 on the target, extend the screen along the axis it already measures and change nothing structural. **OAR metrics**, Dmean and Dmax on the organs driving the endpoints, would let the screen fire on normal-tissue grounds; the upper tail of the non-adapted arms' NTCP distribution would then be truncated, and the study would report adaptation benefit conditional on standard-of-care rescue, which is defensible but is a different result. Both sets are collected, since the OAR metrics are useful descriptively; which enter the screen is decided separately. Fixed before plan generation (Section 8.2) | Clinical partners and RTTs; gated on 19 | The numeraire (Section 8.2), plan generation, and the meaning of the primary endpoint if OAR metrics enter |
| 10 | Endpoint model family for the chosen site. A model with a fractionation term is used as fitted. A mean-dose model without one is evaluated on mean EQD2, after voxel-wise conversion at a declared α/β; the approximation is that it was fitted on physical dose at conventional fraction size, stated as a limitation and bounded by the α/β sensitivity. No model is evaluated on physical dose across schedules, since a five-fraction plan delivers lower physical dose for the same biological effect | Candidate, with clinical partners; gated on 19 | The endpoint set |
| 12 | Plausible range for Δτ_XT, and whether photon plan verification is measurement-based or computational within a session | Clinical partners | The sweep range, not the formulation. The analogue of A15 on the photon side |
| 13 | The reference value C_XT^ref, in absolute minutes, analogous to the 480 proton minutes of the reference study. The sweep axis is settled (Section 5.2) | Clinical partners and supervisor | The (Δτ_PT, Δτ_XT) plane of road 5.7 |
| 19 | Anatomical site: pancreas or adrenal (Section 10.4) | Supervisor and clinical partners | Endpoint selection, cohort, protocol schedules, plan budget, and every quantity downstream of them |
| 23 | Block structure of the hypofractionated schedule: which images represent its blocks, and hence B and the plan budget. If each fraction is a block, with the first fraction delivered on the pCT plan (A23), an adapted arm needs five plans and a patient nineteen before rescues, against fifteen with the standard block structure. If the cohort's repeat images come from conventionally fractionated courses, they span more anatomical change than a one-to-two-week course experiences; the mapping of images to blocks is then set by elapsed time from the start of treatment, and the resulting bias, which overstates the benefit of adapting a short course, is declared | Candidate, with clinical partners; depends on the data | Whether the fractionation axis is affordable in planning hours, and the rescue frequency of the short course |
| 25 | Dose engine and cross-modality reporting conventions. All dose for paper 1 is computed in RayStation and imported (evaluator E16). Which RayStation dose algorithm generates the proton plans, analytical pencil beam or Monte Carlo, and the reporting conventions for both modalities (RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin) are not yet fixed | Clinical partners | Bears on the study's premise: analytical proton dose is least reliable in the heterogeneous abdomen, and the resulting error is systematic, falling on the arm whose anatomical degradation the study measures |
| 26 | Replanning without operator variation. Every adapted arm replans at every block, and every rescue is a replan (Section 8.2). Whether one objective template can be scripted in RayStation and applied without intervention, and whether the resulting plans are clinically plausible, is open. The reference study re-optimised with the objectives of the pCT plan and fine-tuned where necessary to ensure coverage and avoid hot spots, so a template applied without intervention is stricter than the reference. What protects the endpoint in either case is one acceptance rule applied identically to every replan and stated in Methods | Candidate; feasibility probe | Whether plan quality becomes a function of operator effort, which would enter ΔNTCP as a confounder on the primary endpoint |
| 28 | Clinical and reduced margins for both modalities. The clinicians supply them for one modality; the other is derived by conversion. The reference study converted a photon PTV margin (van Herk recipe) into a non-isotropic proton setup error, with robust optimisation capped at 5 mm and the remainder applied as a CTV expansion; the same conversion, or its reverse, applies here. The single uncertainty budget of road 4.2 is what makes the two reduced settings comparable | Candidate proposes; supervisor decides; clinicians supply one modality | Plan generation for every arm |
| 29 | Source of target and OAR contours on the repeat images: clinical recontouring, DIR propagation with review, or delineation for the study, and by whom. Needed for the acceptance judgement, the adapted replans and the rescues | Clinical partners; depends on the data | Plan generation from the second block on; the delineation term of the uncertainty budget (road 4.2) |
| 30 | Route for recomputing a plan on a repeat image in RayStation: dose computed on an additional examination, or the plan copied to the repeat image as a new beam set. The reference study recomputed its non-adapted plans on each repeat CT without stating the route. The route determines what the export contains and how the manifest verifies which image a dose belongs to (extractor 4, X7, X8) | Supervisor | Extraction of every non-adapted block from the second on |
| 31 | Which schedules the photon protocols sanction at the chosen site, for which patients and on which photon arm: adaptive stereotactic, non-adaptive stereotactic, conventional non-adapted, or hypofractionated non-adapted. The photon options of Section 10.1 are reconstructed from the answer; whether the eligibility flag of A32 also constrains XT-A is part of it. Decision 18 fixed the current structure at supervision, so a change goes to the supervisor | Clinical partners, then supervisor; gated on 19 | The photon option set |

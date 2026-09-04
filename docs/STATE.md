# Project state

**Last updated:** 2026-09-04, at tag `design-v6.2`. `allocator_design.md`
bumped to 6.2: T12 and T13 closed, T14 and T15 implemented, three claims
corrected (5.2, 5.3, 6.5), Section 10.3 retired. Detail in `CHANGELOG.md`.

Rewrite this file whenever a document version, an open decision or a code
milestone changes, and rewrite it *before* bumping a document version rather than
after. It is the first file to read and the only file that describes the present.

## 1. Identity

ADAPT-5D, individual research project of DC18 in the RAPTORplus MSCA Doctoral
Network (grant 101226720), hosted at KU Leuven, task T4.2. Supervisor: Sterpin.
Target output: paper 1, covering WP1 (simulation infrastructure) and WP2 (workflow
optimisation). WP3 (reinforcement learning) is deferred to a later publication,
which now also inherits Config 2 and the receding-horizon reallocation.

## 2. Document set

| Document | Version | Owns |
| --- | --- | --- |
| `ROAD_TO_PAPER_1.md` | 6.1 | Scientific question, hypothesis, arm set, uncertainty budget, plan budget, endpoint policy, what the paper claims. Open problems register (4.8). Appendix F, single copy |
| `allocator_design.md` | 6.2 | Optimization problem, algorithm, shadow prices, step-ratio threshold, policy comparison. Assumptions register (11, amended at 11.1) and open decisions (12) |
| `evaluator_design.md` | 5.1 | Dose composition, accumulation ordering, EQD2 conversion, NTCP evaluation, admissibility screens, strategy construction. Assumptions register (10, amended at 10.1) |
| `extractor_design.md` | 4.1 | Ingest, registration, storage, target metrics, plan complexity, ROI naming, provenance |
| `CHANGELOG.md` | - | Version history for all four. Kept in the repository, not in the project knowledge |

The evaluator is one version behind the allocator by convention, not by
oversight: the two registers are amended by the same decision, recorded as
version 6 in one and version 5 in the other. That lockstep is on the major
number only. Allocator 6.2 is a housekeeping and test bump internal to that
document, touching neither a shared decision nor the evaluator, so the minor
numbers (6.2 against 5.1) are not expected to match going forward.

## 3. Design, in one paragraph

The treatment choice is made at prescription on the planning CT. Each patient
carries four workflows per fractionation schedule, XT-NA, XT-A, PT-NA and PT-A,
and eight over the two schedules. An adapted arm adapts at every block and carries
a reduced-margin plan from the first fraction; a non-adapted arm carries the
clinical-margin pCT plan for the whole course, recomputed on each repeat image.
There is no per-block adaptation decision. Two resources are priced: proton
machine time and photon adaptation time. XT-NA consumes neither and is both the
ΔNTCP reference arm and the always-assignable fallback.

## 4. Open decisions

### Sterpin

| ID | Question |
| --- | --- |
| 11 / A3 | Photon adaptation may be rationed. Revises the version 4 decision that photon capacity is unconstrained |
| 16 / A12 | No-harm screen becomes a reported diagnostic rather than an enforced removal. Carries an ethical framing |
| 17 / A22 | Referral threshold applied to ΔNTCP against the reference arm even where that arm is not deliverable |
| 18 | How to treat a free hypofractionated photon arm. Treatment C, a third capacity row for photon stereotactic delivery, is excluded: a five-fraction course releases linac time rather than consuming it, and any scarcity on that side lies in the adaptation, already priced by C_XT. A, B and D remain live and none is adopted |
| 24 | Handling of the coverage screen: whether single-block failure should remove an arm for the whole course, and what the fallback is when XT-NA itself is removed |
| 7b | Whether criteria beyond V95% below 95 per cent enter the coverage screen. Moved here from the candidate list: it defines when the screen fires and belongs with 24 |
| - | Confirmation that paper 1 answers which patient receives which workflow, and that the right-time framing of the work package belongs to a subsequent publication rather than specifically the second |

Decisions 24, 16, 17, 11 and 7b form one question seen from five angles: what
protects the individual patient when the free option is not deliverable. A3 is
part of it and not an aside, since a fallback is a problem only because photon
capacity is rationed: A21 guarantees a free option, XT-A is not free, so a
commitment on C_XT is incurred the moment XT-NA is removed.

**Put to supervision on 31 August 2026**, in one message: the five above, plus 18
and the scope confirmation. Nothing in this section is settled until the reply
arrives, and no manuscript text should be written against any of it in the
meantime.

On A and B, for the record, since the distinction is easy to state wrongly. Both
are constants chosen by us and both are reported as a sweep, so they do not differ
in being fixed against parametric. They differ in that ε filters the option set
before the solve while π reprices inside the objective, and in that ε compares the
hypofractionated arm against one nominated comparator while π compares against
every alternative available to that patient. For a patient whose best alternative
is that comparator, filtering at ε and penalising at π = ε select the same
strategy; they diverge only on the patients where the choice between A and B
changes a result. A third difference is not recorded in allocator 12.1: π enters
the objective, so it changes which options lie on the convex hull and therefore
the duals, making λ_PT and λ_XT functions of π. Reportable as λ(π) if π is a
sweep; concealed if a single value is ever adopted. A and D are not mutually
exclusive: D fixes the option set on clinical grounds and B or A then report how
much of the population mean is fragile to the cost of a schedule change.

Not a decision, recorded so that it stops reappearing as one: fourth-year funding
rests on a verbal assurance from Sterpin that money can be found if needed. No
source is identified and none is required before the Career Development Plan at
M13.

### Clinical partners

| ID | Question |
| --- | --- |
| 3 | PARTICLE operating model: hours per day, rooms, beam sharing, clinical slot length. Which Δτ components are extractable from RayStation plan data |
| 12 / A15 | Plausible range for Δτ_XT, and whether photon plan verification is measurement-based or computational within a session |
| 13 | Reference value C_XT^ref |
| 25 | Which RayStation dose engine generates the proton plans, analytical pencil beam or Monte Carlo, and the reporting conventions for both modalities: RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin. The engine choice bears on the premise of the study, since analytical dose is least reliable in the heterogeneous abdomen and the error is systematic rather than random, so it does not average out over the cohort and it falls on the arm whose degradation under anatomical change the paper measures |
| - | Whether short-course patients in the cohort have any repeated imaging. Determines whether the hypofractionated schedule has blocks at all, and therefore whether decision 23 arises |

### Split

| ID | Question | Split how |
| --- | --- | --- |
| 10 | Endpoint selection, constrained to models admitting an explicit dose-per-fraction correction. Recorded in allocator 12 and road 4.8 as item 3 of the open problems register, but absent from this table until now | Candidate proposes the model family, Sterpin decides; gated on 19 |
| 19 | Anatomical site: pancreas or adrenal | Partners indicate which cases exist; Sterpin judges whether they are suitable |
| 23 | Block granularity for the hypofractionated schedule. Blocks equal to fractions gives five replans and 22 plans per patient; coarser blocks restore parity at 16 but model adaptation less often than the photon literature reports | Candidate proposes, Sterpin decides, conditional on the partner answer on repeated imaging |

### Candidate, unblocked

| ID | Question |
| --- | --- |
| 20 | Per-replan cost accounting as a sensitivity bound on A16 and A19 |
| 26 | Whether the replans required by the adapted arms are producible without manual intervention. PT-A and XT-A adapt at every block, so each patient needs one fresh inverse optimisation per block per adapted arm, not a recomputation of an existing plan on new anatomy as in the non-adapted arms. Decision 23 fixes the count at 16 or 22 plans per patient. If each replan requires an operator to adjust objectives until the plan is acceptable, plan quality becomes a function of effort spent, effort is not constant across arms, and the difference enters ΔNTCP as a confounder on the primary endpoint. The question is therefore whether a fixed objective template can be scripted in RayStation and applied without intervention, and whether the resulting plans are clinically plausible. Raised in `dc18_timeline.docx` §8.3 as an argument for option 4 and left without an owner when that option was dropped |

**Closed by the doctoral candidate, August 2026.**

| ID | Decision | Reason recorded |
| --- | --- | --- |
| 21 | First block evaluated on the planning anatomy, for every arm | The convention of the reference study, followed for comparability. The distortion favours the reduced-margin arms and scales as one over the number of blocks; its direction is known, its size is not measured |
| 22 | The reduced-margin non-adapted diagnostic is not computed | A reduced-margin plan delivered without adaptation is clinically incoherent. Excluded knowingly: the margin-reduction and adaptation components of the benefit must therefore be separated by reference to the published lung cohort rather than within this cohort |
| - | Displaced patients are retained in the denominator of the cohort mean | Comparability with the reference study, which divides by 14 throughout. To be stated in methods, since it makes the mean an intention-to-treat quantity over the referred population rather than over the treated one |

Resolved and recorded for reference: 14 (heuristic ranking convention), 15 (ILP
as reference solver).

## 5. The blocking chain

Decision 19 (site) gates decision 10 (endpoint selection), which gates the entire
fractionation axis. Two facts tighten the chain: fractionation-correctability of
the endpoint models at a candidate site is a criterion for choosing the site, not
only a consequence of having chosen it; and at pancreas the two protocol schedules
differ in elective target coverage, so comparing them confounds fraction size with
target volume.

Decision 24 is second in weight. The count of patients for whom neither XT-NA
under the standard schedule nor XT-NA under the hypofractionated schedule survives
the coverage screen is what makes the no-harm property empirical rather than
structural. No manuscript claim should rest on that property before the count
exists.

## 6. Code

Package `tps5d` in the RAPTORproject repository, `src/tps5d/` with `core`,
`allocator`, `evaluator`, `generator`. Conda environment `OpenTPS`, Windows,
PowerShell. Implemented: `schema.py`, `solve.py`, `dominance.py`, `policies.py`,
`report.py`, `figures.py`, `synth.py`, `evaluator/ntcp.py`,
`evaluator/registry.py`. Exact solver `scipy.optimize.milp` (HiGHS), `solve_dp`
retained as an independent cross-check at C_XT = 0.

**The code implements the version 6 design, tagged `design-v6.2`.**
`dominance.py` and `solve.py` are unchanged since version 6: the hull
reduction they implement is what makes the greedy LP ordering valid, not the
collapse over adaptation counts that version 6 retired. `scripts/step_ratio.py`
is deleted.

**Test count.** 164 at the last count, of which 133 in the seven files
touched this round (`test_admissibility`, `test_lp`, `test_policies`,
`test_report`, `test_solve`, `test_threshold`, `test_two_resource`), plus 31
in `test_ntcp`/`test_registry`, untouched and not re-run this round. Adding
T14's 72 parametrized cases to `test_threshold.py` brings the total to **236**,
all passing on SciPy 1.17.1; SciPy 1.18.0, the environment this was last
confirmed on, should be re-checked before the next commit.

**Fixed this round, `allocator/report.py`.** `dominance_counts` anchored the
proton axis at the origin only by accident, through the same filter that
selects the chain, and never anchored the photon axis at all: two paid photon
rungs are mutually non-dominated by construction of `pareto`/`hull` on two
points, so a rung genuinely LP-dominated by a mixture of the free base and the
other rung was silently kept. Confirmed with an adversarial two-rung
construction before the fix (`n_lp_dominated` read 0, should have read 1) and
after (reads 1); the full suite is unaffected. `solve_exact`/`solve_lp` were
never exposed to this, since they solve the full model directly without any
hull pre-reduction; the effect was confined to the diagnostic count.

**Dose provenance.** All dose in paper 1 is computed in RayStation and imported,
photon and proton alike, chosen for throughput given the plan count implied by
decision 23. OpenTPS performs accumulation, evaluation and allocation and
calculates no dose. The photon CCC implementation in OpenTPS is therefore not on
the critical path of this study, and the contribution to D4.1 is entirely
evaluation-side. Neither `extractor_design.md` 4.1 nor `evaluator_design.md` 5.1
currently states this: the evaluator assumes block-level physical dose already
homogeneous without naming its origin. Two consequences are registered as open
decisions 25 and 26, and the assumption itself is to be written into the two
registers at the next version bump.

**T12, T13 closed; T14 and T15 implemented.** T12 tested an outcome the record
already makes unrepresentable by construction and is retired void: no test
could have failed it. T13's only checkable half, the reference-study ladder,
is T1; the other half had no surviving version 5 implementation to check
against, so it is absorbed rather than written. T14 is implemented and
passing, scoped to a single fractionation scheme: allocator 6.5 and road 1
both state the closed form as a per-scheme statement, so T14 checks it there
and not against the pooled two-scheme proton frontier, which the allocator
resolves directly rather than through a closed form. T15, the two-resource
swap check that lived only in `test_two_resource.py`'s own docstring under a
label that collided with allocator 5.4's own T10, is now registered under its
own number in both places.

## 7. Next actions

**Closed this round (allocator 6.2, `CHANGELOG.md` has the detail).** T12
retired void; T13 absorbed into T1; T14 implemented, scoped to a single
scheme; T15 registered, resolving its collision with the document's own T10.
The P2a/P2b claim of allocator 5.3 is corrected: coincidence holds only
within a single scheme, not pooled across two, which is what "re-measure P2a
against P2b" turned out to mean, a prose correction rather than a magnitude
for the manuscript, since a synthetic gap is not a citable clinical number
either way. Decision 20 gained the general closed form
Δτ\*_replan(w) = (n_fx / B) · τ_0 · a / (m − w) in allocator 6.5, with the
single-scheme reference-study illustration corrected: B = 3 (ten fractions
per block, Section 9) gives 30 course-minutes for the standard schedule's
adaptation cost under per-replan accounting, not the 10 previously written
here, and raises the illustrative threshold to 188 min. The cross-schedule
comparison the phrase "reorders the hull" pointed to still needs B for the
hypofractionated schedule, which decision 23 has not fixed, so decision 20
itself stays open.

Still without data or supervisory input:

1. Map the sign of the utility of the free hypofractionated photon arm over the plausible range of α/β and volume parameter, on synthetic DVHs. If it is non-positive for every patient, decision 18 is empty. Requires the endpoint models, so it follows decision 19.
2. On the first exported case, measure dose grid dimensions and masked ROI volumes before fixing the storage strategy.
3. Run decision 26 as a feasibility probe on one patient rather than as a question: script one adapted-arm replan per modality from a fixed objective template and record whether the result is acceptable without intervention. The answer sizes the whole cohort phase and is needed before the plan-generation effort is committed.

**Result recorded, no action outstanding.** The degeneracy check on `pen` in
`two_scheme_check.py` is done. The standard adapted arm is the highest-cost point
of a patient's proton frontier, so it lies on the hull exactly when it carries
the highest utility, which gives the closed form pen\* = a · (a_mult − 1),
independent of Δτ. At a_mult = 1 the two adapted arms are tied at pen = 0 and the
cheaper one survives only by the tie-break, so the threshold there is zero and
carries no information. This refines allocator 6.5, which currently states that
competition between schemes is resolved by the allocator and not by any closed
form: one component of that competition does have one. Not part of this round;
still to be written into the document at a future version bump.

**Decided, August 2026.** Hypofractionation is not modelled as requiring
adaptation. Non-adapted hypofractionated arms are removed by the coverage screen
on evidence, not by construction. The reason is the side effect: removing them by
construction would also dissolve A27 and open decision 18, retiring two items
nobody had decided to retire. The generator flag is retained as a near-free
sensitivity.

**Still pending a version bump**, none of it touched by 6.2, in
`allocator_design.md`: the closed form for pen\*; the dose provenance
assumption and the cross-modality reporting convention, also in
`evaluator_design.md`; the closure of 21, 22 and the denominator convention;
in 12.1, the exclusion of treatment C with its reason and the note that A or B
and D are not mutually exclusive; and the deletion of Appendix A, the memo on
alternative units for the photon adaptation budget, which is no longer needed.
Each needs a `CHANGELOG.md` entry, which lives in the repository.

## 8. Calendar

Full detail in `dc18_timeline.docx`. Salient points only here.

| PM | Date | Item |
| --- | --- | --- |
| M13 | Jan 2027 | Career Development Plan, and the ADAPT-5D data description for the consortium DMP. Both to be drafted at M11 or M12: M13 to M15 are fully committed |
| M14 | Feb 2027 | Training Camp 1, presentation to the EU Project Officer |
| M15 | Mar 2027 | Secondment 1, Ljubljana, Jeraj, **2 months** |
| M19 | Jul 2027 | **D4.1, Upgraded OpenTPS.** Public, posted automatically by REA. Feature freeze before departure at M14 if possible |
| M30 | Jun 2028 | Secondment 2, HPTC, Blommestein, 2 months |
| M33 | Sep 2028 | **MS13**, verified by implemented software, not by a manuscript. Internal freeze around M28 |
| M37 | Jan 2029 | D4.7, automated biological adaptive PT planning. Depends on D4.2, D4.3 and D4.5 from other groups |
| M40 | Apr 2029 | Secondment 3, COSYLAB, Anderle, 1 month |
| M42 | Jun 2029 | Funded contract ends |
| M48 | Dec 2029 | Thesis draft for MS18 |

Two facts that bear on planning paper 1:

- **The only uninterrupted writing windows in the contract are M19 to M24 and M32 to M39.** Everything else is committed to secondments, network events or reporting.
- **The secondment total is five months, not seven.** Annex 1 requires one visit of at least three months; the deviation was raised by Sterpin and accepted, so no visit needs extending. Recorded so the shortfall is not reopened when reports are collected for MS17.

**Secondment 1 scope is decided: option 1, photon plan evaluation.** Agreed with
Sterpin and the OpenTPS team in August 2026. Options 2, 3 and 4 are dropped; the
four-option assessment is retained in `dc18_timeline.docx` §8.3 so that the
grounds for exclusion are on file for MS17. The detailed work packet is not fixed
beyond the requirement that it serve the content of paper 1. Machine commissioning
and MLC or VMAT work in OpenTPS are excluded. Photon planning is treated as
already present in the platform and as requiring no work from this project.

Two facts qualify the decision and are recorded rather than reopened. Since all
dose is imported from RayStation, the photon CCC implementation is not on the
critical path of paper 1, so the host link that motivated Ljubljana rests on the
evaluation work itself rather than on the dose engine; the secondment report for
MS17 needs a statement of what made those two months specific to that host. And
the D4.1 feature freeze remains scheduled before departure at M14, reconfirmed
after this decision, which means the visit contributes to paper 1 rather than to
the content of D4.1. That was recorded as the main risk of option 1 and is now an
accepted consequence.

The obligations after M42, including the M48 thesis draft, are conditional on the
fourth year being in place.

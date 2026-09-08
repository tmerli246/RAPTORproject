# Project state

**Last updated:** 2026-09-08, at tag `design-v6.3`, after the supervisory reply of
early September 2026 and the code round that followed it, same day. The reply
changes the coverage screen from a removal mechanism to a rescue mechanism and
fixes the fractionation schedule of XT-NA exogenously. Both amend registers in
two documents at once, which is the criterion version 6 used, so the document
round was major: `allocator_design.md` to **7.0**, `evaluator_design.md` to
**6.0**, `ROAD_TO_PAPER_1.md` to **7.0**, `extractor_design.md` to **4.3**.
These four, `CHANGELOG.md`, and this file are committed together in one
commit, separate from and after the four code commits, since the documents
were finalised before the code implementation began but had not been
committed until now. Detail for every round in `CHANGELOG.md`.

**Code tags track behaviour, not the document version number, and the two are
not the same count.** A code round is tagged `design-vX.Y` for the document
generation its *behaviour* matches, X, with Y as a sub-counter for code-only
increments within that generation; it is not bumped to a document's version
number merely because the code touches something that document also covers.
The code round changed the schema and the synthetic generator to carry the
version 7 option-set structure and rescue metadata, but the evaluator's dose
composition and coverage screen, the part of the design that actually
changed *behaviourally* at version 7, are untouched, so the code still
*behaves* like version 6 throughout. **Tagged `design-v6.3`**, the next patch
in the v6 series, not v7.0. Commit history is in Section 6. The first
`design-v7.x` tag is earned once the evaluator implements the rescue
substitution; its number is not decided now.

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

All six live in `docs/` at the repository root, alongside `README.md` and
`src/tps5d/`; see `README.md`'s Structure section.

| Document | Version | Owns |
| --- | --- | --- |
| `ROAD_TO_PAPER_1.md` | 7.0 | Scientific question, hypothesis, arm set, uncertainty budget, plan budget, endpoint policy, what the paper claims. Open problems register (4.8). Appendix F, single copy |
| `allocator_design.md` | 7.0 | Optimization problem, algorithm, shadow prices, step-ratio threshold, policy comparison. Assumptions register (11, amended at 11.1 and 11.2) and open decisions (12) |
| `evaluator_design.md` | 6.0 | Dose composition, accumulation ordering, EQD2 conversion, NTCP evaluation, admissibility screens, strategy construction. Assumptions register (10, amended at 10.1 and 10.2) |
| `extractor_design.md` | 4.3 | Ingest, registration, storage, target metrics, plan complexity, ROI naming, provenance |
| `CHANGELOG.md` | - | Version history for all four. Kept in the repository, not in the project knowledge |

The evaluator is one version behind the allocator by convention on the major
number only. This round moves both majors together, which is what the convention
is for: one supervisory decision amends both registers.

## 3. Design, in one paragraph

The treatment choice is made at prescription on the planning CT. Each patient
carries **seven** options: XT-A, PT-NA and PT-A under each of two fractionation
schedules, plus one XT-NA whose schedule is fixed exogenously by clinical
eligibility. An adapted arm adapts systematically, at every block, at reduced
margin from the first fraction. A non-adapted arm carries the clinical-margin pCT
plan recomputed on each repeat image and is **rescued** by an offline replan at
unchanged margin wherever coverage fails, so "non-adapted" means reactively
adapted rather than never adapted. No screen removes anything. Two resources are
priced, proton machine time and photon adaptation time, and both price online
adaptation only: an offline rescue adds no in-room minutes and is unpriced, which
is the reference study's accounting.
XT-NA consumes neither budget, is assignable for every patient, and is both the
ΔNTCP reference arm and the always-available default.

## 4. Open decisions

### Sterpin

| ID | Question |
| --- | --- |
| 11 / A3 | Photon adaptation may be rationed. Revises the version 4 decision that photon capacity is unconstrained |
| - | Confirmation that paper 1 answers which patient receives which workflow, and that the right-time framing of the work package belongs to a subsequent publication rather than specifically the second |

**Closed by supervision, September 2026.** The reply of early September resolved
five items at once and they are recorded here with their resolution rather than
deleted, since the reasoning is what the manuscript will need.

| ID | Resolution |
| --- | --- |
| 24 | An arm that fails the coverage screen is **rescued** by offline replanning at unchanged margin and continues. Nothing is removed, on any arm. All three sub-questions close: a single-block failure does not remove the arm; there is no fallback problem when XT-NA fails, since XT-NA is rescued like anything else; and the count of patients with no free option is zero by construction, so the no-harm property is structural rather than empirical. Rescue frequency replaces that count as the diagnostic to be produced. A24 amended, A21 becomes structural, A22 void, A27 retired, A28 to A31 added |
| 16 / A12 | No-harm remains a reported diagnostic rather than an enforced removal, now unconditionally: the one case where enforcement changed the answer was a patient whose XT-NA the screen had removed, and no such patient exists |
| 17 / A22 | Closed with 16. No patient's reference arm is unassignable, so the referral rule has no case to qualify |
| 18 | Treatment D applied to the XT-NA arm alone: XT-NA carries one schedule per patient, fixed by clinical eligibility. No threshold and no penalty anywhere; A and B withdrawn, C stays excluded. The proton arms carry both schedules with no threshold, since hypofractionation is beneficial for protons through the capacity it frees irrespective of ΔNTCP. Registered as A32 |
| 7b | Reframed, not closed. The criterion is the plan acceptance protocol used at treatment planning, which supersedes the bare V95% below 95 per cent. Which metrics instantiate it is now a question for the clinical partners and the RTTs, moved out of this table |
| 27 | Opened and closed in the same round. A28: a rescue is unpriced on both budgets, which is the reference study's own accounting. A29: a rescue plan carries forward and is re-screened on later blocks. Both confirmed, so A21 is structural without qualification and nothing in the version 7 design rests on a candidate assumption |

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
| 7b | **Which metrics instantiate the coverage screen.** Two directions, not equivalent, and both to be requested from the RTTs. *Target metrics*, V95% and D5 on the target, extend the screen along the axis it already measures and change nothing structural. *OAR metrics*, Dmean and Dmax on the organs driving the endpoints, would let the screen fire on normal-tissue grounds, so rescue would trigger for OAR reasons and the upper tail of the non-adapted arms' NTCP would be truncated; the study would then report adaptation benefit conditional on standard-of-care rescue, which is defensible but is a different result. Collect both regardless, since the OAR metrics are useful descriptively; deciding which enter the screen is separate. Gated on 19, since the protocol is site-specific |
| 25 | Which RayStation dose engine generates the proton plans, analytical pencil beam or Monte Carlo, and the reporting conventions for both modalities: RBE weighting, dose-to-water or dose-to-medium, grid resolution and origin. The engine choice bears on the premise of the study, since analytical dose is least reliable in the heterogeneous abdomen and the error is systematic rather than random, so it does not average out over the cohort and it falls on the arm whose degradation under anatomical change the paper measures. Registered in allocator 12, evaluator 10 (E16) and extractor 11 |
| - | Clinical eligibility for hypofractionation, per patient. Required data under A32, since it fixes the schedule of the XT-NA arm. Depends on the protocol for the indication and therefore on 19 |
| - | Whether short-course patients in the cohort have any repeated imaging. Determines whether the hypofractionated schedule has blocks at all, and therefore whether decision 23 arises |

### Split

| ID | Question | Split how |
| --- | --- | --- |
| 10 | Endpoint selection, constrained to models admitting an explicit dose-per-fraction correction. Recorded in allocator 12 and road 4.8 as item 3 of the open problems register | Candidate proposes the model family, Sterpin decides; gated on 19 |
| 19 | Anatomical site: pancreas or adrenal | Partners indicate which cases exist; Sterpin judges whether they are suitable |
| 23 | Block granularity for the hypofractionated schedule | Candidate proposes, Sterpin decides, conditional on the partner answer on repeated imaging |

### Candidate, unblocked

| ID | Question |
| --- | --- |
| 20 | Per-replan cost accounting as a sensitivity bound on A16 and A19 |
| 26 | Whether the replans required by the adapted arms are producible without manual intervention. Its weight rose at version 7. The worst-case coverage variant is now prevented at plan generation rather than detected at evaluation, so the adapted arms are guaranteed acceptable by an iteration loop while the non-adapted arms are recomputations with no iteration. Effort is therefore not constant across arms and enters ΔNTCP as a confounder on the primary endpoint. It is now the only route by which plan quality can differ systematically between arms. What protects the endpoint is a fixed acceptance rule applied identically to every arm and stated in Methods, not the quality of the plans. Also unresolved: who does the planning |

**Closed by the doctoral candidate, August 2026.**

| ID | Decision | Reason recorded |
| --- | --- | --- |
| 21 | First block evaluated on the planning anatomy, for every arm | The convention of the reference study, followed for comparability. The distortion favours the reduced-margin arms and scales as one over the number of blocks; its direction is known, its size is not measured |
| 22 | The reduced-margin non-adapted diagnostic is not computed | A reduced-margin plan delivered without adaptation is clinically incoherent. Unchanged at version 7 and reinforced: the coherent missing cell is clinical margin with systematic adaptation, and supervision declined to add it, so the margin and adaptation components are still separated by reference to the published lung cohort |
| - | Displaced patients are retained in the denominator of the cohort mean | Comparability with the reference study, which divides by 14 throughout. To be stated in methods, since it makes the mean an intention-to-treat quantity over the referred population rather than over the treated one |

Resolved and recorded for reference: 14 (heuristic ranking convention), 15 (ILP
as reference solver).

## 5. The blocking chain

**Decision 19 (site) is now the only heavy blocker.** It gates decision 10
(endpoint selection), which gates the entire fractionation axis; it gates the
protocol criteria that instantiate 7b; and it gates the hypofractionation
eligibility flag that A32 requires as data. Two facts tighten the chain:
fractionation-correctability of the endpoint models at a candidate site is a
criterion for choosing the site, not only a consequence of having chosen it; and
at pancreas the two protocol schedules differ in elective target coverage, so
comparing them confounds fraction size with target volume.

Decision 24 was second in weight and is closed. The count that made the no-harm
property empirical is zero by construction, so no manuscript claim waits on it.
What replaces it as the number to produce is rescue frequency, which is a study
output rather than a precondition for writing.

## 6. Code

Package `tps5d` in the RAPTORproject repository, `src/tps5d/` with `core`,
`allocator`, `evaluator`, `generator`. Conda environment `OpenTPS`, Windows,
PowerShell. Implemented: `schema.py`, `solve.py`, `dominance.py`, `policies.py`,
`report.py`, `figures.py`, `synth.py`, `evaluator/ntcp.py`,
`evaluator/registry.py`. Exact solver `scipy.optimize.milp` (HiGHS), `solve_dp`
retained as an independent cross-check at C_XT = 0. `scripts/step_ratio.py` is
deleted, as recorded previously.

**Current state, tagged `design-v6.3`.** Behaviourally the code is still the
version 6 design throughout: dose composition and the coverage screen are
untouched, deliberately, pending the first real patient imaging. What
changed in this tag is structural, in `core/schema.py` and
`generator/synth.py`, readying the codebase for the evaluator work without
pre-empting it:

- `generator` emits **seven** options per patient with the photon adapted arm
  present (five without it), not eight. XT-NA's schedule is drawn from a
  synthetic `hypo_frac` split standing in for the per-patient
  clinical-eligibility flag of A32.
- Every strategy carries an optional `block_plans: list[BlockPlan]` (new
  record: `block_index`, `role` ∈ {planned, rescue}, `source_image`),
  populated by the generator for non-adapted arms via a renewal process
  (`_rescue_sequence`: each block fails independently at `p0 · decay**k`,
  `k` the rescues already incurred by that arm; `p0 = 0.05`, `decay = 0.5`,
  both arbitrary placeholders per open decision 27, not values). Adapted
  arms carry the trivial all-planned sequence, enforced by
  `Strategy.__post_init__` rather than assumed. `block_plans` is empty by
  default, so every pre-version-7 call site is unaffected.
- `report.rescue_counts(cohort)` summarises the sequence: rescue count by
  arm, by block, and `n_modelled` (strategies actually carrying
  `block_plans`, so a cohort built without them, as several fixtures are,
  reports zero rather than a false all-clear).
- `solve.py` and `dominance.py` needed no change and received none; the
  proton-chain argument for why the retired duplicate XT-NA never affected
  any hull or LP result was checked directly against `dominance.pareto`'s
  tie-break, not left as a claim.
- `test_admissibility.py` needed **no** change: its content is the
  admissibility/dominance mechanism, orthogonal to rescue. Two new files
  instead, `tests/test_schema.py` (`BlockPlan` and `block_plans` validation)
  and `tests/test_generator.py` (the rescue renewal process, including a
  Monte Carlo check that `decay` actually reduces a second rescue's
  probability; the seven/five-option count; the XT-NA single-schedule
  guarantee).
- Along the way, three existing tests turned out to assert an invariant that
  is false in general under A32 —
  `test_p0_uses_no_adaptation_and_the_standard_schedule`,
  `test_p1_keeps_the_standard_schedule` (`test_policies.py`), and
  `test_arm_label_carries_the_scheme_when_it_is_not_standard`
  (`test_report.py`) — and passed only because the default seed happened to
  draw zero hypo-eligible patients (≈94 % chance of not being that lucky at
  `hypo_frac = 0.3`, n = 8). All three now force `hypo_frac` to a
  deterministic endpoint rather than relying on the seed; no allocator logic
  changed, only what the assertions claim.

What the evaluator itself still needs, once real imaging is available, is
recorded as a next action in Section 7 rather than here, since it is blocked
on the same data dependency as the science items there.

**Test count.** 260 (236 plus the 24 new), all passing: confirmed in the
working sandbox on SciPy 1.17.1, by Tommaso in the project's own conda
environment, and independently at each of the four commits below in
sequence (236 → 245 → 245 → 260 → 260), by applying the four patches to a
clean checkout of `design-v6.2` and running the suite after each.

**Committed, four commits, `design-v6.3` tagged at the fourth.**

1. `core/schema.py` + `tests/test_schema.py` — 245 passing
2. `generator/synth.py` — 245, unchanged, `test_generator.py` not added yet
3. `allocator/report.py` + `tests/test_generator.py` — 260 passing
4. `tests/test_policies.py` + `tests/test_report.py`, the three-assertion fix
   — 260, unchanged in count

Each of the four is independently green; the qualification given at proposal
time was overstated; the only real limit is granularity, not greenness:
`test_generator.py` does not exist until commit 3, so bisecting a failure to
commit 2 alone has no dedicated test file to run against it yet, since that
file exercises both the generator and `report.rescue_counts` together.

**Fixed in the previous round, `allocator/report.py`.** `dominance_counts`
anchored the proton axis at the origin only by accident and never anchored the
photon axis at all, so a rung genuinely LP-dominated by a mixture of the free
base and the other rung was silently kept. Confirmed with an adversarial two-rung
construction before and after the fix. `solve_exact`/`solve_lp` were never
exposed to this; the effect was confined to the diagnostic count.

**Dose provenance.** All dose in paper 1 is computed in RayStation and imported,
photon and proton alike. OpenTPS performs accumulation, evaluation and allocation
and calculates no dose. The photon CCC implementation in OpenTPS is therefore not
on the critical path of this study, and the contribution to D4.1 is entirely
evaluation-side. Recorded as E16 in the evaluator and in extractor Section 11.

## 7. Next actions

**Closed this round, September 2026, by supervision.** Decisions 24, 16, 17 and
18; 7b reframed and reassigned. A10 corrected: photon dose recomputation on the
repeat images is **inherited** from the reference study, not an amendment to it,
and the "fifth difference" of allocator Section 2 is withdrawn. The correction
came from the candidate's check with an author of the reference study; the
previous reading, that the reference study took planned photon dose as delivered,
was wrong and had been carried since version 1. The rescue there covers the
photon arm as well as the proton arms, so A10 is inherited in full and needs no
qualifying clause. A28, the unpriced rescue, is also the reference study's own
accounting rather than a convention adopted here. Continuity is stronger than the
documents claimed, not weaker: the step-ratio derivation of allocator 6.5
recovers the reference study's break-even condition analytically and requires the
arms on both sides to be constructed alike, which they are.

Still without data or supervisory input, all of it blocked on the same thing
in practice, the first real patient imaging, except where noted:

1. **Evaluator: change the coverage screen from a filter to a substitution.**
   The remaining piece of the version 7 design, deferred this round by
   choice rather than found impossible. A non-adapted arm's dose
   composition becomes a piecewise sequence of clinical-margin plans, with
   breakpoints set by the screen and carried forward under A29, and the
   evaluator emits real `block_plans` (Section 6) in place of the
   generator's synthetic draw. `n_no_free_option` stays a regression check
   expected to read zero either way. Blocked on the first exported case,
   since the screen needs real repeat-CT geometry to fire on.
2. Map the sign of the utility of a hypofractionated photon arm against a standard-schedule one, on synthetic DVHs, over the plausible range of α/β and volume parameter. This no longer decides whether decision 18 is empty; it decides how far the numeraire moves for the patients whose XT-NA is hypofractionated. Requires the endpoint models, so it follows decision 19.
3. On the first exported case, measure dose grid dimensions and masked ROI volumes before fixing the storage strategy.
4. Run decision 26 as a feasibility probe on one patient rather than as a question: script one adapted-arm replan per modality from a fixed objective template and record whether the result is acceptable without intervention. The answer sizes the whole cohort phase and is needed before the plan-generation effort is committed.
5. Draft the metric request to the RTTs, with the target and OAR directions stated separately, to go out with the decision 3 and 12 questions.

**Earlier rounds, retained, and the two thresholds distinguished.** Section
6.5's base closed form, Δτ\* = τ_0 · (a / m), recovers the reference study's
own break-even condition analytically rather than reading it off a scenario
ladder. At the reference-study magnitude for 2-year mortality at the 2 mm
setting (m = 6.9 %, m + a = 10.7 %, so a = 3.8 pp, τ_0 = 34.2 min) it gives
**18.8 min**, against the 19 min the paper itself reports as the point past
which the gain against NA-Clinic stops being significant, checked directly
against Borderías-Villarroel et al. rather than assumed. Dysphagia and
pneumonitis are the same table's other two checks: 42.1 min against a
published curve that never crosses within their 25.7 min sweep, and 20.9 min
against a published crossing near 13.7 min, a genuine discrepancy the
document reads as informative rather than as a failure of the closed form.

Decision 20 asks a different question and is not the same number. Charging
adaptation once per block rather than once per fraction rescales the same
formula by n_fx / B: at B = 3 for the standard schedule (ten fractions per
block, n_fx = 30) the threshold moves from 18.8 to **188 min**, ten times
larger, because the same physical Δτ then buys a cheaper-looking adaptation
on the entry step's own terms. This is not a second measurement of the same
quantity and not an error; it is what the formula gives under per-replan
rather than per-fraction accounting. Decision 20 stays open because the
cross-schedule comparison it actually turns on needs B for the
hypofractionated schedule too, which decision 23 has not fixed.

The pen\* closed form, pen\* = a · (a_mult − 1), independent of Δτ, is also in
6.5 and verified numerically to six decimal places at five values of a_mult.
All three closed forms are unaffected by version 7: rescue shifts a
patient's utilities by a common constant, which leaves intra-patient
orderings, the step ratio and pen\* untouched and moves only the level of
ΔNTCP.

**Decided, August 2026, now partly superseded.** Hypofractionation is not
modelled as requiring adaptation, and that stands. The second half, that
non-adapted hypofractionated arms are removed by the coverage screen on evidence
rather than by construction, is void at version 7: nothing is removed. The
empirical check it was meant to provide survives in better form as rescue
frequency per schedule, which measures how often a five-fraction course delivered
without systematic adaptation would in fact have needed a replan.

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

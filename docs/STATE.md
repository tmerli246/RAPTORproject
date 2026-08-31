# Project state

**Last updated:** 2026-08-31, at tag `design-v6.1`.

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
| `allocator_design.md` | 6.1 | Optimization problem, algorithm, shadow prices, step-ratio threshold, policy comparison. Assumptions register (11, amended at 11.1) and open decisions (12) |
| `evaluator_design.md` | 5.1 | Dose composition, accumulation ordering, EQD2 conversion, NTCP evaluation, admissibility screens, strategy construction. Assumptions register (10, amended at 10.1) |
| `extractor_design.md` | 4.1 | Ingest, registration, storage, target metrics, plan complexity, ROI naming, provenance |
| `CHANGELOG.md` | - | Version history for all four. Kept in the repository, not in the project knowledge |

The evaluator is one version behind the allocator by convention, not by
oversight: the two registers are amended by the same decision, recorded as
version 6 in one and version 5 in the other.

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
| 18 | How to treat a free hypofractionated photon arm. Four treatments recorded in allocator 12.1, none adopted |
| 24 | Handling of the coverage screen: whether single-block failure should remove an arm for the whole course, and what the fallback is when XT-NA itself is removed |
| - | Confirmation that paper 1 answers which patient receives which workflow, and that the right-time framing of the work package belongs to the second publication |
| - | Fourth-year funding: source, obligations, and whether the MSCA allowance continues. To be recorded in the Career Development Plan at M13 |

### Clinical partners

| ID | Question |
| --- | --- |
| 3 | PARTICLE operating model: hours per day, rooms, beam sharing, clinical slot length. Which Δτ components are extractable from RayStation plan data |
| 12 / A15 | Plausible range for Δτ_XT, and whether photon plan verification is measurement-based or computational within a session |
| 13 | Reference value C_XT^ref |
| - | Whether short-course patients in the cohort have any repeated imaging. Determines whether the hypofractionated schedule has blocks at all, and therefore whether decision 23 arises |

### Split

| ID | Question | Split how |
| --- | --- | --- |
| 19 | Anatomical site: pancreas or adrenal | Partners indicate which cases exist; Sterpin judges whether they are suitable |
| 23 | Block granularity for the hypofractionated schedule. Blocks equal to fractions gives five replans and 22 plans per patient; coarser blocks restore parity at 16 but model adaptation less often than the photon literature reports | Candidate proposes, Sterpin decides, conditional on the partner answer on repeated imaging |

### Candidate, unblocked

| ID | Question |
| --- | --- |
| 7b | Whether criteria beyond V95% below 95 per cent enter the coverage screen |
| 20 | Per-replan cost accounting as a sensitivity bound on A16 and A19 |
| 21 | First-block evaluation convention: planning anatomy only, or the interval before the first repeat image |
| 22 | Whether to compute the reduced-margin non-adapted diagnostic, which separates the margin benefit from the adaptation benefit |
| - | Cohort mean denominator convention (displaced patients retained, per the reference study) |

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
`report.py`, `synth.py`, `evaluator/ntcp.py`, `evaluator/registry.py`. Exact
solver `scipy.optimize.milp` (HiGHS), `solve_dp` retained as an independent
cross-check at C_XT = 0.

**The code is at version 6, tagged `design-v6.1`.** 164 tests passing, on SciPy
1.18.0 and on a second, different build; the floor stays at 1.9, where
`scipy.optimize.milp` was introduced. `dominance.py` and `solve.py` were not
touched: the hull reduction they implement is what makes the greedy LP ordering
valid, not the collapse over adaptation counts that version 6 retires.
`scripts/step_ratio.py` is deleted.

T12, T13 and T14 are **not implemented**. The suite passing means nothing
regressed, not that the migration is verified: no test yet asserts that a course
cannot vary modality or schedule, that the per-course occupancy reproduces the
version 5 per-block one, or that the count of patients with PT-NA below the hull
matches the closed form of allocator 6.5.

## 7. Next actions

Migration done. Next, the assertions the migration did not add.

1. Add T12: no selected strategy varies modality or fractionation scheme. The record now makes this unrepresentable, so the test asserts the construction rather than the outcome.
2. Add T13: the per-course occupancy reproduces the version 5 per-block occupancy on a fully adapted arm, and the reference-study ladder through T1 is unchanged.
3. Add T14: the count of patients for whom PT-NA falls below the hull equals the count for whom Δτ_PT is below the closed form of allocator 6.5. This is the load-bearing test of the structural result: at the reference study's magnitudes Δτ\* is 18.8 min for two-year mortality, and the published adaptation increment of 9.3 min sits below it, so PT-NA is off the hull there.
4. Re-measure P2a against P2b. The 1800-instance synthetic magnitudes were measured on multi-rung ladders and do not describe the version 6 option set.
5. Run open decision 20 as a computation, not as a check: per-replan rather than per-fraction accounting moves the standard adaptation cost from 300 course-minutes to 10, which reorders the hull. Whether PT-NA standard is selectable at all depends on it.

Then, still without data or supervisory input:

6. Map the sign of the utility of the free hypofractionated photon arm over the plausible range of α/β and volume parameter, on synthetic DVHs. If it is non-positive for every patient, decision 18 is empty. Requires the endpoint models, so it follows decision 19.
7. On the first exported case, measure dose grid dimensions and masked ROI volumes before fixing the storage strategy.

**Result recorded, no action outstanding.** The degeneracy check on `pen` in
`two_scheme_check.py` is done. The standard adapted arm is the highest-cost point
of a patient's proton frontier, so it lies on the hull exactly when it carries
the highest utility, which gives the closed form pen\* = a · (a_mult − 1),
independent of Δτ. At a_mult = 1 the two adapted arms are tied at pen = 0 and the
cheaper one survives only by the tie-break, so the threshold there is zero and
carries no information. This refines allocator 6.5, which currently states that
competition between schemes is resolved by the allocator and not by any closed
form: one component of that competition does have one. To be written into the
document with the next version bump.

Held for later, not scheduled: whether hypofractionation should be modelled as
requiring adaptation at the chosen site. The recommendation is to let the
coverage screen remove non-adapted hypofractionated arms on evidence rather than
to remove them by construction, since removing them by construction would also
dissolve A27 and open decision 18 as a side effect. A generator flag makes it a
cheap sensitivity.

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

Secondment 1 scope is unsettled: four options are under discussion in
`dc18_timeline.docx` §8.2. Option 1, photon plan evaluation, matches Annex 1 and
serves both photon arms of this study directly, but contributes verification
rather than new content if D4.1 is frozen before departure.

The obligations after M42, including the M48 thesis draft, are conditional on the
fourth year being in place.

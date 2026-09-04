# Version history

Consolidated version history for the four design documents, separated from the
specification so that superseded material does not compete with current
specification during retrieval and reading.

**Reading rule.** Assumption and open-decision identifiers cited in entries for
superseded versions refer to the numbering *of that version*. Where an identifier
has since been reused for different content, this is marked inline. The live
registers are authoritative: allocator Sections 11 and 11.1 (assumptions) and 12
(open decisions), evaluator Sections 10 and 10.1, road Section 4.8 (open problems).

**Section numbering.** Removing the history sections leaves numbering holes at the
end of each specification document. Existing numbers were preserved rather than
compacted, so cross-document pointers of the form "allocator 10.5" remain valid.

---

# Consistency pass, all four documents

Road 6.1, allocator 6.1, evaluator 5.1, extractor 4.1. No design decision is taken
or revised here. The pass removes residual version 5 language left in place when
the prescription-time decision was adopted, and separates four kinds of content
that were previously interleaved in the same files.

| Change | Where |
| --- | --- |
| Version history moved out of the specification documents into this file | all four |
| Appendix F consolidated into a single copy in the road document, F.1 to F.5 at study level and F.6 to F.8 at module level; the module documents carry a pointer. The version 6 note is removed, its content having been written into the cells it annotated | all four |
| `STATE.md` introduced as the single description of the present: document versions, open decisions by owner, next actions, calendar | new file |
| Evaluator assumptions register amended at Section 10.1, mirroring allocator 11.1: E7 retired, E9 superseded by the new E15, E11 superseded, E12 amended | evaluator 10.1 |
| Coverage screen restated to act on arms rather than on families indexed by an adaptation vector. Removal is for the whole course and per schedule | allocator 8.2, evaluator 6.1 |
| Open decision 24 added: how coverage failure should be handled, what the fallback is when XT-NA itself is removed, and the count of patients left with no free option under either schedule | allocator 12 |
| The two cost distortions of A16/A19 and A23 stated to run in opposite directions without cancelling, with the inference given an owner in the section rather than in the appendix | allocator 9 |
| Plan-count paragraph rewritten: the strategy count no longer depends on the number of blocks, so the planning cost is linear in B and the number of repeat CTs is a data-availability parameter | road 4.3 |
| `tau_xt` charged on every fraction of an adapted arm rather than on the fractions of adapted blocks | evaluator 3 |
| Block-level storage justified on grounds independent of the strategy count, matching the treatment the extractor received at version 6 | evaluator 1.1 |
| Rationale of resolved decision 15 corrected: the photon axis takes two values per patient per schedule, not B + 1 | allocator 12 |
| Residual references to a varying adaptation count removed | road 5.4, 5.12 |
| Identifier drift repaired in the retained version 2 entry below, where A15 referred to content now held by A14 and since reversed | this file |
| 72 escaped-bold artifacts from the Word round trip removed | all four |

## Code migration to version 6

The `tps5d` package brought to the version 6 design. 164 tests passing, from 145.
No design decision is taken here.

| Change | Where |
| --- | --- |
| `Strategy.n_adapt: int` becomes `adapted: bool`. An adapted arm adapts at every block and a non-adapted arm never adapts, so no count is representable | `core/schema.py` |
| Occupancy required no change: `occ_pt` and `occ_xt` were already the per-course products of the fraction count and the per-fraction time | `core/schema.py` |
| `ladder_cohort` replaced by `arm_cohort`, two arms per modality per scheme, and by `two_scheme_cohort` spanning both schedules. `n_block` and the `shape` argument over adaptation counts are gone | `generator/synth.py` |
| Non-concave benefit profiles are now generated between schemes rather than within a chain, through the `SHAPES` configurations `both_schemes`, `nonconcave` and `hyp_dominant` | `generator/synth.py` |
| `arm_label` emits PT-NA, PT-A, XT-NA, XT-A, with the schedule appended when it is not the standard one. `n_adapt_total` replaced by `n_adapted` and `n_hypo` | `allocator/report.py` |
| P0 and P1 select on the boolean rather than on a count | `allocator/policies.py` |
| `dominance.py` and `solve.py` unchanged. The hull reduction is not the collapse that version 6 retires: it is the reduction that makes the greedy ordering valid for the LP relaxation, and it is required whatever generated the points | — |
| `scripts/step_ratio.py` deleted. It explored the closed form over the block count B and the concavity exponent p, both of which drop out at B = 1 | — |
| `scripts/two_scheme_check.py` reduced to two arms per scheme. Its question changes from which adaptation counts survive the hull to which arms do, which is what open decision 18 needs | — |

**Test void at version 6.** `test_closed_form_matches_the_hull_and_is_monotone`
was parametrized over the concavity exponent p in {1.0, 0.7}. The exponent
entered the threshold only through the factor B^(1-p) and does not exist at
B = 1, so the p = 0.7 case is removed and the test is no longer parametrized.
T6 of the allocator document, the claim about the dominance collapse over
adaptation counts, had no implementation and so required no removal.

**Known behaviour, not a defect.** Under two schedules a patient holds two
options free on both budgets, XT-NA under each schedule (A27). `pareto` keeps
only the better of two options at equal cost, so one of them leaves the proton
chain. The strategy remains in the option set and the exact solver can assign
it; `Cohort.baseline()` is unaffected, so XT-NA on the standard schedule remains
the numeraire either way; and `no_free_option()` interrogates the option set
rather than the chain, so the count behind the no-harm property is correct in
both cases. Open decision 18 governs what should be reported here.

**Document corrections arising from the migration.**

| Correction | Where |
| --- | --- |
| The T6 row was corrupted: a "V" had migrated out of the status column into the claim text, leaving the status reading "oid". Repaired | allocator 5.4 |
| Two reductions are called dominance and only one is retired. The collapse by dominance of the evaluator is void; the hull reduction of Section 5.3 is retained and is required for T2 and T8. Stated explicitly, because the implementation carries a single module named for the word and reading the sentence as retiring both is an error | allocator 5.1 |
| Where a non-concave benefit profile comes from at version 6: both schemes lie on the same proton cost axis, so a patient's frontier holds four proton points and the standard arms compete against the hypofractionated ones on price. This is the second reason the hull reduction is retained | allocator 6.5 |
| A block is now defined. The term carried three documents and open decision 23 turns on its granularity, but the nearest thing to a definition was a hypothetical inside that decision | allocator 4 |
| The plan-unit paragraph justified block-level storage by an exponential growth in the strategy count that no longer exists. Restated on grounds independent of the strategy count, matching the treatment Section 3 received at version 6 | extractor 1 |

Section 6.5 required no numerical addition: the closed form is already evaluated
against the reference study's published magnitudes there, giving 18.8 min for
two-year mortality against the 19 min at which the published gain ceases to be
significant.

Two further residuals were found while checking the road document against the
migrated threshold test.

| Correction | Where |
| --- | --- |
| The structural-result paragraph still carried the version 5 closed form Δτ* = τ_0 · (a/m) · B^(1−p) and described the threshold as governing whether the per-block adaptation decision has allocative value. Restated at B = 1: the threshold governs whether the non-adapted proton arm is a live rung | road 3 |
| Candidate output 3 described the regime boundary as where per-block allocation carries value. Restated as where the non-adapted proton arm carries value | road 5.12 |

A further nine split bold runs from the Word conversion were repaired, of the
form `**text and** more**` where a single emphasised run had been broken at a
word boundary. These were not caught by the earlier pass, which looked only for
escaped asterisks, and four of them fell in table headers.


---

# Road to Paper 1

## Changes from version 5

One supervisory decision restructures the study, and the rest of this section follows from it.

**Decision.** The treatment choice is made at prescription, on the planning CT. Each patient carries four workflows per fractionation schedule, XT-NA, XT-A, PT-NA and PT-A, and eight over the two schedules. An adapted arm adapts at every block and carries a reduced-margin plan from the first fraction; a non-adapted arm carries the clinical-margin pCT plan for the whole course, recomputed on each repeat image. There is no per-block adaptation decision and no mid-course change of anything.

| Section    | Change                                                                                                                                   | Consequence                                                                                                                                                                       |
|------------|------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 4.1        | Margin becomes a property of the arm rather than of the block. Adapted means adapted at every block. Arms and strategies almost coincide | The option set stops growing with the number of repeat images. The number of blocks governs the extractor, the evaluator and the plan budget, and no longer governs the allocator |
| 4.1        | First-block distortion stated                                                                                                            | The reduced-margin arms bank organ sparing over the first block at zero modelled coverage risk, which favours the larger of the two benefit terms                                 |
| 4.3        | Hypofractionated plan budget flagged: up to twenty-two plans per patient if the hypofractionated block is a fraction                     | Determines whether the fractionation axis is affordable in planning hours                                                                                                         |
| 4.4        | The pragmatic simplification becomes a design property. Item 2 of the open problems register closes                                      | The limitation is written as a property of the question rather than as a cost-driven concession                                                                                   |
| 4.5        | Oracle framing extended from fractionation to the whole strategy tuple, and stated explicitly as a ceiling                               | Makes the prospective version the object of the second publication rather than an afterthought                                                                                    |
| 4.9        | New. Two candidate sites with what each implies, including the target-volume confounder and the escalation dilemma                       | Recorded as options, not decided                                                                                                                                                  |
| 5.2        | Occupancy written per course                                                                                                             | The reference study’s accounting is recovered exactly                                                                                                                             |
| Appendix F | Amended for the arm-level margin and the course-level decision                                                                           | The fractionation axis is unaffected in substance; only the strategy count changes                                                                                                |

**What did not change.** The central hypothesis, the two-resource formulation, the endpoint policy, the admissibility screens, the matched uncertainty budget, the plan budget for the standard schedule, and the treatment of schedule equivalence are untouched.

**What was lost.** Three reportable quantities disappear with the per-block decision: whether adaptation early in the course carries more benefit than adaptation late, whether a partially adapted course is ever the price-efficient choice, and the within-study separation of the adaptation benefit from the margin-reduction benefit. The third is recoverable at the cost of dose recomputations and no new plans, and is recorded as open decision 22 in the allocator document.

**What was gained.** The closed-form threshold of the allocator document, Section 6.5, is now the same condition as the reference study’s own break-even between adapting everyone and adapting no one. That gives the manuscript an analytical benchmark against which the observed allocation can be decomposed by mechanism, which is a stronger deliverable than a threshold reported on its own.

## Changes from version 4

**Amendment within version 5.** Section 5.10 attributed the protection of the individual patient to the no-harm screen. The protection in fact comes from XT-NA being free and universal, which makes removal redundant wherever that holds and leaves it active only where the coverage screen has already removed XT-NA, which is where it can strand a patient who has a deliverable plan. The screen is now a reported diagnostic, by decision of the doctoral candidate pending supervisory confirmation. Section 5.10 states what protects the individual and what is reported to demonstrate it, and Section 5.12 gains the option-set diagnostics as entry 7.

**What this obliges the manuscript to do.** Under the previous design the methods could state that harmful strategies were excluded, and the reader would accept it. That sentence is no longer available. The methods must instead state that the reference arm is free and universal, that it therefore dominates every strategy of negative benefit, and that no optimal allocation contains one. The claim is stronger, since it is proved rather than stipulated, but it costs two sentences of setup and it must be written before the results, not defended afterwards. The reported count of patients without a free assignable arm is what makes it checkable.

**Changes from version 4.**

One design decision restructures the capacity model. It was taken by the doctoral candidate rather than at supervision, and it revises the version 4 supervisory decision that photon capacity is unconstrained, so it is recorded with its justification attached and flagged for confirmation.

**Decision.** Photon delivery remains unconstrained. Photon adaptation is rationed by its own budget. XT-NA consumes nothing and remains the locked reference; XT-A consumes photon adaptation time; PT-NA and PT-A consume proton machine time, the latter more.

**Justification, in the order the manuscript should give it.** First, standard of care: ΔNTCP measures gain against what a patient would otherwise receive, and under the Dutch protocol framing every patient is entitled to non-adapted photon treatment, so that arm is free and universal. Second, continuity: keeping XT-NA as the reference leaves the zero point of every ΔNTCP value unchanged and preserves the comparison with the reference study’s decomposition. Third, adaptation is the scarce quantity, and pricing it on both modalities is what makes the two sides commensurable.

| Section    | Change                                                                                                | Consequence                                                          |
|------------|-------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| 1          | Two budgets stated; the structural result restated with Δτ\* depending on the photon budget           | The threshold is a curve, not a number, even within one scheme       |
| 2          | Scope table: the second resource in scope, photon delivery capacity explicitly out                    |                                                                      |
| 3.2        | Photon adaptation row: improves cohort composition by releasing proton slots                          | Previously recorded as neutral for the proton machine                |
| 4.1        | XT-A adapted per block and rationed                                                                   | The photon arm generates several strategies, as the proton arm does  |
| 4.2        | The PT-A against XT-A comparison identified as a per-patient counterfactual                           | XT-A is not delivered to every patient                               |
| 5.2        | Occupancy written per resource; photon charged the increment only                                     | No photon baseline session length enters the design                  |
| 5.3        | Two constraints; two-chain option set; feasibility and its scope limitation stated                    |                                                                      |
| 5.4        | Two multipliers; λ_XT reported as a curve; ranking statistic for the heuristics flagged as unresolved |                                                                      |
| 5.7        | Third level added to the adaptation-time output: the budget sweep                                     | One computation yields λ_XT and the threshold curve                  |
| 5.11       | Capacity relief restated as an exchange rate                                                          | The version 4 upper bound becomes the limit of the sweep             |
| Appendix F | Consolidated summary of the fractionation dimension                                                   | Requested so that the fractionation design can be revised as a block |

**What did not change.** The central hypothesis, the arm set, the plan budget, the uncertainty budget, the endpoint policy, the admissibility screens and the fractionation treatment are untouched. The plan budget in particular is unaffected, since the three photon plans per patient per schedule already generated for XT-A support a per-block photon adaptation vector without additional planning.

## Changes from version 3 (retained for reference)

Five supervisory decisions are incorporated.

| Decision                                                       | Sections            | Consequence                                                                                                                                                                                                                                                                                                                   |
|----------------------------------------------------------------|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A single adaptive margin level, reduced, on both modalities    | 4.1, 4.2, 4.3, 5.10 | Robustness is determined by the adaptation vector and is no longer a design factor. Plan budget falls from 14 to 8 per patient per schedule, 28 to 16 over both, which buys cohort size. Lost: the within-study decomposition of adaptation benefit from margin benefit, and the conservative fallback under coverage failure |
| Photon capacity unconstrained                                  | 1, 5.11             | XT-A is available to every patient at no proton cost, which raises the step-ratio threshold and makes the photon capacity relief an upper bound rather than an estimate                                                                                                                                                       |
| Sanctioned schedules confirmed available; clinical equivalence | 3.6                 | The route chosen in version 2 is confirmed rather than conditional. Target EQD2 reported for completeness, not to assert equivalence                                                                                                                                                                                          |
| Union probability, no severity weighting                       | 5.5                 | Stated explicitly rather than left as an open item                                                                                                                                                                                                                                                                            |
| Coverage criterion V95% below 95 per cent                      | 5.10                | The screen takes a list of criteria of which all must pass, so later additions are configuration                                                                                                                                                                                                                              |

Two further changes follow from discussion rather than decision.

| Section | Change                                                                                                                                                                | Reason                                                                                                                                                 |
|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1       | The structural result restated as conditional on a fractionation scheme, with the cross-scheme interaction named as the allocator’s problem rather than the formula’s | The derivation compares three rungs at one fraction count; with two schemes the option set is a two-parameter family and no scalar summarises its hull |
| 5.2     | Occupancy written per block rather than per course                                                                                                                    | Under per-block adaptation a patient pays the extra time only on the fractions of adapted blocks, which the uniform per-course form cannot express     |

## Changes from version 2 (retained for reference)

| Section   | Change                                                                                                                                                                                             | Reason                                                                                                                                                                                                                 |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1, 2, 5.7 | Step-ratio threshold added as a structural deliverable; Δτ stated as the independent variable                                                                                                      | No measured Δτ exists for abdominal OAPT; the threshold Δτ\* = τ_0 · (a/m) · B^(1−p) is the reportable object, mirroring the reference study’s own structure one level up                                              |
| 4.1       | Arm set made symmetric: XT-A at two margin levels; margin stated as a per-block property tied to the adaptation vector; retention of both margin levels argued, with the pending decision recorded | Margin reduction presupposes planning on the block’s repeat image; the dominance argument for dropping the margin-1 arms rests on an unverified occupancy assumption, and they are the fallback under coverage failure |
| 4.2       | Photon-payoff caveat added: the photon equivalent of margin reduction may carry little dosimetric benefit even under adaptation                                                                    | The matched budget equates uncertainty accounting, not dosimetric payoff; asserting symmetry of payoff would overclaim                                                                                                 |
| 4.3       | Plan budget revised to 14 per patient per schedule, 28 over both; budget confirmation flagged as blocking the case matrix; drop-margin-1 lever added                                               | Follows from the symmetric arm set                                                                                                                                                                                     |
| 5.1       | Allocator status updated: implemented and tested, reference study reproduced                                                                                                                       | Statement of fact replacing intention                                                                                                                                                                                  |
| 5.4, 5.6  | P2b redefined; measured synthetic magnitudes added; claim tempered to near-optimality of the naive rule in most regimes                                                                            | The corrected heuristic’s advantage over density ranking is real but small; the manuscript should not promise a large effect                                                                                           |
| 5.8       | Second role of borderline enrichment stated: it is the population in which mixed ladders coexist                                                                                                   | Connects the cohort design to the threshold mechanism                                                                                                                                                                  |
| 5.10      | Fallback role of the clinical-margin adaptive arm under coverage failure                                                                                                                           | Follows from retaining both margin levels                                                                                                                                                                              |


---

# Capacity and Allocation Module (allocator)

## Changes from version 6.3

Allocator 6.4. Closes the last items still pending a version bump since 6.2:
transcribes decisions already recorded in `STATE.md` into the document's own
registers, corrects one that had drifted, and registers two decisions that
existed only in `STATE.md`. No new decision is taken.

| Change | Where |
| --- | --- |
| Decision 21 resolved in the text: first block evaluated on the planning anatomy, for every arm, the convention of the reference study. Previously still phrased as an open question, contradicting `STATE.md`'s record | allocator 12 |
| Decision 22 resolved in the text: the reduced-margin non-adapted diagnostic is not computed, for clinical incoherence. Same correction as 21 | allocator 12 |
| The cohort-mean denominator resolved in the text: displaced patients retained, intention-to-treat over the referred population. Previously an unnumbered "additional item" still phrased as open | allocator 12 |
| 12.1 renamed and corrected. Treatment C, a third budget row for photon stereotactic delivery, marked excluded with its reason, kept in the table for the record rather than deleted, rather than presented as one of four live options. A new paragraph states that treatments A and D are not mutually exclusive. Decision 18's own row in 12 updated to match | allocator 12, 12.1 |
| Decisions 25 and 26 registered, previously tracked only in `STATE.md`. 25: which RayStation dose engine and which cross-modality reporting conventions, open, blocked on the clinical partners. 26: whether adapted-arm replanning is scriptable without manual intervention, open, a candidate feasibility probe | allocator 12 |
| Appendix A deleted: the memo on alternative units for the photon adaptation budget, no longer needed | — |

**What did not change.** The formulation, the algorithm, every test claim, every other assumption and open decision.

## Changes from version 6.2

Allocator 6.3. One addition, closing the last item that 6.2 had left pending:
the pen\* closed form, its derivation already recorded in `STATE.md`, is
written into 6.5. Verifying it against `scripts/two_scheme_check.py` surfaced
a stale constant there, corrected in the same pass.

| Change | Where |
| --- | --- |
| Closed form added: PT-A standard, the highest-cost point of a patient's pooled proton frontier at every reachable setting, survives the hull exactly when it also carries the highest utility of the whole set, which reduces to pen\* = a · (a_mult − 1). Independent of Δτ and of every occupancy parameter, since the comparison is between utilities alone. Illustrated at the reference-study magnitude a = 3.8 points already used in this section. Scoped explicitly to this one point of the pooled frontier; the other three remain resolved by the allocator directly | allocator 6.5 |
| Cross-link added from the existing "non-concave profile" paragraph to the new result, since that paragraph already named the mechanism in words | allocator 6.5 |

**Verification.** Checked two ways against `scripts/two_scheme_check.py`:
against its own printed table (pen\* = 1.14, 2.28, 3.80 at a_mult = 1.3, 1.6,
2.0, matching its bisection search to the two decimal places it prints) and
against a direct bisection call to its own `ladder()`/`survivors()` functions
at five a_mult values, matching to six decimal places throughout, including
the a_mult = 1 tie-break boundary the script's own comments already describe.
Independently, 20 000 randomly parametrised patients checked against
`dominance.hull` directly, zero mismatches, and 200 000 more checked for
whether the script's own `startswith('std')` survivor test could ever
disagree with a precise `== 'stdA'` one: zero disagreements while a > 0, the
only regime the model intends, since a patient-level argument shows the two
are equivalent there and not merely coincident. `startswith('std')` is left
as is; the equivalence makes the tighter check a style preference, not a
correction.

### Code

Checking pen\* against `scripts/two_scheme_check.py` surfaced a stale
constant: N_STD = 28 for the standard schedule, labelled as following the
reference study, against n_fx = 30 used for the same schedule in Section 9
and `test_threshold.py` (three blocks of ten fractions).

| Change | Where |
| --- | --- |
| N_STD corrected from 28 to 30. Changes the script's course-cost and surviving-configuration tables (958 to 1026 minutes for a non-adapted standard course); does not change its pen\* table, checked at both values before settling on the correction, which is the independence from n_fx that 6.5 now states algebraically | `scripts/two_scheme_check.py` |

**What did not change.** Every other section, assumption and open decision;
no other code file.

## Changes from version 6.1

Allocator 6.2. No design decision is taken here: this is verification of the
version 6 claims register (T14, T15) and correction of three claims found
inconsistent with the option set structure version 6 itself introduced, found
while carrying that verification out.

| Change | Where |
| --- | --- |
| T12 retired void. It asserted an outcome the record already makes unrepresentable by construction, so no test could have failed it | allocator 5.4 |
| T13 absorbed into T1. The reference-study ladder is its only checkable half; the per-block occupancy comparison had no surviving version 5 implementation to check against | allocator 5.4 |
| T14 implemented and passing, scoped to a single fractionation scheme, matching the scope the closed form itself claims: allocator 6.5 and road 1 both state the threshold as a per-scheme statement | allocator 5.4, `test_threshold.py` |
| T15 added: the two-resource swap check, previously labelled T10 only inside `test_two_resource.py`'s own docstring, where it collided with this document's own T10, the no-harm claim | allocator 5.4, `test_two_resource.py` |
| Cross-reference corrected: the hull reduction is defined in Section 5.2, not 5.3 as written | allocator 5.1 |
| LP-dominance claim restated. "The photon chain holds one rung and cannot be LP-dominated" holds only within a single scheme. Pooled across two schemes, both axes carry two rungs above the free base and both can be LP-dominated by the identical geometric argument; `report.dominance_counts` anchors each axis at its own free point before reducing, so the pooled count is correct, but no closed form covers this case | allocator 5.2 |
| P2a/P2b coincidence claim restated. Holds only within a single scheme. Pooled across two, a best-available upgrade can also skip from the photon base past one scheme's PT-NA to the other scheme's PT-A, which the single-scheme argument does not describe. Illustrated on a synthetic two-scheme cohort, 6.6 per cent against 3.4 per cent, not measured on the study cohort | allocator 5.3 |
| Section 10.3 retired. It re-solved with peak occupancy in place of the course average to bound the risk of within-course variation from partial adaptation; A24 already makes that variation unrepresentable, so nothing remains for the bound to catch. A2 updated to match | allocator 10.3, 11 |
| Per-replan closed form added, Δτ\*_replan(w) = (n_fx / B) · τ_0 · a / (m − w), generalising the existing Δτ\*(w) to the accounting convention of open decision 20. Illustrated at the same published magnitudes already used in this section, with B = 3 from the block definition of Section 9: 30 course-minutes for the standard schedule's adaptation cost under this convention, not the 10 course-minutes previously carried only in `STATE.md`, and a threshold of 188 min rather than 18.8. The cross-schedule comparison decision 20 is actually for remains open, pending B for the hypofractionated schedule from decision 23 | allocator 6.5, 12 |

**What did not change.** The formulation of Section 5.1, the MCKP model itself,
the policy definitions of 5.3 beyond the one claim above, the admissibility
machinery of Section 8, and every other assumption and open decision are
untouched.

### Code

Verification found one bug, in the reporting layer rather than in any solver
or heuristic. 236 tests passing, from 164: 133 confirmed this round across
the seven files touched (`test_admissibility`, `test_lp`, `test_policies`,
`test_report`, `test_solve`, `test_threshold`, `test_two_resource`), 72 of
them new (T14); the remaining 31, in `test_ntcp` and `test_registry`, were not
re-run.

| Change | Where |
| --- | --- |
| `dominance_counts` anchored the proton axis at the origin only by accident, through the same filter that selects the chain; the photon axis was never anchored. Two paid photon rungs are therefore always mutually non-dominated by construction of `pareto`/`hull` on two points, regardless of parameters, so a rung genuinely LP-dominated by a mixture of the free base and the other rung was silently kept. Confirmed on an adversarial two-rung construction: `n_lp_dominated` read 0 before the fix, should read and now reads 1 | `allocator/report.py` |
| `test_summary_counts_every_patient_once`'s exclusion list omitted `n_dntcp_neg`, which also starts with `n_`. Passed only because the fixture carried no stranded patient. Confirmed on a constructed stranded-patient fixture: summed to 3 against `n_patients` 2 before the fix, 2 against 2 after | `test_report.py` |
| T14 added: 72 parametrized cases sweeping Δτ_PT, the presence and price of photon coupling, and the photon budget as a fraction of cohort demand (`demand_xt()`), rather than a cohort built to straddle the threshold. Checked against `dominance.hull` on the photon-outside-option-augmented proton frontier directly, not against `chains()`/`solve_greedy`, neither of which ever forms that point: P2a and P2b rank the proton chain against its own free base only (allocator 5.3), never against the photon price. A first version swept the photon budget in raw minutes and passed even with the w-term of the closed form deliberately deleted, because that range rarely produced w > 0 at these magnitudes; the demand-fraction sweep does, and correctly fails 11 of 76 cases when the same term is deleted | `test_threshold.py` |
| T10 relabelled T15 in this file's own docstring and test name, matching its registration in allocator 5.4 | `test_two_resource.py` |
| Header comment added, mapping this file's A-labelled claims to the document's T-numbers: A1-A2 to T10, A3-A6 to T11. A7-A8 have no T-number in the design document | `test_admissibility.py` |

**What did not change.** `dominance.py`, `solve.py`, `schema.py`,
`policies.py`, `synth.py` and `figures.py` are untouched.

## Changes from version 5

One supervisory decision restructures the option set, and everything else in this section follows from it.

**Decision.** The treatment choice is made at prescription, on the planning CT. Each patient carries four workflows per fractionation schedule, XT-NA, XT-A, PT-NA and PT-A, and eight over the two schedules. An adapted arm adapts at every block and carries a reduced-margin plan from the first fraction; a non-adapted arm carries the clinical-margin pCT plan for the whole course. There is no per-block adaptation decision.

| Section | Change                                                                                                                                                                      | Consequence                                                                                                                                                    |
|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 4       | Strategy tuple loses the adaptation schedule and the robustness setting. Margin becomes a property of the arm. First-block distortion stated                                | The option set is fixed at four per scheme regardless of the number of blocks. The number of repeat images stops being a parameter of the allocation           |
| 5.1     | Occupancy written per course. Option set structure restated as two chains of one and two rungs                                                                              | The reference study’s own accounting is recovered exactly rather than as a special case                                                                        |
| 5.2     | LP-dominance reduced to a single question per patient per scheme, the survival of PT-NA. State-space concern retired                                                        | The dominance count becomes directly interpretable as a patient count                                                                                          |
| 5.3     | P2a and P2b shown to separate only on the same single question. Synthetic magnitudes marked superseded                                                                      | The ranking-statistic contribution to the P3 − P0 gap is expected to be small in this configuration and must be re-measured                                    |
| 5.4     | T12, T13 and T14 added                                                                                                                                                      | T12 makes the scalar strategy record a tested property. T14 ties the closed form to a patient count                                                            |
| 6       | Config 0e added and adopted. Config 2 deferred to paper 2 with what is lost stated                                                                                          | The study releases the per-patient granularity and the second degree of freedom, not the timing                                                                |
| 6.5     | Threshold re-derived at B = 1. Block count and concavity exponent drop out. Coincidence with the reference study’s break-even established. Three departure mechanisms named | The closed form becomes a benchmark against which the observed allocation is decomposed by mechanism, which is a stronger deliverable than the threshold alone |
| 9       | Occupancy per course. Asymmetry of the per-fraction convention between the two schedules declared                                                                           | The conservatism of A16 is no longer uniform, and it biases the fractionation axis                                                                             |
| 9.1     | Photon occupancy per course                                                                                                                                                 | No other change on the photon side                                                                                                                             |
| 10.5    | Adaptive fractionation moved out of scope, specification retained                                                                                                           | The pragmatic simplification of the road document becomes a design property. The right-time framing moves to the second publication                            |
| 10.6    | New. Two candidate sites with their consequences                                                                                                                            | Recorded as options, not decided                                                                                                                               |
| 11.1    | New. A13 retired, A14 superseded, A18 superseded, A21 amended. A23 to A27 added                                                                                             | The first-block distortion, the every-block adaptation rule, the arm-level margin, the undecided site and the second free arm all become declared assumptions  |
| 12      | Open decisions 18 to 23 added, and 12.1 records the four treatments of the free hypofractionated arm without choosing between them                                          | None is adopted. The prior question, whether the free arm can have positive utility at all, is scheduled first                                                 |

**What did not change.** The two-resource formulation, the two shadow prices, the reporting of λ_XT as a curve over a normalised C_XT axis, the coverage and no-harm treatment of Section 8, the utility currency, the separation of the reference arm from the default arm, and the time-model decomposition of Section 9 are untouched.

**What was lost and should be stated as such in the manuscript.** The within-study decomposition of the adaptation benefit from the margin-reduction benefit, unless open decision 22 is resolved in favour of computing it. Whether adaptation early in the course carries more benefit than adaptation late. Whether a partially adapted course is ever the price-efficient choice. All three are properties of a per-block option set and none of them survives the decision.

## Changes from version 4

**Amendments within version 5.** One correction, one addition, and two decisions closing the items the correction opened. The two decisions were taken by the doctoral candidate rather than at supervision, and item 16 revises a convention that has stood since version 1 of the evaluator design, so both are flagged for confirmation and recorded with their justification attached, on the same footing as the version 4 decision on photon capacity.

The correction is to Section 5.1. Version 5 stated that XT-NA is admissible for every patient, so the allocation is always feasible. That contradicts Section 8.2 and A10 of the same document, which require the coverage screen to apply symmetrically to the photon arms and therefore permit XT-NA to be removed for an individual patient. The evaluator design, Section 6.3, had already separated the reference role from the assignable role for exactly this case; the allocator document and the implementation had not followed. Feasibility is now stated conditionally and the condition is reported per cohort.

The addition is Section 8.6, which states the two roles, what follows when they separate, and the three counts now emitted with every allocation. Section 5.1 additionally states why the objective carries no constraint on the sign of the utility, which was implicit in the implementation and nowhere written down.

The first decision converts the no-harm screen from an enforced removal into a reported diagnostic, closing open decision 16. Section 8.3 is rewritten accordingly, and Section 8 now states why the two admissibility conditions are treated asymmetrically. The second decision retains the published referral rule unmodified for patients whose reference arm is not deliverable, closing open decision 17 and fixing A22.

| Section | Amendment                                                                                                                                                                                                   |
|---------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 5.1     | Scope limitation corrected; paragraph added on the absence of a sign constraint and on what the dominance argument does and does not guarantee                                                              |
| 5.4     | T10 and T11 added, both implemented                                                                                                                                                                         |
| 8       | The asymmetry between the two admissibility conditions stated: coverage enforced, no harm reported                                                                                                          |
| 8.3     | Rewritten. No harm becomes a reported diagnostic; the argument for why removal is redundant where it is safe and wrong where it is not; the reported count becomes informative rather than identically zero |
| 8.4     | Coverage is now the only route to infeasibility, which the previous version asserted without it being true                                                                                                  |
| 8.6     | New. Reference arm and default arm, with the reported counts                                                                                                                                                |
| 11      | A21 and A22 added                                                                                                                                                                                           |
| 12      | Open decisions 16 and 17 added, then closed by the doctoral candidate pending supervisory confirmation, retained with their reasoning                                                                       |

**Changes from version 4.** One design decision restructures the capacity model. It was taken by the doctoral candidate rather than at supervision, and it revises a version 4 supervisory decision, so it is recorded with its justification attached.

**Decision.** Photon delivery remains unconstrained. Photon adaptation is rationed by a budget C_XT. The four arms consume as follows: XT-NA nothing, XT-A a share of C_XT, PT-NA a share of proton capacity, PT-A a larger share of proton capacity.

**Justification, in the order the manuscript should give it.**

- *Standard of care.* ΔNTCP measures gain relative to what a patient would otherwise receive. Under the Dutch protocol framing every patient is entitled to non-adapted photon treatment, so XT-NA is the arm that costs nothing and is available to all. This is the primary argument and should lead.

- *Continuity of the decomposition.* XT-NA remains the reference arm, so the zero point of every ΔNTCP value is unchanged and the comparison with the reference study’s published decomposition remains valid. This supports the choice; it does not by itself justify it, since a prior publication’s convention does not bind this one.

- *Adaptation is the scarce quantity.* Modelling adaptation time as the traded resource on both modalities is what makes the photon and proton sides commensurable, and it is the honest representation of where a department’s constraint actually sits.

The option of removing XT-NA and making XT-A the reference is excluded, because XT-NA is required as the zero-cost entitlement that keeps the allocation feasible.

| Section    | Change                                                                                                                                             | Consequence                                                                              |
|------------|----------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| 2          | R4 added: the reference study’s photon arm is non-adapted and free                                                                                 | The second resource is the relaxation of R4                                              |
| 4          | Notation split per resource                                                                                                                        | Two occupancies, two budgets, two multipliers                                            |
| 5.1        | Two constraints; per-arm consumption table; two-chain structure; scope limitation of the zero-cost sink stated                                     | The formulation is a two-resource MCKP. Feasibility is guaranteed by XT-NA               |
| 5.2        | Two multipliers; hull reduction scoped chain by chain; pooled greedy identified as invalid under two resources; λ_XT reported as a curve over C_XT | The LP needs a solver or a price search. The hull argument survives, the greedy does not |
| 5.3        | Ranking statistic for P2a and P2b flagged as undefined under two costs                                                                             | Open decision 14                                                                         |
| 5.4        | T7, T8, T9 added                                                                                                                                   | The two limits of the C_XT sweep are regression tests against version 4 behaviour        |
| 6.3        | Third mechanism for the heterogeneous cohort: the bottom rung is patient-dependent                                                                 | Follows from rationed XT-A                                                               |
| 6.5        | Threshold restated as Δτ\*(C_XT), monotone non-decreasing                                                                                          | Same sweep as λ_XT. Structure checked, algebra not re-derived                            |
| 8.5        | Capacity relief restated as an exchange rate governed by λ_XT / λ_PT                                                                               | The version 4 upper bound becomes the limiting case of the sweep                         |
| 9.1        | Photon time model added: increment only, Δτ_XT as a second independent variable                                                                    | No photon baseline session length required anywhere                                      |
| 10.2       | One shadow price per resource                                                                                                                      | λ_PT and λ_XT are independent; each remains reportable in two units                      |
| 11         | A3 rewritten; A17 to A20 added                                                                                                                     |                                                                                          |
| 12         | Open decisions 11 to 15 added                                                                                                                      |                                                                                          |
| Appendix A | Memo on the alternative unit for the photon budget                                                                                                 | Records the option not taken                                                             |
| Appendix F | Consolidated summary of the fractionation dimension                                                                                                | Requested so that the fractionation design can be revised as a block                     |

## Changes from version 3 (retained for reference)

Five open items are closed by supervisory decision. The consequences are listed with them, since several reach further than the decision itself.

| Decision                                                           | Sections          | Consequence                                                                                                                                                                                                                                                                   |
|--------------------------------------------------------------------|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A single adaptive margin level, reduced, on both modalities        | 4, 6.3, 8.2, A14  | Robustness is fully determined by the adaptation vector and contributes no degree of freedom. The conservative fallback under coverage failure disappears, so the empty-option-set path is marginally more reachable. Plan budget falls from 14 to 8 per patient per schedule |
| Photon capacity unconstrained                                      | 5.1, 6.5, 8.5, A3 | Single constraint and single shadow price retained. XT-A becomes the effective bottom rung of every ladder, which lowers the modality step and therefore **raises** the step-ratio threshold. The photon capacity relief is an upper bound and must be reported as such       |
| Sanctioned schedules available; equivalence by clinical consensus  | 10.4, A5          | The fractionation dimension is clinically live. Target EQD2 reported per arm for completeness, not used to assert equivalence                                                                                                                                                 |
| Union probability, no severity weighting                           | 7                 | The per-endpoint weight interface is retained but not exercised                                                                                                                                                                                                               |
| Coverage criterion V95% below 95 per cent, possibly with additions | 8.2               | The screen takes a list of criteria of which all must pass, so a later addition is configuration rather than code                                                                                                                                                             |

Two further changes follow from the discussion rather than from a decision.

| Section | Change                                                                                                                                                                                                      | Reason                                                                                                                                         |
|---------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| 9       | QA of an adapted plan identified as an independent secondary dose calculation, resolving the open item on beam time. The initial plan of record noted as common to both arms and therefore cancelling in Δτ | Measurement-based QA is impossible with the patient on the couch, and reported adaptation times are consistent only with a computational check |
| 9       | Occupancy written per block, with the per-fraction cost against per-block replanning asymmetry stated and its conservative direction named                                                                  | The reference study makes the same choice silently; under a heterogeneous cohort the two accountings visibly separate and a reader will ask    |

## Changes from version 2 (retained for reference)

| Section      | Change                                                                                                                       | Reason                                                                                                                                                                                                                                 |
|--------------|------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2, 3, 6.5, 9 | Δτ recast as the independent variable of the study                                                                           | No clinical abdominal OAPT exists, so no measured value exists; the reference study treats it the same way                                                                                                                             |
| 4            | Robustness bound to the adaptation vector per block (v2 numbering A14; A14 in the live register, superseded by A25 at version 6); both margin levels retained in the option set (v2 numbering A15, since reversed: version 5 drops the clinical-margin adaptive arm, and A15 in the live register is the patient-specific QA assumption)               | Setup-error reduction presupposes planning on the block’s repeat image; the dominance argument for discarding the clinical-margin arm rests on an unverified occupancy assumption, and that arm is the fallback under coverage failure |
| 5.1          | Discretisation stated, 0.1 min, costs rounded up                                                                             | The resolution changes the answer at 1 min and was undocumented                                                                                                                                                                        |
| 5.2          | Hull reduction scoped to the linear relaxation only; collinear removal stated; Pareto and LP dominance counted separately    | The integer greedy had been implemented on the hull-reduced set, which is wrong: an LP-dominated option can appear in the integer optimum                                                                                              |
| 5.3          | P2b redefined: Pareto-reduced sets, best available upgrade over all higher options; measured synthetic magnitudes added      | The rank-by-rank scan on hull-reduced sets underperformed P2a; the corrected heuristic restores the expected ordering, and the honest effect size is small                                                                             |
| 5.4          | T3 annotated with the bound actually tested; statuses added                                                                  | The test is weaker than the claim and should not be over-read                                                                                                                                                                          |
| 6.3          | Heterogeneous cohort stated as conditional, with the governing mechanism                                                     | The illustration’s conclusion is regime-dependent; asserting it generically was unsupported                                                                                                                                            |
| 6.5          | New section: closed-form threshold Δτ\* = τ_0 · (a/m) · B^(1−p), adimensional form, properties, lung anchor with disclaimers | Converts the collapse condition into a reportable analytical result and the paper’s central deliverable at this level                                                                                                                  |
| 8.2          | Interaction between the coverage screen and the margin ladder; new reportable count                                          | Follows from retaining both margin levels                                                                                                                                                                                              |
| 9            | Second purpose of the decomposition: constructing the plausible Δτ envelope                                                  | Follows from Δτ being unmeasurable                                                                                                                                                                                                     |
| 11, 12       | A14, A15 added; open decision 9 added                                                                                        | As above                                                                                                                                                                                                                               |


---

# Evaluation Module (evaluator)

## Changes from version 5.1

Evaluator 5.2. First change to this document in this run of rounds. Writes
the dose-provenance fact that `STATE.md` has carried since the Secondment 1
scope decision, closing evaluator's half of a two-document item; the other
half is in allocator 6.4.

| Change | Where |
| --- | --- |
| New assumption E16: all dose for paper 1 is computed in RayStation and imported, for both modalities; OpenTPS performs no dose calculation, including no use of its own photon CCC implementation. A provenance fact, not previously stated anywhere in this document, which assumed block-level physical dose already homogeneous without naming its origin | evaluator 10 |
| Cross-reference to E16 added at the point Section 3 defines block-level physical dose as consumed, so a reader meets the provenance where the quantity is first named rather than only in the register | evaluator 3 |

**What E16 does not state.** The reporting convention across modalities, RBE
weighting, dose-to-water or dose-to-medium, grid resolution and origin, is
not written here because it is not decided: E16's own risk column points to
allocator decision 25, open, blocked on the clinical partners. Writing a
convention now would be inventing one.

**What did not change.** `extractor_design.md`, also named in `STATE.md`'s
original note on this gap, is untouched; the same fact may belong there too,
not attempted in this round.

## Changes from version 4

**Decision.** The treatment choice is made at prescription, on the planning CT. Adaptation is a course-level property: an adapted arm adapts at every block and carries a reduced-margin plan from the first fraction, a non-adapted arm carries the clinical-margin pCT plan throughout. There is no adaptation vector.

| Section | Change                                                                                                                                                                                                              | Consequence                                                                                                                                                  |
|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2       | Construction rule rewritten from a per-block mapping to an arm-level one. Option set fixed at four per scheme. First-block dose source made configurable. Mixed strategies identified as computable but not options | The strategy space stops growing with the number of blocks. The evaluator’s dominant cost at large B disappears                                              |
| 5.1     | Adaptation becomes a boolean scalar                                                                                                                                                                                 | Each patient holds eight strategies                                                                                                                          |
| 5.2     | Collapse by dominance retired. Pareto reduction retained                                                                                                                                                            | Nothing shares an occupancy, so there is nothing to collapse. The reportable answer to whether early or late adaptation carries more benefit is lost with it |
| 6       | Unchanged in substance. The coverage screen still applies per block, on the nominal dose of the plan delivered in that block                                                                                        | The screen now acts on four strategies per scheme rather than on families of them                                                                            |

**What did not change.** The interface contract, the accumulation ordering and its sensitivity measurement, the caching boundary at the dose-volume histogram, the NTCP model registry, the utility and reporting outputs, and the treatment of coverage and no harm are untouched.

**An item that becomes load-bearing.** With margin fixed at the arm level, the coverage screen is the only mechanism that can remove a reduced-margin arm from a patient who should not receive it, including on the first block where the plan is evaluated on the anatomy it was made on. The screen’s calibration therefore carries more weight than it did when a non-adapted block could fall back to the clinical-margin plan. The count of blocks on which the reduced-margin plan fails coverage should be read as the frequency with which the licensed margin reduction is not in fact deliverable, and it is the quantitative justification for making the margin reduction conditional on adaptation.

## Changes from version 3

**Amendment within version 4.** Section 6.3 previously concluded that infeasibility can only originate from the coverage screen, while simultaneously enforcing a second screen that could empty an option set once coverage had removed the reference arm. By decision of the doctoral candidate, pending supervisory confirmation, the no-harm screen becomes a reported diagnostic and no longer removes anything, which makes the conclusion true rather than merely asserted. Section 6 now states the asymmetry between an enforced screen and a reported one, Section 6.3 is rewritten, Section 6.4 attributes infeasibility to coverage alone, and E6 records the change.

Nothing else in the module changes. The admissibility flag was already part of the interface contract of Section 3 and already carried the separation of the reference role from the assignable role; it is now set by coverage alone.

**Changes from version 3.**

The allocator’s capacity model now carries two resources: proton machine time and a rationed photon adaptation budget. The evaluator’s share of that change is that the photon arm acquires an adaptation vector and that occupancy is emitted per resource. The decision itself, with its justification, is recorded in Section 13 of the allocator document.

| Section    | Change                                                                                                                    | Reason                                                                                        |
|------------|---------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| 2          | The margin-adaptation coupling extended to photons; the photon group acquires a 2^B schedule space and collapses to B + 1 | Photon adaptation is decided per block, symmetric with protons                                |
| 2          | A patient is presented with 2(B + 1) options per scheme rather than B + 2                                                 | Follows from the above                                                                        |
| 3          | tau split into tau_pt and tau_xt, with the reason stated                                                                  | The two costs draw on disjoint budgets, and the allocator treats the option set as two chains |
| 5.1, 5.2   | Adaptation vector and dominance collapse stated per modality; no dominance taken across modalities                        | Each modality draws on one budget, so the collapse is valid within a modality and not between |
| 10         | E7 restated per resource; E11, E12, E13 added                                                                             |                                                                                               |
| Appendix F | Consolidated summary of the fractionation dimension                                                                       | Requested so that the fractionation design can be revised as a block                          |

**What did not change.** Accumulation ordering, the EQD2 conversion, the caching boundary at the DVH, the NTCP registry and the coverage screen are untouched. XT-NA remains the locked baseline with ΔNTCP identically zero. The no-harm screen was subsequently converted to a diagnostic; see the amendment above.

## Changes from version 2 (retained for reference)

| Section    | Change                                                                                                                                                         | Reason                                                                                                                                           |
|------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| 2, 5.1, E9 | Single adaptive margin level; margin becomes a mapping from the adaptation vector rather than a per-block choice                                               | Supervisory decision. Robustness leaves the strategy tuple entirely                                                                              |
| 2, 6.1     | Conservative fallback under coverage failure removed, with the emitted count restated as a measure of how often the licensed margin reduction is undeliverable | Follows from the single margin level                                                                                                             |
| 6.1        | Coverage criterion fixed at V95% below 95 per cent, expressed as a list of criteria of which all must pass                                                     | Supervisory decision, with further criteria possible                                                                                             |
| 7, E10     | The DVH is taken from OpenTPS rather than computed here, and consumed in cumulative form                                                                       | A separate implementation was unjustified. Binning error below 0.001 per cent at 4096 bins and 106 microseconds per re-evaluation, both measured |
| 9          | Target EQD2 stated as reported for completeness, not to assert equivalence                                                                                     | Schedule equivalence rests on clinical consensus                                                                                                 |

## Changes from version 1 (retained for reference)

| Section  | Change                                                                                                                         | Reason                                                                                                                                                                          |
|----------|--------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1, 2     | Strategy construction added as an evaluator responsibility, with the margin-adaptation coupling as the construction rule       | Setup-error reduction presupposes planning on the block’s repeat image; strategies violating this must never be generated, which is a construction concern rather than a screen |
| 5.1, 5.2 | Tuple constrained by the coupling; the collapse identified as a Pareto reduction, distinct from the allocator’s hull reduction | The hull reduction is valid only for the linear relaxation, and conflating the two caused an error in the allocator’s integer heuristic                                         |
| 6.1      | Coverage-fallback interaction with the margin ladder; new emitted count                                                        | Where the aggressive plan fails a block, the conservative adapted plan is the fallback; the frequency of that condition is informative                                          |
| 9        | Dominance-input paragraph added                                                                                                | Clarifies which module computes which reported count                                                                                                                            |
| 10       | E9 added                                                                                                                       | As above                                                                                                                                                                        |


---

# Extraction Module (extractor)

## Changes from version 4.1

Extractor 4.2. Closes extractor's share of the dose-provenance item, the last
of the three modules to receive it: allocator (decision 25, 6.4) and
evaluator (E16, 5.2) came first in this same run of rounds.

| Change | Where |
| --- | --- |
| Dose provenance stated where physical dose is first described as stored: computed in RayStation for both modalities and imported, OpenTPS calculates none, including no use of its own photon CCC implementation | extractor 3 |
| Fuller statement added to the Provenance section itself, the document's existing designated place for this kind of fact, with the open half named: which RayStation algorithm and the cross-modality reporting conventions are not yet fixed, allocator decision 25 | extractor 11 |

This document carries no A- or E-style numbered assumption register, unlike
the allocator and evaluator documents; the addition is prose in the two
sections above rather than a new numbered entry, matching how the document
already states everything else.

**What did not change.** Every other section; no code file.

## Changes from version 3

The allocator now carries two resources, proton machine time and a rationed photon adaptation budget. The extractor’s share of that change is small, because the photon budget is charged only an adaptation increment that the study sweeps rather than measures.

| Section    | Change                                                         | Reason                                                                      |
|------------|----------------------------------------------------------------|-----------------------------------------------------------------------------|
| 6          | Photon delivery-time model stated as not required              | Only the adaptation increment is charged, and it is an independent variable |
| 10         | `cap_min_day` renamed `cap_pt_min_day`; `cap_xt_min_day` added | Two budgets                                                                 |
| 15         | Open item added on the plausible range for Δτ_XT               | Sets the sweep range, does not block extraction                             |
| Appendix F | Consolidated summary of the fractionation dimension            | Requested so that the fractionation design can be revised as a block        |

**What did not change.** The per-plan extraction unit, the storage rules, the target metrics, the registration cache and the provenance mechanism are untouched. The adapted photon plans on the repeat images were already extracted under version 3, since the arm set was already symmetric, so the photon adaptation introduced in the evaluator requires no new extraction.

## Changes from version 2 (retained for reference)

| Section | Change                                                             | Reason                                                           |
|---------|--------------------------------------------------------------------|------------------------------------------------------------------|
| 4       | The DVH stage attributed to the OpenTPS implementation             | A separate implementation was removed as unjustified duplication |
| 5       | Coverage criterion named rather than pending                       | Supervisory decision, V95% below 95 per cent                     |
| 10      | `robustness` annotated as determined by `adapted` rather than free | A single adaptive margin level makes the mapping exact           |
| 13      | Two open items closed                                              | As above                                                         |

## Changes from version 1 (retained for reference, unchanged)

| Section | Change                                                                                         | Reason                                                                                                                                                                       |
|---------|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1       | Consumer is the evaluator; extraction unit is the plan, not the strategy                       | Strategies are combinations formed downstream                                                                                                                                |
| 3       | Storage rule restated as physical dose on native geometry, with warped BED explicitly excluded | Version 1’s rule was correct but its justification omitted the ordering constraint, which appeared to conflict with the accumulation-ordering requirement recorded elsewhere |
| 4       | Mapping and accumulation reassigned to the evaluator; cache boundary at the DVH                | Follows from the module split and from the parameter propagation requirement                                                                                                 |
| 5       | Target metrics per block rather than accumulated; screen application moved out                 | Coverage is a property of a plan on an anatomy, and the per-block form lets the screen run before composition                                                                |
| 8       | NTCP model registry relocated to the evaluator; cohort validation and workload sizing retained | The registry belongs with the component that evaluates it                                                                                                                    |
| 9       | Generator emits dose metrics; delta NTCP shortcut allowed only for trivial debugging           | Otherwise the NTCP and composition paths are untested until data arrives                                                                                                     |
| 10      | Schema reindexed by plan; `strategies_ok` removed                                              | Follows from the above                                                                                                                                                       |

# 5D-TPS
 
Adaptation, fractionation and capacity-constrained allocation for adaptive proton
therapy in the context of the DC18 RAPTORplus doctoral project at KU Leuven and
UCLouvain, which consists of three work packages.
 
The first two (WP1, WP2) extend the analysis of
Borderias-Villarroel et al. (Radiother Oncol 198, 2024)
by treating fractionation as a second degree of freedom alongside
adaptation timing, and by allocating capacity-constrained resources
across a cohort whose members no longer consume equal machine time.
 
Two resources are modelled. Proton machine time is consumed by the proton arms.
Photon adaptation time is consumed by the adapted photon arm, and only as the
adaptation increment, since photon delivery is treated as unconstrained. The
non-adapted photon arm consumes neither and remains the locked reference against
which every delta NTCP is measured, so the allocation is always feasible: an arm
whose coverage fails on a repeat image is rescued by an offline replan at
unchanged margin rather than withdrawn, and its fractionation schedule is fixed
by clinical eligibility rather than chosen by the allocation.
 
The last one (WP3) involves the development and training of an AI decision-support agent
with reinforcement learning and will be addressed in the future.
 
As of now, the repository consists mostly of what is needed for WP1 and WP2.
 
## Structure
 
    README.md
    docs/             design documents, one per module, plus STATE.md and CHANGELOG.md
    src/tps5d/
        core/         records exchanged between the modules
        extractor/    ingest, registration, per-block dose and target metrics
        evaluator/    dose composition, EQD2, NTCP, admissibility screens
        allocator/    capacity-constrained allocation and the shadow prices
        generator/    synthetic cohorts
    scripts/          analysis entry points
    tests/            the algorithmic claims
 
The design of each module is specified in its own document. `docs/STATE.md` is
the first one to read: it describes the present, and points to the others.
 
## Install
 
Python 3.12 is required: numpy 2.5 and OpenTPS 3.0.1 both need it. The
extractor and the evaluator's composition run on OpenTPS 3.0.1 and on no other
release (`docs/extractor_design.md`, Section 3.1).
 
    python -m pip install -r requirements.txt
    python -m pip install -e .
    python -m pytest tests -q
 
`pip install -e .` alone installs the schema, the allocator, the generator and
the NTCP models. The extractor and the composition also need OpenTPS, which the
`opentps` extra declares (`pip install -e ".[opentps,test]"`).
 
## Status
 
The allocator solves the two-resource multiple-choice knapsack exactly, by
integer linear programming, and reads both shadow prices from the duals of the
same relaxed model. The version 4 single-resource dynamic program and greedy
relaxation are retained as `solve_dp` and `solve_lp_greedy`: they are the
independent cross-checks at zero photon budget, where the formulation reduces to
the reference study's structure. That reduction is tested
(T8), and the reference study is still reproduced as the two-option special case
(T1).
 
The evaluator contains the NTCP models, the biological functions and the
composition of block doses into EQD2 and NTCP. The extractor ingests DICOM,
reads and validates the export manifest, and registers the repeat images. Both
have been tested on synthetic DICOM only: no export from the clinical system
has been inspected yet. The schema and the synthetic generator carry the
seven-option structure and the rescue metadata. What the code does not yet do is
listed in `docs/STATE.md`, Section 6.
 
Tagged `v4-single-resource` marks the state before the second resource was
introduced. Tags since then follow `design-vX.Y`, for the design document
generation the code's behaviour matches rather than for any file touched. The
current tag is named in the first lines of `docs/STATE.md`.

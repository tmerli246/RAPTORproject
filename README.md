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
which every delta NTCP is measured, so the allocation is always feasible.
 
The last one (WP3) involves the development and training of an AI decision-support agent
with reinforcement learning and will be addressed in the future.
 
As of now, the repository consists mostly of what is needed for WP1 and WP2.
 
 
## Structure
 
    src/tps5d/
        core/         records exchanged between the modules
        extractor/    ingest, registration, per-block dose and target metrics
        evaluator/    dose composition, EQD2, NTCP, admissibility screens
        allocator/    capacity-constrained allocation and the shadow prices
        generator/    synthetic cohorts
    scripts/          analysis entry points
    tests/            the algorithmic claims
 
The design of each module is specified in its own document.
 
## Install
 
    pip install -e .
    python -m pytest tests -q
 
## Status
 
The allocator solves the two-resource multiple-choice knapsack exactly, by
integer linear programming, and reads both shadow prices from the duals of the
same relaxed model. The version 4 single-resource dynamic program and greedy
relaxation are retained as `solve_dp` and `solve_lp_greedy`: they are the
independent cross-checks at zero photon budget, where the formulation reduces to
the reference study's structure. That reduction is tested
(T8), and the reference study is still reproduced as the two-option special case
(T1).
 
The evaluator currently contains only the NTCP models and the biological
functions; composition, the admissibility screens and the caching layer are not
yet written. The extractor is not yet written.
 
Tagged `v4-single-resource` marks the state before the second resource was
introduced.
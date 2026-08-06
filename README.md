# 5D-TPS

Adaptation, fractionation and capacity-constrained allocation for adaptive proton
therapy. Work package 1 and 2 of the RAPTORplus doctoral project at KU Leuven and
UCLouvain.

The package extends the analysis of Borderias-Villarroel et al. (Radiother Oncol
198, 2024) by treating fractionation as a second degree of freedom alongside
adaptation timing, and by allocating a capacity-constrained proton resource
across a cohort whose members no longer consume equal machine time.

## Structure

    src/tps5d/
        core/         records exchanged between the modules
        extractor/    ingest, registration, per-block dose and target metrics
        evaluator/    dose composition, EQD2, NTCP, admissibility screens
        allocator/    capacity-constrained allocation and the shadow price
    scripts/          analysis entry points
    tests/            synthetic cohorts and the algorithmic claims

The design of each module is specified in its own document.

## Install

    pip install -e .
    python -m pytest tests -q

## Status

The allocator solves the multiple-choice knapsack exactly and reproduces the
reference study as the two-option special case. The evaluator currently contains
only the NTCP models. The extractor is not yet written.

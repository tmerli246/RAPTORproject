"""Structural invariants of BlockPlan and Strategy.block_plans, introduced at
version 7 to carry the coverage-rescue mechanism (allocator design 7.0,
Section 8.2; A24, A29, A30) as metadata ahead of real imaging data.

These are schema-level guarantees, checkable without a generator or a
solver: an empty block_plans is backward compatible with every Strategy
built before this round, and a populated one must open on the planning
anatomy, be contiguous, and never mark an adapted arm as rescued.
"""

import pytest

from tps5d.core.schema import Strategy, BlockPlan

def _pt(block_plans = None, adapted = False):
    return Strategy('p00', 'sid', 'pt', n_fx = 10, tau_pt = 30.0,
                    ntcp = {'tot': 0.25}, adapted = adapted,
                    block_plans = block_plans or [])

# BlockPlan itself

def test_block_plan_rejects_an_unknown_role():
    with pytest.raises(ValueError, match = "role must be"):
        BlockPlan(0, 'delivered', 'pCT')

def test_block_plan_accepts_planned_and_rescue():
    BlockPlan(0, 'planned', 'pCT')
    BlockPlan(1, 'rescue', 'rCT1')

# Backward compatibility: empty block_plans is untouched by validation

def test_empty_block_plans_is_the_default_and_skips_validation():
    s = _pt()
    assert s.block_plans == []
    assert s.n_rescues == 0

def test_strategy_without_block_plans_keyword_still_constructs():
    """Every pre-version-7 call site omits block_plans entirely."""
    s = Strategy('p00', 'sid', 'xt', n_fx = 1, tau_pt = 0.0,
                 ntcp = {'tot': 0.3}, baseline = True)
    assert s.block_plans == []

# Populated sequences: three structural rules

def test_block_zero_must_be_planned_on_the_planning_anatomy():
    with pytest.raises(ValueError, match = "block 0"):
        _pt([BlockPlan(0, 'rescue', 'rCT0')])

def test_block_plans_must_be_contiguous_and_zero_based():
    with pytest.raises(ValueError, match = "contiguous"):
        _pt([BlockPlan(0, 'planned', 'pCT'), BlockPlan(2, 'planned', 'rCT2')])

def test_adapted_arm_cannot_carry_a_rescue_block():
    """An adapted arm's plan is optimised on the anatomy it is evaluated on
    (A1, A4) and cannot fail the screen by construction."""
    with pytest.raises(ValueError, match = "cannot be rescued"):
        _pt([BlockPlan(0, 'planned', 'pCT'), BlockPlan(1, 'rescue', 'rCT1')],
            adapted = True)

def test_adapted_arm_accepts_an_all_planned_sequence():
    s = _pt([BlockPlan(0, 'planned', 'pCT'), BlockPlan(1, 'planned', 'rCT1')],
            adapted = True)
    assert s.n_rescues == 0

# n_rescues

def test_n_rescues_counts_only_rescue_entries():
    s = _pt([BlockPlan(0, 'planned', 'pCT'),
            BlockPlan(1, 'rescue', 'rCT1'),
            BlockPlan(2, 'planned', 'rCT1'),
            BlockPlan(3, 'rescue', 'rCT3')])
    assert s.n_rescues == 2
    assert len(s.block_plans) == 4

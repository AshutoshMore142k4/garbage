"""D1 -- rule learning from resolved exceptions (plan.md #9, phases.md Phase 8).

A human resolves one escalated bank line; `propose.py` generalizes that single answer into a
candidate rule spec; `validate.py` replays it against train+validation history; `promote.py`
promotes it into the L1 registry only if it hits at least `MIN_HITS` times with zero false
positives. See eval/rule_learning.py for the three-sequential-batch demonstration this feeds and
this package's own module docstrings for the specific pattern this dataset actually has to learn.
"""

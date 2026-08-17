"""The `architect` scope's instrument: a declared-policy import extractor and the
structural metrics computed over it.

The instrument exists because the scope had none. Every other differentiated expert
reads an artifact it did not write — `qe` runs cases, `eval-methodology` reads traces,
`literature` reads retained documents — while `architect` read only its own prose. A
scope whose findings rest on nothing mechanical cannot be wrong in public, which is the
same as not being right.

**The policy is part of the measurement.** Propagation cost over `src/thalamus/`
measures 7.65% counting every import and 5.82% counting only module-level ones — a 31%
swing on one boolean nobody had declared. So the extractor's policy is written down,
digested, and carried on every number the scanner emits: a scan is not interpretable
against a scan produced by a different extractor. `metrics.propagation_cost` therefore
takes a `DependencyGraph` that already knows the policy that built it, and the scan id
(`arch:scan:<repo>:<sha7>:<policy-digest7>`) names both the commit and the policy.

Metrics are recomputed, never stored as truth. The model file retains the
edge list — the observation — and the derived numbers beside it are a rendering of what
the current code computes from those edges.
"""

from thalamus.arch.extractor import (
    DependencyEdge,
    DependencyGraph,
    ExtractorPolicy,
    scan_repo,
)
from thalamus.arch.metrics import Metrics, cycles, propagation_cost, visibility

__all__ = [
    "DependencyEdge",
    "DependencyGraph",
    "ExtractorPolicy",
    "Metrics",
    "cycles",
    "propagation_cost",
    "scan_repo",
    "visibility",
]

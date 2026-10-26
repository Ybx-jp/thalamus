"""A declared-policy import extractor for a Python repository, the structural metrics
computed over it, and the gates that hold the repository to its declared layers.

The repository declares its design in `arch/model.yaml`: the source roots to walk, the
layers its modules fall into, which layer may depend on which, and the exceptions it
accepts with their reasons. `thalamus-arch` measures the import graph, checks it
against those rules, and regenerates the measured half of the file. Nothing here reads
or writes anything but the repository and its git history, and nothing here imports
thalamus: installed beside it, the package also answers as `thalamus arch`.

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

__version__ = "0.1.0"

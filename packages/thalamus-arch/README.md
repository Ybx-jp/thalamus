# thalamus-arch

A structural gate for a Python repository. The repository declares its design in
`arch/model.yaml`: the source roots to walk, the layers its modules fall into, which
layer may depend on which, and the exceptions it accepts, each with its reason.
`thalamus-arch` measures the import graph under that declared policy and reports where
the code and the declaration disagree.

- `thalamus-arch scan` measures the import graph: modules, dependencies, propagation
  cost and cycles. With `--write` it regenerates the measured half of `arch/model.yaml`
  and leaves the authored half byte for byte. With `--check` it exits 1 when the
  committed file no longer matches a fresh scan.
- `thalamus-arch rules --gate` exits 1 on a dependency the declared layers forbid and
  the model does not accept, and 2 on an accepted exception that no longer happens.
- `thalamus-arch dead --gate` exits 1 on a definition under the source roots that
  nothing outside the test roots refers to.
- `thalamus-arch refs` reports names that comments point at and the tree no longer
  holds. It has no gate.
- `thalamus-arch diff <commit>` recomputes both sides and compares them.
- `thalamus-arch show` prints the declared model and the last scan.

Every subcommand takes `--repo`. It defaults to the git repository holding the current
directory.

It depends on PyYAML and pluggy and on nothing from thalamus. Installed beside
[thalamus](https://github.com/Ybx-jp/thalamus), it also answers as `thalamus arch`,
through the `thalamus` entry-point group.

`pip install thalamus-arch` installs it, or `uv tool install thalamus-arch` as a
command of its own. In a checkout of the thalamus repository, `uv sync` installs it into
the development environment. The repository's own [`arch/model.yaml`](https://github.com/Ybx-jp/thalamus/blob/master/arch/model.yaml) is a worked
example of every block.

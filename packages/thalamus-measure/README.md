# thalamus-measure

The eval loop's reports and the pulse dashboard for
[thalamus](https://github.com/Ybx-jp/thalamus). Core lands every memory-tool call as a
priced Trace node (`thalamus eval sync`); this plugin reads them back.

Installing it adds:

- `thalamus eval report`: per-scope retrieval utility, what was used and what was
  ignored;
- `thalamus eval uses`: attribution subgraphs, who cited what and whether it compounds;
- `thalamus eval pins`: per-expert utility when pinned against when consulted;
- `thalamus eval withholding`: whether nodes the randomized-withholding policy held back
  come back;
- `thalamus eval gremlin`, `eval recipes` and `eval profile`: guard rescue rate, the
  recipe store's smoke run, and what each traversal shape costs;
- `thalamus pulse`: the live dashboard over all of the above.

It depends on `thalamus-memory` and nothing else from thalamus, and registers through the
`thalamus` entry-point group.

`pip install thalamus-measure` installs it with the core it needs, or `uv tool install
thalamus-memory --with thalamus-measure`. In a checkout of the repository, `uv sync`
installs it into the development environment.

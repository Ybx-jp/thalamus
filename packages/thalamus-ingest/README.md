# thalamus-ingest

Curated ingestion for [thalamus](https://github.com/Ybx-jp/thalamus): one third-party
document at a time into an expert's knowledge subgraph, gated by that expert's manifest.

Installing it adds two commands to `thalamus`:

- `thalamus ingest <url-or-path> --scope <expert>` fetches or reads the document, checks
  the origin that served it against the expert's `allowlist`, retains the bytes in the
  archive, extracts typed claims and entities with one headless model pass per chunk,
  and hands the batch to the federation contract. `--check` stops before the model
  call; `--write` persists.
- `thalamus backfill-chunks` builds the verbatim Chunk vertices for documents ingested
  before chunking existed. It needs no model.

It depends on `thalamus-memory` and nothing else from thalamus, and registers its
commands through the `thalamus` entry-point group.

`pip install thalamus-ingest` installs it with the core it needs, or `uv tool install
thalamus-memory --with thalamus-ingest`. In a checkout of the repository, `uv sync`
installs it into the development environment.

```bash
thalamus ingest https://arxiv.org/html/2601.00821 --scope literature --check
```

The procedure — demand-driven against open threads, check first, `--write` once — is
in the repository's [CLI reference](https://github.com/Ybx-jp/thalamus/blob/master/docs/cli.md).

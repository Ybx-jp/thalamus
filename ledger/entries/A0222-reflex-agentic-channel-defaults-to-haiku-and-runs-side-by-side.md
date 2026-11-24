---
id: A0222-reflex-agentic-channel-defaults-to-haiku-and-runs-side-by-side
kind: claim
stated: 2026-10-08T00:20:30-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: a344fa846527e589f6ed9d6ee8b328de239962c9248a31c8d211d325d87208a8
---

## Assertion

The reflex agentic plan runs on the channel THALAMUS_REFLEX_CHANNEL names: claude when it is unset, local when it says local, and any other value records every queued job as an error naming the value. It asks the channel for the model THALAMUS_REFLEX_MODEL names, passed through unchecked, or else haiku on claude and the local server's model on local. On the claude channel every trigger starts a worker, workers take no global lock and run jobs side by side, and no (session, agent) key has two jobs in flight; on the local channel a worker holds the global lock and runs jobs one at a time, and a trigger that finds it held starts none.

## Scope

metric: which channel and model run a queued agentic job, and how many jobs run at once
cohort: agentic reflex jobs queued by the trigger hook and run by thalamus reflex --work
condition: the variables are read from the environment the trigger hook and the worker inherit; a worker started before a change of channel keeps the one it read

## Grounds

- code: src/thalamus/harness/reflex_channel.py § "CHANNELS" =sha256:b4271f14991e431fd670f574161b927d5ee3cc4288a143d92cff068ffc9890bb
- code: src/thalamus/harness/reflex_channel.py § "channel" =sha256:ad0c3126f65b5ac1dc279e8330992db08ebed4a8ca42ef7ef9bf5a74335d4471
- code: src/thalamus/harness/reflex_channel.py § "resolve" =sha256:ebe0da54755293b41dd668b922f68b8e269748f042001c704f8fa7ef0514d720
- code: src/thalamus/harness/reflex_channel.py § "concurrent" =sha256:8e4e001c54ddd3c74366ee44d895c9903a391d27327e9449aca52c1327ddd752
- code: src/thalamus/harness/reflex_worker.py § "work" =sha256:6f767b366064c9d6f87c0f310f0f783eca10d7399ded609a336d492c927013ed
- code: src/thalamus/harness/reflex_worker.py § "_refuse_all" =sha256:371798e26d646c58bc228a5dbef9a7089196f9f60f7c13f76d5dfd794ef63b71
- code: src/thalamus/harness/reflex_worker.py § "claim_next" =sha256:4166ac11ea909557794e82936040cece7c1448f8001475b81061e6f1c868d193
- code: src/thalamus/harness/reflex_worker.py § "_in_flight" =sha256:3ef301e45d19ae55df13e68c089a9536cb94949e00ae96283bd23483a349354f
- code: src/thalamus/harness/reflex_queue.py § "spawn_worker" =sha256:525aacebff4539650a9be5463dc9f80c9a45591614a250026f4e105ca1dbbee0
- search: corpus=src/thalamus; query="worker_lock_path"; date=2026-10-08

## Warrant

channel returns DEFAULT_CHANNEL, claude, for an unset or blank CHANNEL_ENV and raises UnknownChannel for a value CHANNELS lacks; resolve returns cli_for of the channel and the first of the caller's model, MODEL_ENV and the channel's CHANNELS default, with no check of the name. work resolves the channel when no cli is passed and hands an UnknownChannel to _refuse_all, which claims every pending job and appends an error outcome carrying the message; it takes the global flock only when the cli is not reached by subprocess. concurrent is false only for local or an unknown channel, and spawn_worker skips its worker_running check when told concurrent, which fire does from concurrent. claim_next passes over a key whose directory holds a claimed file of another live process (_in_flight), and work returns when every pending job's key is in flight. A search of src/thalamus for worker_lock_path finds only work, which flocks it on the local channel alone, and worker_running, which spawn_worker skips when concurrent; nothing else takes a lock a claude-channel worker would wait on.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_channel.py § "CHANNELS" =sha256:b4271f14991e431fd670f574161b927d5ee3cc4288a143d92cff068ffc9890bb
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_channel.py § "channel" =sha256:ad0c3126f65b5ac1dc279e8330992db08ebed4a8ca42ef7ef9bf5a74335d4471
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_channel.py § "resolve" =sha256:ebe0da54755293b41dd668b922f68b8e269748f042001c704f8fa7ef0514d720
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_channel.py § "concurrent" =sha256:8e4e001c54ddd3c74366ee44d895c9903a391d27327e9449aca52c1327ddd752
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "work" =sha256:6f767b366064c9d6f87c0f310f0f783eca10d7399ded609a336d492c927013ed
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "_refuse_all" =sha256:371798e26d646c58bc228a5dbef9a7089196f9f60f7c13f76d5dfd794ef63b71
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "claim_next" =sha256:4166ac11ea909557794e82936040cece7c1448f8001475b81061e6f1c868d193
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "_in_flight" =sha256:3ef301e45d19ae55df13e68c089a9536cb94949e00ae96283bd23483a349354f
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/reflex_queue.py § "spawn_worker" =sha256:525aacebff4539650a9be5463dc9f80c9a45591614a250026f4e105ca1dbbee0
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py § "CHANNELS" =sha256:b4271f14991e431fd670f574161b927d5ee3cc4288a143d92cff068ffc9890bb
  note: src/thalamus/harness/reflex_channel.py moved into the thalamus-reflex plugin package as reflex_channel.py with CHANNELS unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py § "channel" =sha256:ad0c3126f65b5ac1dc279e8330992db08ebed4a8ca42ef7ef9bf5a74335d4471
  note: src/thalamus/harness/reflex_channel.py moved into the thalamus-reflex plugin package as reflex_channel.py with channel unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py § "resolve" =sha256:ebe0da54755293b41dd668b922f68b8e269748f042001c704f8fa7ef0514d720
  note: src/thalamus/harness/reflex_channel.py moved into the thalamus-reflex plugin package as reflex_channel.py with resolve unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py § "concurrent" =sha256:8e4e001c54ddd3c74366ee44d895c9903a391d27327e9449aca52c1327ddd752
  note: src/thalamus/harness/reflex_channel.py moved into the thalamus-reflex plugin package as reflex_channel.py with concurrent unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_worker.py § "work" =sha256:6f767b366064c9d6f87c0f310f0f783eca10d7399ded609a336d492c927013ed
  note: src/thalamus/harness/reflex_worker.py moved into the thalamus-reflex plugin package as reflex_worker.py with work unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_worker.py § "_refuse_all" =sha256:371798e26d646c58bc228a5dbef9a7089196f9f60f7c13f76d5dfd794ef63b71
  note: src/thalamus/harness/reflex_worker.py moved into the thalamus-reflex plugin package as reflex_worker.py with _refuse_all unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_worker.py § "claim_next" =sha256:4166ac11ea909557794e82936040cece7c1448f8001475b81061e6f1c868d193
  note: src/thalamus/harness/reflex_worker.py moved into the thalamus-reflex plugin package as reflex_worker.py with claim_next unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_worker.py § "_in_flight" =sha256:3ef301e45d19ae55df13e68c089a9536cb94949e00ae96283bd23483a349354f
  note: src/thalamus/harness/reflex_worker.py moved into the thalamus-reflex plugin package as reflex_worker.py with _in_flight unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/reflex_queue.py § "spawn_worker" =sha256:525aacebff4539650a9be5463dc9f80c9a45591614a250026f4e105ca1dbbee0
  note: src/thalamus/harness/reflex_queue.py moved into the thalamus-reflex plugin package as reflex_queue.py with spawn_worker unchanged, so the assertion is unaffected

## References

- docs/cli.md · standing · cites-as-live
- packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py · standing · cites-as-live

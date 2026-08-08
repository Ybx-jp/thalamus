# 045 — The registry that was not the socket

**Ends in: the room's structural boundary is real, and it is not the one that was
shipped. `XDG_RUNTIME_DIR` isolates nothing — five sessions across three
separate socket registries all listed each other. Peer discovery never reads a
socket directory; it enumerates `$CLAUDE_CONFIG_DIR/sessions/*.json`, each
descriptor publishing its own `messagingSocketPath`. A per-room
`CLAUDE_CONFIG_DIR` partitions the roster cleanly, in both directions, and with
`projects/` symlinked back it costs the room nothing in distillation reach.**

**Date:** 2026-08-08 · **Harness:** Claude Code 2.1.226 · **Status:** measured,
end-to-end, with positive controls; lab/044's discovery claim refuted

## The A/B lab/044 left unrun

lab/044 confirmed the boundary *structurally* — which directory a socket binds in
— and named the gap itself: "confirmed structurally and not end-to-end (what
`ListAgents` actually shows a member and a non-member). Run it before the cheap
tier ships." This is that run.

Five concurrent sessions, pre-registered before launch:

| session | `XDG_RUNTIME_DIR` | role |
|---|---|---|
| this session | default `/run/user/1000` | default-registry witness |
| `outsider` | default `/run/user/1000` | non-member prober |
| `alpha-one`, `alpha-two` | `/run/user/1000/rooms/alpha` | member probers |
| `beta-one` | `/run/user/1000/rooms/beta` | second-room prober |

Each probe slept, called `ListAgents`, slept, and called it again, so a peer that
had not yet registered at the first call could not be misread as invisible. Every
socket path was asserted under the 103-byte cliff (47 and 46 bytes). Probes ran
with `THALAMUS_SANDBOX=1` so four throwaway transcripts stayed out of the graph.

The pre-declared rule, carried over from lab/044's error: **a negative is only
readable beside a positive from the same instrument.** If the in-room and
default-registry controls failed, the isolation result would measure nothing.

## Arm 1: the sockets partitioned. The visibility did not.

The registries did exactly what lab/044 predicted, at every sample:

| registry | sockets during the window |
|---|---|
| `/run/user/1000/cc-socks` | `679962` (this session), `681802` (`outsider`) |
| `rooms/alpha/cc-socks` | `681799`, `681800` |
| `rooms/beta/cc-socks` | `681801` |
| `/tmp/cc-socks-1000` | empty — nothing overflowed |

And all four probes, on both calls, listed **all four peers**: every room member
saw the other room, saw the outsider, and saw this session; the outsider saw both
rooms. Controls pass (in-room mutual visibility, default-registry visibility), so
the negative is readable — and it is a clean, total isolation failure. Both
directions, room-to-room and room-to-outside.

## Why: discovery reads a descriptor, not a directory

The peer roster is built by enumerating `$CLAUDE_CONFIG_DIR/sessions/`, taking
every `<pid>.json`, and reading the socket address **out of the file**:

```js
let e = join(Ln(), "sessions"); …
t.filter(n => /^\d+\.json$/.test(n)).map(async n => { …
  return { sock: typeof l.messagingSocketPath === "string" ? l.messagingSocketPath : "", … }
```

A live descriptor on this box:

```json
{"pid":679962,"sessionId":"95c7e1d5-…","cwd":"/home/ybx/code/thalamus",
 "messagingSocketPath":"/run/user/1000/cc-socks/679962.sock",
 "name":"thalamus-c9","kind":"interactive","tmux":"thalamus:@0.%0", …}
```

No socket directory is ever scanned. `XDG_RUNTIME_DIR` chooses where a session
*binds*, and the descriptor then hands that address to every session sharing the
config dir. A per-room socket dir does not hide a session; it only changes the
address at which everyone reaches it.

## The generalisable error, and it is the same one twice

lab/044 watched the location its hypothesis predicted and read silence as
absence. This entry's target claim was made the same way in the other direction:
having found that `XDG_RUNTIME_DIR` *is* honoured for binding, it concluded that
discovery must therefore read that directory. It confirmed the mechanism it went
looking for and never asked what the reader actually reads. **Confirming where a
write lands does not establish where a read comes from.**

## Arm 2: the config dir is the lever, and it partitions cleanly

Same probes, and the variable isolated on purpose — **every session used the
default `XDG_RUNTIME_DIR`**, so all sockets bound in the one shared directory and
any partition is attributable to the config dir alone. A room config dir carries
a private `sessions/`, with `.credentials.json` symlinked (one token file, no
second copy) and `.claude.json` copied, since probes write to it.

| prober | config dir | saw |
|---|---|---|
| `alpha-one` | `rooms/alpha-cfg` | `alpha-two`, nothing else |
| `alpha-two` | `rooms/alpha-cfg` | `alpha-one`, nothing else |
| `beta-one` | `rooms/beta-cfg` | nothing |
| `outsider` | real `~/.claude` | this session, nothing else |

Meanwhile every probe socket sat in the shared `/run/user/1000/cc-socks`, and the
three `sessions/` registries held exactly their own members. Visibility followed
the registries, not the sockets — which is both the result and a direct control
on the mechanism claim above. `beta-one`'s empty listing carries no in-room
positive control of its own (it was a room of one); it counts only as a target
`alpha-*` and `outsider` failed to see.

A room config dir refuses to start without reaching `.credentials.json` — a probe
with a fresh config dir fails at the API with no credentials to find.

## Arm 3: and it need not cost the room its memory

A separate config dir also relocates `projects/`, where transcripts are written.
Arm 2's room transcripts landed under `rooms/<room>-cfg/projects/` — on **tmpfs**,
and nowhere `thalamus extract` looks. Uncorrected, joining a room silently costs
a session its distillation.

The fix is that `projects/` is not part of the discovery mechanism, so it can be
symlinked back. Arm 3 kept only `sessions/` and `statsig/` private and symlinked
`projects/`, `todos/`, `skills`, `agents`, `plugins`, `commands`:

- the partition held, on both calls, both members — `alpha-one` ↔ `alpha-two`,
  `outsider` saw only this session;
- room transcripts were written into the real `~/.claude/projects/`;
- nothing was left behind on tmpfs.

## Arm 4: the send path refuses an out-of-band name, and a leaked ref

Discovery being partitioned does not settle *delivery*. If `SendMessage`
resolved a target by any route but the caller's own roster, a non-member who
learned a name out-of-band would reach in anyway and the boundary would be
cosmetic. The adversarial version: a scout **inside** the room called
`ListAgents` and wrote out the member's exact addressable string, which was
handed to the outsider verbatim.

| cell | sender → target | result |
|---|---|---|
| in-room | `alpha-two` → `alpha-one [ref]` | **delivered** — receiver reports `PROBE-INROOM` |
| control | `outsider-send` → `outsider-recv [ref]` | **delivered** — receiver reports `PROBE-CONTROL` |
| out-of-band | `outsider-send` → `alpha-one [da1b10]`, leaked | `No agent named 'alpha-one [da1b10]' is reachable.` |

Both positive controls delivered end-to-end and both receivers reported the
inbound `<cross-session-message>` wrapper, so the receiver-side instrument is
valid and the negative is readable.

A first run of this arm delivered nothing in any cell: `SendMessage` requires the
disambiguated `name [ref]` form on first contact, and the senders had been told
not to retry. That run is not evidence of isolation — it is an instrument
failure, and it is only the re-run with refs that decides anything.

**The boundary is name resolution, not transport.** Every session in this arm
bound its socket in the *same shared* `/run/user/1000/cc-socks` — the delivered
messages carry `from="uds:/run/user/1000/cc-socks/713944.sock"` — so `alpha-one`'s
socket was reachable to the outsider the whole time and the resolver simply
refused to name it. A room is therefore a boundary against an agent using the
sanctioned tool, which is the docs/05 threat model, and **not** a confinement
boundary against a hostile local process of the same uid.

## Consequences

- **docs/07's structural-boundary paragraph and `room-guard.sh`'s header comment
  named the wrong variable and are corrected in this change.** Both stated that
  per-room `XDG_RUNTIME_DIR` "gives members a registry only they can see".
- **The room launcher's isolation argument is `CLAUDE_CONFIG_DIR`, not
  `XDG_RUNTIME_DIR`** — a room dir with a private `sessions/`, credentials
  symlinked, and `projects/`/`todos/` symlinked back to the real config.
- **The guard returns to defence-in-depth**, over a boundary that now exists.
  Its outbound-only limit is survivable again for the same reason as before: a
  non-member is not in the roster to be addressed, and arm 4 shows it cannot
  address one out-of-band either.
- **`projects/` must not be symlinked after all** — [lab/046](046-the-third-channel-is-the-transcript.md)
  found that arm 3's fix opens a transcript channel straight through this
  boundary, and replaces it with a room dir that owns its `projects/` on
  persistent disk.
- `--messaging-socket-path` (hidden flag, from the lab/044 consultation) sets the
  bind address directly and is irrelevant to isolation — the descriptor publishes
  whatever it sets.

## Not yet measured

- Whether the cheap unprovenanced intra-room protocol is defensible *given* this
  boundary. This entry establishes that a boundary can be drawn, not that the
  protocol inside it is safe; the lab/042 verdict on the write-path judge stands.
- What else a private config dir silently forks. `projects/`, `todos/` and
  `statsig/` were checked; `history.jsonl`, `file-history/`, `teams/`, `tasks/`
  and `ide/` were not, and `settings.json` is currently a **copy**, so a settings
  edit would not reach a live room.
- Everything here used `claude -p`. Interactive sessions publish the same
  descriptor shape (this session's is quoted above), but their visibility was not
  probed from inside a room.

# 045 — The registry that was not the socket

**Ends in: the structural room boundary does not exist. Five concurrent sessions
across three isolated socket registries all listed each other. `XDG_RUNTIME_DIR`
relocates the *socket*; peer discovery never reads a socket directory — it reads
`$CLAUDE_CONFIG_DIR/sessions/*.json`, and each descriptor publishes its own
`messagingSocketPath` to every reader. `room-guard.sh` is not defence-in-depth
over a structural boundary. It is the only boundary there is.**

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

## The sockets partitioned. The visibility did not.

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

## Consequences

- **docs/07's structural-boundary paragraph and `room-guard.sh`'s header comment
  were false and are corrected in this change.** Both stated that per-room
  `XDG_RUNTIME_DIR` "gives members a registry only they can see".
- **The guard is now the whole boundary, not the second layer.** Its known limit
  — outbound only, since `crossSessionInbound` cannot discriminate by sender —
  was survivable *because* a non-member was supposedly undiscoverable. It isn't.
  An outsider can enumerate every room member by name and message in, and no room
  member's hook fires on that path.
- **The cheap intra-room protocol does not ship on this footing.** Its whole
  defence was that unprovenanced content could not leave the room. What actually
  holds today is one sender-side hook over a fully public roster.
- **`CLAUDE_CONFIG_DIR` is the candidate lever** — it is what `Ln()` resolves, and
  a private `sessions/` under it would partition the roster itself. Untested
  end-to-end: a room config dir needs the session to reach `.credentials.json`,
  and both routes tried (copy, symlink) were refused by the permission
  classifier. The arm is designed and blocked, not run.
- `--messaging-socket-path` (hidden flag, from the lab/044 consultation) sets the
  bind address directly. It cannot help here either: the descriptor publishes
  whatever it sets.

## Not yet measured

- The `CLAUDE_CONFIG_DIR` arm above.
- Whether a room member's descriptor can be withheld from the shared registry at
  all without also cutting it off from `main` and its own subagents.
- Everything here used `claude -p`. Interactive sessions publish the same
  descriptor shape (this session's is quoted above), but their visibility was not
  probed from inside a room.

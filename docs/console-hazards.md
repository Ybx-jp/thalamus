# Hazards of driving tmux from a phone

Everything here has actually bitten a running system, and none of it is specific to
this project — it applies to any setup where **a long-lived tmux session is created by
a systemd unit and driven over HTTP from a browser**. The failures share a shape:
tmux, systemd, and the browser each report success while the thing you wanted quietly
did not happen.

If you are building something like this, these are the traps in the order they tend to
find you.

---

## 1. Whoever creates the session defines window 0 — forever

tmux window indexes are assigned in creation order and never reshuffle. If your control
plane treats "the lowest-indexed window" as special — an anchor, a home tab, the
reference directory — then **whichever process creates the session first decides what
that window is**, for the entire life of the tmux server.

The classic way to lose this race: a web terminal like `ttyd` configured with
`tmux new -A -s <session>`. It attaches if the session exists and *creates it with a
bare login shell* if it doesn't. First browser connect after a reboot, and index 0 is
now a shell instead of your real process. Everything that assumes the anchor is a real
process then misbehaves — commands typed into it land in `bash`, which answers
`-bash: /exit: No such file or directory` and never exits, so any "wait for it to die"
logic hangs for its full timeout.

**Fix:** give the session an explicit owner — a `oneshot` unit that creates it, ordered
`Before=` everything else that might.

```ini
Before=my-tty.service my-console.service
```

**Repair a live one:** confirm index 0 really is an idle shell (`tmux list-panes`, no
child processes), `tmux kill-window -t <session>:0`, then re-run the owner.

**Corollary:** identify the anchor by *lowest index*, never by name. A name guard
protects every window that happens to share the name.

---

## 2. The tmux server lives in the cgroup of the unit that created it

This one destroys everything at once.

systemd puts a forked process in the creating unit's cgroup, and the default
`KillMode=control-group` kills the **entire cgroup** on stop. So if unit A happened to
create the tmux session, `systemctl --user restart A` kills every session in it — even
though A has nothing to do with them.

```ini
[Service]
Type=oneshot
RemainAfterExit=yes
KillMode=process     # confine the stop to ExecStart; leave the sessions alone
```

**Always check who holds it before restarting anything:**

```sh
cat /proc/$(pgrep -f 'tmux new-session.*<session>' | head -1)/cgroup
```

---

## 3. A pane inherits the PATH of the client that created the window

Not the PATH of your shell. Not the PATH in `~/.profile`. The PATH of whatever process
called `tmux new-window`.

When that caller is a systemd user unit, the PATH is whatever the *user manager* had at
unit start — and a systemd user unit never gets a login shell's PATH. Worse, that value
differs depending on **when** the unit started:

| Unit started | PATH includes `~/.local/bin`? |
|---|---|
| At boot (lingering / enabled) | **No** |
| After a desktop login | Yes — the session ran `import-environment` |

So a tool installed in `~/.local/bin` — which is where `uv`, `ttyd`, `claude`, `pipx`
shims and most user-level installs land — resolves fine when you test by hand, resolves
fine if the service was started from your terminal, and **cannot be found after an
unattended reboot**. The bug hides until the machine reboots on its own.

**Fix:** pin PATH in the unit rather than inheriting it.

```ini
Environment=PATH=%h/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

---

## 4. `tmux new-window` returns 0 before your command execs

This is what makes hazard 3 so hard to see.

`tmux new-window` reports success as soon as it has **forked**. Whether the command
then execs is not part of its exit status. So a command that cannot start at all —
wrong PATH, missing binary, bad interpreter — produces:

1. `tmux new-window` → exit 0
2. the pane dies immediately
3. tmux reaps the window (no `remain-on-exit`), so it isn't even there to inspect
4. every layer above reports success

The API answers `{"ok": true}` and the button does nothing. There is no error anywhere,
because nothing errored — the evidence deleted itself.

**Never treat a zero exit as proof a window exists.** Ask `new-window` for the id of
the window it just made (`-P -F '#{window_id}'`) and poll *that* window until it has
survived a settle deadline:

```python
window_id = tmux("new-window", "-d", "-P", "-F", "#{window_id}", "--", *argv)
deadline = time.monotonic() + SETTLE
while True:
    if pane_dead(window_id):             # or the window is gone entirely
        return False, epitaph(window_id)
    if time.monotonic() >= deadline:
        return True
    time.sleep(0.05)
```

Poll, don't sleep the deadline out: only a launch that succeeds should pay the full
wait. Confirm against the id rather than a diff of the window list — a diff can only
ask whether *some* new window is alive, which stops being the same question the
moment anything else creates windows.

**How long to settle is a property of the command, not of tmux**, and the gap between
two commands is large enough that one constant cannot serve both. Measured on this box
(2026-08-12), launching each CLI in a window and timing the death:

| launch | outcome | measured |
|---|---|---|
| missing binary (any) | dies, status 127 | 0.010 s |
| `claude`, rejected flag | dies, status 1 | 0.278 s |
| `claude`, untrusted dir / bad API key / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent` (Cursor), untrusted dir / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent`, rejected API key | dies, status 1 | 1.07–1.14 s (n=9) |
| `agent`, rejected API key, +2 s of proxy latency | dies, status 1 | 3.14–3.20 s (n=3) |

The last two rows are the same failure under two network conditions: the time to death
moved by exactly the latency added in front of it. **A death that resolves after a
round trip has no bound**, so the deadline for such a command is a bet sized on a
measurement, not a guarantee — pick it per command, name the residual, and remember
the window list is what shows a death that lands after it. The tempting fix of one
generous global deadline is worse than it looks: it is paid on **every** successful
spawn, by an operator watching a phone.

Serialize spawns anyway if the session may not exist yet, or two of them race to
create it.

**Read the corpse, don't just count it.** Turn `remain-on-exit` on for the settle and
the window that died is still there to explain itself — `pane_dead_status` for the exit
code, `capture-pane` for what it printed. Two details or you get nothing back:

- **`-S -`.** When a pane dies its output is pushed up out of the viewport and the
  "Pane is dead" banner is left alone on the visible screen. Without the history flag
  you capture 200 blank lines and the banner.
- **`-J`.** A roster pane is 60 columns, so one sentence of vendor English is three
  screen lines; taking the last few unjoined quotes a fragment starting mid-word.

Turn the option **back off** the moment the window proves alive. A window that keeps it
leaves a corpse when its real session ends, which every close and recycle path reads as
a window still there.

**To debug one live:** `tmux set -wg remain-on-exit on` makes the corpse stay so you can
read `pane_dead_status` and `capture-pane`. Note the *global* (`-wg`) form — a
session-level set is not inherited by new windows. Turn it back off afterwards; lingering
dead panes confuse close/recycle logic. If the process clears the screen on exit, wrap
it in `script -qfc '<cmd>' /tmp/log` to capture what it actually printed.

---

## 5. Create windows detached, or you yank every attached client

`tmux new-window` without `-d` switches **all** attached clients to the new window. If a
background process adds windows, anyone with a terminal attached gets teleported
mid-keystroke. Use `-d` for anything programmatic; keep the switch only where a human
explicitly asked for that window.

---

## 6. Window geometry is load-bearing when you scrape with `capture-pane`

A full-screen TUI runs on the terminal's alternate screen, so `capture-pane` returns
exactly the window's height in lines — the geometry *is* your API's page size, and your
client's layout assumptions are pinned to the column count.

Setting `window-size manual` keeps a window at a fixed size even while a desktop client
with a different terminal size is attached. But on tmux 3.4, setting it **globally**
and then creating a window with no client attached **segfaults the server** — taking
every session down. Set it per-window, after creation:

```sh
tmux new-window -d …                          # create first
tmux set -w -t <window_id> window-size manual # then pin
```

---

## 7. The phone is usually lying about the server

When the browser shows something stale or broken and the server measures healthy,
suspect the PWA layer, not the backend. Diagnose in this order — loopback API first,
then through the proxy, then the installed app:

```sh
curl -s 127.0.0.1:<port>/api/panes          # server truth
curl -s https://<host>/<mount>/api/panes    # proxy truth
```

Two things reliably cause "the server is fine but the phone isn't":

- **A cache-first service worker** serving a stale shell. Keep the SW network-first for
  the shell, and **never let it intercept `/api/`**. The discriminator for a stale
  install is a full close (swipe from recents) and reopen — not a refresh.
- **Android WebAPK scope collisions.** Installed PWAs claim a URL scope **per hostname,
  ignoring the port**. Two apps on one host must get disjoint path scopes
  (`/app-a/`, `/app-b/`); a root-scoped install captures the other app's links
  host-wide.

---

## 8. Reverse proxies strip the mount path

`tailscale serve --set-path /console http://127.0.0.1:8378` forwards `/console/api/panes`
to the backend as `/api/panes`. That is usually what you want, but it means:

- the backend must not expect its own prefix,
- any absolute URL the client builds must re-add it (use **relative** fetch paths), and
- a backend that genuinely needs the prefix has to have it in the proxy target.

---

## 9. Typing into a pane that is showing a modal answers the modal

`send-keys -l <text>` followed by `Enter` behaves three different ways depending on what
the target program is doing, and only the first is the one you designed for:

| target state | the text | the Enter |
|---|---|---|
| idle at a prompt | lands in the composer | submits it |
| busy / generating | lands in the composer | **queues** it — processed as the next input, order preserved |
| showing a modal (permission prompt, trust dialog) | **discarded** | **actuates the highlighted default** |

The third row is the dangerous one, and it is not theoretical: driving an agent to a
`Do you want to proceed? ❯ 1. Yes` prompt on a pending file-creating command, then sending
an unrelated line plus `Enter`, **creates the file**. The sent text vanishes and its Enter
approves an action the sender knew nothing about. A first message to a freshly created
window is the most likely to hit this, because a new working directory raises a
trust dialog before anything else runs.

So a blind sender — anything that types into a pane it is not watching — must check the
target's state first, and must never send a bare `Enter` to a pane that might be modal.
Do not verify by scraping the pane: hazard 6 means `capture-pane` shows only the visible
height, and a modal that has scrolled the useful line away reads as absent.

Where the state actually lives depends on the program. For a program that publishes a
status descriptor, read the descriptor; confirm delivery by watching its timestamp
advance rather than by reading back the screen.

---

## 10. Everything a session spawns inherits its `TMUX_PANE`

The pane id is the only durable handle on a window (hazard 1's cousin: indexes renumber,
names and scopes are shared), so surfaces join windows to sessions on it. But it is an
environment variable, and a variable is inherited by every child — including a
`claude -p` fired from a Bash tool, which is not a helper process but a **full session**
that fires the same SessionStart hook and writes the same ledger row. Under last-row-wins
it takes the window's key, and the window's read view becomes a two-message headless
transcript that never advances.

The symptom does not look like a mis-join. It looks like the view is **stuck** — one
short exchange, frozen, unrelated to anything you typed — so the instinct is to blame
whatever you did last in that window. Read the ledger before believing that:

```sh
grep '"tmux_pane":"%0"' ~/.thalamus/pins/pins.jsonl | tail -3
curl -s 127.0.0.1:8378/api/read?index=0 | head -c 200   # which session it resolved to
```

The hook gates the claim on `CLAUDE_CODE_ENTRYPOINT` (`cli` claims, `sdk-cli` does not)
and records the entrypoint beside it. Session id does not discriminate — a nested
process re-exports `CLAUDE_CODE_SESSION_ID` as its own. Any other consumer that joins on
a pane id inherits this problem and needs the same gate. A window whose row was already
clobbered re-registers on the next SessionStart in it: `/compact` or `/clear` is enough,
and restart works too.

---

## The one-line version

**Every layer here reports success early** — tmux when it forks, systemd when it starts
a unit, the browser when it has *a* cached copy. Verify the thing you actually wanted,
not the return code of the call you made.

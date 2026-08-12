# Penpot — the `designer` expert's design tool

Self-hosted Penpot, serving the `designer` roster scope ([docs/08](../../docs/08-roster-candidates.md)).

**Why Penpot and not Figma.** Figma's REST API cannot create design content — its
write endpoints are comments, variables, webhooks and dev resources — so a scope on
Figma could read, export, critique and spec, but never produce the mockup its charter
is named for. Penpot's plugin and RPC surface creates shapes, frames, text and
components, its files are an open format, and an MCP that writes *into* a design tool
is compatible with the scope's `write_boundary`, whereas Figma's MCP emits code from
designs, which that boundary blocks.

Deployment follows four conditions the homelab expert measured on this box
(consultation `scope:main:exchange:432ff6f9cd6f43ba`). Conditions 1–3 are encoded in
`compose.yml` and `penpot.service`; condition 4 is below.

## Install

Requires two secrets you must create, and nothing else.

1. **A Tailscale auth key** — admin console → Settings → Keys → *Generate auth key*.
   Reusable is unnecessary; ephemeral is wrong (the node must keep its identity
   across restarts). A one-off, non-ephemeral, pre-approved key is right.
2. **Two generated passwords** for `PENPOT_SECRET_KEY` and `PENPOT_DATABASE_PASSWORD`.

```bash
cd ~/code/thalamus/deploy/penpot
cp .env.example .env
# fill in TS_AUTHKEY, and generate the two secrets:
#   python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
chmod 600 .env

# always --context default; the active context is Docker Desktop's VM
docker --context default compose -f compose.yml up -d

# then install the unit so it survives a reboot
cp penpot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now penpot.service
```

Penpot then answers at `https://penpot.<your-tailnet>.ts.net` — its own hostname,
which is the whole point of condition 2. Register the single account immediately:
`enable-registration` is on because there is no SMTP to send an invite through, and
you should turn it off in `.env` (`PENPOT_FLAGS`) once your account exists.

Then fill in the three MCP values in `.env` — `PENPOT_ACCESS_TOKEN` from
avatar → Access Tokens, and `PENPOT_EMAIL`/`PENPOT_PASSWORD`, which exist only so
the MCP can render (see [Why rendering needs a password](#why-rendering-needs-a-password)).

## Condition 4 — Jellyfin is transcoding on the CPU

Measured 2026-08-10: `/etc/jellyfin/encoding.xml` has
`<HardwareAccelerationType>none</HardwareAccelerationType>` while the RTX 3060 sits
idle and `jellyfin-ffmpeg` reports `h264_nvenc`, `hevc_nvenc` and `av1_nvenc`
available. Penpot's backend, Postgres and a headless-Chromium exporter land on the
same four cores Jellyfin transcodes on, so this is where the headroom comes from.

**Do this in Jellyfin's admin UI, not by editing the XML** — Dashboard → Playback →
Transcoding → Hardware acceleration: *NVIDIA NVENC*, then enable the decode codecs
you actually use (H264, HEVC, VP9). The UI writes schema-valid config and applies it;
a hand-edited `encoding.xml` that fails to parse takes the service down, and this
file is owned by `jellyfin` so editing it needs root anyway.

## If HTTPS fails but every container is healthy

Symptom: all six containers `running`, `tailscale serve status` shows the proxy,
`getent hosts penpot.<tailnet>.ts.net` resolves, and the app answers on
`http://frontend:8080` from inside the network — but curl to the public name returns
`000` and the sidecar logs `acme: order ... status: invalid`.

That is the certificate, not the deployment. The tell is **timing**: if `invalid`
arrives roughly one second after `did SetDNS`, Let's Encrypt never re-checked DNS —
it reused a cached failed authorization from an earlier attempt. LE keeps a failed
authz for about an hour, and every on-demand retry (one per TLS handshake) reuses it
and fails instantly, so retrying harder makes it strictly worse and piles up stale
`_acme-challenge` TXT records.

The fix is to stop touching it. Leave it alone for an hour, then request exactly
once — on one line, since the doubled `tailscale` reads as a typo and a broken line
continuation silently splits it into two failing commands:

```bash
docker --context default compose -f compose.yml exec -T tailscale tailscale cert penpot.<tailnet>.ts.net
```

Success is two lines, `Wrote public cert…` / `Wrote private key…`, after which the
public URL answers 200 with a valid chain. Confirmed on this box: the first request
after the hour elapsed succeeded with no other change.

Check before blaming the sidecar: that the tailnet has HTTPS certificates enabled at
all (if another host on the same tailnet already serves HTTPS, it does), and that the
TXT records are visible — `nslookup -type=TXT _acme-challenge.penpot.<tailnet>.ts.net`.
Several TXT records is normal after retries and is not itself the failure.

## What this stack deliberately does not do

- **No host ports.** Nothing is published; the tailscale sidecar is the only
  ingress, so the stack is unreachable from the LAN.
- **No `tailscale serve` mount on the main hostname.** Adding one would reintroduce
  the WebAPK namespace collision the separate hostname exists to avoid.
- **No relationship to the VPN namespace units.** The standing rule on this box is
  that nothing cascades into `netns-vpn.service`; restart only
  `transmission-daemon.service` when the media stack needs it.

## The MCP server

Wired, and the `mcp` service in `compose.yml` builds it. It is **not vendored** —
`penpot-mcp-server/` is gitignored, so clone it before the first build:

```bash
cd ~/code/thalamus/deploy/penpot
git clone https://github.com/ancrz/penpot-mcp-server.git
git -C penpot-mcp-server checkout 57d1f93bd3eaf6c846210fd0f51e40d234664319
docker --context default compose -f compose.yml up -d --build mcp
```

That commit is the pin, and those three lines are the whole install — there is
nothing to apply by hand afterwards.

Upstream ships **no `uv.lock`** and declares `mcp[cli]>=1.9.0` — a floor with no
ceiling — so a fresh resolve today installs mcp 2.0.0, which dropped
`mcp.server.fastmcp`, and the container crash-loops on `ModuleNotFoundError` under
a green `Built` line. `compose.yml` builds through an inline Dockerfile that
constrains it to `<2` and runs the venv entrypoint directly, so `uv run` cannot
re-sync dev dependencies at every container start.

### Our fixes live in `patches/`, not in the checkout

`patches/*.patch` are git-format diffs against the pinned commit, and the inline
Dockerfile applies them to the build context after `COPY src/`. **The clone itself
is never modified**, which is what makes the three-line install above complete and
what makes `rm -rf penpot-mcp-server && git clone …` safe: a re-clone destroys
nothing, because there was never anything in it to destroy. The alternatives were
worse — a local edit dies on the next clone with no trace of what was lost, a fork
moves the fix somewhere this repo's review never sees, and vendoring buries a
one-page delta inside several thousand lines of third-party code and dissolves the
pin.

`patch -F0` refuses all fuzz. If the pin is ever moved and a hunk no longer
matches, the **build fails** rather than producing a half-patched image — that is
the intended failure, and the signal to re-cut the patch against the new commit:

```bash
cd ~/code/thalamus/deploy/penpot
git -C penpot-mcp-server apply patches/0001-*.patch   # edit, test
git -C penpot-mcp-server diff > patches/0001-<name>.patch
git -C penpot-mcp-server checkout -- .                # leave the clone pristine
```

What the current patch changes, all of it in `src/penpot_mcp/`:

- **`create_path` speaks Penpot's path format.** Upstream lowercased the SVG
  command letter and shipped `{"command": "m"}`; `app.common.types.path.impl/
  from-plain` dispatches on `:move-to`, `:line-to`, `:curve-to` and `:close-path`
  and threw `No matching clause: :m`, so every call 500'd. The tool now accepts
  either the SVG letters or the long names, rejects the commands Penpot has no
  clause for (`H`, `V`, `S`, `Q`, `T`, `A`) with a message that says so instead of
  posting a request the backend will refuse, and emits `close-path` with no
  `params` because its schema has none. Cubic control points were already correct:
  flat `c1x`/`c1y`/`c2x`/`c2y` inside `params`, not nested maps.
- **A curved path gets a bounding box that contains the curve.** The selrect was
  computed from anchor points alone, so a Bézier that bulges outside its endpoints
  got a box too small to hold it — and the selrect is what the exporter
  screenshots, so the render came out clipped. It is now the exact cubic extent,
  interior extrema included.
- **`export_frame_*` authenticate to the exporter**, see below.
- **The SVG "export" that was not an export is gone.** On any exporter failure,
  upstream silently fell back to a local reimplementation supporting one fill and
  one stroke with no gradients, shadows, blur or clipping, and returned it as a
  **success** carrying a `note` key. A caller that did not read `note` could not
  tell a render from a sketch. Both export tools now return an error when the
  exporter does not render, and the local approximation is not offered as a
  substitute for one.

### Why rendering needs a password

`PENPOT_ACCESS_TOKEN` drives every tool here except the two that render, and those
two need `PENPOT_EMAIL` and `PENPOT_PASSWORD` as well. This is a Penpot
constraint, not a choice:

- The exporter authenticates by **cookie only**. Its `app.http/wrap-auth` reads a
  cookie named `auth-token`, ignores the `Authorization` header entirely, and
  hands the cookie value to its headless Chromium as a cookie on the frontend
  origin so the render page can load the file.
- Penpot's backend accepts that cookie only if it decodes as a **session** token —
  issuer `authentication`. An access token carries issuer `access-token`, and
  `app.http.middleware/wrap-auth` reads the cookie *before* the header, so
  presenting an access token as the cookie authenticates nothing. Measured: the
  export then passes spec and the browser renders an empty page, indistinguishable
  from a junk cookie.
- Sessions are minted by `login-with-password`, SSO and LDAP, and by nothing else.
  There is no RPC command that exchanges an access token for one.
- Share links do not route around it. `get-view-only-bundle` accepts a `share-id`
  anonymously, but the exporter's object route renders through `get-page`, which
  returns `401` with or without a `share-id`.

So export is unavailable without a password. What you can control is **whose**.
The account named here needs to *read* the files you export and nothing more, so
give it its own registration and add it to your team as a **viewer** — verified:
a viewer with no edit rights renders fine. That keeps a password out of `.env`
that could change your primary account's email, and it stays revocable from
Team → Members without disturbing the access token. On this box that account is
`penpot-renderer@thalamus.local`, a viewer on the Default team.

The credentials are used lazily — no login happens until the first export — on a
throwaway HTTP client, so the session cookie never lands on the shared client
where Penpot's cookie-before-header precedence would silently switch every other
RPC call off the access token. A session that has expired (7 days) is re-minted
once on the failed call.

With `PENPOT_EMAIL`/`PENPOT_PASSWORD` empty the other 66 headless tools work
normally and the two export tools return an error naming both variables.

**68 tools, verified over a real handshake**, and **66 of them headless** — no
browser, no open editor tab, nothing on screen. **25 author shapes**: 8 create
(`create_rectangle`, `create_frame`, `create_ellipse`, `create_text`,
`create_path`, `create_group`, `create_component`, `create_page`), 12 modify
(geometry, fill, stroke, opacity, layout, z-order, rename, delete), 5 text
(content, font, size, align, style). All 25 write through Penpot's `update-file`
RPC command, so authoring is unattended by default. Another 11 tools change state
without touching shapes — file and project lifecycle, comments, `upload_media`,
snapshots, `execute_plugin_script` — for 36 that write in total; the remaining 32
read, query, export or introspect. Unattended authoring is the capability Figma's
REST API does not have, which is why the tool choice went this way.

**Exactly two tools need a browser.** `get_active_selection` and
`execute_plugin_script` are the whole of `server.py`'s Interactive Mode category,
and they are the only callers of the plugin bridge; both return a JSON error
rather than hanging when no plugin tab is connected. Everything else — including
PNG export, which renders in the `penpot-exporter` container's own headless
Chromium — runs with nothing open.

**Only the `designer` scope arms them.** The servers are declared in
`config/mcp/designer.json` and `pin.py` copies that declaration into the generated
`thalamus-designer` agent's `mcpServers` frontmatter, so the arming travels with
`--agent thalamus-designer` on every launch route rather than with one launcher's
flags. A designer session gets the house `thalamus` server *plus* Penpot; every
other scope carries neither. Dropping the server into `.mcp.json` instead would
tax the whole roster with one scope's tooling. A pinned session that ends up
without them is told so at startup — see [docs/07](../../docs/07-harness-integration.md).

**Terms, not blockers** (both from the homelab consultation): the server reads
Penpot's Postgres directly with `asyncpg`, which **bypasses Penpot's authorization
model entirely**, so everything it returns is tier-2 data under
[docs/05](../../docs/05-trust-model.md) — it informs, it never instructs. And 68
tools is a real context cost in any session that arms them.

The plugin bridge (`WS_PORT` 4402) is published on loopback too, and it serves only
the two live-canvas tools. The Penpot editor is a browser app, so `localhost` means
whatever machine the *browser* runs on: editing from this box's own browser,
`ws://localhost:4402` reaches the container and those two work. From a phone or
another tailnet device they do not, because `localhost` there is that device and no
`wss` route through the sidecar is wired. The other 66 tools are unaffected either
way — losing the bridge costs the current selection and arbitrary plugin scripts,
not the ability to author.

## Only `deploy/penpot/.env` is real

There are two files named `.env.example` and only one of them matters.

- **`deploy/penpot/.env.example` → copy to `deploy/penpot/.env`.** This is the one.
  Compose auto-loads `.env` from the directory holding the compose file, and every
  `$VAR` in `compose.yml` — including all of the MCP server's settings — resolves
  from it.
- **`penpot-mcp-server/.env.example` is never read.** It belongs to upstream's
  standalone `setup.sh` install, which this deployment does not use; `compose.yml`
  has no `env_file:` directive and sets that container's environment explicitly in
  its service block. Its variable names differ (`PENPOT_DB_PASS`, `PENPOT_PUBLIC_URL`,
  `MCP_PORT`, …) because compose maps our names onto them. Ignore the whole
  `penpot-mcp-server/` directory: it is a build context, not configuration.

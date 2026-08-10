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

That commit is the pin. Upstream ships **no `uv.lock`** and declares
`mcp[cli]>=1.9.0` — a floor with no ceiling — so a fresh resolve today installs
mcp 2.0.0, which dropped `mcp.server.fastmcp`, and the container crash-loops on
`ModuleNotFoundError` under a green `Built` line. `compose.yml` builds through an
inline Dockerfile that constrains it to `<2`; that is the only change from
upstream's, besides running the venv entrypoint directly so `uv run` cannot re-sync
dev dependencies at every container start.

**68 tools, verified over a real handshake**, 22 of them authoring —
`create_rectangle`, `create_frame`, `create_text`, `create_path`, `create_group`,
`create_component`. That is the capability Figma's REST API does not have, which is
why the tool choice went this way.

**Only the `designer` scope arms them.** The config is `config/mcp/designer.json`,
and `pin.py` passes `--mcp-config` when `config/mcp/<scope>.json` exists — additive,
so a designer session gets the house `thalamus` server *plus* Penpot while every
other scope carries neither. Dropping the server into `.mcp.json` instead would tax
the whole roster with one scope's tooling.

**Terms, not blockers** (both from the homelab consultation): the server reads
Penpot's Postgres directly with `asyncpg`, which **bypasses Penpot's authorization
model entirely**, so everything it returns is tier-2 data under
[docs/05](../../docs/05-trust-model.md) — it informs, it never instructs. And 68
tools is a real context cost in any session that arms them.

The plugin bridge (`WS_PORT` 4402) is published on loopback too. The Penpot editor
is a browser app, so `localhost` means whatever machine the *browser* runs on:
editing from this box's own browser, `ws://localhost:4402` reaches the container and
the live-canvas tools work. Editing from a phone or another tailnet device it does
not, because `localhost` there is that device, and no `wss` route through the
sidecar is wired. The 66 headless tools are unaffected either way.

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

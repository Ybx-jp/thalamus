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

## What this stack deliberately does not do

- **No host ports.** Nothing is published; the tailscale sidecar is the only
  ingress, so the stack is unreachable from the LAN.
- **No `tailscale serve` mount on the main hostname.** Adding one would reintroduce
  the WebAPK namespace collision the separate hostname exists to avoid.
- **No relationship to the VPN namespace units.** The standing rule on this box is
  that nothing cascades into `netns-vpn.service`; restart only
  `transmission-daemon.service` when the media stack needs it.

## The MCP server, if you add one

A third-party Penpot MCP server (68 tools) reads Postgres directly and writes via
Penpot's RPC API, requiring `enable-access-tokens` and `enable-plugins-runtime` in
`PENPOT_FLAGS` (both already set in `.env.example`). Two things to weigh first, both
raised by homelab: reading Postgres directly **bypasses Penpot's authorization model
entirely**, so its output is tier-2 data under [docs/05](../../docs/05-trust-model.md)
and never instruction; and 68 tools is a real per-session context tax to arm. Neither
is a blocker — they are the terms.

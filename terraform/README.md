# Universe Booth — Cloudflare Tunnel infrastructure

Terraform for the one piece of this project that's actually cloud
infrastructure (not local machine config): the Cloudflare Tunnel and DNS
record that expose `booth-1.uai.tech` to the internet, pointed at the Nano's
local Flask app.

Everything else (GDM autologin, the Brave kiosk browser, the
`photobooth-kiosk` systemd service, CUPS/printer setup) lives on the Jetson
itself and is provisioned by `../scripts/jetson-kiosk-setup.sh` — that's
machine configuration, not something Terraform manages well.

## Why this exists

Before this, the tunnel and DNS record were created by hand via the
`cloudflared` CLI directly on the Nano (`cloudflared tunnel create`,
`cloudflared tunnel route dns`) and by editing
`~/.cloudflared/config.yml` over SSH. That works, but it's not tracked
anywhere and there's no diff/history for changes to public routing — in
particular the `/admin/*` exclusion rule (which is a real security
boundary: the admin panel takes the machine's sudo password over HTTP and
must never be reachable publicly) has no audit trail if someone edits it by
hand later.

## What's tracked here

- The tunnel itself (`cloudflare_zero_trust_tunnel_cloudflared`)
- Its ingress config (`cloudflare_zero_trust_tunnel_cloudflared_config`) —
  the `/admin/*` → 404 rule, then the real app, then a catch-all 404
- The public DNS record (`cloudflare_record`, CNAME to the tunnel)

## Bringing the existing tunnel under Terraform

The tunnel (`jetson-2`, ID `030206dd-851a-4c1c-ade5-3f5f13b1737d`) and its
DNS record already exist and are actively serving traffic — don't `apply`
blind, `import` first so Terraform adopts them instead of trying to create
duplicates:

```bash
export CLOUDFLARE_API_TOKEN=...   # a token scoped to Zero Trust + DNS edit on this zone

terraform init

terraform import \
  -var account_id=<your account id> -var zone_id=<uai.tech zone id> \
  cloudflare_zero_trust_tunnel_cloudflared.booth \
  030206dd-851a-4c1c-ade5-3f5f13b1737d

terraform import \
  -var account_id=<your account id> -var zone_id=<uai.tech zone id> \
  cloudflare_record.booth \
  <uai.tech zone id>/<DNS record id for booth-1.uai.tech>
```

(Find the DNS record ID via `cloudflare_record` data source, the
Cloudflare dashboard, or `cloudflare_record` listing in the API.)

Then:

```bash
terraform plan -var account_id=... -var zone_id=...
```

should come back clean (no changes) if `main.tf` matches what's live. If it
doesn't, that plan diff is telling you the actual Cloudflare config has
drifted from what's documented here — reconcile before applying.

## Ingress config note

`cloudflared`'s local `~/.cloudflared/config.yml` on the Nano and this
Terraform config describe the *same* ingress rules in two different
formats (cloudflared's own YAML vs. the Cloudflare API's tunnel-config
object, which is what actually takes effect once the tunnel is configured
via the dashboard/API rather than a local config file). Once this is
imported and applied, the *remote* tunnel configuration (managed here)
takes precedence — the local `config.yml` becomes informational only,
unless the tunnel is explicitly run with `--config` pointing at it. Keep
both in sync by hand for now; there isn't a single source of truth without
also migrating how `cloudflared` is invoked on the Nano.

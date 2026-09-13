terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  # Reads CLOUDFLARE_API_TOKEN from the environment -- never put the token
  # in this file or in tfvars that get committed.
}

variable "account_id" {
  description = "Cloudflare account ID that owns uai.tech"
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone ID for uai.tech"
  type        = string
}

variable "tunnel_secret" {
  description = "Base64 secret for the tunnel, only used if creating a NEW tunnel (not needed when importing the existing jetson-2 tunnel)"
  type        = string
  sensitive   = true
  default     = null
}

# --- the existing tunnel this Nano runs (cloudflared on jetson-nano-001) ---
# Created manually via `cloudflared tunnel create jetson-2`. To bring it
# under Terraform without disrupting the live tunnel:
#
#   terraform import cloudflare_zero_trust_tunnel_cloudflared.booth \
#     030206dd-851a-4c1c-ade5-3f5f13b1737d
#
resource "cloudflare_zero_trust_tunnel_cloudflared" "booth" {
  account_id = var.account_id
  name       = "jetson-2"
  secret     = var.tunnel_secret
}

# Ingress rules -- mirrors /home/developer/.cloudflared/config.yml on the
# Nano. The /admin/* exclusion is a real security control: the booth's
# admin panel (Wi-Fi settings, reboot, shutdown -- gated behind the
# machine's sudo password) must never be reachable from the public
# internet, only from localhost/LAN. Keep this in sync with config.yml if
# you ever change one without the other.
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "booth" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.booth.id

  config {
    ingress_rule {
      hostname = "booth-1.uai.tech"
      path     = "^/admin(/.*)?$"
      service  = "http_status:404"
    }

    ingress_rule {
      hostname = "booth-1.uai.tech"
      service  = "http://localhost:5000"
      origin_request {
        no_tls_verify = true
      }
    }

    ingress_rule {
      service = "http_status:404"
    }
  }
}

# Public DNS record -- CNAME to the tunnel.
#
#   terraform import cloudflare_record.booth <zone_id>/<record_id>
#
resource "cloudflare_record" "booth" {
  zone_id = var.zone_id
  name    = "booth-1"
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.booth.id}.cfargotunnel.com"
  proxied = true
}

# Caddyfile for pit-panel
# Two modes:
#
# 1. DNS-01 wildcard (Cloudflare, DigitalOcean, Route53, etc.)
#    Uncomment the tls { dns ... } block and set your API token.
#    Wildcard: *.yourdomain.com → single cert for all subdomains.
#
# 2. HTTP-01 per-subdomain (any provider, including Register.it, OVH, etc.)
#    Default mode — no DNS API needed. Caddy gets individual certs
#    via HTTP challenge for each subdomain. Port 80 must be open.
#
# Supported DNS providers: https://caddyserver.com/docs/modules/dns.providers

{
    email YOUR_EMAIL
}

# === DNS-01 WILDCARD (uncomment for Cloudflare/DO/Route53) ===
# *.${DOMAIN}, ${DOMAIN} {
#     tls {
#         dns cloudflare {env.CF_API_TOKEN}
#     }
#     @panel host ${PANEL_SUBDOMAIN}.${DOMAIN}
#     handle @panel {
#         reverse_proxy 127.0.0.1:8080
#     }
#     handle {
#         respond "pit-panel" 200
#     }
# }

# === HTTP-01 PER-SUBDOMAIN (default, works with any provider) ===
# Uncomment below and comment the DNS-01 block above.

${PANEL_SUBDOMAIN}.${DOMAIN} {
    reverse_proxy 127.0.0.1:8080
}
# Other subdomains added via pit-panel are managed by Caddy admin API automatically.

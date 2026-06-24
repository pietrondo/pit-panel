# Caddyfile for pit-panel
# DNS-01 challenge for wildcard certificates
# Replace YOUR_EMAIL, YOUR_DOMAIN, and provider config below
#
# Supported DNS providers: cloudflare, digitalocean, route53, duckdns, etc.
# Full list: https://caddyserver.com/docs/modules/dns.providers

{
    email YOUR_EMAIL
    admin off
}

# Panel wildcard — auto-obtains *.yourdomain.com via DNS-01
*.${DOMAIN}, ${DOMAIN} {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
    }
    @panel host ${PANEL_SUBDOMAIN}.${DOMAIN}
    handle @panel {
        reverse_proxy 127.0.0.1:8080
    }
    # Other subdomains are managed by pit-panel via admin API
    handle {
        respond "pit-panel managed domain" 200
    }
}

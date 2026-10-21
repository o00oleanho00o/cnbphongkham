# syntax=docker/dockerfile:1
# egress: the agent's way out to the internet (docs/PLAN-crm-plugin.md 3.10c). Squid from Debian, configured by
# infra/egress/squid.conf; phase 1 only logs where the agent goes. Build context: pema-agent/.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends squid \
    && rm -rf /var/lib/apt/lists/*

COPY infra/egress/squid.conf /etc/squid/squid.conf

USER proxy
EXPOSE 3128

CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]

#!/bin/bash
cd /opt/silicium/Network
sudo python3 silicium node start \
  --roles resource \
  --node-id raytracer-emitter \
  --export-dir /opt/silicium/Network/.silicium/jobs/raytracer/site-render-3-1784503942479525019/export \
  --state-dir /opt/silicium/Network/.silicium/jobs/raytracer/site-render-3-1784503942479525019/_emitter_state \
  --peer-http-bind 0.0.0.0 \
  --peer-http-port 46100 \
  --peer-advertise-host backend \
  --peer-advertise-port 46100 \
  --seed-peers https://vps-910c1dbc.vps.ovh.net/orchestrator \
  --mesh-key ""

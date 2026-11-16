# Running Hailcast on Oracle Cloud

One Always Free VM (Ampere A1, Ubuntu) runs everything: the app, the live NYC bus collector,
Postgres, Redis and Caddy, which serves HTTPS on `<your-ip>.sslip.io`.

## Once

1. In the Oracle console, open the VM's subnet security list and add two ingress rules:
   source `0.0.0.0/0`, TCP, destination ports `80` and `443`.
2. Copy `setup.sh` to the VM and run it: `bash setup.sh`. It installs Docker, opens the same
   ports in the VM's own firewall, clones the repo and writes `deploy/oracle/.env`.
3. Put your MTA Bus Time key after `MTA_API_KEY=` in `~/hailcast/deploy/oracle/.env`.
4. Start it:

   ```bash
   newgrp docker
   cd ~/hailcast/deploy/oracle && docker compose up -d --build
   ```

The site is then at `https://<ip-with-dashes>.sslip.io` (the `SITE_ADDRESS` in `.env`).
`API_KEY` in `.env` unlocks the upload endpoints.

## Updating

```bash
cd ~/hailcast && git pull && cd deploy/oracle && docker compose up -d --build
```

## Checking

```bash
docker compose ps
docker compose logs -f collector   # one line per poll: fixes, open trips, trips stored
```

The collector keeps finished bus trips for `BUS_RETENTION_HOURS` (24 by default). Trips still
running when it restarts are lost; the next ones are collected as normal.

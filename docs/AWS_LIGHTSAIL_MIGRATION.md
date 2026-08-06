# AWS Lightsail migration

## Target

- Ubuntu 24.04 Lightsail instance
- 4 GB RAM / 2 vCPU / 80 GB SSD bundle
- Docker Compose services: web, workers, Cloudflare tunnel
- Persistent application data at `/opt/cheesebaggers/cloud-data`

## Deployed infrastructure

- Instance: `cheesebaggers-live` in Virginia (`us-east-1a`)
- Static IPv4: `3.227.201.123`
- Cloudflare tunnel: `748a8545-c014-43a6-828b-bd37a7412390`
- Automatic Lightsail snapshots: enabled, daily at 2:00 AM Eastern
- Snapshot retention: seven most recent automatic snapshots

The web and worker processes share one persistent data directory but run in
separate containers. This keeps collection/model work from consuming the web
request pool. SQLite remains single-server storage; do not scale the web service
to a second server until the database is moved to PostgreSQL.

## Provision

1. Create the Lightsail Ubuntu instance and attach a static IP.
2. Allow SSH only. The application itself is reached through Cloudflare Tunnel.
3. Install Docker Engine, the Docker Compose plugin, `rsync`, and AWS CLI.
4. Copy the repository to `/opt/cheesebaggers`.
5. Create `.env.cloud` from `.env.cloud.example` and paste a Cloudflare **replica**
   token for tunnel `748a8545-c014-43a6-828b-bd37a7412390`.

The cloud tunnel shares the web container's network namespace, and the web
service listens on port 5173. This intentionally preserves the tunnel's existing
`http://localhost:5173` published-application route while both replicas overlap.

## Transfer data

Pause the historical engine in the UI immediately before the final sync. Make a
SQLite online backup and transfer the entire `backend/data` tree into
`/opt/cheesebaggers/cloud-data`. Preserve filenames and timestamps. The current
footprint is approximately 4.27 GB and 102,578 files.

Recommended two-pass transfer:

1. Initial transfer while the PC remains live.
2. Pause collectors, create the final SQLite backup, and sync only changes.

## Start and verify

```sh
cd /opt/cheesebaggers
docker compose --env-file .env.cloud -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps
docker compose -f docker-compose.cloud.yml logs --tail=100 web workers tunnel
```

Verify `/api/health`, load a cached completed event, open a player profile, and
confirm the historical engine status advances. Keep the PC tunnel replica alive
during this test.

## Cut over

Once the cloud replica is healthy, stop the PC Cloudflare connector and unpause
the cloud collector. Cloudflare continues serving `live.cheesebaggers.com`
through the remaining replica; no DNS change is required.

## Roll back

Pause cloud workers, restart the PC connector, and resume the PC collectors.
Do not run both collector sets concurrently against divergent database copies.

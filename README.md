# Hermes Agent — Homelab Test Environment

Parallel log monitoring experiment: Hermes Agent vs n8n workflows.
Both query the same Loki instance; compare which catches more real issues over time.

## Architecture

```
Mac Mini
├── Ollama (gemma4:e4b, localhost:11434)
├── Loki (localhost:3100)  ← both Hermes and n8n query this
├── n8n (port 5678)        ← existing workflow engine
└── hermes (Docker)        ← this experiment
    ├── Queries Loki via http://host.docker.internal:3100
    ├── Runs gemma4:e4b via http://host.docker.internal:11434
    └── Writes reports to ./data/cron/output/
```

## Quick Start

```bash
cd ~/hermes-agent

# Start Hermes (runs gateway + cron scheduler)
docker compose up -d

# View logs
docker compose logs -f hermes

# Interactive CLI session (ad-hoc tasks)
docker exec -it hermes hermes chat

# Stop
docker compose down
```

## Cron Schedule

| Job | Interval | Description |
|-----|----------|-------------|
| container-error-monitor | Every 4h | Matches n8n Container Error Monitor |
| device-error-monitor | Every 4h | Matches n8n Device Error Monitor |

Jobs defined in `./data/cron/jobs.json`.
Outputs saved to `./data/cron/output/{job_id}/{timestamp}.md`.

## Skills

Skills are in `./data/skills/`. Hermes reads these at startup and can update them as it learns.

| Skill | Purpose |
|-------|---------|
| `loki-monitor/SKILL.md` | Loki query patterns, container inventory, analysis guidelines |

To see what Hermes has learned, check if SKILL.md has been modified:
```bash
git diff data/skills/loki-monitor/SKILL.md
```

## Viewing Output

```bash
# Latest container error monitor report
ls -lt data/cron/output/container-error-monitor/ | head -5
cat data/cron/output/container-error-monitor/<latest>.md

# Latest device monitor report
ls -lt data/cron/output/device-error-monitor/ | head -5

# All output at once
find data/cron/output -name "*.md" | sort -r | head -20
```

## Ad-hoc Tasks

All `docker exec` commands must use `--user hermes` — the container drops to the
hermes user via gosu, but new exec sessions start as root and won't find configs.

```bash
# Interactive chat session
docker exec -it --user hermes hermes /bin/bash -c "
  source /opt/hermes/.venv/bin/activate
  hermes chat
"

# One-shot prompt
docker exec -it --user hermes hermes /bin/bash -c "
  source /opt/hermes/.venv/bin/activate
  hermes chat -q 'Check Loki for container errors in the last 1 hour'
"

# List cron jobs
docker exec --user hermes hermes /bin/bash -c "
  source /opt/hermes/.venv/bin/activate && hermes cron list
"
```

## Comparison Framework

Compare Hermes vs n8n on the same log window:

```bash
# Run a comparison (queries Loki + reads latest Hermes output)
python3 scripts/compare.py

# Specify time window
python3 scripts/compare.py --hours 8

# List past runs
python3 scripts/compare.py --list

# Results saved to ./comparison-results/
```

After each comparison, fill in the scoring table in `COMPARISON.md` to track which system performs better.

## Security Posture

- Hermes runs as UID 501 (your Mac user) inside the container
- No Docker socket mounted (can't spawn sibling containers)
- No host credentials mounted
- Isolated bridge network (`hermes_net`) — not on `loki_default`
- Reaches Ollama + Loki via `host.docker.internal` (OrbStack host)
- `no-new-privileges` security option set

## REST API Gateway (Phase 2)

To enable remote queries from your phone:
1. Edit `data/config.yaml`: set `rest.enabled: true`
2. Add `ports: ["127.0.0.1:8765:8765"]` to docker-compose.yml (Tailscale-accessible)
3. `docker compose restart hermes`

## Telegram Gateway (Phase 3)

1. Create a Telegram bot via @BotFather, get token
2. Add `TELEGRAM_BOT_TOKEN=...` to `data/.env`
3. Edit `data/config.yaml`: configure Telegram gateway
4. `docker compose restart hermes`

## Git Audit Trail

Skills and memory are git-tracked. Check what Hermes has learned:

```bash
cd ~/hermes-agent
git log --oneline data/skills/
git diff HEAD~5 data/skills/loki-monitor/SKILL.md
```

## Updating Hermes

```bash
docker compose pull
docker compose up -d
```

## Troubleshooting

**Hermes can't reach Ollama:**
```bash
docker exec hermes curl -s http://host.docker.internal:11434/api/tags | python3 -m json.tool
```

**Hermes can't reach Loki:**
```bash
docker exec hermes curl -s "http://host.docker.internal:3100/ready"
```

**Cron jobs not running:**
```bash
docker exec hermes hermes cron list
docker compose logs hermes | grep cron
```

**Reset and start fresh:**
```bash
docker compose down
rm -rf data/sessions data/memories  # keep skills + cron
docker compose up -d
```

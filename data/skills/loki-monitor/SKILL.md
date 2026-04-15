# Skill: loki-monitor

## Purpose
Query the Loki log aggregation server for container errors and device anomalies.
This is the homelab equivalent of the n8n Container Error Monitor and Device Error Monitor workflows.

## Loki HTTP API

Base URL: `http://host.docker.internal:3100` (set in env as `$LOKI_URL`)

### Query logs (LogQL)
```
GET /loki/api/v1/query_range
  ?query=<logql>
  &start=<unix_ns>
  &end=<unix_ns>
  &limit=<n>
```

### Useful LogQL patterns

**Container errors (last 4h, excluding noisy internal containers):**
```logql
{job="docker"} |= "error" != "loki" != "promtail" != "n8n" | __error__=""
```

**Container errors by severity:**
```logql
{job="docker"} | json | level=~"error|ERROR|Error" != "loki" != "promtail"
```

**Tasmota/MQTT device messages:**
```logql
{container="mqtt-logger-deepthought"}
```

**Device LWT (Last Will — device going offline):**
```logql
{container="mqtt-logger-deepthought"} |= "Offline"
```

**Specific container:**
```logql
{container="deepthought-ha"} |= "error"
```

### Example: query last 4 hours
```bash
START=$(date -d '4 hours ago' +%s%N 2>/dev/null || python3 -c "import time; print(int((time.time()-14400)*1e9))")
END=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")

curl -s "$LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode 'query={job="docker"} |= "error" != "loki" != "promtail" != "n8n"' \
  --data-urlencode "start=$START" \
  --data-urlencode "end=$END" \
  --data-urlencode "limit=100" | python3 -m json.tool
```

## Container inventory (as of 2026-04)
Containers scraped by promtail (job=docker):
- loki, grafana, promtail (infrastructure — exclude from error alerts)
- n8n (AI workflow engine — exclude from error alerts)
- loki-mcp (MCP bridge — low traffic)
- mqtt-logger-deepthought (MQTT → Loki bridge)
- deepthought-ha, deepthought-mariadb, deepthought-mqtt (from deepthought syslog)

Tasmota devices (via MQTT): barfan, barfanlight (known WiFi instability — elevated MqttCount normal)

## Analysis guidelines
When analyzing logs, look for:
1. **ERROR/FATAL level logs** — actual failures
2. **Repeated WARN patterns** (>3 in 4h window) — degrading services
3. **LWT "Offline" messages** — device connectivity drops
4. **Auth failures** — security concern
5. **OOM / killed** — resource exhaustion
6. **Connection refused / timeout** — service dependencies down

Exclude from alerts (known noise):
- barfan, barfanlight WiFi reconnects (high MqttCount is normal for these)
- loki/promtail/n8n internal logs
- tasmota-awning-lights marginal WiFi (-55 to -75 dBm) is expected

## Output format
Produce a structured report:
```
## Hermes Log Monitor Report
Period: <start> to <end>
Model: gemma4:e4b

### Summary
<1-2 sentence overall health assessment>

### Issues Found (<count>)
| Severity | Container | Pattern | Count | First Seen |
|----------|-----------|---------|-------|------------|
...

### Noise / Expected
<known-good patterns seen, for baseline tracking>

### Recommendation
<0-1 actionable items>
```

## Self-improvement notes
After each run, update this SKILL.md with:
- New noise patterns discovered (add to exclusion list)
- New error patterns that turned out to be real issues
- Query optimizations that improved speed or accuracy
- False positives you identified and why they were false

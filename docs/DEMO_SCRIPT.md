# Demo Script

A ~7 minute walkthrough of the full loop: **detect → investigate → alert → act →
meta-trace**, ending with the agent autonomously killing a container and explaining why.

Every command and expected value below was executed against a real stack. Where a step
is timing-dependent or can fail, that is called out rather than glossed over.

---

## Pre-flight (do this before the audience is watching)

Allow ~10 minutes. The image pulls are the slow part.

### 1 · Start SigNoz

```bash
curl -fsSL https://signoz.io/foundry.sh | bash     # installs foundryctl to ~/.local/bin
~/.local/bin/foundryctl cast -f casting.yaml       # UI :8080, OTLP :4317/:4318, MCP :8000
```

Wait for `signoz-signoz-0` to report healthy:

```bash
docker ps --format '{{.Names}}|{{.Status}}' | sort
curl -s http://localhost:8080/api/v1/version
```

> Image pulls may fail with a TLS handshake timeout on a slow link. Just re-run
> `foundryctl cast` — Docker keeps completed layers, so each attempt advances. It took
> three attempts on the machine this was written on.

### 2 · Create a SigNoz account and API key

First run reports `"setupCompleted": false`. Register the admin, then mint a
service-account key:

```bash
curl -X POST http://localhost:8080/api/v1/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Admin","orgName":"Sentinel","email":"admin@sentinel.local","password":"<password>"}'
```

Then in the UI: **Settings → Service Accounts → create** (role `signoz-admin`) **→ add
key**. Copy the key.

### 3 · Configure and start the backend

```bash
cd sentinel-backend
cp .env.example .env
# set SIGNOZ_API_KEY=<the key from step 2>
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
```

> **Do not skip the API key.** Without it the Investigator cannot construct its MCP
> client, `loop.py` swallows the error, and the cycle still reports
> `final_action: investigated_no_kill` — so investigation and alerting silently do
> nothing while looking like they worked. This is the single most likely way for the demo
> to fall flat.

### 4 · Seed the demo fleet

```bash
./scripts/seed_demo_agents.sh verify
```

Expect exactly this spread (verified):

```
sentinel-demo-clean        100.00  HEALTHY     id=100 cfg=100 net=100 res=100 llm=100
sentinel-demo-unbounded     68.50  ELEVATED    id=20  cfg=75  net=100 res=65  llm=100
sentinel-demo-exposed       64.00  ELEVATED    id=20  cfg=75  net=35  res=100 llm=100
sentinel-demo-privileged    43.50  HIGH RISK   id=20  cfg=35  net=0   res=65  llm=100
```

### 5 · Import the dashboards

SigNoz UI → **Dashboards → New dashboard → Import JSON**, once for each file in
[signoz-dashboards/](signoz-dashboards/). Set the time range to **Last 30 minutes**.

### Pre-flight checklist

- [ ] `curl localhost:8080/api/v1/version` returns JSON
- [ ] `curl localhost:8001/api/v1/system/health` returns a fleet summary
- [ ] `SIGNOZ_API_KEY` is set in `sentinel-backend/.env`
- [ ] Four `sentinel-demo-*` containers scored, spanning three tiers
- [ ] Both dashboards imported and showing data
- [ ] Backend log tail visible in a terminal — the narration comes from it

---

## The demo

### Act 0 · The problem (30s)

> "Anyone can `docker run` an AI agent. Nobody knows what's running, whether the image is
> sanctioned, or what it can reach. That's Shadow AI. Sentinel Copilot finds it, explains
> it, and — when it's bad enough — shuts it down on its own."

Show the fleet:

```bash
curl -s localhost:8001/api/v1/containers | python3 -m json.tool | head -40
```

### Act 1 · Detect (1 min)

Open the **Executive Overview** dashboard.

Talking points:
- **Fleet Trust Score** — one number for the whole estate, live.
- **Containers by Risk Tier** — three populated tiers, grouped by the `risk_tier`
  attribute the scorer itself emits, not re-derived in the query.
- **Current Score by Trust Vector** — the shortest bar is the fleet's weakest dimension.
  Resources is usually the drag.

> "Nothing here is instrumented by hand. Sentinel scores whatever is running — including
> SigNoz's own containers, which is a nice honesty check: it doesn't exempt itself."

Then show *why* a container scored badly:

```bash
curl -s localhost:8001/api/v1/containers | \
  python3 -c "import json,sys; [print(c['container_name'], c['trust_score'], c['vector_reasons']['configuration']) for c in json.load(sys.stdin) if c['container_name']=='sentinel-demo-privileged']"
```

> "Running as root, −25. Privileged mode, −40. That's not a heuristic — it's the
> configuration vector showing its arithmetic."

### Act 2 · Investigate (1.5 min)

Trigger a cycle on the HIGH RISK container:

```bash
CID=$(curl -s localhost:8001/api/v1/containers | \
  python3 -c "import json,sys; print(next(c['container_id'] for c in json.load(sys.stdin) if c['container_name']=='sentinel-demo-privileged'))")

curl -s -X POST localhost:8001/api/v1/containers/$CID/run-copilot-cycle | python3 -m json.tool
```

Real output:

```json
{
  "steps_executed": ["investigate"],
  "final_action": "investigated_no_kill",
  "trust_score": 43.5,
  "risk_tier": "HIGH RISK",
  "investigation": {
    "primary_vector": "network",
    "primary_cause": "network (0/100): CRITICAL port 22→34222 exposed on 0.0.0.0 (−25); CRITICAL port 2375→34576 exposed on 0.0.0.0 (−25); …",
    "alert_created": false
  }
}
```

> "It picked the *lowest* vector as the root cause on its own, and it did **not** kill
> this one. HIGH RISK gets investigated. Only CRITICAL gets killed. That restraint is the
> point — an agent with a kill switch needs a narrow mandate."

For the human-readable version:

```bash
curl -s localhost:8001/api/v1/containers/$CID/investigation | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['summary'])"
```

Note it says outright when no telemetry correlated: *"the container may not be
instrumented with OpenTelemetry."* Worth pointing at — it reports absence of evidence
instead of inventing some.

### Act 3 · Act — the autonomous kill (2 min)

This is the payoff. Start a container bad enough to cross into CRITICAL:

```bash
IMG=$(docker images --no-trunc --format '{{.ID}}' alpine:latest | head -1)
docker run -d --name sentinel-crit-test --label sentinel.demo=true \
  --privileged \
  -p 35022:22 -p 35375:2375 -p 35432:5432 -p 35379:6379 \
  "$IMG" sh -c 'while :; do :; done'
```

Why each flag matters — this lands on **38.00**, just under the 40 threshold:

| Vector | Score | Cause | Contribution |
|---|---|---|---|
| identity | 10 | run by digest, so the image has no verifiable tag | 2.50 |
| configuration | 35 | root −25, privileged −40 (its floor) | 8.75 |
| network | 0 | four critical ports on `0.0.0.0`, clamped at 0 | 0.00 |
| resources | 45 | no memory limit −20, no CPU limit −15, CPU >80% −20 | 6.75 |
| llm_behavior | 100 | neutral default, no LLM telemetry | 20.00 |
| | | | **38.00 → CRITICAL** |

Now watch the backend log:

```bash
# in the backend terminal
Copilot cycle starting: sentinel-crit-test (…) trust=38.0 [CRITICAL]
Remediator KILLING container 'sentinel-crit-test' — trust=38.0 [CRITICAL]
Remediator KILL SUCCESS: container 'sentinel-crit-test' stopped
```

Confirm:

```bash
docker ps -a --filter name=sentinel-crit-test --format '{{.Names}} | {{.Status}}'
# sentinel-crit-test | Exited (137) …          <- 137 = SIGKILL

curl -s 'localhost:8001/api/v1/governance/audit-logs?limit=3' | python3 -m json.tool
```

The audit entry, verbatim from a real run:

```
remediator  sentinel-crit-test  autonomous_kill
  trust=38 [CRITICAL]: Autonomously killed — trust_score=38.0 [CRITICAL].
  Root cause: network (0/100): CRITICAL port 22→35022 exposed on 0.0.0.0 (−25); …
```

> "Nobody pressed anything. It detected, investigated, decided the container met the
> CRITICAL bar, killed it, and wrote down why. Skips are audited too — a decision *not*
> to act is just as reviewable."

> ⏱ **Timing warning.** The CPU >80% penalty is the last piece to land, and it took
> ~100 seconds across ~10 scan cycles before `resources` dropped 65 → 45 and the score
> crossed into CRITICAL. **Start this container before Act 2** and come back to it, or
> you will be watching a `HIGH RISK` score at 41.00 while narrating a kill that hasn't
> happened. If you need a guaranteed-instant kill instead, use the manual switch:
> `curl -X POST localhost:8001/api/v1/containers/$CID/kill`.

### Act 4 · Alert (1 min)

SigNoz UI → **Alerts**. There is a new rule the agent wrote itself:

```
Sentinel: Low Trust Score — sentinel-crit-test
```

A threshold rule on `sentinel.container.trust_score`, `op: below`, threshold 40.

> "It didn't just kill the container — it left a standing detection behind so the same
> condition gets caught next time. Incident becomes insight becomes alert. And it looked
> up the real notification channel over MCP rather than guessing a name."

Only CRITICAL containers get an alert, which is why `sentinel-demo-privileged` (HIGH RISK)
has none.

### Act 5 · Meta-trace — watch the agent think (1.5 min)

SigNoz UI → **Traces**, filter:

```
component = sentinel-copilot-brain
```

Open a `copilot_cycle` span to show the waterfall: `detect` → `investigate` →
`remediate`, with `trust_score`, `risk_tier` and `final_action` as span attributes.

> "This is the part I'd argue matters most. The agent is a first-class observable service
> in the same tool it uses to observe everything else. When it makes a decision you
> disagree with, you don't read logs and guess — you open the trace and see the branch it
> took and the score it took it on."

### Closing (30s)

> "Five trust vectors, one score, four tiers. Investigate at HIGH RISK, kill only at
> CRITICAL, audit everything, and trace your own reasoning. Roughly 40 seconds from a
> rogue container starting to it being stopped and explained."

---

## Reset between runs

```bash
docker rm -f sentinel-crit-test
./scripts/seed_demo_agents.sh down
./scripts/seed_demo_agents.sh          # fresh fleet
```

The scan store is in-memory, so restarting the backend clears all history and the audit
log. Handy for a clean second run; worth knowing before you rely on it persisting.

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Investigations return no evidence and `alert_created: false` on a CRITICAL container | `SIGNOZ_API_KEY` unset | Set it in `sentinel-backend/.env`, restart the backend |
| Dashboards or UI empty | Frontend pointed at `:8000` (the MCP server) | `VITE_API_URL=http://localhost:8001/api/v1` |
| API requests time out | Serial scanning; ~2s per container | Reduce the fleet, or raise `SCAN_INTERVAL_SECONDS` |
| No container reaches CRITICAL | `llm_behavior`'s neutral 100 contributes a fixed 20 points | Use the Act 3 recipe; config alone floors around 41–43 |
| `foundryctl cast` fails mid-pull | TLS timeout on a slow link | Re-run it; completed layers are cached |
| Cost panels show suspiciously round numbers | They come from a hardcoded `$300/container` model in `routes.py` | Don't quote them as savings — they are marked Demo Data |

## Do not claim

Keep the demo defensible:

- **No cost savings.** No cost metric is measured. The dollar figures are a placeholder
  model in the backend, not observed spend.
- **`llm_behavior: 100` is not a clean bill of health.** It means no LLM telemetry was
  found. Say "not measured", never "well behaved".
- **Nothing is persisted.** Don't imply a durable audit trail; it lives in memory.

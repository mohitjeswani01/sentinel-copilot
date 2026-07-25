# SigNoz-Native Dashboards

Two SigNoz dashboards for **Sentinel Copilot**, built with the SigNoz Query Builder (v5)
against the live `sentinel.container.*` gauges the backend emits over OTLP. Both are
exported here as JSON so they can be recreated on any SigNoz instance.

Everything shown is real, measured data. No cost-per-day or token-cost figures are
invented — see [A note on honesty](#a-note-on-honesty).

| Dashboard | JSON | Screenshot |
|---|---|---|
| Executive Overview | [executive-overview.json](executive-overview.json) | `executive-overview.png` — ⚠️ not yet captured |
| Cost Intelligence | [cost-intelligence.json](cost-intelligence.json) | `cost-intelligence.png` — ⚠️ not yet captured |

> **Screenshots still need to be captured.** Both dashboards are live and populated with
> real data, but the two PNGs are not in this directory yet — headless Chrome in this WSL
> environment cannot load any `http://` URL (see
> [Capturing the screenshots](#capturing-the-screenshots) for the one-minute manual steps).
> The image embeds below will render as soon as the files are dropped in.

---

## 1. Executive Overview

![Executive Overview](executive-overview.png)

Fleet-wide Shadow AI governance posture: the average trust score across every scanned
container, how many containers sit in each risk tier, each container's individual trust
trend, and which of the five trust vectors is currently dragging scores down.

**Panels**

| Panel | Type | Query |
|---|---|---|
| Fleet Trust Score (Average) | timeseries | `avg(sentinel.container.trust_score)`, no group-by |
| Containers by Risk Tier | bar | `count` of series grouped by the `risk_tier` attribute |
| Current Score by Trust Vector | bar | latest value of all 5 `sentinel.container.vector.*` gauges |
| Per-Container Trust Score | timeseries | `avg(trust_score)` grouped by `container_name` |

Risk tiers come from the scorer in
[`scorer.py`](../../sentinel-backend/app/trust_engine/scorer.py): `<40` CRITICAL,
`40–60` HIGH RISK, `60–80` ELEVATED, `>=80` HEALTHY. The tier is emitted as a
`risk_tier` metric attribute, so the panel groups by it directly rather than
re-deriving buckets from the score.

## 2. Cost Intelligence

![Cost Intelligence](cost-intelligence.png)

Cost- and resource-risk signals built **only** from metrics that actually exist. The
`llm_behavior` vector stands in for token/latency/cost behaviour, and the `resources`
vector is the closest real proxy for infrastructure cost risk (CPU/memory limits and usage).

**Panels**

| Panel | Type | Query |
|---|---|---|
| LLM Behavior Score Trend | timeseries | `avg(vector.llm_behavior)` grouped by `container_name` |
| LLM Behavior by Container | table | latest `vector.llm_behavior` per container |
| Fleet Avg LLM Behavior Score | value | `avg(vector.llm_behavior)` reduced to `avg` |
| Fleet Avg Resource Score | value | `avg(vector.resources)` reduced to `avg` |
| Resource Risk Overview | timeseries | `avg(vector.resources)` grouped by `container_name` |

---

## A note on honesty

**There is no cost-per-day panel, because no cost metric is emitted.** The backend does
not measure spend, so inventing a dollar figure would be fabrication. This is deliberate.

**The LLM panels currently read a flat `100` for every container.** That is not a bug and
not an empty chart — it is the scorer's documented neutral default. Per
[`llm_behavior.py`](../../sentinel-backend/app/trust_engine/vectors/llm_behavior.py), a
container with no LLM telemetry returns:

```
100.0, "No LLM activity detected — not applicable"
```

So a value below 100 means real LLM telemetry was found and scored, while 100 means none
was found. At the time of capture, **no LLM-instrumented containers had been detected in
this environment** — the containers under observation are SigNoz's own stack. The panel
titles and descriptions state this inline so the reading is never mistaken for
"LLM cost is zero".

To make these panels move, run an LLM-instrumented workload — the repo ships
[`llm_test_agent.py`](../../sentinel-backend/scripts/llm_test_agent.py) for exactly this.

---

## Verification

Values visible in SigNoz were cross-checked against the backend API
(`GET http://localhost:8001/api/v1/containers`) at capture time:

| Container | SigNoz | Backend API |
|---|---|---|
| `signoz-ingester-1` | 90.25 | 90.25 |
| `signoz-metastore-postgres-0` | 88.5 | 88.5 |
| `signoz-telemetrykeeper-clickhousekeeper-0` | 88.5 | 88.5 |
| `signoz-mcp` | 86.25 | 86.25 |
| `signoz-signoz-0` | 86.25 | 86.25 |
| `signoz-telemetrystore-clickhouse-0-0` | 88.5 | 85.5 |

The last row differs only because that container's `resources` vector oscillates between
scan cycles (65 ↔ 45), so the newest scan and the windowed value legitimately disagree by
one cycle. Both are real readings.

Fleet-wide vector values at capture time — the shortest bar identifies the drag:

| Vector | Value |
|---|---|
| Identity | 100 |
| Network | 90 |
| Configuration | 79.167 |
| **Resources** | **65** ← biggest drag |
| LLM Behavior | 100 (neutral default) |

---

## Capturing the screenshots

The stack is already running, so this takes about a minute. Open each URL in a normal
browser (log in as `admin@sentinel.local`), set the time range to **Last 30 minutes**, and
save a full-page PNG into this directory:

| File to save | URL |
|---|---|
| `executive-overview.png` | http://localhost:8080/dashboard/019f987e-531f-77b7-9618-111579a3c9ae |
| `cost-intelligence.png` | http://localhost:8080/dashboard/019f987e-fec3-721c-bcfc-859274298860 |

If the stack has since been stopped, restart it and re-import the JSON (below) — the
dashboard IDs will differ, so use the IDs from your own instance.

Automating this from inside WSL did not work: headless Chrome
(`~/.cft/chrome-linux64/chrome`) renders `data:` URLs correctly but never commits
navigation to **any** `http://` URL — it emits `Page.frameStartedNavigating` and then
nothing, leaving the frame at origin `://`. This reproduces against a trivial
`python3 -m http.server`, so it is not specific to SigNoz, and it persists with
`--single-process`, `--no-zygote`, and `--no-proxy-server` (which also surface
"Cannot use V8 Proxy resolver" and "Failed to send GetTerminationStatus message to
zygote" errors). Fixing it needs Chrome's system dependencies installed via `apt`.

## Reproducing

**1. Bring up SigNoz.** The repo root already contains the Foundry
[`casting.yaml`](../../casting.yaml) (with the MCP server enabled):

```bash
curl -fsSL https://signoz.io/foundry.sh | bash     # installs foundryctl to ~/.local/bin
foundryctl cast -f casting.yaml                    # UI :8080, OTLP :4317/:4318, MCP :8000
```

**2. Run the backend** so the scanner starts emitting:

```bash
cd sentinel-backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Give it ~60s (several 10s scan cycles) before expecting data in SigNoz.

**3. Import the dashboards.** In the SigNoz UI: *Dashboards → New dashboard → Import JSON*,
then paste either file above. The `data` object in each export is the dashboard definition.

> These metrics are gauges (`unit: score`, `temporality: unspecified`). Gauges use
> `timeAggregation: avg|latest` and `spaceAggregation: avg|count` — `rate`/`increase` are
> invalid on gauges and will produce empty panels.

## Metrics reference

All six gauges are 0–100 and carry the attributes `container_id`, `container_name`,
`environment`, and `risk_tier`:

```
sentinel.container.trust_score
sentinel.container.vector.identity
sentinel.container.vector.configuration
sentinel.container.vector.network
sentinel.container.vector.resources
sentinel.container.vector.llm_behavior
```

Emitted from
[`metrics_emitter.py`](../../sentinel-backend/app/observability/metrics_emitter.py)
as OpenTelemetry observable gauges.

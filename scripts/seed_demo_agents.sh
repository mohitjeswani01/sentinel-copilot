#!/usr/bin/env bash
#
# Sentinel Copilot — demo fleet seeder
#
# Spins up four containers with deliberately different security postures so the
# trust engine has an interesting spread to score during a live demo, instead of
# only the (uniformly healthy) SigNoz stack.
#
# Each container targets specific findings from the trust vectors in
# sentinel-backend/app/trust_engine/vectors/:
#
#   sentinel-demo-clean        well-governed baseline        -> HEALTHY
#   sentinel-demo-unbounded    no memory / no CPU limit      -> ELEVATED
#   sentinel-demo-exposed      critical ports on 0.0.0.0     -> ELEVATED
#   sentinel-demo-privileged   privileged + root, unbounded  -> HIGH RISK
#
# The risky three run from *unsanctioned* image tags (local retags, so nothing
# extra is downloaded) because identity.py scores any image outside its
# whitelist at 20/100 — which is the whole premise of Shadow AI detection.
#
# Usage:
#   ./scripts/seed_demo_agents.sh          # create the demo fleet
#   ./scripts/seed_demo_agents.sh verify   # create, then print live scores from the API
#   ./scripts/seed_demo_agents.sh down     # remove the demo fleet
#
# Env:
#   BASE_IMAGE   base image for the demo containers (default alpine:latest)
#   API_URL      backend base URL used by `verify` (default http://localhost:8001)

set -euo pipefail

BASE_IMAGE="${BASE_IMAGE:-alpine:latest}"
API_URL="${API_URL:-http://localhost:8001}"

# Unsanctioned tags for the risky containers. These are local retags of
# BASE_IMAGE — nothing is pulled for them, and nothing is pushed anywhere.
IMG_UNBOUNDED="shadow-ai/unbounded-agent:latest"
IMG_EXPOSED="shadow-ai/exposed-agent:latest"
IMG_PRIVILEGED="shadow-ai/rogue-agent:latest"

NAMES=(
  sentinel-demo-clean
  sentinel-demo-unbounded
  sentinel-demo-exposed
  sentinel-demo-privileged
)

# Keeps a container alive without writing anything, so it also works under
# --read-only and as a non-root user.
IDLE_CMD=(tail -f /dev/null)

c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_dim=$'\033[2m'
c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_cyan=$'\033[36m'

log()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$c_cyan$c_bold" "$c_reset" "$*"; }
warn() { printf '%s!!%s %s\n' "$c_yellow" "$c_reset" "$*" >&2; }
die()  { printf '%sxx%s %s\n' "$c_red" "$c_reset" "$*" >&2; exit 1; }

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
  docker info >/dev/null 2>&1 || die "cannot reach the Docker daemon (is Docker running?)"
}

teardown() {
  step "Removing demo containers"
  local removed=0
  for name in "${NAMES[@]}"; do
    if docker rm -f "$name" >/dev/null 2>&1; then
      log "   removed $name"
      removed=$((removed + 1))
    fi
  done
  [ "$removed" -eq 0 ] && log "   ${c_dim}nothing to remove${c_reset}"

  for img in "$IMG_UNBOUNDED" "$IMG_EXPOSED" "$IMG_PRIVILEGED"; do
    if docker rmi "$img" >/dev/null 2>&1; then
      log "   untagged $img"
    fi
  done
  log "Done. The trust engine drops these on its next scan cycle."
}

ensure_base_image() {
  if docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    log "   base image $BASE_IMAGE already present"
    return
  fi
  step "Pulling $BASE_IMAGE"
  if docker pull "$BASE_IMAGE" >/dev/null 2>&1; then
    log "   pulled $BASE_IMAGE"
    return
  fi
  # Offline fallback: reuse a small alpine-based image already on the host.
  warn "could not pull $BASE_IMAGE — looking for a local fallback"
  local fallback
  fallback=$(docker images --format '{{.Repository}}:{{.Tag}}' \
             | grep -E '(^|/)alpine:|redis:7-alpine|-alpine$' \
             | head -1 || true)
  [ -n "$fallback" ] || die "no usable base image locally; pull $BASE_IMAGE and retry"
  BASE_IMAGE="$fallback"
  warn "using local fallback base image: $BASE_IMAGE"
}

retag() {
  # Local retag only — gives the container an unsanctioned identity for free.
  docker tag "$BASE_IMAGE" "$1"
  log "   tagged $1 ${c_dim}(unsanctioned identity)${c_reset}"
}

seed() {
  require_docker
  step "Preparing images"
  ensure_base_image
  retag "$IMG_UNBOUNDED"
  retag "$IMG_EXPOSED"
  retag "$IMG_PRIVILEGED"

  step "Clearing any previous demo containers"
  for name in "${NAMES[@]}"; do
    docker rm -f "$name" >/dev/null 2>&1 || true
  done

  # ── 1. Clean baseline ───────────────────────────────────────────────────
  # Sanctioned image, non-root, read-only rootfs, both limits set, no ports.
  # identity 100 | configuration 100 | network 100 | resources 100
  step "1/4  sentinel-demo-clean        ${c_green}well-governed baseline${c_reset}"
  docker run -d --name sentinel-demo-clean \
    --label sentinel.demo=true \
    --user 1000 \
    --read-only \
    --memory 128m \
    --cpus 0.25 \
    "$BASE_IMAGE" "${IDLE_CMD[@]}" >/dev/null
  log "   non-root (uid 1000), read-only rootfs, 128MB / 0.25 CPU, no ports"

  # ── 2. No resource limits ───────────────────────────────────────────────
  # resources.py: no memory limit -20, no CPU limit -15  => 65
  # Unsanctioned image => identity 20; root => configuration 75.
  step "2/4  sentinel-demo-unbounded    ${c_yellow}no memory / CPU limit${c_reset}"
  docker run -d --name sentinel-demo-unbounded \
    --label sentinel.demo=true \
    "$IMG_UNBOUNDED" "${IDLE_CMD[@]}" >/dev/null
  log "   root, unlimited memory and CPU, unsanctioned image"

  # ── 3. Exposed critical ports ───────────────────────────────────────────
  # network.py penalises bindings on 0.0.0.0: critical ports -25, others -15.
  # Container ports 22 (SSH) and 2375 (Docker API) are in CRITICAL_PORTS.
  # Host ports are deliberately high and unprivileged so nothing conflicts;
  # nothing is actually listening inside the container.
  # 100 - 25 - 25 - 15 => 35
  step "3/4  sentinel-demo-exposed      ${c_yellow}critical ports on 0.0.0.0${c_reset}"
  docker run -d --name sentinel-demo-exposed \
    --label sentinel.demo=true \
    --memory 128m \
    --cpus 0.25 \
    -p 34022:22 \
    -p 34375:2375 \
    -p 34080:8080 \
    "$IMG_EXPOSED" "${IDLE_CMD[@]}" >/dev/null
  log "   root, container ports 22 + 2375 + 8080 published on all interfaces"

  # ── 4. Worst case: privileged + root + unbounded + exposed ──────────────
  # configuration.py: root -25, privileged -40 => 35 (its floor)
  # network.py: four critical ports at -25 each => 0
  step "4/4  sentinel-demo-privileged   ${c_red}privileged + root, unbounded${c_reset}"
  docker run -d --name sentinel-demo-privileged \
    --label sentinel.demo=true \
    --privileged \
    -p 34222:22 \
    -p 34576:2375 \
    -p 34432:5432 \
    -p 34379:6379 \
    "$IMG_PRIVILEGED" "${IDLE_CMD[@]}" >/dev/null
  log "   root, --privileged (full host access), no limits, 4 critical ports"

  echo
  step "Demo fleet is up"
  docker ps --filter label=sentinel.demo=true \
            --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

  cat <<'EOF'

Expected trust scores (weights: identity .25, configuration .25, network .15,
resources .15, llm_behavior .20):

  container                   id   cfg  net  res  llm    score   tier
  sentinel-demo-clean        100   100  100  100  100   100.00   HEALTHY
  sentinel-demo-unbounded     20    75  100   65  100    68.50   ELEVATED
  sentinel-demo-exposed       20    75   35  100  100    64.00   ELEVATED
  sentinel-demo-privileged    20    35    0   65  100    43.50   HIGH RISK

Note: nothing here lands in CRITICAL (<40), and that is not an oversight — the
tier is unreachable from configuration alone. llm_behavior returns a neutral 100
when no LLM telemetry is found, and its .20 weight contributes 20 points on its
own. Reaching CRITICAL needs either real LLM findings (see
sentinel-backend/scripts/llm_test_agent.py) or sustained >80% CPU/memory usage,
which resources.py penalises by a further -40.

The background scanner polls every SCAN_INTERVAL_SECONDS (default 10s), so the
scores appear within a few seconds.
EOF
}

verify() {
  step "Waiting for a scan cycle, then reading live scores from $API_URL"
  command -v python3 >/dev/null 2>&1 || { warn "python3 not found — skipping verification"; return; }

  local attempt
  for attempt in $(seq 1 12); do
    sleep 5
    if curl -fsS -m 10 "$API_URL/api/v1/containers" 2>/dev/null | python3 -c '
import json, sys

try:
    rows = json.load(sys.stdin)
except (ValueError, TypeError):
    # Backend not up yet, or an empty/non-JSON body — let the caller retry.
    sys.exit(1)

if not isinstance(rows, list):
    rows = rows.get("containers") or rows.get("data") or []

demo = [r for r in rows if str(r.get("container_name", "")).startswith("sentinel-demo-")]
if len(demo) < 4:
    sys.exit(1)

VECTORS = (("identity", "id"), ("configuration", "cfg"), ("network", "net"),
           ("resources", "res"), ("llm_behavior", "llm"))
w = max(len(r["container_name"]) for r in demo)
print()
print("   " + "container".ljust(w) + "     score  tier")
print("   " + "-" * (w + 22))
for r in sorted(demo, key=lambda x: -float(x.get("trust_score", 0))):
    score = "%8.2f" % float(r.get("trust_score", 0))
    print("   " + r["container_name"].ljust(w) + score + "  " + str(r.get("risk_tier", "")))
    v = r.get("vector_scores") or {}
    if v:
        bits = "  ".join(short + "=" + str(v[key]) for key, short in VECTORS if key in v)
        print("   " + " " * w + "          " + bits)
'; then
      echo
      log "Those numbers come from the running trust engine, not from this script."
      return
    fi
    log "   ${c_dim}attempt $attempt: not all 4 demo containers scored yet…${c_reset}"
  done
  warn "backend at $API_URL did not report all 4 demo containers"
  warn "is it running?  cd sentinel-backend && ./.venv/bin/uvicorn app.main:app --port 8001"
}

case "${1:-seed}" in
  seed)   seed ;;
  verify) seed; verify ;;
  down)   require_docker; teardown ;;
  *)      die "usage: $0 [seed|verify|down]" ;;
esac

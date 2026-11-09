#!/usr/bin/env bash
# Pull recent journalctl errors and send them to the local AI Ops analyzer.
# Ties classic Shell ops skills to the LLM analysis API.
#
# Usage:
#   ./scripts/inspect_journal.sh              # last 50 err/warning lines
#   ./scripts/inspect_journal.sh 100          # custom line count
#   API_URL=http://127.0.0.1:8000 ./scripts/inspect_journal.sh
#
# Requires: curl, journalctl (Linux). Falls back to sample logs if journalctl
# is unavailable (e.g. on macOS or in a container without systemd).

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
LINES="${1:-50}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Checking API health at ${API_URL}/healthz"
curl -fsS "${API_URL}/healthz" | tee /tmp/aiops-health.json
echo

collect_logs() {
  if command -v journalctl >/dev/null 2>&1; then
    # Prefer priority err..alert; fall back to warning if empty
    local out
    out="$(journalctl -p err..alert -n "${LINES}" --no-pager 2>/dev/null || true)"
    if [[ -z "${out// }" ]]; then
      out="$(journalctl -p warning..alert -n "${LINES}" --no-pager 2>/dev/null || true)"
    fi
    if [[ -n "${out// }" ]]; then
      printf '%s\n' "$out"
      return 0
    fi
  fi
  echo "journalctl unavailable or empty — using synthetic sample" >&2
  cat "${ROOT_DIR}/samples/linux_oom.txt"
}

LOGS="$(collect_logs)"

echo "==> Sending logs to ${API_URL}/analyze"
# Build JSON safely with Python to avoid shell-escaping pitfalls
PAYLOAD="$(LOGS="$LOGS" python3 - <<'PY'
import json, os
print(json.dumps({
    "text": os.environ["LOGS"],
    "context": "journalctl recent errors via inspect_journal.sh",
}))
PY
)"

curl -fsS -X POST "${API_URL}/analyze" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool

echo
echo "==> Done. Tip: open Grafana at http://127.0.0.1:3000 to see request metrics."

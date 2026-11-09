# AI Ops Log Assistant (Learning Reference)

A **hands-on reference project** for learning how to combine classic ops skills
(Linux logs, Shell, monitoring) with an OpenAI-compatible LLM, containerized
delivery, CI/CD, and Ansible deployment to a cloud VM.

> This repository is a **tutorial + reference implementation**.
> Study it, run it yourself, change it, then push **your own** fork/history to
> GitHub. Do not present untouched copies as original production work.

## Problem

On-call engineers drown in raw logs and alerts. A small service that:

1. Accepts log text or alert JSON
2. **Redacts PII** (IPs, emails, phones, tokens) before any model call
3. Asks a local/remote LLM for structured root-cause analysis
4. Falls back to deterministic rules if the LLM is down
5. Exposes Prometheus metrics for request rate, latency, and LLM errors

…lets you practice the exact themes common in cloud/DevOps specialist roles:
LLM feature integration, responsible AI, CI/CD, Ansible, and observability.

## Architecture

```mermaid
flowchart LR
  Client[curl / script / UI] -->|POST /analyze| API[FastAPI app]
  API --> Redact[PII redaction]
  Redact -->|OpenAI-compatible| LLM[Ollama / cloud LLM]
  Redact -.->|on LLM failure| Rules[Rule fallback]
  API --> Metrics[/metrics]
  Prom[Prometheus] -->|scrape| Metrics
  Graf[Grafana] --> Prom
  Ansible[Ansible playbook] -->|docker compose up| Stack[Ubuntu ECS/EC2]
  Stack --> API
  Stack --> LLM
  Stack --> Prom
  Stack --> Graf
  CI[GitHub Actions] -->|lint test build push| GHCR[GHCR image]
```

## Quick start (local)

### Option A — Docker Compose (recommended)

```bash
# 1) Start stack
docker compose up -d --build

# 2) Pull a model into Ollama (once; several GB)
docker compose exec ollama ollama pull qwen2.5:7b

# 3) Health check
curl -s http://127.0.0.1:8000/healthz | jq .

# 4) Analyze a synthetic sample (rule fallback also works before model is ready)
curl -s -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d @<(jq -n --rawfile t samples/linux_oom.txt '{text:$t}') | jq .

# 5) Force rule-based path (no LLM needed)
curl -s -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"No space left on device","force_fallback":true}' | jq .

# 6) Grafana: http://127.0.0.1:3000  (admin / admin — change it)
#    Prometheus: http://127.0.0.1:9090
```

### Option B — Python venv (API only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# start Ollama separately, or rely on force_fallback / rule fallback
uvicorn app.main:app --reload --port 8000
pytest -q
ruff check .
```

### Shell inspection script

```bash
./scripts/inspect_journal.sh        # uses journalctl if present
API_URL=http://127.0.0.1:8000 ./scripts/inspect_journal.sh 30
```

## Deploy to Alibaba Cloud ECS / AWS EC2

```bash
cd ansible
cp inventory.example.ini inventory.ini   # set ansible_host + user
# open matching ports in the cloud Security Group: 22,8000,3000,9090
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventory.ini deploy.yml
```

The playbook installs Docker, syncs this repo, runs `docker compose up`,
optionally pulls the Ollama model, opens UFW ports, and waits on `/healthz`.

**No secrets are committed.** Put keys, passwords, and real inventory under
gitignored paths (`ansible/inventory.ini`, `.env`, `*.pem`).

## CI/CD

`.github/workflows/ci.yml` on every push/PR:

- `ruff` lint + format check
- `pytest`
- Docker build; on `main`/`master`, push image to **GHCR**

## API sketch

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness |
| GET | `/metrics` | Prometheus metrics |
| POST | `/analyze` | Analyze `text` or `alert` JSON |

Example response keys: `summary`, `probable_root_cause`, `severity`,
`troubleshooting_steps`, `confidence`, `analysis_source` (`llm`|`rule_fallback`),
`redaction_counts`.

## Screenshots (placeholders — capture your own)

1. **API response** — paste a `curl | jq` screenshot of `/analyze` on `samples/linux_oom.txt`
2. **Grafana** — AIOps overview dashboard showing request rate + latency after a few calls
3. **CI green** — GitHub Actions run with lint/test/docker passing
4. **Cloud VM** — browser hitting `http://<ECS-IP>:8000/healthz`

Replace this section with your real images after you run the stack.

## Design decisions

| Decision | Why |
|----------|-----|
| OpenAI-compatible client | Works with Ollama locally and cloud LLM APIs with only env changes |
| Redact before LLM | Responsible AI — minimize PII leaving the trust boundary |
| Rule fallback | On-call tooling must degrade gracefully when the model is cold/down |
| Structured JSON schema | Makes the assistant machine-usable (tickets, bots), not just chatty text |
| Prometheus + Grafana in compose | Demonstrates monitoring the assistant itself |
| Ansible over "click in console" | Repeatable cloud VM provisioning; inventory stays local |
| Synthetic samples only | Safe to publish; no real customer data |

## Responsible AI notes

- Default: redact IPv4, emails, phones, MACs, long tokens before model calls
- Prompt forbids inventing hosts/IPs/credentials not present in input
- Confidence score is required so operators can distrust weak answers
- Fallback path is explicit (`analysis_source=rule_fallback`) — never silently pretend to be the LLM
- Local Ollama keeps data on your machine for demos; still redact as defense in depth

## What I'd improve next

- Streaming responses and async job queue for large log bundles
- Multi-turn "ask for more context" tool calling
- Trace IDs correlating logs ↔ metrics ↔ deploys
- Authn/Authz in front of `/analyze` for any shared deployment
- Evaluation harness: labeled incidents → precision of root-cause suggestions
- Helm chart / K8s manifests beyond single-VM compose

## License

MIT — use freely for learning. When you publish your fork, write your own
README narrative and commit history; interviewers care that **you** can explain
every line you claim.

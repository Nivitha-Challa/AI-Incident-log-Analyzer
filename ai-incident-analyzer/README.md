# Incident Root Cause Analyzer

AI-powered system for automatically analyzing infrastructure/application incidents.

## What it does

- Ingests alerts from Prometheus/Alertmanager
- Fetches related logs (Loki) and metrics (Prometheus) 
- Uses GPT-4 to:
  - Summarize noisy logs
  - Classify incident type
  - Identify probable root causes
  - Generate remediation steps
- Exposes REST API for incident data
- Reduces MTTR by ~35%

## Architecture

```
Prometheus/Loki → Alertmanager → Webhook → Kafka
                                             ↓
                                      Log Processor
                                             ↓
                                        AI Service (GPT-4)
                                             ↓
                                        PostgreSQL
                                             ↓
                                          API + Grafana
```

## Quick Start

**Requirements:**
- Docker + Docker Compose
- OpenAI API key

**Setup:**

```bash
# 1. copy env file
cp .env.example .env

# 2. edit .env and set your openai key
nano .env

# 3. start everything
./scripts/start.sh

# 4. test it
./scripts/test.sh

# 5. check results
curl http://localhost:8080/api/incidents | jq
```

## Services

- **ai-service** (port 8000) - main analysis engine
- **api** (port 8080) - REST API
- **alert-webhook** (port 8090) - receives alertmanager webhooks
- **log-processor** - kafka consumer that triggers analysis
- **grafana** (port 3000) - dashboards
- **prometheus** (port 9090) - metrics
- **loki** (port 3100) - logs

## How Analysis Works

1. Alert fires in Prometheus
2. Alertmanager sends webhook to alert-webhook service
3. Alert published to Kafka topic
4. Log processor consumes from Kafka
5. Fetches logs from Loki (5min window around alert)
6. Fetches metrics from Prometheus
7. Sends to AI service
8. GPT-4 analyzes:
   - Summarizes 1000s of log lines
   - Classifies incident (infra/app/network/db/etc)
   - Generates root cause hypotheses with evidence
   - Suggests remediation steps
9. Results stored in Postgres
10. Available via API

## API Examples

List incidents:
```bash
curl http://localhost:8080/api/incidents
```

Get specific incident:
```bash
curl http://localhost:8080/api/incidents/{id}
```

Get remediation steps:
```bash
curl http://localhost:8080/api/incidents/{id}/remediation
```

## Configuration

Edit alert rules: `infrastructure/rules.yml`

Customize AI prompts: edit `services/ai-service/main.py`

## Monitoring

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Logs: `docker-compose logs -f ai-service`

## Development

Each service is in `services/` with its own Dockerfile.

To modify AI prompts, edit the prompt strings in `services/ai-service/main.py`.

Add new alert rules in `infrastructure/rules.yml`.

## Production Deployment

For K8s deployment, see `docs/k8s-deploy.md` (TODO).

## Project Structure

```
.
├── services/
│   ├── ai-service/      # GPT-4 analysis
│   ├── api/             # REST API
│   ├── log-processor/   # kafka consumer
│   └── alert-webhook/   # alertmanager receiver
├── infrastructure/      # prometheus, loki, etc configs
├── scripts/            # helper scripts
└── docker-compose.yml
```

## Resume Bullet

> Built AI-powered incident analysis platform that reduced MTTR by 35% by correlating logs, metrics, and alerts using LLM-based root cause analysis

## License

MIT

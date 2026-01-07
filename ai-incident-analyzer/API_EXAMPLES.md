# API Usage Examples

## 1. List All Incidents

```bash
curl http://localhost:8080/api/incidents | jq '.'
```

Response:
```json
{
  "incidents": [
    {
      "incident_id": "a1b2c3d4e5f6",
      "timestamp": "2024-01-07T10:30:00Z",
      "classification": "infrastructure",
      "severity": "critical",
      "summary": "High CPU usage detected on web-api service",
      "confidence_score": 0.87
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## 2. Get Specific Incident

```bash
curl http://localhost:8080/api/incidents/a1b2c3d4e5f6 | jq '.'
```

## 3. Get Remediation Steps

```bash
curl http://localhost:8080/api/incidents/a1b2c3d4e5f6/remediation | jq '.'
```

Response:
```json
{
  "incident_id": "a1b2c3d4e5f6",
  "remediation_steps": [
    {
      "step": 1,
      "action": "Check pod resource limits",
      "command": "kubectl describe pod web-api-7d8f9c-xks2l",
      "expected_outcome": "Identify resource constraints",
      "risk_level": "low"
    },
    {
      "step": 2,
      "action": "Scale up deployment",
      "command": "kubectl scale deployment web-api --replicas=5",
      "expected_outcome": "Distribute load across more pods",
      "risk_level": "medium"
    }
  ]
}
```

## 4. Filter Incidents by Classification

```bash
# Get all infrastructure incidents
curl "http://localhost:8080/api/incidents?classification=infrastructure" | jq '.'

# Get all critical incidents
curl "http://localhost:8080/api/incidents?severity=critical" | jq '.'
```

## 5. Get Statistics

```bash
curl http://localhost:8080/api/stats | jq '.'
```

Response:
```json
{
  "total_incidents": 42,
  "avg_confidence": 0.83,
  "critical_count": 12,
  "warning_count": 30,
  "infrastructure_count": 15,
  "application_count": 18,
  "network_count": 9
}
```

## 6. Send Test Alert Directly

```bash
curl -X POST http://localhost:8090/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "incident-analyzer",
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "DatabaseSlowQueries",
        "service": "postgres-db",
        "severity": "warning"
      },
      "annotations": {
        "summary": "Database queries taking longer than 5 seconds",
        "description": "Multiple slow queries detected on production database"
      },
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
  }'
```

## 7. Trigger AI Analysis Directly

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "alert": {
      "name": "HighMemoryUsage",
      "severity": "critical",
      "timestamp": "2024-01-07T14:30:00Z",
      "labels": {
        "service": "api-gateway",
        "namespace": "production",
        "pod": "api-gateway-abc123"
      },
      "annotations": {
        "summary": "Memory usage above 90%",
        "description": "Pod api-gateway-abc123 consuming 3.8GB of 4GB limit"
      }
    },
    "context_window": 300
  }' | jq '.'
```

## 8. Prometheus Queries

```bash
# Get total incident count
curl -s 'http://localhost:9090/api/v1/query?query=incident_analyses_total' | jq '.'

# Get analysis duration (p95)
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(incident_analysis_duration_seconds_bucket[5m]))' | jq '.'

# Get incident rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(incident_analyses_total[5m])' | jq '.'
```

## 9. Loki Log Queries

```bash
# Get AI service logs from last hour
curl -s 'http://localhost:3100/loki/api/v1/query_range?query={service="ai-service"}&limit=100' | jq '.'

# Get error logs
curl -s 'http://localhost:3100/loki/api/v1/query_range?query={service="ai-service"}|~"ERROR"' | jq '.'
```

## 10. Python Example

```python
import requests
import json
from datetime import datetime

# List incidents
response = requests.get('http://localhost:8080/api/incidents')
incidents = response.json()

for incident in incidents['incidents']:
    print(f"Incident {incident['incident_id']}:")
    print(f"  Type: {incident['classification']}")
    print(f"  Severity: {incident['severity']}")
    print(f"  Confidence: {incident['confidence_score']}")
    print()

# Get specific incident details
incident_id = incidents['incidents'][0]['incident_id']
response = requests.get(f'http://localhost:8080/api/incidents/{incident_id}')
details = response.json()

print(f"Root Causes for {incident_id}:")
for cause in details['root_causes']:
    print(f"  - {cause['cause']} (confidence: {cause['confidence']})")

# Get remediation steps
response = requests.get(f'http://localhost:8080/api/incidents/{incident_id}/remediation')
remediation = response.json()

print(f"\nRemediation Steps:")
for step in remediation['remediation_steps']:
    print(f"  {step['step']}. {step['action']}")
    if step['command']:
        print(f"     Command: {step['command']}")
```

## 11. JavaScript Example

```javascript
// Fetch incidents
async function fetchIncidents() {
  const response = await fetch('http://localhost:8080/api/incidents');
  const data = await response.json();
  
  data.incidents.forEach(incident => {
    console.log(`Incident ${incident.incident_id}:`);
    console.log(`  Type: ${incident.classification}`);
    console.log(`  Severity: ${incident.severity}`);
    console.log(`  Confidence: ${incident.confidence_score}`);
  });
}

// Send alert
async function sendAlert() {
  const alert = {
    receiver: "incident-analyzer",
    status: "firing",
    alerts: [{
      status: "firing",
      labels: {
        alertname: "TestAlert",
        service: "test-service",
        severity: "warning"
      },
      annotations: {
        summary: "Test alert from JavaScript",
        description: "This is a test"
      },
      startsAt: new Date().toISOString()
    }]
  };
  
  const response = await fetch('http://localhost:8090/webhook', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(alert)
  });
  
  const result = await response.json();
  console.log('Alert sent:', result);
}
```

## 12. Bash Script for Monitoring

```bash
#!/bin/bash
# monitor-incidents.sh - Watch for new incidents

while true; do
    clear
    echo "=== AI Incident Analyzer - Live Monitor ==="
    echo ""
    
    # Get stats
    stats=$(curl -s http://localhost:8080/api/stats)
    echo "Statistics:"
    echo "$stats" | jq -r '"  Total: \(.total_incidents), Critical: \(.critical_count), Warning: \(.warning_count)"'
    echo ""
    
    # Get recent incidents
    echo "Recent Incidents:"
    curl -s 'http://localhost:8080/api/incidents?page_size=5' | \
        jq -r '.incidents[] | "  [\(.timestamp)] \(.classification) - \(.severity) - \(.summary)"'
    
    echo ""
    echo "Refreshing in 10 seconds... (Ctrl+C to stop)"
    sleep 10
done
```

Make it executable:
```bash
chmod +x monitor-incidents.sh
./monitor-incidents.sh
```

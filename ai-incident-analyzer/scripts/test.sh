#!/bin/bash
# send test alert

curl -X POST http://localhost:8090/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "webhook",
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighCPU",
        "service": "web-api",
        "severity": "critical"
      },
      "annotations": {
        "summary": "CPU usage high",
        "description": "CPU > 85% for 5 min"
      },
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
  }'

echo ""
echo "alert sent - wait ~30s for analysis"
echo "check: curl http://localhost:8080/api/incidents | jq"

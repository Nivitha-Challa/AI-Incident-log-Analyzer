#!/bin/bash

set -e

echo "🔥 Generating Test Incident"
echo "=========================="

# Send a test alert to the alert receiver
curl -X POST http://localhost:8090/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "incident-analyzer",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "HighCPUUsage",
          "service": "web-api",
          "severity": "critical",
          "namespace": "production",
          "pod": "web-api-7d8f9c-xks2l"
        },
        "annotations": {
          "summary": "High CPU usage detected on web-api",
          "description": "CPU usage has been above 85% for the last 5 minutes on pod web-api-7d8f9c-xks2l"
        },
        "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus:9090/graph?g0.expr=rate%28container_cpu_usage_seconds_total%5B5m%5D%29+%3E+0.85",
        "fingerprint": "test12345"
      }
    ],
    "groupLabels": {
      "alertname": "HighCPUUsage"
    },
    "commonLabels": {
      "alertname": "HighCPUUsage",
      "service": "web-api",
      "severity": "critical"
    },
    "commonAnnotations": {
      "summary": "High CPU usage detected on web-api"
    },
    "externalURL": "http://alertmanager:9093",
    "version": "4",
    "groupKey": "{}:{alertname=\"HighCPUUsage\"}"
  }'

echo ""
echo "=========================="
echo "✅ Test alert sent!"
echo ""
echo "📊 Check the results:"
echo "   1. View AI Service logs: docker-compose logs -f ai-service"
echo "   2. View Log Processor logs: docker-compose logs -f log-processor"
echo "   3. Check API for incidents: curl http://localhost:8080/api/incidents"
echo ""
echo "⏳ Analysis may take 30-60 seconds..."
echo ""

# Wait a bit and check if incident was created
sleep 5

echo "🔍 Checking for created incidents..."
curl -s http://localhost:8080/api/incidents | jq '.' || echo "Failed to fetch incidents (jq not installed or API error)"

echo ""
echo "=========================="

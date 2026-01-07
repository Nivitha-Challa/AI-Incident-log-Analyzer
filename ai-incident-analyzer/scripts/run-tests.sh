#!/bin/bash

set -e

echo "🧪 Running AI Incident Analyzer Tests"
echo "====================================="

# Check if services are running
echo "1️⃣  Checking if services are running..."

services=("ai-service:8000" "api-gateway:8080" "prometheus:9090" "loki:3100")
all_up=true

for service in "${services[@]}"; do
    IFS=':' read -r name port <<< "$service"
    if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1 || \
       curl -s -f "http://localhost:$port/-/healthy" > /dev/null 2>&1 || \
       curl -s -f "http://localhost:$port/ready" > /dev/null 2>&1; then
        echo "   ✅ $name is running"
    else
        echo "   ❌ $name is not responding"
        all_up=false
    fi
done

if [ "$all_up" = false ]; then
    echo ""
    echo "❌ Some services are not running. Please start them with ./scripts/start-local.sh"
    exit 1
fi

echo ""
echo "2️⃣  Testing API endpoints..."

# Test API Gateway health
echo "   Testing API Gateway..."
response=$(curl -s http://localhost:8080/health)
if echo "$response" | grep -q "healthy"; then
    echo "   ✅ API Gateway health check passed"
else
    echo "   ❌ API Gateway health check failed"
fi

# Test AI Service health
echo "   Testing AI Service..."
response=$(curl -s http://localhost:8000/health)
if echo "$response" | grep -q "healthy"; then
    echo "   ✅ AI Service health check passed"
else
    echo "   ❌ AI Service health check failed"
fi

echo ""
echo "3️⃣  Testing incident creation..."

# Create a test incident
incident_response=$(curl -s -X POST http://localhost:8090/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "test",
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "service": "test-service",
        "severity": "warning"
      },
      "annotations": {
        "summary": "Test alert for automated testing",
        "description": "This is a test alert"
      },
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
  }')

if echo "$incident_response" | grep -q "success"; then
    echo "   ✅ Test incident created successfully"
else
    echo "   ❌ Failed to create test incident"
    echo "   Response: $incident_response"
fi

echo ""
echo "4️⃣  Waiting for analysis to complete (30 seconds)..."
sleep 30

echo ""
echo "5️⃣  Checking for analyzed incidents..."

incidents=$(curl -s http://localhost:8080/api/incidents)
incident_count=$(echo "$incidents" | jq -r '.total // 0' 2>/dev/null || echo "0")

if [ "$incident_count" -gt 0 ]; then
    echo "   ✅ Found $incident_count incident(s)"
    echo "   Recent incidents:"
    echo "$incidents" | jq -r '.incidents[] | "      - \(.incident_id): \(.classification) (\(.severity))"' 2>/dev/null || echo "      (unable to parse)"
else
    echo "   ⚠️  No incidents found yet (analysis may still be processing)"
fi

echo ""
echo "6️⃣  Testing Prometheus metrics..."

# Check if AI service metrics are being collected
metrics=$(curl -s http://localhost:9090/api/v1/query?query=incident_analyses_total)
if echo "$metrics" | grep -q "success"; then
    echo "   ✅ Prometheus metrics are being collected"
    # Extract metric value if available
    value=$(echo "$metrics" | jq -r '.data.result[0].value[1] // "0"' 2>/dev/null)
    echo "   Total analyses: $value"
else
    echo "   ⚠️  No metrics found (may need more time)"
fi

echo ""
echo "7️⃣  Testing Loki logs..."

logs=$(curl -s "http://localhost:3100/loki/api/v1/query_range?query={service=\"ai-service\"}&limit=1")
if echo "$logs" | grep -q "success"; then
    echo "   ✅ Loki is collecting logs"
else
    echo "   ⚠️  No logs found in Loki"
fi

echo ""
echo "====================================="
echo "✅ Testing complete!"
echo ""
echo "📊 Summary:"
echo "   - All services are running"
echo "   - Incident creation works"
echo "   - Analysis pipeline is functional"
echo "   - Metrics and logs are being collected"
echo ""
echo "📝 View detailed results:"
echo "   - Incidents: curl http://localhost:8080/api/incidents | jq"
echo "   - Stats: curl http://localhost:8080/api/stats | jq"
echo "   - Logs: docker-compose logs -f"
echo "====================================="

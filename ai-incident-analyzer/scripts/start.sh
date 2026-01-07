#!/bin/bash
# start everything locally

set -e

echo "starting incident analyzer..."

if [ ! -f .env ]; then
    echo "no .env file - copy from .env.example and add your openai key"
    exit 1
fi

source .env

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your-key-here" ]; then
    echo "error: set OPENAI_API_KEY in .env"
    exit 1
fi

# check docker running
if ! docker info > /dev/null 2>&1; then
    echo "error: docker not running"
    exit 1
fi

echo "stopping old containers..."
docker-compose down 2>/dev/null || true

echo "starting services..."
docker-compose up -d

echo "waiting for services..."
sleep 10

# check health
services=("ai-service:8000" "api:8080" "prometheus:9090")
for svc in "${services[@]}"; do
    name=$(echo $svc | cut -d: -f1)
    port=$(echo $svc | cut -d: -f2)
    
    for i in {1..20}; do
        if curl -sf http://localhost:$port/health > /dev/null 2>&1; then
            echo "✓ $name ready"
            break
        fi
        sleep 2
    done
done

echo ""
echo "services running:"
echo "  grafana:    http://localhost:3000 (admin/admin)"
echo "  prometheus: http://localhost:9090"
echo "  api docs:   http://localhost:8080/docs"
echo "  ai service: http://localhost:8000/docs"
echo ""
echo "generate test incident:"
echo "  ./scripts/test.sh"
echo ""
echo "stop: docker-compose down"

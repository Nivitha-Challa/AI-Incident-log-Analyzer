#!/bin/bash

set -e

echo "🚀 Starting AI Incident Analyzer (Local Development)"
echo "================================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "📝 Please edit .env and add your OPENAI_API_KEY before continuing"
    echo "   Then run this script again."
    exit 1
fi

# Source environment variables
source .env

# Check for required variables
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your-openai-api-key-here" ]; then
    echo "❌ ERROR: Please set OPENAI_API_KEY in .env file"
    exit 1
fi

echo "✅ Environment variables loaded"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ ERROR: Docker is not running. Please start Docker and try again."
    exit 1
fi

echo "✅ Docker is running"

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down -v 2>/dev/null || true

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo "🔍 Checking service health..."

check_service() {
    local name=$1
    local url=$2
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f $url > /dev/null 2>&1; then
            echo "✅ $name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "   Waiting for $name... (attempt $attempt/$max_attempts)"
        sleep 2
    done
    
    echo "❌ $name failed to start"
    return 1
}

check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3000/api/health"
check_service "Loki" "http://localhost:3100/ready"
check_service "AI Service" "http://localhost:8000/health"
check_service "API Gateway" "http://localhost:8080/health"

echo ""
echo "================================================="
echo "🎉 All services started successfully!"
echo "================================================="
echo ""
echo "📊 Access the dashboards:"
echo "   Grafana:        http://localhost:3000 (admin/admin)"
echo "   Prometheus:     http://localhost:9090"
echo "   AI Service API: http://localhost:8000/docs"
echo "   API Gateway:    http://localhost:8080/docs"
echo ""
echo "📝 Next steps:"
echo "   1. Import Grafana dashboard from dashboards/incident-analyzer.json"
echo "   2. Generate test incident: ./scripts/generate-test-incident.sh"
echo "   3. View logs: docker-compose logs -f ai-service"
echo ""
echo "🛑 To stop: docker-compose down"
echo "================================================="

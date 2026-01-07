#!/bin/bash

echo "🛑 Stopping AI Incident Analyzer"
echo "================================"

# Check what's running
if docker-compose ps | grep -q "Up"; then
    echo "📊 Current services:"
    docker-compose ps
    echo ""
    
    # Ask for confirmation
    read -p "Stop all services and remove volumes? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 Stopping services..."
        docker-compose down -v
        
        echo "🧹 Cleaning up Docker resources..."
        docker system prune -f
        
        echo "✅ All services stopped and cleaned up"
    else
        echo "🛑 Stopping services (keeping volumes)..."
        docker-compose down
        echo "✅ Services stopped (data preserved)"
    fi
else
    echo "ℹ️  No services currently running"
fi

echo ""
echo "To restart: ./scripts/start-local.sh"

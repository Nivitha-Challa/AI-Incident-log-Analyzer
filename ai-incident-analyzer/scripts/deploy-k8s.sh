#!/bin/bash

set -e

echo "🚀 Deploying AI Incident Analyzer to Kubernetes"
echo "================================================"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

echo "✅ Connected to Kubernetes cluster"

# Create namespace
echo "📦 Creating namespace..."
kubectl create namespace incident-analyzer --dry-run=client -o yaml | kubectl apply -f -

# Build Docker images (if using local registry)
echo "🏗️  Building Docker images..."
cd services/ai-service && docker build -t ai-incident-analyzer/ai-service:latest . && cd ../..
cd services/api-gateway && docker build -t ai-incident-analyzer/api-gateway:latest . && cd ../..
cd services/log-processor && docker build -t ai-incident-analyzer/log-processor:latest . && cd ../..
cd services/alert-receiver && docker build -t ai-incident-analyzer/alert-receiver:latest . && cd ../..

echo "✅ Docker images built"

# Update secrets (prompt user)
echo ""
echo "⚠️  Please update the secrets in k8s/deployment.yaml with your actual values:"
echo "   - OPENAI_API_KEY"
echo "   - POSTGRES_PASSWORD"
echo ""
read -p "Press Enter when ready to continue..."

# Apply Kubernetes manifests
echo "📝 Applying Kubernetes manifests..."
kubectl apply -f k8s/deployment.yaml

# Wait for deployments to be ready
echo "⏳ Waiting for deployments to be ready..."
kubectl wait --for=condition=available --timeout=300s \
    deployment/ai-service \
    deployment/api-gateway \
    deployment/log-processor \
    deployment/alert-receiver \
    -n incident-analyzer

echo "✅ All deployments are ready"

# Get service endpoints
echo ""
echo "================================================"
echo "🎉 Deployment successful!"
echo "================================================"
echo ""
echo "📊 Service endpoints:"
kubectl get services -n incident-analyzer

echo ""
echo "🔍 Pod status:"
kubectl get pods -n incident-analyzer

echo ""
echo "📝 Next steps:"
echo "   1. Port-forward to access services:"
echo "      kubectl port-forward -n incident-analyzer svc/api-gateway 8080:8080"
echo "   2. View logs:"
echo "      kubectl logs -f -n incident-analyzer deployment/ai-service"
echo "   3. Scale services:"
echo "      kubectl scale deployment ai-service --replicas=3 -n incident-analyzer"
echo ""
echo "================================================"

"""
AI Service - Root Cause Analysis Engine
Analyzes incidents using LLM to determine root cause and suggest remediation
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import openai
import os
import json
from datetime import datetime, timedelta
import asyncio
import httpx
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response
import logging
from collections import defaultdict
import hashlib

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="AI Incident Analyzer", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
analysis_counter = Counter('incident_analyses_total', 'Total number of incident analyses')
analysis_duration = Histogram('incident_analysis_duration_seconds', 'Time spent analyzing incidents')
classification_counter = Counter('incident_classifications_total', 'Incident classifications', ['category'])

# OpenAI configuration
openai.api_key = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

# Service URLs
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")

# Models
class Alert(BaseModel):
    name: str
    severity: str
    timestamp: datetime
    labels: Dict[str, str]
    annotations: Dict[str, str]

class MetricData(BaseModel):
    metric_name: str
    values: List[tuple]  # [(timestamp, value), ...]
    labels: Dict[str, str]

class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    message: str
    service: str
    labels: Dict[str, str] = {}

class IncidentAnalysisRequest(BaseModel):
    alert: Alert
    context_window: int = 300  # seconds

class RootCauseHypothesis(BaseModel):
    cause: str
    confidence: float
    evidence: List[str]
    category: str

class RemediationStep(BaseModel):
    step: int
    action: str
    command: Optional[str] = None
    expected_outcome: str
    risk_level: str

class IncidentAnalysis(BaseModel):
    incident_id: str
    timestamp: datetime
    alert: Alert
    root_causes: List[RootCauseHypothesis]
    classification: str
    severity: str
    affected_services: List[str]
    remediation_steps: List[RemediationStep]
    related_incidents: List[str]
    summary: str
    confidence_score: float

# Cache for similar incidents
incident_cache = {}

def generate_incident_id(alert: Alert) -> str:
    """Generate unique incident ID"""
    content = f"{alert.name}_{alert.timestamp}_{json.dumps(alert.labels)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]

async def fetch_prometheus_metrics(query: str, start_time: datetime, end_time: datetime) -> List[MetricData]:
    """Fetch metrics from Prometheus"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={
                    "query": query,
                    "start": int(start_time.timestamp()),
                    "end": int(end_time.timestamp()),
                    "step": "15s"
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Prometheus query failed: {response.text}")
                return []
            
            data = response.json()
            metrics = []
            
            for result in data.get("data", {}).get("result", []):
                metric_data = MetricData(
                    metric_name=result.get("metric", {}).get("__name__", "unknown"),
                    values=[(float(v[0]), float(v[1])) for v in result.get("values", [])],
                    labels=result.get("metric", {})
                )
                metrics.append(metric_data)
            
            return metrics
    except Exception as e:
        logger.error(f"Error fetching Prometheus metrics: {e}")
        return []

async def fetch_loki_logs(service: str, start_time: datetime, end_time: datetime, limit: int = 1000) -> List[LogEntry]:
    """Fetch logs from Loki"""
    try:
        query = f'{{service="{service}"}}'
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LOKI_URL}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": int(start_time.timestamp() * 1e9),  # nanoseconds
                    "end": int(end_time.timestamp() * 1e9),
                    "limit": limit
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Loki query failed: {response.text}")
                return []
            
            data = response.json()
            logs = []
            
            for stream in data.get("data", {}).get("result", []):
                for value in stream.get("values", []):
                    timestamp_ns, log_line = value
                    log_entry = LogEntry(
                        timestamp=datetime.fromtimestamp(int(timestamp_ns) / 1e9),
                        level="INFO",  # Parse from log if possible
                        message=log_line,
                        service=service,
                        labels=stream.get("stream", {})
                    )
                    logs.append(log_entry)
            
            return logs
    except Exception as e:
        logger.error(f"Error fetching Loki logs: {e}")
        return []

def summarize_logs_with_ai(logs: List[LogEntry]) -> str:
    """Use AI to summarize logs and extract key information"""
    if not logs:
        return "No logs available"
    
    # Take sample of logs if too many
    sample_size = min(100, len(logs))
    log_sample = logs[:sample_size]
    
    log_text = "\n".join([f"[{log.timestamp}] {log.level}: {log.message}" for log in log_sample])
    
    prompt = f"""Analyze these logs and provide a concise summary of key events, errors, and patterns:

{log_text}

Summary (focus on errors, warnings, and unusual patterns):"""
    
    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a log analysis expert. Summarize logs concisely, focusing on errors and anomalies."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error summarizing logs: {e}")
        return f"Log summary failed. Sample: {logs[0].message if logs else 'No logs'}"

def analyze_metrics_trend(metrics: List[MetricData]) -> str:
    """Analyze metric trends"""
    if not metrics:
        return "No metrics available"
    
    analysis = []
    for metric in metrics:
        if len(metric.values) < 2:
            continue
        
        values = [v[1] for v in metric.values]
        avg = sum(values) / len(values)
        max_val = max(values)
        min_val = min(values)
        
        # Simple trend detection
        recent = values[-10:]
        older = values[:10] if len(values) > 10 else values
        
        recent_avg = sum(recent) / len(recent) if recent else avg
        older_avg = sum(older) / len(older) if older else avg
        
        trend = "increasing" if recent_avg > older_avg * 1.2 else "decreasing" if recent_avg < older_avg * 0.8 else "stable"
        
        analysis.append(f"{metric.metric_name}: {trend} (avg: {avg:.2f}, max: {max_val:.2f}, min: {min_val:.2f})")
    
    return "\n".join(analysis)

async def classify_incident(alert: Alert, log_summary: str, metric_analysis: str) -> tuple[str, float]:
    """Classify incident into category using AI"""
    
    prompt = f"""Classify this incident into one of these categories:
- infrastructure (node failures, disk space, memory issues)
- application (bugs, crashes, deadlocks, memory leaks)
- network (DNS issues, timeouts, connectivity, packet loss)
- security (suspicious activity, unauthorized access, breaches)
- database (slow queries, connection issues, locks)
- external (third-party service failures, API issues)

Alert: {alert.name}
Severity: {alert.severity}
Description: {alert.annotations.get('description', 'N/A')}

Log Summary:
{log_summary}

Metric Analysis:
{metric_analysis}

Respond with JSON in this format:
{{
  "category": "infrastructure|application|network|security|database|external",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert SRE. Classify incidents accurately based on symptoms."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.2
        )
        
        result = json.loads(response.choices[0].message.content.strip())
        classification_counter.labels(category=result["category"]).inc()
        return result["category"], result["confidence"]
    except Exception as e:
        logger.error(f"Error classifying incident: {e}")
        return "unknown", 0.5

async def generate_root_cause_hypotheses(
    alert: Alert,
    log_summary: str,
    metric_analysis: str,
    classification: str
) -> List[RootCauseHypothesis]:
    """Generate root cause hypotheses using AI"""
    
    prompt = f"""Analyze this incident and provide 2-3 ranked root cause hypotheses.

Alert: {alert.name}
Severity: {alert.severity}
Category: {classification}
Description: {alert.annotations.get('description', 'N/A')}

Log Summary:
{log_summary}

Metric Trends:
{metric_analysis}

Labels:
{json.dumps(alert.labels, indent=2)}

Provide 2-3 root cause hypotheses ranked by likelihood. For each hypothesis:
1. Describe the probable root cause
2. Provide confidence score (0.0-1.0)
3. List supporting evidence from logs/metrics
4. Categorize the cause

Respond in JSON format:
[
  {{
    "cause": "description of root cause",
    "confidence": 0.85,
    "evidence": ["evidence point 1", "evidence point 2"],
    "category": "infrastructure|application|network|etc"
  }}
]"""

    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert SRE performing root cause analysis. Be specific and evidence-based."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        hypotheses_data = json.loads(response.choices[0].message.content.strip())
        hypotheses = [RootCauseHypothesis(**h) for h in hypotheses_data]
        return sorted(hypotheses, key=lambda x: x.confidence, reverse=True)
    except Exception as e:
        logger.error(f"Error generating root cause hypotheses: {e}")
        return [RootCauseHypothesis(
            cause="Analysis failed - manual investigation required",
            confidence=0.3,
            evidence=["AI analysis encountered an error"],
            category="unknown"
        )]

async def generate_remediation_steps(
    alert: Alert,
    root_causes: List[RootCauseHypothesis],
    classification: str
) -> List[RemediationStep]:
    """Generate remediation steps using AI"""
    
    top_cause = root_causes[0] if root_causes else None
    
    prompt = f"""Generate step-by-step remediation instructions for this incident.

Alert: {alert.name}
Classification: {classification}
Most Likely Root Cause: {top_cause.cause if top_cause else 'Unknown'}
Confidence: {top_cause.confidence if top_cause else 0}

Provide 4-6 remediation steps in order of execution. For each step:
1. Action description
2. Command to execute (if applicable)
3. Expected outcome
4. Risk level (low/medium/high)

Respond in JSON format:
[
  {{
    "step": 1,
    "action": "Check service health status",
    "command": "kubectl get pods -n production",
    "expected_outcome": "Identify failed pods",
    "risk_level": "low"
  }}
]"""

    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert SRE creating runbooks. Provide safe, effective remediation steps."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1200,
            temperature=0.3
        )
        
        steps_data = json.loads(response.choices[0].message.content.strip())
        return [RemediationStep(**step) for step in steps_data]
    except Exception as e:
        logger.error(f"Error generating remediation steps: {e}")
        return [RemediationStep(
            step=1,
            action="Manual investigation required - AI remediation failed",
            command=None,
            expected_outcome="Gather more information",
            risk_level="low"
        )]

@app.post("/analyze", response_model=IncidentAnalysis)
async def analyze_incident(request: IncidentAnalysisRequest, background_tasks: BackgroundTasks):
    """Main endpoint to analyze an incident"""
    analysis_counter.inc()
    
    with analysis_duration.time():
        incident_id = generate_incident_id(request.alert)
        logger.info(f"Analyzing incident {incident_id}")
        
        # Calculate time window
        alert_time = request.alert.timestamp
        start_time = alert_time - timedelta(seconds=request.context_window)
        end_time = alert_time + timedelta(seconds=60)  # Look a bit into the future
        
        # Extract affected service from labels
        service = request.alert.labels.get("service", request.alert.labels.get("job", "unknown"))
        
        # Fetch data in parallel
        logs_task = fetch_loki_logs(service, start_time, end_time)
        
        # Build Prometheus queries based on service
        cpu_query = f'rate(container_cpu_usage_seconds_total{{service="{service}"}}[5m])'
        memory_query = f'container_memory_usage_bytes{{service="{service}"}}'
        error_query = f'rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])'
        
        metrics_tasks = [
            fetch_prometheus_metrics(cpu_query, start_time, end_time),
            fetch_prometheus_metrics(memory_query, start_time, end_time),
            fetch_prometheus_metrics(error_query, start_time, end_time)
        ]
        
        # Gather all data
        logs = await logs_task
        all_metrics = await asyncio.gather(*metrics_tasks)
        metrics = [m for metric_list in all_metrics for m in metric_list]  # Flatten
        
        logger.info(f"Fetched {len(logs)} logs and {len(metrics)} metric series")
        
        # Analyze with AI
        log_summary = summarize_logs_with_ai(logs)
        metric_analysis = analyze_metrics_trend(metrics)
        
        classification, class_confidence = await classify_incident(
            request.alert, log_summary, metric_analysis
        )
        
        root_causes = await generate_root_cause_hypotheses(
            request.alert, log_summary, metric_analysis, classification
        )
        
        remediation_steps = await generate_remediation_steps(
            request.alert, root_causes, classification
        )
        
        # Calculate overall confidence
        confidence_score = (
            class_confidence * 0.3 +
            (root_causes[0].confidence if root_causes else 0) * 0.7
        )
        
        # Generate summary
        summary = f"Incident classified as {classification}. "
        if root_causes:
            summary += f"Most likely cause: {root_causes[0].cause}. "
        summary += f"{len(remediation_steps)} remediation steps suggested."
        
        analysis = IncidentAnalysis(
            incident_id=incident_id,
            timestamp=datetime.now(),
            alert=request.alert,
            root_causes=root_causes,
            classification=classification,
            severity=request.alert.severity,
            affected_services=[service],
            remediation_steps=remediation_steps,
            related_incidents=[],  # TODO: Find similar incidents
            summary=summary,
            confidence_score=confidence_score
        )
        
        # Cache result
        incident_cache[incident_id] = analysis
        
        logger.info(f"Analysis complete for {incident_id}: {classification} ({confidence_score:.2f})")
        
        return analysis

@app.get("/incidents/{incident_id}", response_model=IncidentAnalysis)
async def get_incident(incident_id: str):
    """Retrieve cached incident analysis"""
    if incident_id not in incident_cache:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident_cache[incident_id]

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

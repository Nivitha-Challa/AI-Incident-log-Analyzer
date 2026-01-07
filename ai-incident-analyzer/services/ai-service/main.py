#!/usr/bin/env python3
"""
Main AI analysis service
TODO: refactor the prompt templates into separate file
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import httpx
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response

# setup logging - need to configure proper rotation later
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# metrics for monitoring
analysis_count = Counter('incidents_analyzed', 'Total incidents analyzed')
analysis_time = Histogram('analysis_duration', 'Analysis duration in seconds')

# config from env
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    logger.warning("No OpenAI API key found - some features won't work")

PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")

# request models
class Alert(BaseModel):
    name: str
    severity: str
    timestamp: datetime
    labels: Dict
    annotations: Dict

class AnalysisRequest(BaseModel):
    alert: Alert
    context_window: int = 300

class RootCause(BaseModel):
    description: str
    confidence: float
    evidence: List[str]
    type: str

class Step(BaseModel):
    number: int
    action: str
    command: Optional[str]
    risk: str

class AnalysisResult(BaseModel):
    id: str
    timestamp: datetime
    alert: Alert
    category: str
    root_causes: List[RootCause]
    steps: List[Step]
    summary: str

# cache to avoid re-analyzing same incident
_cache = {}

def _gen_id(alert: Alert) -> str:
    # simple hash for incident id
    import hashlib
    s = f"{alert.name}_{alert.timestamp}_{alert.labels.get('service', '')}"
    return hashlib.md5(s.encode()).hexdigest()[:10]

async def _get_metrics(query: str, start: datetime, end: datetime):
    """fetch prometheus metrics - sometimes times out so added retry logic"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{PROM_URL}/api/v1/query_range",
                params={
                    "query": query,
                    "start": int(start.timestamp()),
                    "end": int(end.timestamp()),
                    "step": "15s"
                }
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("result", [])
                return data
            else:
                logger.error(f"prometheus error: {resp.text}")
                return []
    except Exception as e:
        logger.error(f"failed to fetch metrics: {e}")
        return []

async def _get_logs(service: str, start: datetime, end: datetime, limit=1000):
    """pull logs from loki"""
    query = f'{{service="{service}"}}'
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{LOKI_URL}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": int(start.timestamp() * 1e9),
                    "end": int(end.timestamp() * 1e9),
                    "limit": limit
                }
            )
            if resp.status_code == 200:
                logs = []
                for stream in resp.json().get("data", {}).get("result", []):
                    for ts, msg in stream.get("values", []):
                        logs.append({"ts": int(ts) / 1e9, "msg": msg})
                return logs
            return []
    except Exception as e:
        logger.error(f"loki fetch failed: {e}")
        return []

def _summarize_logs(logs: List[Dict]) -> str:
    """use LLM to summarize log noise"""
    if not logs or not openai.api_key:
        return "No logs available or API key missing"
    
    # only send a sample to avoid token limits
    sample = logs[:100] if len(logs) > 100 else logs
    log_text = "\n".join([f"[{datetime.fromtimestamp(l['ts'])}] {l['msg']}" for l in sample])
    
    prompt = f"""Summarize these logs, focus on errors and anomalies:

{log_text}

Keep it under 100 words."""

    try:
        resp = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "you're an SRE analyzing logs"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"openai error: {e}")
        return f"Log summary failed: {str(e)[:100]}"

def _analyze_metrics(metrics: List) -> str:
    """basic metric trend analysis"""
    if not metrics:
        return "No metrics"
    
    results = []
    for m in metrics[:5]:  # only first 5
        values = [float(v[1]) for v in m.get("values", [])]
        if len(values) < 2:
            continue
        
        avg = sum(values) / len(values)
        trend = "up" if values[-1] > values[0] * 1.2 else "down" if values[-1] < values[0] * 0.8 else "stable"
        metric_name = m.get("metric", {}).get("__name__", "unknown")
        results.append(f"{metric_name}: {trend} (avg={avg:.2f})")
    
    return "\n".join(results) if results else "No significant trends"

async def _classify(alert: Alert, log_summary: str, metrics_info: str) -> tuple:
    """classify incident type using AI"""
    
    # prompt could be better - TODO: tune this
    prompt = f"""Classify this incident:
    
Alert: {alert.name}
Severity: {alert.severity}
Description: {alert.annotations.get('description', 'n/a')}

Logs: {log_summary}
Metrics: {metrics_info}

Categories: infrastructure, application, network, database, security, external

Return JSON:
{{"category": "...", "confidence": 0.0-1.0, "reason": "..."}}"""

    try:
        resp = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "classify incidents accurately"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.2
        )
        result = json.loads(resp.choices[0].message.content.strip())
        return result["category"], result["confidence"]
    except:
        return "unknown", 0.5

async def _find_root_causes(alert: Alert, log_summary: str, metrics_info: str, category: str) -> List[RootCause]:
    """generate root cause hypotheses"""
    
    prompt = f"""Find root cause for this incident:

Alert: {alert.name}
Category: {category}
Severity: {alert.severity}

Logs: {log_summary}
Metrics: {metrics_info}

Provide 2-3 hypotheses with evidence. JSON format:
[
  {{"description": "...", "confidence": 0.8, "evidence": ["..."], "type": "..."}}
]"""

    try:
        resp = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "you're an expert SRE doing RCA"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.3
        )
        causes = json.loads(resp.choices[0].message.content.strip())
        return [RootCause(**c) for c in causes]
    except Exception as e:
        logger.error(f"RCA failed: {e}")
        return [RootCause(
            description="Manual investigation needed",
            confidence=0.3,
            evidence=["automated analysis error"],
            type="unknown"
        )]

async def _gen_remediation(alert: Alert, causes: List[RootCause]) -> List[Step]:
    """generate fix steps"""
    
    top_cause = causes[0] if causes else None
    if not top_cause:
        return []
    
    prompt = f"""Generate remediation steps for:

Alert: {alert.name}
Root cause: {top_cause.description}

Provide 3-5 steps. JSON:
[
  {{"number": 1, "action": "...", "command": "...", "risk": "low/medium/high"}}
]"""

    try:
        resp = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "create safe runbook steps"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.3
        )
        steps = json.loads(resp.choices[0].message.content.strip())
        return [Step(**s) for s in steps]
    except:
        return [Step(number=1, action="Manual intervention required", command=None, risk="low")]

@app.post("/analyze")
async def analyze(req: AnalysisRequest):
    """main analysis endpoint"""
    analysis_count.inc()
    
    with analysis_time.time():
        incident_id = _gen_id(req.alert)
        logger.info(f"analyzing {incident_id}")
        
        # check cache
        if incident_id in _cache:
            logger.info(f"returning cached result for {incident_id}")
            return _cache[incident_id]
        
        # time window for context
        alert_time = req.alert.timestamp
        start = alert_time - timedelta(seconds=req.context_window)
        end = alert_time + timedelta(seconds=60)
        
        service = req.alert.labels.get("service", req.alert.labels.get("job", "unknown"))
        
        # fetch data in parallel
        logs = await _get_logs(service, start, end)
        
        # metric queries - could make these configurable
        cpu_q = f'rate(container_cpu_usage_seconds_total{{service="{service}"}}[5m])'
        mem_q = f'container_memory_usage_bytes{{service="{service}"}}'
        
        cpu_data, mem_data = await asyncio.gather(
            _get_metrics(cpu_q, start, end),
            _get_metrics(mem_q, start, end)
        )
        
        metrics = cpu_data + mem_data
        
        logger.info(f"got {len(logs)} logs, {len(metrics)} metrics")
        
        # analyze
        log_summary = _summarize_logs(logs)
        metrics_info = _analyze_metrics(metrics)
        
        category, confidence = await _classify(req.alert, log_summary, metrics_info)
        root_causes = await _find_root_causes(req.alert, log_summary, metrics_info, category)
        steps = await _gen_remediation(req.alert, root_causes)
        
        summary = f"Classified as {category}. "
        if root_causes:
            summary += f"Likely cause: {root_causes[0].description}. "
        summary += f"Generated {len(steps)} remediation steps."
        
        result = AnalysisResult(
            id=incident_id,
            timestamp=datetime.now(),
            alert=req.alert,
            category=category,
            root_causes=root_causes,
            steps=steps,
            summary=summary
        )
        
        # cache it
        _cache[incident_id] = result
        
        logger.info(f"analysis done for {incident_id}: {category}")
        return result

@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    if incident_id not in _cache:
        raise HTTPException(404, "not found")
    return _cache[incident_id]

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now().isoformat()}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

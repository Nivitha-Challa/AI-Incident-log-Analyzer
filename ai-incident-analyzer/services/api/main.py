#!/usr/bin/env python3
"""
REST API for accessing incident data
"""
import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import asyncpg

app = FastAPI(title="Incident Analyzer API")

AI_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "incidents")
DB_USER = os.getenv("POSTGRES_USER", "incident_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "incident_pass")

db_pool = None

class IncidentSummary(BaseModel):
    id: str
    timestamp: datetime
    category: str
    severity: str
    summary: str

class IncidentList(BaseModel):
    incidents: List[IncidentSummary]
    total: int
    page: int

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        min_size=2,
        max_size=10
    )

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()

@app.get("/api/incidents")
async def list_incidents(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    severity: Optional[str] = None
):
    """list incidents with filters"""
    try:
        async with db_pool.acquire() as conn:
            query = "SELECT * FROM incidents WHERE 1=1"
            params = []
            
            if category:
                query += f" AND category = ${len(params)+1}"
                params.append(category)
            
            if severity:
                query += f" AND severity = ${len(params)+1}"
                params.append(severity)
            
            query += f" ORDER BY timestamp DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
            params.extend([page_size, (page-1)*page_size])
            
            rows = await conn.fetch(query, *params)
            
            # get total
            count_q = "SELECT COUNT(*) FROM incidents WHERE 1=1"
            count_params = []
            if category:
                count_q += " AND category = $1"
                count_params.append(category)
            if severity:
                count_q += f" AND severity = ${len(count_params)+1}"
                count_params.append(severity)
            
            total = await conn.fetchval(count_q, *count_params)
            
            incidents = [
                IncidentSummary(
                    id=r['incident_id'],
                    timestamp=r['timestamp'],
                    category=r['category'],
                    severity=r['severity'],
                    summary=r['summary']
                )
                for r in rows
            ]
            
            return IncidentList(incidents=incidents, total=total, page=page)
    except Exception as e:
        raise HTTPException(500, f"db error: {e}")

@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """get full incident details"""
    try:
        # try AI service cache first
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{AI_URL}/incidents/{incident_id}")
            if resp.status_code == 200:
                return resp.json()
        
        # fall back to db
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM incidents WHERE incident_id = $1",
                incident_id
            )
            
            if not row:
                raise HTTPException(404, "not found")
            
            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"error: {e}")

@app.get("/api/incidents/{incident_id}/remediation")
async def get_remediation(incident_id: str):
    """get fix steps"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT steps FROM incidents WHERE incident_id = $1",
                incident_id
            )
            
            if not row:
                raise HTTPException(404, "not found")
            
            return {"incident_id": incident_id, "steps": row['steps']}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"error: {e}")

@app.get("/api/stats")
async def get_stats():
    """overall stats"""
    try:
        async with db_pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical,
                    COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning,
                    COUNT(CASE WHEN category = 'infrastructure' THEN 1 END) as infra,
                    COUNT(CASE WHEN category = 'application' THEN 1 END) as app
                FROM incidents
                WHERE timestamp > NOW() - INTERVAL '7 days'
            """)
            
            return dict(stats)
    except Exception as e:
        raise HTTPException(500, f"error: {e}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

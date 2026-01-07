"""
API Gateway
REST API for accessing incident analysis results
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
from datetime import datetime
import asyncpg
from contextlib import asynccontextmanager

app = FastAPI(title="Incident Analyzer API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "incidents")
POSTGRES_USER = os.getenv("POSTGRES_USER", "incident_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "incident_pass")

# Database connection pool
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=int(POSTGRES_PORT),
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        min_size=2,
        max_size=10
    )
    yield
    # Shutdown
    await db_pool.close()

app = FastAPI(title="Incident Analyzer API Gateway", version="1.0.0", lifespan=lifespan)

class IncidentSummary(BaseModel):
    incident_id: str
    timestamp: datetime
    classification: str
    severity: str
    summary: str
    confidence_score: float

class IncidentListResponse(BaseModel):
    incidents: List[IncidentSummary]
    total: int
    page: int
    page_size: int

@app.get("/api/incidents", response_model=IncidentListResponse)
async def list_incidents(
    page: int = 1,
    page_size: int = 20,
    classification: Optional[str] = None,
    severity: Optional[str] = None
):
    """List all incidents with pagination and filtering"""
    try:
        async with db_pool.acquire() as conn:
            # Build query
            query = "SELECT * FROM incidents WHERE 1=1"
            params = []
            param_idx = 1
            
            if classification:
                query += f" AND classification = ${param_idx}"
                params.append(classification)
                param_idx += 1
            
            if severity:
                query += f" AND severity = ${param_idx}"
                params.append(severity)
                param_idx += 1
            
            query += f" ORDER BY timestamp DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([page_size, (page - 1) * page_size])
            
            # Execute query
            rows = await conn.fetch(query, *params)
            
            # Count total
            count_query = "SELECT COUNT(*) FROM incidents WHERE 1=1"
            count_params = []
            if classification:
                count_query += " AND classification = $1"
                count_params.append(classification)
            if severity:
                count_query += f" AND severity = ${len(count_params) + 1}"
                count_params.append(severity)
            
            total = await conn.fetchval(count_query, *count_params)
            
            incidents = [
                IncidentSummary(
                    incident_id=row['incident_id'],
                    timestamp=row['timestamp'],
                    classification=row['classification'],
                    severity=row['severity'],
                    summary=row['summary'],
                    confidence_score=row['confidence_score']
                )
                for row in rows
            ]
            
            return IncidentListResponse(
                incidents=incidents,
                total=total,
                page=page,
                page_size=page_size
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/incidents/{incident_id}")
async def get_incident_details(incident_id: str):
    """Get full details of a specific incident"""
    try:
        # Try AI service cache first
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AI_SERVICE_URL}/incidents/{incident_id}")
            if response.status_code == 200:
                return response.json()
        
        # Fall back to database
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM incidents WHERE incident_id = $1",
                incident_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="Incident not found")
            
            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/incidents/{incident_id}/remediation")
async def get_remediation_steps(incident_id: str):
    """Get remediation steps for an incident"""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT remediation_steps FROM incidents WHERE incident_id = $1",
                incident_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="Incident not found")
            
            return {"incident_id": incident_id, "remediation_steps": row['remediation_steps']}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/stats")
async def get_statistics():
    """Get overall statistics"""
    try:
        async with db_pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_incidents,
                    AVG(confidence_score) as avg_confidence,
                    COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning_count,
                    COUNT(CASE WHEN classification = 'infrastructure' THEN 1 END) as infrastructure_count,
                    COUNT(CASE WHEN classification = 'application' THEN 1 END) as application_count,
                    COUNT(CASE WHEN classification = 'network' THEN 1 END) as network_count
                FROM incidents
                WHERE timestamp > NOW() - INTERVAL '7 days'
            """)
            
            return dict(stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

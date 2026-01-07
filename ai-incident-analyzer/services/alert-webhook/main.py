#!/usr/bin/env python3
"""
receives alertmanager webhooks and pushes to kafka
"""
import os
import json
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from kafka import KafkaProducer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI()

KAFKA_SERVERS = os.getenv("KAFKA_SERVERS", "kafka:9092").split(",")

producer = None

def get_producer():
    global producer
    if not producer:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    return producer

@app.post("/webhook")
async def webhook(request: Request):
    """alertmanager webhook endpoint"""
    try:
        data = await request.json()
        log.info(f"received webhook")
        
        alerts = data.get('alerts', [])
        
        for alert in alerts:
            alert_data = {
                "name": alert.get('labels', {}).get('alertname', 'unknown'),
                "severity": alert.get('labels', {}).get('severity', 'unknown'),
                "timestamp": alert.get('startsAt', datetime.now().isoformat()),
                "labels": alert.get('labels', {}),
                "annotations": alert.get('annotations', {}),
                "status": alert.get('status', 'firing')
            }
            
            # push to kafka
            p = get_producer()
            p.send('incident-alerts', value=alert_data)
            p.flush()
            
            log.info(f"published: {alert_data['name']}")
        
        return {"status": "ok", "count": len(alerts)}
        
    except Exception as e:
        log.error(f"error: {e}")
        return {"status": "error", "msg": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)

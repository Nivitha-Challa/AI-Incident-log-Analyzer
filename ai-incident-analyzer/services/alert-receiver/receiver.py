"""
Alert Receiver
Receives webhooks from Alertmanager and publishes to Kafka
"""

from fastapi import FastAPI, Request
import json
import os
import logging
from kafka import KafkaProducer
from datetime import datetime

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Alert Receiver", version="1.0.0")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")

# Initialize Kafka producer
producer = None

def get_kafka_producer():
    global producer
    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    return producer

@app.post("/webhook")
async def receive_alert(request: Request):
    """Receive alert from Alertmanager"""
    try:
        data = await request.json()
        logger.info(f"Received alert webhook: {json.dumps(data, indent=2)}")
        
        # Alertmanager sends alerts in this format
        alerts = data.get('alerts', [])
        
        for alert in alerts:
            # Extract alert information
            alert_data = {
                "name": alert.get('labels', {}).get('alertname', 'Unknown'),
                "severity": alert.get('labels', {}).get('severity', 'unknown'),
                "timestamp": alert.get('startsAt', datetime.now().isoformat()),
                "labels": alert.get('labels', {}),
                "annotations": alert.get('annotations', {}),
                "status": alert.get('status', 'firing'),
                "receiver": data.get('receiver', 'default')
            }
            
            # Publish to Kafka
            producer = get_kafka_producer()
            producer.send('incident-alerts', value=alert_data)
            producer.flush()
            
            logger.info(f"Published alert to Kafka: {alert_data['name']}")
        
        return {"status": "success", "alerts_processed": len(alerts)}
        
    except Exception as e:
        logger.error(f"Error processing alert: {e}")
        return {"status": "error", "message": str(e)}, 500

@app.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)

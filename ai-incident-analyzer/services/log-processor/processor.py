"""
Log Processor Service
Consumes log events from Kafka and triggers AI analysis
"""

import json
import os
import logging
from kafka import KafkaConsumer
import httpx
import asyncio
from datetime import datetime
from collections import deque
import time

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")

# Alert aggregation
alert_buffer = deque(maxlen=1000)
processed_incidents = set()

def should_trigger_analysis(alert_data):
    """Determine if alert should trigger AI analysis"""
    # Don't re-analyze same alert within 5 minutes
    alert_id = f"{alert_data.get('name')}_{alert_data.get('labels', {}).get('service')}"
    
    if alert_id in processed_incidents:
        logger.info(f"Alert {alert_id} already processed recently, skipping")
        return False
    
    # Only analyze critical/warning alerts
    severity = alert_data.get('severity', '').lower()
    if severity not in ['critical', 'warning', 'high']:
        logger.info(f"Alert severity {severity} too low, skipping")
        return False
    
    return True

async def trigger_ai_analysis(alert_data):
    """Trigger AI analysis for alert"""
    try:
        async with httpx.AsyncClient() as client:
            # Convert alert data to expected format
            analysis_request = {
                "alert": {
                    "name": alert_data.get("name", "Unknown Alert"),
                    "severity": alert_data.get("severity", "unknown"),
                    "timestamp": alert_data.get("timestamp", datetime.now().isoformat()),
                    "labels": alert_data.get("labels", {}),
                    "annotations": alert_data.get("annotations", {})
                },
                "context_window": 300
            }
            
            logger.info(f"Sending analysis request for alert: {alert_data.get('name')}")
            
            response = await client.post(
                f"{AI_SERVICE_URL}/analyze",
                json=analysis_request,
                timeout=60.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Analysis complete: {result['incident_id']} - {result['classification']}")
                
                # Mark as processed
                alert_id = f"{alert_data.get('name')}_{alert_data.get('labels', {}).get('service')}"
                processed_incidents.add(alert_id)
                
                # Clean old processed incidents (keep last 100)
                if len(processed_incidents) > 100:
                    processed_incidents.pop()
                
                return result
            else:
                logger.error(f"AI analysis failed: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error triggering AI analysis: {e}")
        return None

def process_alert_message(message):
    """Process alert message from Kafka"""
    try:
        alert_data = json.loads(message.value.decode('utf-8'))
        logger.info(f"Received alert: {alert_data.get('name')}")
        
        if should_trigger_analysis(alert_data):
            # Run async analysis
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(trigger_ai_analysis(alert_data))
            loop.close()
            
            if result:
                logger.info(f"Successfully analyzed incident: {result.get('incident_id')}")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode message: {e}")
    except Exception as e:
        logger.error(f"Error processing alert: {e}")

def main():
    """Main consumer loop"""
    logger.info(f"Starting Log Processor, connecting to Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    
    retry_count = 0
    max_retries = 10
    
    while retry_count < max_retries:
        try:
            consumer = KafkaConsumer(
                'incident-alerts',
                'incident-logs',
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='log-processor-group',
                value_deserializer=lambda x: x,
                consumer_timeout_ms=1000
            )
            
            logger.info("Connected to Kafka, starting to consume messages...")
            
            for message in consumer:
                try:
                    if message.topic == 'incident-alerts':
                        process_alert_message(message)
                    elif message.topic == 'incident-logs':
                        # Process log events if needed
                        pass
                        
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue
                    
        except Exception as e:
            retry_count += 1
            logger.error(f"Kafka connection error (attempt {retry_count}/{max_retries}): {e}")
            time.sleep(5)
            
    logger.error("Max retries reached, exiting")

if __name__ == "__main__":
    main()

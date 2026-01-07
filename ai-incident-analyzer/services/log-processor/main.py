#!/usr/bin/env python3
"""
processes alerts from kafka and triggers analysis
runs as a daemon
"""
import os
import json
import time
import logging
from kafka import KafkaConsumer
import httpx
import asyncio

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

KAFKA_SERVERS = os.getenv("KAFKA_SERVERS", "kafka:9092").split(",")
AI_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")

# track what we've processed so we don't duplicate
processed = set()

def should_process(alert):
    """decide if alert needs analysis"""
    alert_id = f"{alert.get('name')}_{alert.get('labels', {}).get('service')}"
    
    if alert_id in processed:
        log.debug(f"skipping duplicate: {alert_id}")
        return False
    
    severity = alert.get('severity', '').lower()
    if severity not in ['critical', 'warning', 'high']:
        log.debug(f"severity {severity} too low")
        return False
    
    return True

async def trigger_analysis(alert):
    """send to AI service"""
    try:
        payload = {
            "alert": {
                "name": alert.get("name", "unknown"),
                "severity": alert.get("severity", "unknown"),
                "timestamp": alert.get("timestamp"),
                "labels": alert.get("labels", {}),
                "annotations": alert.get("annotations", {})
            },
            "context_window": 300
        }
        
        log.info(f"analyzing: {alert.get('name')}")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{AI_URL}/analyze",
                json=payload,
                timeout=60.0
            )
            
            if resp.status_code == 200:
                result = resp.json()
                log.info(f"done: {result['id']} -> {result['category']}")
                return result
            else:
                log.error(f"analysis failed: {resp.status_code}")
    except Exception as e:
        log.error(f"error: {e}")
    return None

def process_message(msg):
    """handle kafka message"""
    try:
        alert = json.loads(msg.value.decode('utf-8'))
        log.debug(f"got alert: {alert.get('name')}")
        
        if should_process(alert):
            # run async analysis
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(trigger_analysis(alert))
            loop.close()
            
            if result:
                alert_id = f"{alert.get('name')}_{alert.get('labels', {}).get('service')}"
                processed.add(alert_id)
                
                # keep set from growing too large
                if len(processed) > 200:
                    processed.pop()
    except Exception as e:
        log.error(f"processing error: {e}")

def main():
    log.info(f"connecting to kafka: {KAFKA_SERVERS}")
    
    retries = 0
    max_retries = 10
    
    while retries < max_retries:
        try:
            consumer = KafkaConsumer(
                'incident-alerts',
                bootstrap_servers=KAFKA_SERVERS,
                auto_offset_reset='latest',
                group_id='log-processor',
                value_deserializer=lambda x: x
            )
            
            log.info("connected to kafka, starting consumer")
            
            for msg in consumer:
                try:
                    process_message(msg)
                except Exception as e:
                    log.error(f"msg error: {e}")
                    continue
                    
        except Exception as e:
            retries += 1
            log.error(f"kafka error (retry {retries}/{max_retries}): {e}")
            time.sleep(5)
    
    log.error("max retries reached, exiting")

if __name__ == "__main__":
    main()

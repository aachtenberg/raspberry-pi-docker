import json
import os
import time
import logging
import paho.mqtt.client as mqtt
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanContext, TraceFlags

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "esp-sensor-hub/#")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "mqtt-otel-bridge")

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mqtt-bridge")

# OTEL Setup
resource = Resource.create({"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        data = json.loads(payload_str)
        
        # Extract trace context from payload if available
        # Expecting: trace_id (UUID string), span_id (optional), sequence (int)
        device_id = data.get("device", "unknown")
        trace_id_str = data.get("trace_id")
        sequence = data.get("sequence")
        
        # Create span attributes
        attributes = {
            "messaging.system": "mqtt",
            "messaging.destination": msg.topic,
            "messaging.payload_size": len(msg.payload),
            "device.id": device_id,
        }
        
        if sequence is not None:
            attributes["device.sequence"] = sequence
            
        # If we have a trace_id from the device, use it to continue the trace
        context = None
        if trace_id_str:
            try:
                # Convert UUID string to 128-bit int for OTEL
                # Remove hyphens if present
                clean_trace_id = trace_id_str.replace("-", "")
                if len(clean_trace_id) == 32:
                    trace_id_int = int(clean_trace_id, 16)
                    
                    # Generate a random span ID since we don't have one from parent
                    # or use a deterministic one if needed
                    span_id_int = int(os.urandom(8).hex(), 16)
                    
                    span_context = SpanContext(
                        trace_id=trace_id_int,
                        span_id=span_id_int,
                        is_remote=True,
                        trace_flags=TraceFlags(TraceFlags.SAMPLED)
                    )
                    context = trace.set_span_in_context(trace.NonRecordingSpan(span_context))
                    attributes["link.trace_id"] = trace_id_str
            except Exception as e:
                logger.warning(f"Failed to parse trace_id {trace_id_str}: {e}")

        # Start the span
        with tracer.start_as_current_span(
            f"mqtt.receive {msg.topic}", 
            context=context,
            kind=trace.SpanKind.CONSUMER,
            attributes=attributes
        ) as span:
            span.set_status(trace.Status(trace.StatusCode.OK))
            logger.info(f"Processed message from {device_id} (trace_id: {trace_id_str})")
            
    except json.JSONDecodeError:
        logger.warning(f"Failed to decode JSON from topic {msg.topic}")
    except Exception as e:
        logger.error(f"Error processing message: {e}")

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            logger.error(f"Connection failed: {e}. Retrying in 5s...")
            time.sleep(5)

    client.loop_forever()

if __name__ == "__main__":
    main()

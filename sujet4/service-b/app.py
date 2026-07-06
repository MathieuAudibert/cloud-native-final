import time
import random
import os
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor

resource = Resource.create({"service.name": "service-b", "service.version": "1.0.0"})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318") + "/v1/traces"
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("service-b")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

PROCESSED_ORDERS = Counter(
    "service_b_orders_processed_total", "Total orders processed", ["status"]
)
PROCESSING_TIME = Histogram(
    "service_b_processing_duration_seconds", "Order processing duration",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)
DB_QUERY_LATENCY = Histogram(
    "service_b_db_query_seconds", "Simulated DB query latency"
)


def simulate_db_write(order_id: str):
    with tracer.start_as_current_span("db-write") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", "INSERT")
        span.set_attribute("db.table", "orders")
        latency = random.uniform(0.02, 0.15)
        time.sleep(latency)
        DB_QUERY_LATENCY.observe(latency)
        # simulate occasional slow queries
        if random.random() < 0.1:
            time.sleep(0.3)
            span.set_attribute("db.slow_query", True)


@app.route("/process", methods=["POST"])
def process_order():
    start = time.time()
    data = request.json or {}
    order_id = data.get("order_id", f"ORD-{int(time.time())}")
    item = data.get("item", "unknown")

    with tracer.start_as_current_span("process-order") as span:
        span.set_attribute("order.id", order_id)
        span.set_attribute("order.item", item)

        time.sleep(random.uniform(0.01, 0.04))

        simulate_db_write(order_id)

        if random.random() < 0.05:
            span.set_status(trace.StatusCode.ERROR, "Processing failed")
            PROCESSED_ORDERS.labels("error").inc()
            PROCESSING_TIME.observe(time.time() - start)
            return jsonify({"error": "Processing failed", "order_id": order_id}), 500

        duration = time.time() - start
        PROCESSED_ORDERS.labels("success").inc()
        PROCESSING_TIME.observe(duration)

        return jsonify({
            "order_id": order_id,
            "item": item,
            "status": "processed",
            "duration_ms": round(duration * 1000, 2),
        })


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "B"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)

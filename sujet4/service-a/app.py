import time
import random
import requests
import os
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

resource = Resource.create({"service.name": "service-a", "service.version": "1.0.0"})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318") + "/v1/traces"
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("service-a")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

REQUEST_COUNT = Counter(
    "service_a_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "service_a_request_latency_seconds", "Request latency in seconds", ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)
DOWNSTREAM_ERRORS = Counter(
    "service_a_downstream_errors_total", "Errors calling downstream services"
)

SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:5001")


@app.route("/api/order", methods=["POST"])
def create_order():
    start = time.time()
    with tracer.start_as_current_span("create-order") as span:
        user_id = request.json.get("user_id", "anonymous") if request.json else "anonymous"
        item = request.json.get("item", "unknown") if request.json else "unknown"
        span.set_attribute("user.id", user_id)
        span.set_attribute("order.item", item)

        time.sleep(random.uniform(0.01, 0.05))

        try:
            resp = requests.post(
                f"{SERVICE_B_URL}/process",
                json={"order_id": f"ORD-{int(time.time())}", "item": item},
                timeout=5,
            )
            result = resp.json()
            span.set_attribute("order.id", result.get("order_id", ""))
            status = "success"
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            DOWNSTREAM_ERRORS.inc()
            result = {"error": str(exc)}
            status = "error"

        latency = time.time() - start
        REQUEST_COUNT.labels("POST", "/api/order", status).inc()
        REQUEST_LATENCY.labels("/api/order").observe(latency)

        return jsonify({"service": "A", "result": result, "latency_ms": round(latency * 1000, 2)})


@app.route("/api/status")
def status():
    with tracer.start_as_current_span("check-status"):
        time.sleep(random.uniform(0.005, 0.02))
        REQUEST_COUNT.labels("GET", "/api/status", "success").inc()
        return jsonify({"service": "A", "status": "ok"})


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "A"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

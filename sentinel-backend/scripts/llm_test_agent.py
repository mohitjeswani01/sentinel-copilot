"""
Sentinel Copilot — LLM Test Agent.

A standalone script that generates OpenTelemetry spans representing LLM calls
(e.g., ``llm.chat.completion``) with attributes for token counts and latency,
exporting to the SigNoz OTLP gRPC endpoint.

Can be run directly or inside a Docker container to produce real LLM telemetry
that SigNoz ingests and Sentinel Copilot correlates via MCP.

Usage (Host / Local):
    python scripts/llm_test_agent.py

Usage (Docker container):
    docker run --rm --net=host \\
      -e SIGNOZ_OTLP_ENDPOINT="http://localhost:4317" \\
      -e SERVICE_NAME="shadow-llm-agent" \\
      python:3.12-slim bash -c "pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp google-genai && python -c '...'"
"""

from __future__ import annotations

import os
import sys
import time
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_test_agent")

def run_llm_agent() -> None:
    endpoint = os.getenv("SIGNOZ_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("SERVICE_NAME", "sentinel-llm-agent")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    logger.info("Initializing OpenTelemetry for LLM agent '%s' → %s", service_name, endpoint)

    resource = Resource.create({"service.name": service_name, "service.instance.id": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("llm_test_agent")

    prompt = "Explain shadow AI governance in SRE in 2 sentences."
    logger.info("Prompting LLM: '%s'", prompt)

    start_time = time.time()
    response_text = ""
    total_tokens = 450
    input_tokens = 50
    output_tokens = 400

    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            response_text = res.text or ""
            if hasattr(res, "usage_metadata") and res.usage_metadata:
                input_tokens = getattr(res.usage_metadata, "prompt_token_count", 50)
                output_tokens = getattr(res.usage_metadata, "candidates_token_count", 400)
                total_tokens = getattr(res.usage_metadata, "total_token_count", input_tokens + output_tokens)
            logger.info("Gemini API response received successfully.")
        except Exception as exc:
            logger.warning("Gemini API call failed (%s); generating instrumented fallback trace", exc)
            response_text = "Shadow AI governance ensures unauthorized LLM usage is detected and mitigated automatically."
    else:
        logger.info("GEMINI_API_KEY not set. Set GEMINI_API_KEY=<key> to make live calls. Generating instrumented LLM span.")
        response_text = "Shadow AI governance ensures unauthorized LLM usage is detected and mitigated automatically."
        time.sleep(0.5)

    duration_ms = (time.time() - start_time) * 1000

    # Record OpenTelemetry GenAI span
    with tracer.start_as_current_span(
        "llm.chat.completion",
        attributes={
            "gen_ai.system": "gemini",
            "gen_ai.request.model": "gemini-2.5-flash",
            "gen_ai.usage.prompt_tokens": input_tokens,
            "gen_ai.usage.completion_tokens": output_tokens,
            "gen_ai.usage.total_tokens": total_tokens,
            "llm.token_count.total": total_tokens,
            "llm.response.text": response_text[:100],
            "llm.latency_ms": duration_ms,
        },
    ):
        logger.info("Emitted 'llm.chat.completion' OTel span with %d total tokens (latency: %.1fms)", total_tokens, duration_ms)

    # Flush spans
    provider.shutdown()
    logger.info("Traces successfully flushed to SigNoz OTLP endpoint.")

if __name__ == "__main__":
    run_llm_agent()

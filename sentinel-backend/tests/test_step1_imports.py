"""Quick smoke test — verifies all Step 1 imports resolve cleanly."""
import sys

def main() -> int:
    try:
        from app.core.config import settings
        print(f"config OK: {settings.PROJECT_NAME}")

        from app.core.docker_bridge import (
            get_docker_client,
            list_running_containers,
            get_container_inspect,
            get_container_stats,
            kill_container,
        )
        print("docker_bridge OK")

        from app.observability.otel_setup import setup_opentelemetry, get_meter
        print("otel_setup OK")

        from app.observability.metrics_emitter import SentinelMetricsEmitter
        print("metrics_emitter OK")

        print("ALL IMPORTS PASSED")
        return 0
    except Exception as exc:
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

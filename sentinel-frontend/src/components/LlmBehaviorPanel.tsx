/**
 * LlmBehaviorPanel — shows the LLM Behavior trust vector (Issue #7) per container.
 *
 * Reads live values from GET /containers via getLlmBehavior(). The important
 * subtlety: the vector reports a neutral 100 when it finds no LLM telemetry
 * ("No LLM activity detected — not applicable"), so a wall of 100s means
 * "nothing measured", not "perfect behaviour". This panel states that
 * explicitly rather than letting a full green column imply a clean bill of
 * health.
 */
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Brain, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getLlmBehavior, LLM_NEUTRAL_SCORE } from "@/services/serviceApi";

function scoreColor(score: number, hasTelemetry: boolean): string {
  if (!hasTelemetry) return "text-muted-foreground";
  if (score < 40) return "text-threat";
  if (score < 60) return "text-signal";
  if (score < 80) return "text-foreground";
  return "text-success-val";
}

export function LlmBehaviorPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["llm-behavior"],
    queryFn: getLlmBehavior,
    refetchInterval: 15000,
  });

  if (isLoading) {
    return (
      <div className="glass-panel glow-border rounded-xl p-6 space-y-3">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="glass-panel glow-border rounded-xl p-6">
        <div className="flex items-center gap-2 mb-1">
          <Brain className="h-4 w-4 text-muted-foreground" />
          <p className="text-xs text-muted-foreground uppercase tracking-wider">
            LLM Behavior Vector
          </p>
        </div>
        <p className="text-sm text-muted-foreground mt-2">
          Could not reach the Sentinel API. Is the backend running on port 8001?
        </p>
      </div>
    );
  }

  const { containers, fleetAverage, withTelemetry, total } = data;
  const noneInstrumented = withTelemetry === 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel glow-border rounded-xl p-6 card-hover"
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-cyber" />
            <p className="text-xs text-muted-foreground uppercase tracking-wider">
              LLM Behavior Vector
            </p>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Weighted 20% of every container&apos;s Trust Score
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-black text-cyber tracking-tight">
            {fleetAverage.toFixed(1)}
          </div>
          <div className="text-xs text-muted-foreground">fleet average</div>
        </div>
      </div>

      {/* Honest framing: a neutral 100 means "not measured", not "healthy". */}
      {noneInstrumented ? (
        <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 mb-4">
          <Info className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
          <p className="text-xs text-muted-foreground leading-relaxed">
            No LLM-instrumented containers detected yet. All {total} scanned
            containers report the neutral default of {LLM_NEUTRAL_SCORE}, which
            means the scorer found no LLM telemetry — not that their LLM
            behaviour is perfect. Run an instrumented workload
            (<span className="font-mono">sentinel-backend/scripts/llm_test_agent.py</span>)
            to make this vector move.
          </p>
        </div>
      ) : (
        <div className="flex items-center gap-2 mb-4">
          <Badge variant="outline" className="border-0 bg-cyber/10 text-cyber text-xs">
            {withTelemetry} of {total} scored from real telemetry
          </Badge>
        </div>
      )}

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {containers.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No containers are being scanned yet.
          </p>
        )}
        {containers.map((c) => (
          <div
            key={c.containerId}
            className="flex items-center justify-between gap-3 rounded-lg border border-border/50 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">{c.containerName}</div>
              {c.reason && (
                <div className="text-xs text-muted-foreground truncate">{c.reason}</div>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!c.hasTelemetry && (
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  not measured
                </span>
              )}
              <span className={`text-lg font-bold ${scoreColor(c.score, c.hasTelemetry)}`}>
                {c.score.toFixed(0)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

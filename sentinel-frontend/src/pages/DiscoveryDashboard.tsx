import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMonitoredContainers, executeAction, type MonitoredContainer } from "@/services/serviceApi";
import { motion } from "framer-motion";
import { Search, Eye, Zap, ShieldOff, Container } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { ServerActionDialog } from "@/components/discovery/ServerActionDialog";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const riskColors: Record<string, string> = {
  low: "bg-success/10 text-success-val border-success/20",
  medium: "bg-signal\/10 text-signal border-signal/20",
  high: "bg-signal\/10 text-signal border-signal/20",
  critical: "bg-threat\/10 text-threat border-threat-critical/20",
};

const statusColors: Record<string, string> = {
  running: "bg-success/10 text-success-val",
  quarantined: "bg-signal\/10 text-signal",
  stopped: "bg-secondary text-muted-foreground",
};

const containerAnim = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } };

function formatTimestamp(ts: string) {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}

function RiskTooltip() {
  return (
    <span
      className="inline-flex items-center justify-center h-4 w-4 rounded-full bg-muted text-[10px] text-muted-foreground cursor-help"
      title="Risk = 100 − Trust Score. Lower trust → higher risk."
    >
      ?
    </span>
  );
}

export default function DiscoveryDashboard() {
  return (
    <ErrorBoundary>
      <DiscoveryDashboardContent />
    </ErrorBoundary>
  );
}

function DiscoveryDashboardContent() {
  const [search, setSearch] = useState("");
  const [actionTarget, setActionTarget] = useState<{ container: MonitoredContainer; action: "quarantine" | "kill" } | null>(null);
  const queryClient = useQueryClient();

  const { data: containers, isLoading, error } = useQuery({
    queryKey: ["monitored-containers"],
    queryFn: getMonitoredContainers,
    refetchInterval: 10_000, // Poll every 10 seconds
  });

  const killMutation = useMutation({
    mutationFn: ({ containerId }: { containerId: string }) => executeAction("kill", containerId),
    onSuccess: (res, vars) => {
      if (res.success) {
        // Optimistic update: remove the killed row immediately
        queryClient.setQueryData<MonitoredContainer[]>(["monitored-containers"], (old) =>
          old ? old.filter((c) => c.id !== vars.containerId) : []
        );
        toast.error(res.message, { description: "Container removed permanently" });
      } else {
        toast.warning(res.message);
      }
      setActionTarget(null);
    },
    onError: (err: any) => {
      toast.warning(err.message || "Kill failed");
      setActionTarget(null);
    },
  });

  const quarantineMutation = useMutation({
    mutationFn: ({ containerId }: { containerId: string }) => executeAction("quarantine", containerId),
    onSuccess: (res, vars) => {
      if (res.success) {
        // Optimistic update: mark the container as quarantined
        queryClient.setQueryData<MonitoredContainer[]>(["monitored-containers"], (old) =>
          old
            ? old.map((c) =>
                c.id === vars.containerId ? { ...c, status: "quarantined" as const } : c
              )
            : []
        );
        toast.warning(res.message, { description: "Container quarantined (stopped)" });
      } else {
        toast.warning(res.message);
      }
      setActionTarget(null);
    },
    onError: (err: any) => {
      toast.warning(err.message || "Quarantine failed");
      setActionTarget(null);
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full max-w-sm" />
        {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16" />)}
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="text-2xl font-bold tracking-tight">Discovery & Governance</div>
        <div className="glass-panel glow-border rounded-xl p-6 text-center">
          <p className="text-destructive font-semibold mb-2">Failed to load discovery data</p>
          <p className="text-muted-foreground text-sm mb-4">Make sure your backend is running on http://localhost:8001</p>
          <Button onClick={() => window.location.reload()}>Retry</Button>
        </div>
      </div>
    );
  }

  const safeContainers = containers || [];
  const filtered = safeContainers.filter(
    (c) => c.name.toLowerCase().includes(search.toLowerCase()) || c.id.includes(search)
  );

  return (
    <motion.div variants={containerAnim} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Discovery & Governance</h1>
        <p className="text-muted-foreground text-sm mt-1">Operational visibility into all monitored Docker containers</p>
      </motion.div>

      <motion.div variants={item} className="flex items-center gap-4">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search containers..." className="pl-9 bg-secondary border-border" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Container className="h-4 w-4" />
          <span>{safeContainers.length} containers monitored</span>
        </div>
      </motion.div>

      <motion.div variants={containerAnim} initial="hidden" animate="show" className="glass-panel glow-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50">
                <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Container</th>
                <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Status</th>
                <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium flex items-center gap-1">Risk <RiskTooltip /></th>
                <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Trust Score</th>
                <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Last Seen</th>
                <th className="text-right p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-muted-foreground">
                    {safeContainers.length === 0 ? "No containers detected yet. Waiting for scanner..." : "No containers match your search."}
                  </td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <motion.tr key={c.id} variants={item} className="border-b border-border/30 hover:bg-accent/50 transition-colors">
                    <td className="p-4">
                      <div className="font-medium">{c.name}</div>
                      <div className="font-mono-id text-muted-foreground mt-0.5">{c.id}</div>
                    </td>
                    <td className="p-4">
                      <Badge variant="outline" className={`${statusColors[c.status] || statusColors.stopped} border-0 text-xs`}>
                        {c.status}
                      </Badge>
                    </td>
                    <td className="p-4">
                      <Badge variant="outline" className={`${riskColors[c.riskLevel]} text-xs`}>
                        {c.riskTier}
                      </Badge>
                    </td>
                    <td className="p-4">
                      <span className={`font-bold ${c.trustScore >= 80 ? "text-success-val" : c.trustScore >= 60 ? "text-signal" : "text-threat"}`}>
                        {c.trustScore.toFixed(1)}
                      </span>
                    </td>
                    <td className="p-4 text-muted-foreground text-xs">
                      {formatTimestamp(c.lastSeen)}
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-signal hover:text-signal"
                          onClick={() => setActionTarget({ container: c, action: "quarantine" })}
                          disabled={c.status === "quarantined"}
                        >
                          <ShieldOff className="h-3 w-3 mr-1" /> Quarantine
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                          onClick={() => setActionTarget({ container: c, action: "kill" })}
                        >
                          <Zap className="h-3 w-3 mr-1" /> Kill
                        </Button>
                      </div>
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* Unified action dialog — handles both Kill and Quarantine */}
      {actionTarget && (
        <ServerActionDialog
          server={{
            id: actionTarget.container.id,
            name: actionTarget.container.name,
            status: actionTarget.container.status === "running" ? "active" : "dormant",
            riskScore: 100 - actionTarget.container.trustScore,
            riskLevel: actionTarget.container.riskLevel,
            lastSeen: actionTarget.container.lastSeen,
            connectedAgents: 0,
            toolsExposed: 0,
            region: "local",
            protocol: "docker",
            trustScore: actionTarget.container.trustScore,
          }}
          actionType={actionTarget.action}
          open={!!actionTarget}
          onOpenChange={(v) => !v && setActionTarget(null)}
          onConfirm={(id) => {
            if (actionTarget.action === "kill") {
              killMutation.mutate({ containerId: id });
            } else {
              quarantineMutation.mutate({ containerId: id });
            }
          }}
          isPending={killMutation.isPending || quarantineMutation.isPending}
        />
      )}
    </motion.div>
  );
}

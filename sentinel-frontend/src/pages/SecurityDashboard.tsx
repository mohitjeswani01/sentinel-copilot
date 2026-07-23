import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSecurityMetrics, type Security_Alert } from "@/services/serviceApi";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldAlert, AlertTriangle, Clock, CheckCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoDataBadge } from "@/components/DemoDataBadge";

const severityConfig: Record<string, { color: string; bg: string }> = {
  critical: { color: "text-threat", bg: "bg-threat\/10" },
  high: { color: "text-signal", bg: "bg-signal\/10" },
  medium: { color: "text-foreground", bg: "bg-secondary" },
};

const statusIcons: Record<string, typeof AlertTriangle> = {
  active: AlertTriangle,
  investigating: Clock,
  resolved: CheckCircle,
};

const container = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
const item = { hidden: { opacity: 0, x: -12 }, show: { opacity: 1, x: 0 } };

export default function SecurityDashboard() {
  const [filter, setFilter] = useState<string>("all");
  const { data, isLoading } = useQuery({ queryKey: ["security"], queryFn: getSecurityMetrics });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-16 w-full" />
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }

  const isCritical = data.threatLevel === "critical";
  const filtered = filter === "all" ? data.alerts : data.alerts.filter((a) => a.severity === filter);

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      {/* Critical Banner */}
      {isCritical && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="gradient-threat rounded-xl p-4 flex items-center gap-3 threat-pulse"
        >
          <ShieldAlert className="h-6 w-6 text-destructive-foreground" />
          <div>
            <p className="font-bold text-destructive-foreground">CRITICAL THREAT LEVEL</p>
            <p className="text-sm text-destructive-foreground/80">Immediate action required — active data exfiltration detected</p>
          </div>
        </motion.div>
      )}

      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Security Command</h1>
        <p className="text-muted-foreground text-sm mt-1">Real-time threat detection and response</p>
      </motion.div>

      {/* Threat Level Bar */}
      <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Current Threat Level</p>
          <p className={`text-3xl font-black uppercase ${data.threatLevel === "critical" ? "text-threat" : data.threatLevel === "high" ? "text-signal" : "text-success-val"}`}>
            {data.threatLevel}
          </p>
        </div>
        <div className="flex gap-2">
          {["critical", "high", "medium"].map((sev) => {
            const count = data.alerts.filter((a) => a.severity === sev).length;
            return (
              <div key={sev} className="text-center px-4">
                <div className={`text-2xl font-bold ${severityConfig[sev].color}`}>{count}</div>
                <div className="text-xs text-muted-foreground capitalize">{sev}</div>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div variants={item} className="flex gap-2">
        {["all", "critical", "high", "medium"].map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(f)}
            className={filter === f ? "gradient-cyber text-cyber-foreground" : ""}
          >
            {f === "all" ? "All Alerts" : f.charAt(0).toUpperCase() + f.slice(1)}
          </Button>
        ))}
      </motion.div>

      {/* Alert Cards */}
      <AnimatePresence mode="popLayout">
        <div className="space-y-3">
          {filtered.map((alert) => {
            const StatusIcon = statusIcons[alert.status] || AlertTriangle;
            const config = severityConfig[alert.severity];
            return (
              <motion.div
                key={alert.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className={`glass-panel glow-border rounded-xl p-5 card-hover border-l-4 ${alert.severity === "critical" ? "border-l-destructive" : alert.severity === "high" ? "border-l-warning" : "border-l-border"}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline" className={`${config.bg} ${config.color} border-0 text-xs font-semibold uppercase`}>
                        {alert.severity}
                      </Badge>
                      <span className="font-mono-id text-muted-foreground">{alert.id}</span>
                      <DemoDataBadge />
                    </div>
                    <h3 className="font-semibold">{alert.violationType}</h3>
                    <p className="text-sm text-muted-foreground mt-1">{alert.description}</p>
                    <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
                      <span>Agent: <span className="text-foreground font-medium">{alert.agentName}</span></span>
                      <span>{new Date(alert.timestamp).toLocaleString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusIcon className={`h-4 w-4 ${alert.status === "active" ? "text-destructive" : alert.status === "investigating" ? "text-signal" : "text-success-val"}`} />
                    <span className="text-xs capitalize">{alert.status}</span>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </AnimatePresence>
    </motion.div>
  );
}

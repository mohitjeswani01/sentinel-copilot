import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuditLog, getLatestLogs, type Audit_Log_Event } from "@/services/serviceApi";
import { motion } from "framer-motion";
import { Terminal } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

const statusColor: Record<string, string> = {
  success: "text-success-val",
  warning: "text-signal",
  failed: "text-threat",
};

const container = { hidden: {}, show: { transition: { staggerChildren: 0.04 } } };
const item = { hidden: { opacity: 0, x: -8 }, show: { opacity: 1, x: 0 } };

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function AuditLogDashboard() {
  const { data: initialData, isLoading } = useQuery({ queryKey: ["audit-log"], queryFn: getAuditLog });
  const [logs, setLogs] = useState<Audit_Log_Event[]>([]);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  // Initialize logs from query
  useEffect(() => {
    if (initialData) setLogs(initialData);
  }, [initialData]);

  // Poll for new entries every 3 seconds
  useEffect(() => {
    if (!initialData) return;
    const interval = setInterval(async () => {
      try {
        const newEntries = await getLatestLogs();
        setLogs((prev) => [...newEntries, ...prev]);
        setNewIds((prev) => {
          const next = new Set(prev);
          newEntries.forEach((e) => next.add(e.id));
          return next;
        });
        // Clear highlights after 3s
        setTimeout(() => {
          setNewIds((prev) => {
            const next = new Set(prev);
            newEntries.forEach((e) => next.delete(e.id));
            return next;
          });
        }, 3000);
      } catch {
        // ignore polling errors
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [initialData]);

  if (isLoading || !initialData) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-8" />)}
      </div>
    );
  }

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Audit Log</h1>
        <p className="text-muted-foreground text-sm mt-1">Immutable record of all agent activity — live stream</p>
      </motion.div>

      <motion.div variants={item} className="glass-panel glow-border rounded-xl overflow-hidden">
        {/* Terminal Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50">
          <Terminal className="h-4 w-4 text-cyber" />
          <span className="text-xs font-mono text-muted-foreground">sentinel-copilot:~$ tail -f /var/log/agent-activity.log</span>
          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
              <span className="text-[10px] text-muted-foreground font-mono">LIVE</span>
            </div>
            <div className="flex gap-1.5">
              <div className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-warning/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-success/60" />
            </div>
          </div>
        </div>

        {/* Log Entries */}
        <div ref={scrollRef} className="p-4 max-h-[600px] overflow-y-auto bg-background/50">
          <div className="space-y-1">
            {logs.map((log) => (
              <div
                key={log.id}
                className={`terminal-line flex items-start gap-2 py-1.5 px-2 rounded transition-all duration-500 ${
                  newIds.has(log.id)
                    ? "bg-cyber\/10 border-l-2 border-l-cyber"
                    : "hover:bg-accent/30"
                }`}
              >
                <span className="text-muted-foreground shrink-0">[{formatTime(log.timestamp)}]</span>
                <span className="text-cyber shrink-0">{log.agentName}</span>
                <span className="text-muted-foreground">→</span>
                <span className="text-foreground">{log.action}</span>
                <span className="text-muted-foreground">Tool:</span>
                <span className="text-foreground">{log.tool}</span>
                <span className="text-muted-foreground">|</span>
                <span className="text-muted-foreground">STATUS:</span>
                <span className={`font-semibold ${statusColor[log.status]}`}>{log.status.toUpperCase()}</span>
                <span className="text-muted-foreground ml-auto shrink-0">{log.duration}ms</span>
              </div>
            ))}
          </div>
        </div>

        {/* Blinking cursor */}
        <div className="px-6 py-2 border-t border-border/30">
          <span className="terminal-line text-muted-foreground">
            <span className="animate-pulse-glow">█</span>
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}

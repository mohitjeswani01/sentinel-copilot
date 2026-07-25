import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getDiscovery, executeAction, type MCP_Server, type AI_Agent } from "@/services/serviceApi";
import { motion } from "framer-motion";
import { Search, Eye, Zap, ShieldOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { AgentInspectDialog, RiskTooltip } from "@/components/discovery/AgentInspectDialog";
import { ServerInspectDialog } from "@/components/discovery/ServerInspectDialog";
import { KillSwitchDialog } from "@/components/discovery/KillSwitchDialog";
import { ServerActionDialog } from "@/components/discovery/ServerActionDialog";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const riskColors: Record<string, string> = {
  low: "bg-success/10 text-success-val border-success/20",
  medium: "bg-signal\/10 text-signal border-signal/20",
  high: "bg-signal\/10 text-signal border-signal/20",
  critical: "bg-threat\/10 text-threat border-threat-critical/20",
};

const statusColors: Record<string, string> = {
  active: "bg-success/10 text-success-val",
  dormant: "bg-secondary text-muted-foreground",
  rogue: "bg-threat\/10 text-threat",
};

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } };

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
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
  const [inspectAgent, setInspectAgent] = useState<AI_Agent | null>(null);
  const [inspectServer, setInspectServer] = useState<MCP_Server | null>(null);
  const [killTarget, setKillTarget] = useState<AI_Agent | null>(null);
  const [serverActionTarget, setServerActionTarget] = useState<{ server: MCP_Server; action: "quarantine" | "kill" } | null>(null);

  const { data, isLoading, error } = useQuery({ queryKey: ["discovery"], queryFn: getDiscovery });

  const killMutation = useMutation({
    mutationFn: ({ agentId }: { agentId: string }) => executeAction("kill", agentId),
    onSuccess: (res) => {
      toast.error(res.message, { description: "Kill switch executed" });
      setKillTarget(null);
    },
  });

  const serverActionMutation = useMutation({
    mutationFn: ({ actionType, serverId }: { actionType: string; serverId: string }) => executeAction(actionType, serverId),
    onSuccess: (res, vars) => {
      const toastFn = vars.actionType === "kill" ? toast.error : toast.warning;
      toastFn(res.message, { description: `Server ${vars.actionType} executed` });
      setServerActionTarget(null);
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

  const safeData = data || { servers: [], agents: [] };
  const filteredAgents = (safeData.agents || []).filter((a) => a.name.toLowerCase().includes(search.toLowerCase()) || a.id.includes(search));
  const filteredServers = (safeData.servers || []).filter((s) => s.name.toLowerCase().includes(search.toLowerCase()) || s.id.includes(search));

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Discovery & Governance</h1>
        <p className="text-muted-foreground text-sm mt-1">Operational visibility into all AI infrastructure</p>
      </motion.div>

      <motion.div variants={item} className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input placeholder="Search agents or servers..." className="pl-9 bg-secondary border-border" value={search} onChange={(e) => setSearch(e.target.value)} />
      </motion.div>

      <Tabs defaultValue="agents">
        <TabsList className="bg-secondary">
          <TabsTrigger value="agents">AI Agents ({(safeData.agents || []).length})</TabsTrigger>
          <TabsTrigger value="servers">MCP Servers ({(safeData.servers || []).length})</TabsTrigger>
        </TabsList>

        <TabsContent value="agents" className="mt-4">
          <motion.div variants={container} initial="hidden" animate="show" className="glass-panel glow-border rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Agent</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Status</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium flex items-center gap-1">Risk <RiskTooltip /></th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Model</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Last Seen</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Cost/Day</th>
                    <th className="text-right p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAgents.map((agent) => (
                    <motion.tr key={agent.id} variants={item} className="border-b border-border/30 hover:bg-accent/50 transition-colors">
                      <td className="p-4">
                        <div className="font-medium">{agent.name}</div>
                        <div className="font-mono-id text-muted-foreground mt-0.5">{agent.id}</div>
                      </td>
                      <td className="p-4">
                        <Badge variant="outline" className={`${statusColors[agent.status]} border-0 text-xs`}>{agent.status}</Badge>
                      </td>
                      <td className="p-4">
                        <Badge variant="outline" className={`${riskColors[agent.riskLevel]} text-xs`}>{agent.riskScore} — {agent.riskLevel}</Badge>
                      </td>
                      <td className="p-4 font-mono-id">{agent.model}</td>
                      <td className="p-4 text-muted-foreground text-xs">{formatTimestamp(agent.lastSeen)}</td>
                      <td className="p-4 font-mono-id">${agent.costPerDay.toFixed(2)}</td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setInspectAgent(agent)}>
                            <Eye className="h-3 w-3 mr-1" /> Inspect
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive hover:text-destructive" onClick={() => setKillTarget(agent)}>
                            <Zap className="h-3 w-3 mr-1" /> Kill
                          </Button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        </TabsContent>

        <TabsContent value="servers" className="mt-4">
          <motion.div variants={container} initial="hidden" animate="show" className="glass-panel glow-border rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Server</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Status</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium flex items-center gap-1">Risk <RiskTooltip /></th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Region</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Agents</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Tools</th>
                    <th className="text-left p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Last Seen</th>
                    <th className="text-right p-4 text-xs text-muted-foreground uppercase tracking-wider font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredServers.map((server) => (
                    <motion.tr key={server.id} variants={item} className="border-b border-border/30 hover:bg-accent/50 transition-colors">
                      <td className="p-4">
                        <div className="font-medium">{server.name}</div>
                        <div className="font-mono-id text-muted-foreground mt-0.5">{server.id}</div>
                      </td>
                      <td className="p-4">
                        <Badge variant="outline" className={`${statusColors[server.status]} border-0 text-xs`}>{server.status}</Badge>
                      </td>
                      <td className="p-4">
                        <Badge variant="outline" className={`${riskColors[server.riskLevel]} text-xs`}>{server.riskScore} — {server.riskLevel}</Badge>
                      </td>
                      <td className="p-4 font-mono-id">{server.region}</td>
                      <td className="p-4">{server.connectedAgents}</td>
                      <td className="p-4">{server.toolsExposed}</td>
                      <td className="p-4 text-muted-foreground text-xs">{formatTimestamp(server.lastSeen)}</td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setInspectServer(server)}>
                            <Eye className="h-3 w-3 mr-1" /> Inspect
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-signal hover:text-signal" onClick={() => setServerActionTarget({ server, action: "quarantine" })}>
                            <ShieldOff className="h-3 w-3 mr-1" /> Quarantine
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive hover:text-destructive" onClick={() => setServerActionTarget({ server, action: "kill" })}>
                            <Zap className="h-3 w-3 mr-1" /> Kill
                          </Button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <AgentInspectDialog agent={inspectAgent} open={!!inspectAgent} onOpenChange={(v) => !v && setInspectAgent(null)} />
      <ServerInspectDialog server={inspectServer} open={!!inspectServer} onOpenChange={(v) => !v && setInspectServer(null)} />
      <KillSwitchDialog
        agent={killTarget}
        open={!!killTarget}
        onOpenChange={(v) => !v && setKillTarget(null)}
        onConfirm={(id) => killMutation.mutate({ agentId: id })}
        isPending={killMutation.isPending}
      />
      <ServerActionDialog
        server={serverActionTarget?.server ?? null}
        actionType={serverActionTarget?.action ?? "quarantine"}
        open={!!serverActionTarget}
        onOpenChange={(v) => !v && setServerActionTarget(null)}
        onConfirm={(id) => serverActionMutation.mutate({ actionType: serverActionTarget!.action, serverId: id })}
        isPending={serverActionMutation.isPending}
      />
    </motion.div>
  );
}

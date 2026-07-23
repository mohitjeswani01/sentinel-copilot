import type { AI_Agent } from "@/services/serviceApi";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HelpCircle } from "lucide-react";

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

interface Props {
  agent: AI_Agent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AgentInspectDialog({ agent, open, onOpenChange }: Props) {
  if (!agent) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-panel glow-border max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {agent.name}
            <Badge variant="outline" className={`${statusColors[agent.status]} border-0 text-xs`}>
              {agent.status}
            </Badge>
          </DialogTitle>
          <DialogDescription className="font-mono-id">{agent.id}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Risk Score */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground uppercase tracking-wider">Risk Score</span>
              <RiskTooltip />
            </div>
            <Badge variant="outline" className={`${riskColors[agent.riskLevel]} text-xs`}>
              {agent.riskScore} — {agent.riskLevel}
            </Badge>
          </div>

          {/* Details grid */}
          <div className="grid grid-cols-2 gap-3">
            <DetailItem label="Model" value={agent.model} mono />
            <DetailItem label="MCP Server" value={agent.mcpServerId} mono />
            <DetailItem label="Total API Calls" value={agent.totalCalls.toLocaleString()} />
            <DetailItem label="Cost / Day" value={`$${agent.costPerDay.toFixed(2)}`} />
            <DetailItem label="Last Seen" value={new Date(agent.lastSeen).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} />
          </div>

          {/* Capabilities */}
          <div>
            <span className="text-xs text-muted-foreground uppercase tracking-wider block mb-2">Capabilities</span>
            <div className="flex flex-wrap gap-1.5">
              {agent.capabilities.map((cap) => (
                <span key={cap} className="px-2 py-0.5 rounded bg-secondary text-xs font-mono-id">{cap}</span>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DetailItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="glass-panel rounded-lg p-3">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">{label}</span>
      <span className={`text-sm font-medium ${mono ? "font-mono-id" : ""}`}>{value}</span>
    </div>
  );
}

export function RiskTooltip() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-[240px] text-xs">
        <p className="font-semibold mb-1">Why this score?</p>
        <p>Derived from Sentinel Copilot trust analysis combining behavioral monitoring, API access patterns, data sensitivity exposure, and policy compliance history.</p>
      </TooltipContent>
    </Tooltip>
  );
}

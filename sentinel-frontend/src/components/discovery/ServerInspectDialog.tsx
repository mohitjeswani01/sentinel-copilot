import type { MCP_Server } from "@/services/serviceApi";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { RiskTooltip } from "./AgentInspectDialog";

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
  server: MCP_Server | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ServerInspectDialog({ server, open, onOpenChange }: Props) {
  if (!server) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-panel glow-border max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {server.name}
            <Badge variant="outline" className={`${statusColors[server.status]} border-0 text-xs`}>
              {server.status}
            </Badge>
          </DialogTitle>
          <DialogDescription className="font-mono-id">{server.id}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground uppercase tracking-wider">Risk Score</span>
              <RiskTooltip />
            </div>
            <Badge variant="outline" className={`${riskColors[server.riskLevel]} text-xs`}>
              {server.riskScore} — {server.riskLevel}
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <DetailItem label="Region" value={server.region} mono />
            <DetailItem label="Protocol" value={server.protocol} mono />
            <DetailItem label="Connected Agents" value={String(server.connectedAgents)} />
            <DetailItem label="Tools Exposed" value={String(server.toolsExposed)} />
            <DetailItem label="Last Seen" value={new Date(server.lastSeen).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} />
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

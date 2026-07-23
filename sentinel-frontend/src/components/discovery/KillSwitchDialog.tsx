import { useState } from "react";
import type { AI_Agent } from "@/services/serviceApi";
import { AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface Props {
  agent: AI_Agent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (agentId: string) => void;
  isPending?: boolean;
}

export function KillSwitchDialog({ agent, open, onOpenChange, onConfirm, isPending }: Props) {
  const [confirmText, setConfirmText] = useState("");

  if (!agent) return null;

  const isConfirmed = confirmText === agent.id;

  return (
    <AlertDialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setConfirmText(""); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Terminate Agent: {agent.name}
          </AlertDialogTitle>
          <AlertDialogDescription className="space-y-3">
            <span className="block">
              This will immediately terminate <span className="font-mono-id font-semibold text-foreground">{agent.id}</span> and revoke all access tokens. This action is irreversible.
            </span>
            <span className="block text-xs text-muted-foreground">
              All active sessions will be destroyed. Connected MCP server bindings will be severed.
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* Confirmation Input */}
        <div className="mt-2 space-y-2">
          <label className="text-sm text-muted-foreground">
            Type <span className="font-mono-id font-semibold text-foreground">{agent.id}</span> to confirm:
          </label>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={agent.id}
            className="font-mono-id bg-secondary border-border"
            autoFocus
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => setConfirmText("")}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={!isConfirmed || isPending}
            onClick={() => { onConfirm(agent.id); setConfirmText(""); }}
          >
            {isPending ? "Executing..." : "Execute Kill Switch"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

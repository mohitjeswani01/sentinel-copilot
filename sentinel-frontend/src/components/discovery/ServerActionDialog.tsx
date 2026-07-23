import { useState } from "react";
import type { MCP_Server } from "@/services/serviceApi";
import { AlertTriangle, ShieldOff } from "lucide-react";
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
    server: MCP_Server | null;
    actionType: "quarantine" | "kill";
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: (serverId: string) => void;
    isPending?: boolean;
}

const config = {
    quarantine: {
        icon: ShieldOff,
        title: "Quarantine Server",
        description: (id: string) =>
            `This will immediately isolate server ${id}, block all inbound agent connections, and sever existing bindings. The server will remain online but inaccessible.`,
        button: "Execute Quarantine",
        pendingButton: "Quarantining...",
        color: "bg-signal text-signal-foreground hover:bg-signal/90",
    },
    kill: {
        icon: AlertTriangle,
        title: "Terminate Server",
        description: (id: string) =>
            `This will immediately shut down server ${id}, destroy all active sessions, sever all agent bindings, and revoke all access tokens. This action is irreversible.`,
        button: "Execute Kill Switch",
        pendingButton: "Executing...",
        color: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
    },
};

export function ServerActionDialog({ server, actionType, open, onOpenChange, onConfirm, isPending }: Props) {
    const [confirmText, setConfirmText] = useState("");

    if (!server) return null;

    const cfg = config[actionType];
    const Icon = cfg.icon;
    const isConfirmed = confirmText === server.id;

    return (
        <AlertDialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setConfirmText(""); }}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle className="flex items-center gap-2">
                        <Icon className="h-5 w-5 text-destructive" />
                        {cfg.title}: {server.name}
                    </AlertDialogTitle>
                    <AlertDialogDescription className="space-y-3">
                        <span className="block">
                            {actionType === "quarantine"
                                ? <>This will immediately isolate server <span className="font-mono-id font-semibold text-foreground">{server.id}</span>, block all inbound agent connections, and sever existing bindings. The server will remain online but inaccessible.</>
                                : <>This will immediately shut down server <span className="font-mono-id font-semibold text-foreground">{server.id}</span>, destroy all active sessions, sever all agent bindings, and revoke all access tokens. This action is irreversible.</>
                            }
                        </span>
                        <span className="block text-xs text-muted-foreground">
                            All {server.connectedAgents} connected agent(s) will lose access. {server.toolsExposed} exposed tool(s) will become unavailable.
                        </span>
                    </AlertDialogDescription>
                </AlertDialogHeader>

                <div className="mt-2 space-y-2">
                    <label className="text-sm text-muted-foreground">
                        Type <span className="font-mono-id font-semibold text-foreground">{server.id}</span> to confirm:
                    </label>
                    <Input
                        value={confirmText}
                        onChange={(e) => setConfirmText(e.target.value)}
                        placeholder={server.id}
                        className="font-mono-id bg-secondary border-border"
                        autoFocus
                    />
                </div>

                <AlertDialogFooter>
                    <AlertDialogCancel onClick={() => setConfirmText("")}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                        className={`${cfg.color} disabled:opacity-40 disabled:cursor-not-allowed`}
                        disabled={!isConfirmed || isPending}
                        onClick={() => { onConfirm(server.id); setConfirmText(""); }}
                    >
                        {isPending ? cfg.pendingButton : cfg.button}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  LayoutDashboard,
  Radar,
  ShieldAlert,
  DollarSign,
  ScrollText,
  Zap,
  Search,
} from "lucide-react";

const navCommands = [
  { label: "Executive Overview", icon: LayoutDashboard, path: "/dashboard" },
  { label: "Discovery & Governance", icon: Radar, path: "/discovery" },
  { label: "Security Command", icon: ShieldAlert, path: "/security" },
  { label: "Cost Intelligence", icon: DollarSign, path: "/cost" },
  { label: "Audit Log", icon: ScrollText, path: "/audit" },
];

const actionCommands = [
  { label: "Kill Rogue Agent", icon: Zap, action: "kill-rogue" },
  { label: "Search Agents", icon: Search, action: "search-agents" },
];

const researchCommands = [
  { label: "AI Agent Risk Assessment Framework", icon: Search, description: "NIST AI RMF compliance patterns" },
  { label: "MCP Protocol Security Analysis", icon: Search, description: "Tool-use attack vectors & mitigations" },
  { label: "LLM Cost Optimization Strategies", icon: Search, description: "Token usage, caching, model routing" },
  { label: "AI Governance Policy Templates", icon: Search, description: "Enterprise-grade policy documentation" },
  { label: "Agent Orchestration Best Practices", icon: Search, description: "Multi-agent coordination patterns" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Jump to dashboard, agent, or action..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {navCommands.map((cmd) => (
            <CommandItem
              key={cmd.path}
              onSelect={() => {
                navigate(cmd.path);
                setOpen(false);
              }}
            >
              <cmd.icon className="mr-2 h-4 w-4" />
              {cmd.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Actions">
          {actionCommands.map((cmd) => (
            <CommandItem
              key={cmd.action}
              onSelect={() => setOpen(false)}
            >
              <cmd.icon className="mr-2 h-4 w-4" />
              {cmd.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Research & Insights">
          {researchCommands.map((cmd) => (
            <CommandItem
              key={cmd.label}
              onSelect={() => setOpen(false)}
            >
              <cmd.icon className="mr-2 h-4 w-4" />
              <div className="flex flex-col">
                <span>{cmd.label}</span>
                <span className="text-xs text-muted-foreground">{cmd.description}</span>
              </div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

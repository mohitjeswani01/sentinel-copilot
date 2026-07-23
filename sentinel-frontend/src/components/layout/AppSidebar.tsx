import {
  LayoutDashboard,
  Radar,
  ShieldAlert,
  DollarSign,
  ScrollText,
  LogOut,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation, useNavigate } from "react-router-dom";
import { logout } from "@/services/serviceApi";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const navItems = [
  { title: "Executive Overview", url: "/dashboard", icon: LayoutDashboard },
  { title: "Discovery & Governance", url: "/discovery", icon: Radar },
  { title: "Security Command", url: "/security", icon: ShieldAlert },
  { title: "Cost Intelligence", url: "/cost", icon: DollarSign },
  { title: "Audit Log", url: "/audit", icon: ScrollText },
];

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <Sidebar className="border-r border-border/50">
      <SidebarContent className="pt-4">
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs uppercase tracking-widest text-muted-foreground/60 mb-2">
            Dashboards
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive = location.pathname === item.url;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        end
                        className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors hover:bg-accent"
                        activeClassName="bg-accent text-cyber font-medium"
                      >
                        <item.icon className={`h-4 w-4 shrink-0 ${isActive ? "text-cyber" : ""}`} />
                        <span>{item.title}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <div className="mt-auto p-4 space-y-3">
          <div className="glass-panel rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <div className="h-2 w-2 rounded-full bg-success animate-pulse-glow" />
              <span className="text-xs font-medium">System Online</span>
            </div>
            <p className="text-xs text-muted-foreground"> MCP server connected</p>
            <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-border/30">
              <span className="text-[10px] font-semibold tracking-wide" style={{ color: "#F5A623" }}>
                ⚡ Powered by SigNoz
              </span>
            </div>
          </div>
          <Button variant="ghost" size="sm" className="w-full justify-start text-xs text-muted-foreground hover:text-destructive" onClick={handleLogout}>
            <LogOut className="h-3.5 w-3.5 mr-2" />
            Sign Out
          </Button>
        </div>
      </SidebarContent>
    </Sidebar>
  );
}

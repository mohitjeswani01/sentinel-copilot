import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { Outlet } from "react-router-dom";
import { CommandPalette } from "@/components/CommandPalette";

export function AppLayout() {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 glass-header flex items-center px-4 sticky top-0 z-30">
            <SidebarTrigger className="mr-4" />
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 gradient-cyber rounded-md" />
              <span className="font-semibold text-sm tracking-wide">SENTINEL COPILOT</span>
            </div>
            <div className="ml-auto flex items-center gap-3">
              <button
                onClick={() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono rounded border border-border bg-secondary text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
              >
                ⌘K
              </button>
            </div>
          </header>
          <main className="flex-1 p-6 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette />
    </SidebarProvider>
  );
}

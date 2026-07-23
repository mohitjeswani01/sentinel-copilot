import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import ExecutiveDashboard from "@/pages/ExecutiveDashboard";
import DiscoveryDashboard from "@/pages/DiscoveryDashboard";
import SecurityDashboard from "@/pages/SecurityDashboard";
import CostDashboard from "@/pages/CostDashboard";
import AuditLogDashboard from "@/pages/AuditLogDashboard";
import LoginPage from "@/pages/LoginPage";
import NotFound from "./pages/NotFound";
import { isAuthenticated } from "@/services/serviceApi";

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
            <Route path="/dashboard" element={<ExecutiveDashboard />} />
            <Route path="/discovery" element={<DiscoveryDashboard />} />
            <Route path="/security" element={<SecurityDashboard />} />
            <Route path="/cost" element={<CostDashboard />} />
            <Route path="/audit" element={<AuditLogDashboard />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;

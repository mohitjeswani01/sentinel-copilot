import { useQuery } from "@tanstack/react-query";
import { getExecutiveMetrics } from "@/services/serviceApi";
import { motion } from "framer-motion";
import { TrendingDown, TrendingUp, ShieldAlert, DollarSign, Bot, Shield } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskTooltip } from "@/components/discovery/AgentInspectDialog";
import { DemoDataBadge } from "@/components/DemoDataBadge";

const container = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } };
const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } };

export default function ExecutiveDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["executive-metrics"],
    queryFn: getExecutiveMetrics,
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  const threatColor = {
    low: "text-success-val",
    elevated: "text-signal",
    high: "text-signal",
    critical: "text-threat",
  }[data.threatLevel];

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      {/* Header */}
      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Executive Overview</h1>
        <p className="text-muted-foreground text-sm mt-1">Real-time AI governance intelligence</p>
      </motion.div>

      {/* Bento Grid — Hero row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Money Saved Hero — spans 2 cols */}
        <motion.div variants={item} className="md:col-span-2 glass-panel glow-border rounded-xl p-6 card-hover">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground mb-1">Total Cost Eliminated <DemoDataBadge className="ml-2" /></p>
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-black text-cyber tracking-tight">
                  ${data.moneySaved.toLocaleString()}
                </span>
                <span className="gradient-cyber text-cyber-foreground text-sm font-bold px-2 py-0.5 rounded-full">
                  {data.costReduction}% reduction
                </span>
              </div>
            </div>
            <div className="hidden md:flex items-center justify-center h-16 w-16 rounded-xl bg-cyber\/10">
              <DollarSign className="h-8 w-8 text-cyber" />
            </div>
          </div>
        </motion.div>

        {/* Threat Gauge */}
        <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 card-hover flex flex-col items-center justify-center">
          <div className="flex items-center gap-2 mb-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Threat Level</p>
              <RiskTooltip />
          </div>
          <div className={`text-4xl font-black uppercase tracking-wide ${threatColor} ${data.threatLevel === "critical" ? "threat-pulse" : ""}`}>
            {data.threatLevel}
          </div>
          <p className="text-sm text-muted-foreground mt-2 flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-threat" />
            {data.alertsActive} active alerts
          </p>
        </motion.div>
      </div>

      {/* Bento Grid — KPI cards */}
      <motion.div variants={item} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {data.kpiDeltas.map((kpi, i) => {
          const icons = [Bot, Shield, ShieldAlert, ShieldAlert];
          const Icon = icons[i] || Bot;
          const valueColor = kpi.label === "Avg Trust Score" ? "text-cyber" : "";
          // The API exposes only current values, so a change indicator is shown
          // only when a real delta is present — never a placeholder percentage.
          const hasDelta = typeof kpi.delta === "number";
          const isPositive = kpi.trend === "up" ? kpi.delta! > 0 : kpi.delta! < 0;
          return (
            <div key={kpi.label} className="glass-panel glow-border rounded-xl p-4 card-hover">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-muted-foreground uppercase tracking-wider">{kpi.label}</span>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className={`text-2xl font-bold ${valueColor}`}>{kpi.value}</div>
              {hasDelta ? (
                <div className={`flex items-center gap-1 mt-1 text-xs ${isPositive ? "text-success-val" : "text-threat"}`}>
                  {kpi.delta! > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                  <span>{Math.abs(kpi.delta!)}% from last period</span>
                </div>
              ) : (
                <div className="mt-1 text-xs text-muted-foreground">current value</div>
              )}
            </div>
          );
        })}
      </motion.div>

      {/* Bento Grid — Cost vs Risk Chart.
          The API exposes only point-in-time metrics, so when no historical
          series is available this renders an explicit empty state rather than a
          hardcoded trend line. */}
      <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 card-hover">
        <p className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Cost vs Risk Trend</p>
        {data.costVsRiskTrend.length === 0 ? (
          <div className="h-[240px] flex flex-col items-center justify-center text-center gap-2">
            <p className="text-sm text-muted-foreground">No historical trend data available</p>
            <p className="text-xs text-muted-foreground max-w-md">
              The Sentinel API reports current values only. Historical trends are
              available in the SigNoz dashboards, which retain the
              <span className="font-mono"> sentinel.container.* </span>
              time series.
            </p>
          </div>
        ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data.costVsRiskTrend}>
            <defs>
              <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(187 100% 50%)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(187 100% 50%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(240 4% 16%)" />
            <XAxis dataKey="month" tick={{ fill: "hsl(240 5% 55%)", fontSize: 12 }} axisLine={false} />
            <YAxis tick={{ fill: "hsl(240 5% 55%)", fontSize: 12 }} axisLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(240 6% 6%)",
                border: "1px solid hsl(240 4% 16%)",
                borderRadius: "8px",
                color: "hsl(0 0% 95%)",
                fontSize: 12,
              }}
            />
            <Area type="monotone" dataKey="cost" stroke="hsl(187 100% 50%)" fill="url(#costGrad)" strokeWidth={2} />
            <Line type="monotone" dataKey="risk" stroke="hsl(0 72% 51%)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
        )}
      </motion.div>
    </motion.div>
  );
}

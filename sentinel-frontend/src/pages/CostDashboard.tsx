import { useQuery } from "@tanstack/react-query";
import { getCostAnalytics } from "@/services/serviceApi";
import { motion } from "framer-motion";
import { TrendingDown, TrendingUp, DollarSign, Lightbulb, Flame } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoDataBadge } from "@/components/DemoDataBadge";

const container = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } };
const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } };

export default function CostDashboard() {
  const { data, isLoading } = useQuery({ queryKey: ["cost"], queryFn: getCostAnalytics });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item}>
        <h1 className="text-2xl font-bold tracking-tight">Cost Intelligence</h1>
        <p className="text-muted-foreground text-sm mt-1">Financial governance and optimization</p>
      </motion.div>

      {/* Savings Hero */}
      <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 card-hover">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground mb-1">Total Savings Achieved <DemoDataBadge className="ml-2" /></p>
            <span className="text-4xl font-black text-success-val">${data.totalSaved.toLocaleString()}</span>
            <span className="ml-3 gradient-cyber text-cyber-foreground text-sm font-bold px-2 py-0.5 rounded-full">{data.savingsPercent}%</span>
          </div>
          <DollarSign className="h-10 w-10 text-success hidden md:block" />
        </div>
      </motion.div>

      {/* Stats Row */}
      <motion.div variants={item} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Daily Burn Rate", value: `$${data.burnRate}`, icon: Flame, color: "text-signal" },
          { label: "Total Spend", value: `$${data.totalSpend.toLocaleString()}`, icon: DollarSign, color: "text-foreground" },
          { label: "Projected Monthly", value: `$${data.projectedMonthly.toLocaleString()}`, icon: TrendingDown, color: "text-cyber" },
        ].map((stat) => (
          <div key={stat.label} className="glass-panel glow-border rounded-xl p-4 card-hover">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground uppercase tracking-wider">{stat.label}</span>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </div>
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
          </div>
        ))}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Burn Chart */}
        <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 card-hover">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Daily Cost Burn-Down</p>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.dailyBurn}>
              <defs>
                <linearGradient id="burnGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(25 95% 53%)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(25 95% 53%)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="optGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(142 71% 45%)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(142 71% 45%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(240 4% 16%)" />
              <XAxis dataKey="date" tick={{ fill: "hsl(240 5% 55%)", fontSize: 12 }} axisLine={false} />
              <YAxis tick={{ fill: "hsl(240 5% 55%)", fontSize: 12 }} axisLine={false} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(240 6% 6%)", border: "1px solid hsl(240 4% 16%)", borderRadius: "8px", color: "hsl(0 0% 95%)", fontSize: 12 }} />
              <Area type="monotone" dataKey="cost" stroke="hsl(25 95% 53%)" fill="url(#burnGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="optimized" stroke="hsl(142 71% 45%)" fill="url(#optGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Top Cost Offenders */}
        <motion.div variants={item} className="glass-panel glow-border rounded-xl p-6 card-hover">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Top Cost Offenders</p>
          <div className="space-y-3">
            {data.agentCosts.map((agent, i) => (
              <div key={agent.agentName} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-5">{i + 1}.</span>
                  <span className="text-sm font-medium">{agent.agentName}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono-id">${agent.cost}/day</span>
                  <span className={`flex items-center gap-0.5 text-xs ${agent.trend > 0 ? "text-threat" : "text-success-val"}`}>
                    {agent.trend > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                    {Math.abs(agent.trend)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Optimization Insights */}
      <motion.div variants={item}>
        <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Optimization Insights</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.optimizationInsights.map((insight) => (
            <div key={insight.title} className="glass-panel glow-border rounded-xl p-4 card-hover">
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-lg bg-cyber\/10 flex items-center justify-center shrink-0">
                  <Lightbulb className="h-4 w-4 text-cyber" />
                </div>
                <div>
                  <p className="font-medium text-sm">{insight.title}</p>
                  <p className="text-xs text-muted-foreground mt-1">{insight.impact}</p>
                  <p className="text-xs text-success-val font-semibold mt-1">Save ${insight.savings.toLocaleString()}/mo</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

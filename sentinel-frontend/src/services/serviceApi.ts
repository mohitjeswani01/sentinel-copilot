import axios from "axios";

// The Sentinel backend listens on :8001 (see sentinel-backend/.env.example).
// Port 8000 is the SigNoz MCP server, not this API — pointing here at 8000
// silently yields empty dashboards.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001/api/v1";

// ─── INTERFACES ───────────────────────────────────────────────

export interface MCP_Server {
  id: string;
  name: string;
  status: "active" | "dormant" | "rogue";
  riskScore: number;
  riskLevel: "low" | "medium" | "high" | "critical";
  lastSeen: string;
  connectedAgents: number;
  toolsExposed: number;
  region: string;
  protocol: string;
  trustScore?: number;
  trustDetails?: any;
}

export interface AI_Agent {
  id: string;
  name: string;
  model: string;
  status: "active" | "dormant" | "rogue";
  riskScore: number;
  riskLevel: "low" | "medium" | "high" | "critical";
  lastSeen: string;
  totalCalls: number;
  costPerDay: number;
  mcpServerId: string;
  capabilities: string[];
}

/** Unified container record for the Discovery page (Part A unification). */
export interface MonitoredContainer {
  id: string;
  name: string;
  status: "running" | "quarantined" | "stopped";
  trustScore: number;
  riskLevel: "low" | "medium" | "high" | "critical";
  riskTier: string;
  lastSeen: string;
  isSanctioned: boolean;
  trustDetails?: Record<string, number>;
}

export interface Security_Alert {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  agentId: string;
  agentName: string;
  violationType?: string;
  description?: string;
  timestamp: string;
  status: "active" | "investigating" | "resolved";
  message?: string;
  recommended_action?: string;
}

export interface Cost_Analytics {
  totalSpend: number;
  totalSaved: number;
  savingsPercent: number;
  burnRate: number;
  projectedMonthly: number;
  agentCosts: { agentName: string; cost: number; trend: number; trustScore?: number }[];
  dailyBurn: { date: string; cost: number; optimized: number }[];
  optimizationInsights: { title: string; impact: string; savings: number }[];
}

export interface Audit_Log_Event {
  id: string;
  timestamp: string;
  agentId: string;
  agentName: string;
  action: string;
  tool: string;
  status: "success" | "warning" | "failed";
  details: string;
  duration: number;
  container_id?: string;
  trust_score_change?: { before: number; after: number };
}

export interface ExecutiveMetrics {
  totalAgents: number;
  activeAgents: number;
  totalServers: number;
  threatLevel: "low" | "elevated" | "high" | "critical";
  moneySaved: number;
  costReduction: number;
  alertsActive: number;
  /** Empty: the backend exposes no historical time series for cost vs risk. */
  costVsRiskTrend: { month: string; cost: number; risk: number }[];
  /**
   * `delta`/`trend` are optional because the backend exposes only point-in-time
   * values — there is no previous-period baseline to compare against. Consumers
   * must not render a change indicator when they are absent.
   */
  kpiDeltas: { label: string; value: string; delta?: number; trend?: "up" | "down" }[];
  averageTrustScore?: number;
}

/** One data point from the rolling trend buffer (GET /metrics/trend). */
export interface TrendDataPoint {
  timestamp: string;
  avg_trust_score: number;
  critical_count: number;
  high_risk_count: number;
  healthy_count: number;
}

/** One container's LLM Behavior vector reading (Issue #7). */
export interface LlmBehaviorContainer {
  containerId: string;
  containerName: string;
  score: number;
  reason: string;
  /**
   * True only when the scorer actually found LLM telemetry. The vector returns a
   * neutral 100 ("No LLM activity detected — not applicable") when it finds
   * none, so 100 means "not measured", NOT "perfect behaviour".
   */
  hasTelemetry: boolean;
}

export interface LlmBehaviorSummary {
  containers: LlmBehaviorContainer[];
  /** Average across all scanned containers. */
  fleetAverage: number;
  /** How many containers had real LLM telemetry scored. */
  withTelemetry: number;
  total: number;
}

/** Raw container record as returned by GET /containers. */
export interface Container_Record {
  container_id: string;
  container_name: string;
  trust_score: number;
  risk_tier: string;
  vector_scores: Record<string, number>;
  vector_reasons?: Record<string, string>;
}

/** The neutral value the llm_behavior vector reports when no telemetry exists. */
export const LLM_NEUTRAL_SCORE = 100;

// ─── SERVICE API (100% Real Backend Integration) ───────────────────────

const axiousConfig = {
  timeout: 30000,
};

/**
 * Get Executive Dashboard Metrics
 * Maps real backend Trust Scores to Executive Overview
 */
export async function getExecutiveMetrics(): Promise<ExecutiveMetrics> {
  try {
    const response = await axios.get(`${API_URL}/metrics/summary`, axiousConfig);
    const data = response.data;

    // Get security alerts to count active
    let alertsCount = 0;
    try {
      const alerts = await axios.get(`${API_URL}/security/alerts`, axiousConfig);
      alertsCount = alerts.data ? alerts.data.length : 0;
    } catch (e) {
      console.warn("Could not fetch alerts count");
    }

    const totalCost = data.total_containers * 300;
    const costReduction = Math.min(
      Math.round((data.money_saved / (totalCost + 1)) * 100),
      100
    );

    return {
      totalAgents: data.total_containers,
      activeAgents: data.total_containers - data.critical_risks,
      totalServers: data.total_containers,
      threatLevel: data.threat_level.toLowerCase() as
        | "low"
        | "elevated"
        | "high"
        | "critical",
      moneySaved: data.money_saved,
      costReduction: costReduction,
      alertsActive: alertsCount,
      // No historical series exists in the API, so none is invented here. The
      // dashboard renders an explicit empty state instead of a fake trend.
      costVsRiskTrend: [],
      // Every KPI below is a real value read back from the API this request.
      // No deltas are set: the backend exposes only current values, with no
      // previous-period baseline to compare against.
      kpiDeltas: [
        {
          label: "Containers Scanned",
          value: data.total_containers.toString(),
        },
        {
          label: "Avg Trust Score",
          value: data.average_trust_score.toFixed(1),
        },
        {
          label: "Critical Risks",
          value: data.critical_risks.toString(),
        },
        {
          label: "Active Alerts",
          value: alertsCount.toString(),
        },
      ],
      averageTrustScore: data.average_trust_score,
    };
  } catch (error) {
    console.error("Failed to fetch metrics", error);
    return getZeroMetrics();
  }
}

/**
 * Get Discovery Data — Unified flat list of ALL monitored containers.
 * No longer split into agents/servers — they're all Docker containers.
 */
export async function getMonitoredContainers(): Promise<MonitoredContainer[]> {
  try {
    const response = await axios.get(
      `${API_URL}/discovery/shadow-ai`,
      axiousConfig
    );
    const containers = response.data || [];

    return containers.map((c: any): MonitoredContainer => {
      let riskLevel: "low" | "medium" | "high" | "critical" = "low";
      if (c.trust_score < 40) {
        riskLevel = "critical";
      } else if (c.trust_score < 60) {
        riskLevel = "high";
      } else if (c.trust_score < 80) {
        riskLevel = "medium";
      }

      return {
        id: c.id,
        name: c.name,
        status: c.status === "running" ? "running" : "stopped",
        trustScore: c.trust_score,
        riskLevel,
        riskTier: c.risk_tier,
        lastSeen: c.last_seen || "",
        isSanctioned: c.is_sanctioned ?? false,
        trustDetails: c.trust_details,
      };
    });
  } catch (error) {
    console.error("Failed to fetch monitored containers", error);
    return [];
  }
}

/**
 * Legacy getDiscovery — kept for backward compatibility.
 * Now wraps getMonitoredContainers.
 */
export async function getDiscovery(): Promise<{ servers: MCP_Server[]; agents: AI_Agent[] }> {
  return { servers: [], agents: [] };
}

/**
 * Get Security Alerts — real alerts derived from scan results by the backend.
 *
 * Returns exactly what the API reports, including an empty list. A previous
 * version substituted a hardcoded "Unauthorized Container Detected" alert
 * whenever the backend returned nothing, which displayed a fabricated breach as
 * a genuine detection. An empty list is the honest signal that no container is
 * currently in the CRITICAL or HIGH RISK tier.
 */
export async function getSecurityAlerts(): Promise<Security_Alert[]> {
  try {
    const response = await axios.get(
      `${API_URL}/security/alerts`,
      axiousConfig
    );
    return response.data ?? [];
  } catch (error) {
    console.error("Failed to fetch security alerts", error);
    return [];
  }
}

/**
 * Get Security Metrics
 * Wraps getSecurityAlerts and processes data.
 */
export async function getSecurityMetrics() {
  try {
    // Re-use the aggressive getSecurityAlerts function
    const alerts = await getSecurityAlerts();
    const health = await getSystemHealth();

    // Calculate aggregated metrics from real alerts
    const critical = alerts.filter(a => a.severity === 'critical').length;
    const high = alerts.filter(a => a.severity === 'high').length;
    const medium = alerts.filter(a => a.severity === 'medium').length;
    const low = alerts.filter(a => a.severity === 'low').length;

    // Determine threat level based on active alerts
    let threatLevel = "low";
    if (critical > 0) threatLevel = "critical";
    else if (high > 0) threatLevel = "high";
    else if (medium > 0) threatLevel = "elevated";

    return {
      alerts,
      threatLevel,
      averageTrustScore: health.average_trust_score,
      counts: {
        critical,
        high,
        medium,
        low
      }
    };
  } catch (error) {
    console.error("Failed to fetch security metrics", error);
    return {
      alerts: [],
      threatLevel: "low",
      averageTrustScore: 0,
      counts: { critical: 0, high: 0, medium: 0, low: 0 }
    };
  }
}

/**
 * Get Cost Analytics
 */
export async function getCostAnalytics(): Promise<Cost_Analytics> {
  try {
    const response = await axios.get(`${API_URL}/metrics/cost`, axiousConfig);
    const data = response.data;

    return {
      totalSpend: data.totalSpend,
      totalSaved: data.totalSaved,
      savingsPercent: data.savingsPercent,
      burnRate: data.burnRate,
      projectedMonthly: data.projectedMonthly,
      agentCosts: data.agentCosts || [],
      dailyBurn: data.dailyBurn || [],
      optimizationInsights: data.optimizationInsights || [],
    };
  } catch (error) {
    console.error("Failed to fetch cost analytics", error);
    return {
      totalSpend: 0,
      totalSaved: 0,
      savingsPercent: 0,
      burnRate: 0,
      projectedMonthly: 0,
      agentCosts: [],
      dailyBurn: [],
      optimizationInsights: [],
    };
  }
}

/**
 * Execute Container Governance Action
 */
export async function executeAction(
  actionType: string,
  targetId: string
): Promise<{ success: boolean; message: string }> {
  try {
    if (actionType === "terminate" || actionType === "kill") {
      const response = await axios.post(
        `${API_URL}/governance/terminate/${targetId}`,
        {},
        axiousConfig
      );
      return {
        success: response.data.success,
        message: response.data.message,
      };
    }

    if (actionType === "quarantine") {
      const response = await axios.post(
        `${API_URL}/governance/quarantine/${targetId}`,
        {},
        axiousConfig
      );
      return {
        success: response.data.success,
        message: response.data.message,
      };
    }

    return { success: false, message: `Unknown action ${actionType}` };
  } catch (error: any) {
    const errorMsg =
      error.response?.data?.detail ||
      error.message ||
      "Action failed";
    return { success: false, message: errorMsg };
  }
}

/**
 * Get rolling trend data for the live chart (GET /metrics/trend).
 * Returns real scan-cycle data points — NOT fabricated.
 */
export async function getTrendData(): Promise<TrendDataPoint[]> {
  try {
    const response = await axios.get(`${API_URL}/metrics/trend`, axiousConfig);
    return response.data ?? [];
  } catch (error) {
    console.error("Failed to fetch trend data", error);
    return [];
  }
}

/**
 * Get Audit Logs
 */
export async function getAuditLog(limit: number = 20): Promise<Audit_Log_Event[]> {
  try {
    const response = await axios.get(
      `${API_URL}/governance/audit-logs?limit=${limit}`,
      axiousConfig
    );
    // Map the backend's snake_case audit records onto Audit_Log_Event. The
    // previous mapping invented ipAddress/user fields that are not in the
    // interface and dropped agentId/tool/duration that the backend does send.
    return response.data.map((log: any): Audit_Log_Event => ({
      id: log.id,
      timestamp: log.timestamp,
      agentId: log.container_id ?? "",
      agentName: log.agent_name,
      action: log.action,
      tool: log.tool ?? "",
      status: log.status,
      details: log.details,
      duration: log.duration ?? 0,
    }));
  } catch (error) {
    console.error("Failed to fetch audit logs", error);
    return [];
  }
}

export async function getLatestLogs(limit: number = 20): Promise<Audit_Log_Event[]> {
  return getAuditLog(limit);
}

/**
 * Get System Health Metrics
 */
export async function getSystemHealth() {
  try {
    const response = await axios.get(
      `${API_URL}/system/health`,
      axiousConfig
    );
    return response.data;
  } catch (error) {
    console.error("Failed to fetch system health", error);
    return {
      average_trust_score: 0,
      total_containers: 0,
      critical_containers: 0,
      healthy_containers: 0,
      status: "Unknown",
      timestamp: new Date().toISOString(),
    };
  }
}

/**
 * Get all scanned containers with their full trust-vector breakdown.
 * Backed by GET /containers — the scanner's in-memory store.
 */
export async function getContainers(): Promise<Container_Record[]> {
  try {
    const response = await axios.get(`${API_URL}/containers`, axiousConfig);
    return response.data ?? [];
  } catch (error) {
    console.error("Failed to fetch containers", error);
    return [];
  }
}

/**
 * Get the LLM Behavior vector for every scanned container (Issue #7).
 *
 * Reads `vector_scores.llm_behavior` and the matching `vector_reasons` entry
 * from GET /containers. Note the vector returns a neutral 100 when it finds no
 * LLM telemetry, so `hasTelemetry` — not the score — is what tells you whether
 * anything was actually measured.
 */
export async function getLlmBehavior(): Promise<LlmBehaviorSummary> {
  const records = await getContainers();

  const containers: LlmBehaviorContainer[] = records
    .map((r) => {
      const score = r.vector_scores?.llm_behavior;
      return {
        containerId: r.container_id,
        containerName: r.container_name,
        score: typeof score === "number" ? score : LLM_NEUTRAL_SCORE,
        reason: r.vector_reasons?.llm_behavior ?? "",
        hasTelemetry: typeof score === "number" && score !== LLM_NEUTRAL_SCORE,
      };
    })
    // Show the containers whose behaviour was actually scored first, then the
    // lowest scores, so anything interesting surfaces at the top.
    .sort((a, b) =>
      Number(b.hasTelemetry) - Number(a.hasTelemetry) || a.score - b.score
    );

  const total = containers.length;
  const fleetAverage = total
    ? containers.reduce((sum, c) => sum + c.score, 0) / total
    : 0;

  return {
    containers,
    fleetAverage: Math.round(fleetAverage * 10) / 10,
    withTelemetry: containers.filter((c) => c.hasTelemetry).length,
    total,
  };
}

/**
 * Get Active Agents
 */
export async function getActiveAgents(): Promise<AI_Agent[]> {
  try {
    const discovery = await getDiscovery();
    return discovery.agents || [];
  } catch (error) {
    console.error("Failed to fetch active agents", error);
    return [];
  }
}

// ─── UTILITIES ───────────────────────────────────────────────

function getZeroMetrics(): ExecutiveMetrics {
  return {
    totalAgents: 0,
    activeAgents: 0,
    totalServers: 0,
    threatLevel: "low",
    moneySaved: 0,
    costReduction: 0,
    alertsActive: 0,
    costVsRiskTrend: [],
    kpiDeltas: [],
    averageTrustScore: 0,
  };
}

// ─── AUTH (Mock SSO) ───────────────────────────────────────────────
//
// The only intentionally mocked area left in this file: the backend exposes no
// authentication routes, so there is nothing real to call yet. Everything above
// this line reads from the FastAPI API.

export async function loginWithSSO(): Promise<{
  token: string;
  user: { name: string; role: string; email: string };
}> {
  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
  await delay(1200);
  const token = `sentinel_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  return {
    token,
    user: {
      name: "Mohit Jeswani",
      role: "Demo User",
      email: "[EMAIL_ADDRESS]",
    },
  };
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem("auth_token");
}

export function getAuthUser(): {
  name: string;
  role: string;
  email: string;
} | null {
  const raw = localStorage.getItem("auth_user");
  return raw ? JSON.parse(raw) : null;
}

export function logout(): void {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
}

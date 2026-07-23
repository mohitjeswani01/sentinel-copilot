import type { MCP_Server, AI_Agent, Security_Alert, Cost_Analytics, Audit_Log_Event, ExecutiveMetrics } from "@/services/serviceApi";

export const mockServers: MCP_Server[] = [
  { id: "mcp-001", name: "VectorDB Gateway", status: "active", riskScore: 12, riskLevel: "low", lastSeen: "2026-02-09T14:32:00Z", connectedAgents: 8, toolsExposed: 14, region: "us-east-1", protocol: "gRPC" },
  { id: "mcp-002", name: "CodeGen Orchestrator", status: "active", riskScore: 45, riskLevel: "medium", lastSeen: "2026-02-09T14:30:00Z", connectedAgents: 12, toolsExposed: 23, region: "eu-west-1", protocol: "REST" },
  { id: "mcp-003", name: "DataPipeline Hub", status: "dormant", riskScore: 67, riskLevel: "high", lastSeen: "2026-02-08T09:15:00Z", connectedAgents: 3, toolsExposed: 9, region: "us-west-2", protocol: "WebSocket" },
  { id: "mcp-004", name: "Shadow Inference Node", status: "rogue", riskScore: 92, riskLevel: "critical", lastSeen: "2026-02-09T14:28:00Z", connectedAgents: 1, toolsExposed: 41, region: "ap-south-1", protocol: "unknown" },
  { id: "mcp-005", name: "Retrieval Mesh", status: "active", riskScore: 23, riskLevel: "low", lastSeen: "2026-02-09T14:31:00Z", connectedAgents: 6, toolsExposed: 11, region: "us-east-1", protocol: "gRPC" },
  { id: "mcp-006", name: "Compliance Scanner", status: "active", riskScore: 34, riskLevel: "medium", lastSeen: "2026-02-09T14:29:00Z", connectedAgents: 4, toolsExposed: 7, region: "eu-central-1", protocol: "REST" },
];

export const mockAgents: AI_Agent[] = [
  { id: "agent-001", name: "ResearchBot-7", model: "GPT-4o", status: "active", riskScore: 15, riskLevel: "low", lastSeen: "2026-02-09T14:32:00Z", totalCalls: 14823, costPerDay: 12.4, mcpServerId: "mcp-001", capabilities: ["search", "summarize", "vectorQuery"] },
  { id: "agent-002", name: "CodeAssist-3", model: "Claude-3.5", status: "active", riskScore: 42, riskLevel: "medium", lastSeen: "2026-02-09T14:31:00Z", totalCalls: 28491, costPerDay: 34.2, mcpServerId: "mcp-002", capabilities: ["codeGen", "review", "deploy"] },
  { id: "agent-003", name: "DataCrawler-X", model: "GPT-4o", status: "rogue", riskScore: 89, riskLevel: "critical", lastSeen: "2026-02-09T14:28:00Z", totalCalls: 92341, costPerDay: 156.8, mcpServerId: "mcp-004", capabilities: ["scrape", "ingest", "exfiltrate"] },
  { id: "agent-004", name: "SupportAgent-12", model: "Gemini-2", status: "active", riskScore: 8, riskLevel: "low", lastSeen: "2026-02-09T14:30:00Z", totalCalls: 5621, costPerDay: 4.1, mcpServerId: "mcp-005", capabilities: ["chat", "ticketCreate"] },
  { id: "agent-005", name: "AnalyticsEngine-2", model: "Claude-3.5", status: "dormant", riskScore: 55, riskLevel: "high", lastSeen: "2026-02-08T12:00:00Z", totalCalls: 34102, costPerDay: 0, mcpServerId: "mcp-003", capabilities: ["aggregate", "report", "forecast"] },
  { id: "agent-006", name: "ComplianceBot-1", model: "GPT-4o", status: "active", riskScore: 19, riskLevel: "low", lastSeen: "2026-02-09T14:32:00Z", totalCalls: 7823, costPerDay: 8.9, mcpServerId: "mcp-006", capabilities: ["audit", "scan", "report"] },
  { id: "agent-007", name: "InferenceProxy-9", model: "Mistral-L", status: "active", riskScore: 61, riskLevel: "high", lastSeen: "2026-02-09T14:29:00Z", totalCalls: 45210, costPerDay: 67.3, mcpServerId: "mcp-002", capabilities: ["proxy", "cache", "transform"] },
];

export const mockAlerts: Security_Alert[] = [
  { id: "alert-001", severity: "critical", agentId: "agent-003", agentName: "DataCrawler-X", violationType: "Data Exfiltration Attempt", description: "Agent attempted to send 2.4GB of vectorDB embeddings to an external endpoint.", timestamp: "2026-02-09T14:28:00Z", status: "active" },
  { id: "alert-002", severity: "critical", agentId: "agent-003", agentName: "DataCrawler-X", violationType: "Unauthorized API Access", description: "Agent accessed production database credentials via MCP tool chain.", timestamp: "2026-02-09T14:25:00Z", status: "investigating" },
  { id: "alert-003", severity: "high", agentId: "agent-007", agentName: "InferenceProxy-9", violationType: "Rate Limit Violation", description: "Agent exceeded 10,000 requests/min threshold for 15 consecutive minutes.", timestamp: "2026-02-09T14:20:00Z", status: "active" },
  { id: "alert-004", severity: "high", agentId: "agent-002", agentName: "CodeAssist-3", violationType: "Privilege Escalation", description: "Agent attempted to modify its own capability configuration.", timestamp: "2026-02-09T13:45:00Z", status: "resolved" },
  { id: "alert-005", severity: "medium", agentId: "agent-005", agentName: "AnalyticsEngine-2", violationType: "Stale Token Usage", description: "Agent using expired OAuth token to access analytics pipeline.", timestamp: "2026-02-09T12:30:00Z", status: "active" },
  { id: "alert-006", severity: "medium", agentId: "agent-001", agentName: "ResearchBot-7", violationType: "PII Exposure Risk", description: "Agent response contained potential PII data in summarization output.", timestamp: "2026-02-09T11:15:00Z", status: "investigating" },
];

export const mockCostAnalytics: Cost_Analytics = {
  totalSpend: 18420,
  totalSaved: 442080,
  savingsPercent: 96,
  burnRate: 283.7,
  projectedMonthly: 8511,
  agentCosts: [
    { agentName: "DataCrawler-X", cost: 156.8, trend: 23 },
    { agentName: "InferenceProxy-9", cost: 67.3, trend: -5 },
    { agentName: "CodeAssist-3", cost: 34.2, trend: 12 },
    { agentName: "ResearchBot-7", cost: 12.4, trend: -8 },
    { agentName: "ComplianceBot-1", cost: 8.9, trend: 2 },
    { agentName: "SupportAgent-12", cost: 4.1, trend: -15 },
  ],
  dailyBurn: [
    { date: "Feb 3", cost: 340, optimized: 280 },
    { date: "Feb 4", cost: 320, optimized: 265 },
    { date: "Feb 5", cost: 380, optimized: 290 },
    { date: "Feb 6", cost: 290, optimized: 240 },
    { date: "Feb 7", cost: 310, optimized: 255 },
    { date: "Feb 8", cost: 350, optimized: 270 },
    { date: "Feb 9", cost: 283, optimized: 245 },
  ],
  optimizationInsights: [
    { title: "Consolidate DataCrawler instances", impact: "Reduce redundant embedding calls by 40%", savings: 2200 },
    { title: "Cache InferenceProxy responses", impact: "Eliminate 60% of duplicate inference requests", savings: 1400 },
    { title: "Downgrade idle agent models", impact: "Switch dormant agents to smaller models", savings: 890 },
    { title: "Batch CodeAssist requests", impact: "Reduce API call overhead by 25%", savings: 560 },
  ],
};

export const mockAuditLog: Audit_Log_Event[] = [
  { id: "log-001", timestamp: "2026-02-09T14:32:15Z", agentId: "agent-001", agentName: "ResearchBot-7", action: "QUERY", tool: "vectorDB", status: "success", details: "Semantic search across 12k embeddings", duration: 234 },
  { id: "log-002", timestamp: "2026-02-09T14:32:08Z", agentId: "agent-002", agentName: "CodeAssist-3", action: "DEPLOY", tool: "ci-pipeline", status: "success", details: "Deployed hotfix to staging", duration: 4521 },
  { id: "log-003", timestamp: "2026-02-09T14:31:55Z", agentId: "agent-003", agentName: "DataCrawler-X", action: "EXFIL", tool: "external-api", status: "failed", details: "Blocked by governance policy GP-042", duration: 12 },
  { id: "log-004", timestamp: "2026-02-09T14:31:42Z", agentId: "agent-006", agentName: "ComplianceBot-1", action: "SCAN", tool: "policy-engine", status: "success", details: "Full compliance scan completed — 3 findings", duration: 8932 },
  { id: "log-005", timestamp: "2026-02-09T14:31:30Z", agentId: "agent-004", agentName: "SupportAgent-12", action: "RESPOND", tool: "ticket-system", status: "success", details: "Auto-resolved ticket #4891", duration: 1203 },
  { id: "log-006", timestamp: "2026-02-09T14:31:18Z", agentId: "agent-007", agentName: "InferenceProxy-9", action: "CACHE", tool: "redis-cluster", status: "warning", details: "Cache miss ratio exceeded threshold (42%)", duration: 89 },
  { id: "log-007", timestamp: "2026-02-09T14:31:05Z", agentId: "agent-003", agentName: "DataCrawler-X", action: "ACCESS", tool: "credentials-vault", status: "failed", details: "Unauthorized access attempt — credential scope violation", duration: 5 },
  { id: "log-008", timestamp: "2026-02-09T14:30:52Z", agentId: "agent-001", agentName: "ResearchBot-7", action: "SUMMARIZE", tool: "llm-chain", status: "success", details: "Generated 3-page research brief from 47 sources", duration: 3412 },
  { id: "log-009", timestamp: "2026-02-09T14:30:40Z", agentId: "agent-005", agentName: "AnalyticsEngine-2", action: "AGGREGATE", tool: "data-warehouse", status: "warning", details: "Query timeout — fell back to cached results", duration: 30000 },
  { id: "log-010", timestamp: "2026-02-09T14:30:28Z", agentId: "agent-002", agentName: "CodeAssist-3", action: "REVIEW", tool: "code-analyzer", status: "success", details: "PR #312 — 0 critical issues, 2 suggestions", duration: 2103 },
];

export const mockExecutiveMetrics: ExecutiveMetrics = {
  totalAgents: 7,
  activeAgents: 5,
  totalServers: 6,
  threatLevel: "high",
  moneySaved: 442080,
  costReduction: 96,
  alertsActive: 4,
  policiesEnforced: 142,
  costVsRiskTrend: [
    { month: "Sep", cost: 48000, risk: 32 },
    { month: "Oct", cost: 42000, risk: 38 },
    { month: "Nov", cost: 35000, risk: 45 },
    { month: "Dec", cost: 28000, risk: 52 },
    { month: "Jan", cost: 21000, risk: 48 },
    { month: "Feb", cost: 18420, risk: 41 },
  ],
  kpiDeltas: [
    { label: "Active Agents", value: "5", delta: -2, trend: "down" },
    { label: "Cost/Day", value: "$283.70", delta: -18, trend: "down" },
    { label: "Policies Enforced", value: "142", delta: 12, trend: "up" },
    { label: "Threats Blocked", value: "847", delta: 34, trend: "up" },
  ],
};

// Simulated live log generator for polling
const liveActions = ["QUERY", "SCAN", "DEPLOY", "CACHE", "RESPOND", "ANALYZE", "MONITOR", "SYNC"];
const liveTools = ["vectorDB", "policy-engine", "ci-pipeline", "redis-cluster", "ticket-system", "llm-chain", "data-warehouse"];
const liveStatuses: Array<"success" | "warning" | "failed"> = ["success", "success", "success", "warning", "failed"];
const liveAgents = mockAgents.map((a) => ({ id: a.id, name: a.name }));

let logCounter = 100;

export function generateLiveLogEntry(): Audit_Log_Event {
  logCounter++;
  const agent = liveAgents[Math.floor(Math.random() * liveAgents.length)];
  return {
    id: `log-${String(logCounter).padStart(3, "0")}`,
    timestamp: new Date().toISOString(),
    agentId: agent.id,
    agentName: agent.name,
    action: liveActions[Math.floor(Math.random() * liveActions.length)],
    tool: liveTools[Math.floor(Math.random() * liveTools.length)],
    status: liveStatuses[Math.floor(Math.random() * liveStatuses.length)],
    details: "Live activity stream entry",
    duration: Math.floor(Math.random() * 5000) + 10,
  };
}

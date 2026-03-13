import { useState, useEffect } from "react";

// ─── Icon Components ───────────────────────────────────────────
const Icons = {
  Inbox: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2 8 2 14 14 14 14 8" /><polyline points="5 5 8 8 11 5" /><line x1="8" y1="2" x2="8" y2="8" />
    </svg>
  ),
  Issues: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" /><circle cx="8" cy="8" r="2" />
    </svg>
  ),
  Reviews: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4h12v8H4l-2 2V4z" />
    </svg>
  ),
  Pulse: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 8 4 8 6 3 8 13 10 6 12 8 15 8" />
    </svg>
  ),
  Projects: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" />
    </svg>
  ),
  Search: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="7" cy="7" r="5" /><line x1="11" y1="11" x2="14" y2="14" />
    </svg>
  ),
  Plus: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" />
    </svg>
  ),
  Filter: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="2" y1="4" x2="14" y2="4" /><line x1="4" y1="8" x2="12" y2="8" /><line x1="6" y1="12" x2="10" y2="12" />
    </svg>
  ),
  Chevron: () => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 4 10 8 6 12" />
    </svg>
  ),
  Check: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 8 7 12 13 4" />
    </svg>
  ),
  Clock: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="6" /><polyline points="8 5 8 8 10.5 9.5" />
    </svg>
  ),
  Circle: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="5" />
    </svg>
  ),
  HalfCircle: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" strokeWidth="1.5">
      <circle cx="8" cy="8" r="5" stroke="currentColor" /><path d="M8 3a5 5 0 0 1 0 10V3z" fill="currentColor" />
    </svg>
  ),
  Bolt: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
      <path d="M9 1L4 9h4l-1 6 5-8H8l1-6z" />
    </svg>
  ),
};

// ─── Status Badge ──────────────────────────────────────────────
const StatusIcon = ({ status }) => {
  const map = {
    backlog: { icon: <Icons.Circle />, color: "var(--text-quaternary)" },
    todo: { icon: <Icons.Circle />, color: "var(--accent-orange)" },
    "in-progress": { icon: <Icons.HalfCircle />, color: "var(--accent-yellow)" },
    "in-review": { icon: <Icons.Clock />, color: "var(--accent-blue)" },
    done: { icon: <Icons.Check />, color: "var(--accent-green)" },
    urgent: { icon: <Icons.Bolt />, color: "var(--accent-red)" },
  };
  const s = map[status] || map.backlog;
  return <span style={{ color: s.color, display: "flex", alignItems: "center" }}>{s.icon}</span>;
};

// ─── Priority Badge ────────────────────────────────────────────
const PriorityBadge = ({ level }) => {
  const bars = [1, 2, 3, 4];
  const colors = { 1: "var(--accent-red)", 2: "var(--accent-orange)", 3: "var(--accent-yellow)", 4: "var(--text-quaternary)" };
  return (
    <div style={{ display: "flex", gap: 1, alignItems: "flex-end", height: 12 }}>
      {bars.map((b) => (
        <div key={b} style={{ width: 2.5, height: 3 + b * 2.5, borderRadius: 1, background: b <= level ? colors[level] || "var(--text-quaternary)" : "var(--border-subtle)", opacity: b <= level ? 1 : 0.3 }} />
      ))}
    </div>
  );
};

// ─── Tag ───────────────────────────────────────────────────────
const Tag = ({ label, color }) => (
  <span style={{ fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 3, background: `${color}18`, color, letterSpacing: "0.02em" }}>
    {label}
  </span>
);

// ─── Avatar ────────────────────────────────────────────────────
const Avatar = ({ name, size = 20 }) => {
  const colors = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4"];
  const idx = name.charCodeAt(0) % colors.length;
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", background: colors[idx], display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.45, fontWeight: 600, color: "#fff", flexShrink: 0, letterSpacing: "-0.02em" }}>
      {name.split(" ").map((n) => n[0]).join("").slice(0, 2)}
    </div>
  );
};

// ─── Sparkline ─────────────────────────────────────────────────
const Sparkline = ({ data, color = "var(--accent-blue)", width = 80, height = 24 }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(" ");
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

// ─── Progress Bar ──────────────────────────────────────────────
const ProgressBar = ({ value, color = "var(--accent-blue)" }) => (
  <div style={{ width: 80, height: 4, borderRadius: 2, background: "var(--bg-tertiary)", overflow: "hidden" }}>
    <div style={{ width: `${value}%`, height: "100%", borderRadius: 2, background: color, transition: "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)" }} />
  </div>
);

// ─── MOCK DATA ─────────────────────────────────────────────────
const TEAMS = [
  { id: "ENG", name: "Engineering", color: "#6366f1" },
  { id: "DES", name: "Design", color: "#ec4899" },
  { id: "OPS", name: "Operations", color: "#f59e0b" },
];

const ISSUES = [
  { id: "ENG-421", title: "Pipeline CI/CD — migration vers GitHub Actions", status: "in-progress", priority: 1, assignee: "Gabriel B", team: "ENG", tags: ["infra", "devops"], created: "2h" },
  { id: "ENG-420", title: "Optimiser les requêtes N+1 sur l'API produits", status: "in-review", priority: 2, assignee: "Léa M", team: "ENG", tags: ["perf", "api"], created: "5h" },
  { id: "ENG-419", title: "Implémenter le websocket pour les notifications temps réel", status: "todo", priority: 2, assignee: "Thomas R", team: "ENG", tags: ["feature"], created: "1d" },
  { id: "DES-112", title: "Design system — composants de tableaux de bord", status: "in-progress", priority: 2, assignee: "Clara V", team: "DES", tags: ["design-system"], created: "3h" },
  { id: "ENG-418", title: "Fix memory leak dans le worker de synchronisation", status: "urgent", priority: 1, assignee: "Gabriel B", team: "ENG", tags: ["bug", "critical"], created: "30m" },
  { id: "OPS-089", title: "Configurer le monitoring Prometheus + Grafana", status: "todo", priority: 3, assignee: "Nadia K", team: "OPS", tags: ["monitoring"], created: "2d" },
  { id: "ENG-417", title: "Ajouter les tests e2e pour le flow d'onboarding", status: "backlog", priority: 3, assignee: "Léa M", team: "ENG", tags: ["testing"], created: "3d" },
  { id: "DES-111", title: "Refonte des écrans de paramètres utilisateur", status: "done", priority: 4, assignee: "Clara V", team: "DES", tags: ["ui"], created: "4d" },
  { id: "OPS-088", title: "Automatiser le backup quotidien des bases de données", status: "in-progress", priority: 2, assignee: "Nadia K", team: "OPS", tags: ["infra", "data"], created: "1d" },
  { id: "ENG-416", title: "Migrer les modèles Prisma vers la v5", status: "todo", priority: 3, assignee: "Thomas R", team: "ENG", tags: ["migration"], created: "5d" },
];

const INBOX_ITEMS = [
  { id: 1, type: "mention", text: "Léa t'a mentionné dans ENG-420", issue: "ENG-420", time: "Il y a 5 min", read: false, avatar: "Léa M" },
  { id: 2, type: "assign", text: "ENG-418 t'a été assigné — priorité urgente", issue: "ENG-418", time: "Il y a 30 min", read: false, avatar: "System" },
  { id: 3, type: "comment", text: "Thomas a commenté sur ENG-419", issue: "ENG-419", time: "Il y a 2h", read: false, avatar: "Thomas R" },
  { id: 4, type: "status", text: "DES-111 marqué comme terminé", issue: "DES-111", time: "Il y a 4h", read: true, avatar: "Clara V" },
  { id: 5, type: "review", text: "PR #247 prête pour review", issue: "ENG-420", time: "Il y a 5h", read: true, avatar: "Léa M" },
];

const REVIEWS = [
  { id: "PR-251", title: "feat: real-time notifications via WebSocket", author: "Thomas R", issue: "ENG-419", status: "pending", changes: "+342 / -28", files: 8 },
  { id: "PR-250", title: "perf: optimize N+1 queries on products API", author: "Léa M", issue: "ENG-420", status: "approved", changes: "+89 / -156", files: 4 },
  { id: "PR-247", title: "fix: memory leak in sync worker", author: "Gabriel B", issue: "ENG-418", status: "changes_requested", changes: "+23 / -12", files: 2 },
  { id: "PR-245", title: "chore: migrate Prisma models to v5", author: "Thomas R", issue: "ENG-416", status: "draft", changes: "+567 / -489", files: 15 },
];

const PROJECTS = [
  { id: 1, name: "Infrastructure Modernization", lead: "Gabriel B", progress: 65, status: "on-track", issues: 12, completed: 8, team: "ENG", color: "#6366f1", velocity: [3, 5, 4, 7, 6, 8, 5, 9] },
  { id: 2, name: "Design System v2", lead: "Clara V", progress: 40, status: "at-risk", issues: 8, completed: 3, team: "DES", color: "#ec4899", velocity: [2, 3, 1, 4, 2, 3, 4, 2] },
  { id: 3, name: "API Performance Sprint", lead: "Léa M", progress: 80, status: "on-track", issues: 6, completed: 5, team: "ENG", color: "#10b981", velocity: [4, 6, 5, 7, 8, 6, 7, 9] },
  { id: 4, name: "Observability Stack", lead: "Nadia K", progress: 25, status: "on-track", issues: 10, completed: 2, team: "OPS", color: "#f59e0b", velocity: [1, 2, 1, 3, 2, 3, 4, 3] },
];

const PULSE_DATA = {
  velocity: [12, 18, 15, 22, 19, 25, 21, 28],
  burndown: [45, 40, 38, 32, 28, 25, 20, 14],
  statusDistribution: { backlog: 2, todo: 3, "in-progress": 3, "in-review": 1, done: 1 },
};

// ═══════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════
export default function ProductionManager() {
  const [activeTab, setActiveTab] = useState("inbox");
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { setTimeout(() => setLoaded(true), 100); }, []);

  const navItems = [
    { id: "inbox", label: "Inbox", icon: <Icons.Inbox />, badge: 3 },
    { id: "issues", label: "Issues", icon: <Icons.Issues /> },
    { id: "reviews", label: "Reviews", icon: <Icons.Reviews />, badge: 1 },
    { id: "pulse", label: "Pulse", icon: <Icons.Pulse /> },
  ];

  const workspaceItems = [
    { id: "projects", label: "Projects", icon: <Icons.Projects /> },
  ];

  const renderContent = () => {
    if (activeWorkspace === "projects") return <ProjectsView />;
    switch (activeTab) {
      case "inbox": return <InboxView />;
      case "issues": return <IssuesView selectedIssue={selectedIssue} setSelectedIssue={setSelectedIssue} />;
      case "reviews": return <ReviewsView />;
      case "pulse": return <PulseView />;
      default: return <InboxView />;
    }
  };

  const currentLabel = activeWorkspace ? "Projects" : navItems.find((n) => n.id === activeTab)?.label;

  return (
    <div style={{
      width: "100%", height: "100vh", display: "flex", fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', 'Cascadia Code', monospace",
      background: "var(--bg-primary)", color: "var(--text-primary)", fontSize: 13, overflow: "hidden",
      "--bg-primary": "#0a0a0c", "--bg-secondary": "#111114", "--bg-tertiary": "#1a1a1f", "--bg-hover": "#1e1e24",
      "--bg-active": "#24242c", "--bg-elevated": "#16161b", "--border-subtle": "#222228", "--border-strong": "#2e2e36",
      "--text-primary": "#e8e8ec", "--text-secondary": "#9898a4", "--text-tertiary": "#6b6b78", "--text-quaternary": "#45454f",
      "--accent-blue": "#5b8def", "--accent-green": "#3ecf8e", "--accent-orange": "#f0a050", "--accent-yellow": "#e8c44a",
      "--accent-red": "#ef5555", "--accent-purple": "#a78bfa",
      opacity: loaded ? 1 : 0, transform: loaded ? "none" : "translateY(4px)", transition: "opacity 0.5s ease, transform 0.5s ease",
    }}>
      {/* ── SIDEBAR ─────────────────────────────────── */}
      <div style={{
        width: sidebarCollapsed ? 52 : 220, minWidth: sidebarCollapsed ? 52 : 220, height: "100%",
        background: "var(--bg-secondary)", borderRight: "1px solid var(--border-subtle)",
        display: "flex", flexDirection: "column", transition: "width 0.2s ease, min-width 0.2s ease",
        overflow: "hidden",
      }}>
        {/* Workspace Header */}
        <div style={{
          padding: sidebarCollapsed ? "16px 14px" : "16px 16px", display: "flex", alignItems: "center", gap: 10,
          borderBottom: "1px solid var(--border-subtle)", cursor: "pointer",
        }} onClick={() => setSidebarCollapsed(!sidebarCollapsed)}>
          <div style={{
            width: 24, height: 24, borderRadius: 6, background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", flexShrink: 0,
          }}>P</div>
          {!sidebarCollapsed && (
            <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: "-0.02em", whiteSpace: "nowrap" }}>Production</span>
          )}
        </div>

        {/* Search */}
        {!sidebarCollapsed && (
          <div style={{ padding: "10px 12px 4px" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
              background: "var(--bg-tertiary)", borderRadius: 6, color: "var(--text-tertiary)", fontSize: 12,
            }}>
              <Icons.Search /><span>Search...</span>
              <span style={{ marginLeft: "auto", fontSize: 10, padding: "1px 5px", borderRadius: 3, border: "1px solid var(--border-subtle)", color: "var(--text-quaternary)" }}>⌘K</span>
            </div>
          </div>
        )}

        {/* Nav Items */}
        <div style={{ padding: "8px 8px 0", display: "flex", flexDirection: "column", gap: 1 }}>
          {!sidebarCollapsed && <div style={{ padding: "8px 8px 4px", fontSize: 10, fontWeight: 600, color: "var(--text-quaternary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Navigation</div>}
          {navItems.map((item) => {
            const isActive = !activeWorkspace && activeTab === item.id;
            return (
              <div key={item.id} onClick={() => { setActiveTab(item.id); setActiveWorkspace(null); setSelectedIssue(null); }}
                style={{
                  display: "flex", alignItems: "center", gap: sidebarCollapsed ? 0 : 10,
                  padding: sidebarCollapsed ? "7px 0" : "7px 10px", borderRadius: 6, cursor: "pointer",
                  background: isActive ? "var(--bg-active)" : "transparent",
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  justifyContent: sidebarCollapsed ? "center" : "flex-start",
                  transition: "background 0.15s ease",
                }}>
                <span style={{ display: "flex", flexShrink: 0 }}>{item.icon}</span>
                {!sidebarCollapsed && <span style={{ fontSize: 13, fontWeight: isActive ? 500 : 400 }}>{item.label}</span>}
                {!sidebarCollapsed && item.badge && (
                  <span style={{
                    marginLeft: "auto", fontSize: 10, fontWeight: 600, minWidth: 18, textAlign: "center",
                    padding: "1px 5px", borderRadius: 10, background: "var(--accent-blue)22", color: "var(--accent-blue)",
                  }}>{item.badge}</span>
                )}
              </div>
            );
          })}
        </div>

        {/* Workspace */}
        <div style={{ padding: "12px 8px 0", display: "flex", flexDirection: "column", gap: 1 }}>
          {!sidebarCollapsed && <div style={{ padding: "8px 8px 4px", fontSize: 10, fontWeight: 600, color: "var(--text-quaternary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Workspace</div>}
          {workspaceItems.map((item) => {
            const isActive = activeWorkspace === item.id;
            return (
              <div key={item.id} onClick={() => { setActiveWorkspace(item.id); setSelectedIssue(null); }}
                style={{
                  display: "flex", alignItems: "center", gap: sidebarCollapsed ? 0 : 10,
                  padding: sidebarCollapsed ? "7px 0" : "7px 10px", borderRadius: 6, cursor: "pointer",
                  background: isActive ? "var(--bg-active)" : "transparent",
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  justifyContent: sidebarCollapsed ? "center" : "flex-start",
                  transition: "background 0.15s ease",
                }}>
                <span style={{ display: "flex", flexShrink: 0 }}>{item.icon}</span>
                {!sidebarCollapsed && <span style={{ fontSize: 13, fontWeight: isActive ? 500 : 400 }}>{item.label}</span>}
              </div>
            );
          })}
        </div>

        {/* Teams */}
        {!sidebarCollapsed && (
          <div style={{ padding: "12px 8px 0", display: "flex", flexDirection: "column", gap: 1 }}>
            <div style={{ padding: "8px 8px 4px", fontSize: 10, fontWeight: 600, color: "var(--text-quaternary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Teams</div>
            {TEAMS.map((team) => (
              <div key={team.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 10px", borderRadius: 6, cursor: "pointer", color: "var(--text-secondary)" }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: team.color, flexShrink: 0 }} />
                <span style={{ fontSize: 12 }}>{team.name}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-quaternary)" }}>{team.id}</span>
              </div>
            ))}
          </div>
        )}

        {/* Bottom User */}
        <div style={{ marginTop: "auto", padding: 12, borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", gap: 10 }}>
          <Avatar name="Gabriel B" size={24} />
          {!sidebarCollapsed && <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Gabriel B</span>}
        </div>
      </div>

      {/* ── MAIN CONTENT ────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header Bar */}
        <div style={{
          padding: "0 20px", height: 46, minHeight: 46, display: "flex", alignItems: "center",
          borderBottom: "1px solid var(--border-subtle)", gap: 12,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.02em" }}>{currentLabel}</span>
          <div style={{ flex: 1 }} />
          <div style={{
            display: "flex", alignItems: "center", gap: 6, padding: "4px 10px",
            borderRadius: 6, border: "1px solid var(--border-subtle)", cursor: "pointer", color: "var(--text-tertiary)", fontSize: 12,
          }}>
            <Icons.Filter /><span>Filter</span>
          </div>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            width: 28, height: 28, borderRadius: 6, background: "var(--accent-blue)", cursor: "pointer", color: "#fff",
          }}>
            <Icons.Plus />
          </div>
        </div>

        {/* View Content */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// INBOX VIEW
// ═══════════════════════════════════════════════════════════════
function InboxView() {
  const [hoveredId, setHoveredId] = useState(null);
  const typeIcons = { mention: "@", assign: "→", comment: "💬", status: "●", review: "⟐" };

  return (
    <div style={{ padding: "0" }}>
      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, padding: "0 20px", borderBottom: "1px solid var(--border-subtle)" }}>
        {["All", "Mentions", "Assigned", "Reviews"].map((tab, i) => (
          <div key={tab} style={{
            padding: "10px 14px", fontSize: 12, cursor: "pointer",
            color: i === 0 ? "var(--text-primary)" : "var(--text-tertiary)",
            borderBottom: i === 0 ? "2px solid var(--accent-blue)" : "2px solid transparent",
            fontWeight: i === 0 ? 500 : 400,
          }}>{tab}</div>
        ))}
      </div>

      {INBOX_ITEMS.map((item, i) => (
        <div key={item.id}
          onMouseEnter={() => setHoveredId(item.id)} onMouseLeave={() => setHoveredId(null)}
          style={{
            display: "flex", alignItems: "center", gap: 12, padding: "12px 20px",
            borderBottom: "1px solid var(--border-subtle)",
            background: hoveredId === item.id ? "var(--bg-hover)" : "transparent",
            cursor: "pointer", transition: "background 0.12s ease",
            opacity: item.read ? 0.6 : 1,
            animation: `fadeSlideIn 0.3s ease ${i * 60}ms both`,
          }}>
          {!item.read && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-blue)", flexShrink: 0 }} />}
          {item.read && <div style={{ width: 6, flexShrink: 0 }} />}
          <Avatar name={item.avatar} size={28} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: item.read ? 400 : 500, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.text}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-quaternary)", marginTop: 2 }}>{item.issue}</div>
          </div>
          <span style={{ fontSize: 11, color: "var(--text-quaternary)", flexShrink: 0 }}>{item.time}</span>
        </div>
      ))}

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ISSUES VIEW
// ═══════════════════════════════════════════════════════════════
function IssuesView({ selectedIssue, setSelectedIssue }) {
  const [hoveredId, setHoveredId] = useState(null);
  const [groupBy, setGroupBy] = useState("status");

  const groups = {};
  ISSUES.forEach((issue) => {
    const key = issue[groupBy] || "other";
    if (!groups[key]) groups[key] = [];
    groups[key].push(issue);
  });

  const statusOrder = ["urgent", "in-progress", "in-review", "todo", "backlog", "done"];
  const sortedKeys = groupBy === "status" ? statusOrder.filter((s) => groups[s]) : Object.keys(groups);

  const statusLabels = {
    urgent: "Urgent", "in-progress": "In Progress", "in-review": "In Review",
    todo: "Todo", backlog: "Backlog", done: "Done",
  };

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {/* Issue List */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {/* Group Tabs */}
        <div style={{ display: "flex", gap: 0, padding: "0 20px", borderBottom: "1px solid var(--border-subtle)" }}>
          {["status", "team", "assignee"].map((g) => (
            <div key={g} onClick={() => setGroupBy(g)} style={{
              padding: "10px 14px", fontSize: 12, cursor: "pointer", textTransform: "capitalize",
              color: groupBy === g ? "var(--text-primary)" : "var(--text-tertiary)",
              borderBottom: groupBy === g ? "2px solid var(--accent-blue)" : "2px solid transparent",
              fontWeight: groupBy === g ? 500 : 400,
            }}>{g}</div>
          ))}
        </div>

        {sortedKeys.map((key) => (
          <div key={key}>
            {/* Group Header */}
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "10px 20px",
              background: "var(--bg-secondary)", borderBottom: "1px solid var(--border-subtle)",
              position: "sticky", top: 0, zIndex: 1,
            }}>
              {groupBy === "status" && <StatusIcon status={key} />}
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                {statusLabels[key] || key}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-quaternary)" }}>{groups[key].length}</span>
            </div>

            {/* Issues */}
            {groups[key].map((issue) => (
              <div key={issue.id}
                onClick={() => setSelectedIssue(issue)}
                onMouseEnter={() => setHoveredId(issue.id)} onMouseLeave={() => setHoveredId(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "9px 20px",
                  borderBottom: "1px solid var(--border-subtle)",
                  background: selectedIssue?.id === issue.id ? "var(--bg-active)" : hoveredId === issue.id ? "var(--bg-hover)" : "transparent",
                  cursor: "pointer", transition: "background 0.12s ease",
                }}>
                <PriorityBadge level={issue.priority} />
                <span style={{ fontSize: 11, color: "var(--text-quaternary)", fontWeight: 500, width: 64, flexShrink: 0 }}>{issue.id}</span>
                <StatusIcon status={issue.status} />
                <span style={{ flex: 1, fontSize: 13, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {issue.title}
                </span>
                <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                  {issue.tags.slice(0, 2).map((t) => (
                    <Tag key={t} label={t} color={t === "critical" || t === "bug" ? "var(--accent-red)" : t === "feature" ? "var(--accent-blue)" : "var(--accent-purple)"} />
                  ))}
                </div>
                <Avatar name={issue.assignee} size={20} />
                <span style={{ fontSize: 11, color: "var(--text-quaternary)", width: 28, textAlign: "right", flexShrink: 0 }}>{issue.created}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Issue Detail Panel */}
      {selectedIssue && (
        <div style={{
          width: 340, borderLeft: "1px solid var(--border-subtle)", overflow: "auto",
          background: "var(--bg-secondary)", animation: "slideIn 0.2s ease",
        }}>
          <div style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <span style={{ fontSize: 11, color: "var(--text-quaternary)", fontWeight: 500 }}>{selectedIssue.id}</span>
              <div style={{ flex: 1 }} />
              <span onClick={() => setSelectedIssue(null)} style={{ cursor: "pointer", color: "var(--text-quaternary)", fontSize: 16 }}>×</span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.4, margin: "0 0 20px", letterSpacing: "-0.02em" }}>{selectedIssue.title}</h3>

            {/* Properties */}
            {[
              { label: "Status", value: <div style={{ display: "flex", alignItems: "center", gap: 6 }}><StatusIcon status={selectedIssue.status} /><span style={{ fontSize: 12 }}>{selectedIssue.status}</span></div> },
              { label: "Priority", value: <div style={{ display: "flex", alignItems: "center", gap: 8 }}><PriorityBadge level={selectedIssue.priority} /><span style={{ fontSize: 12 }}>P{selectedIssue.priority}</span></div> },
              { label: "Assignee", value: <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Avatar name={selectedIssue.assignee} size={18} /><span style={{ fontSize: 12 }}>{selectedIssue.assignee}</span></div> },
              { label: "Team", value: <span style={{ fontSize: 12 }}>{selectedIssue.team}</span> },
              { label: "Created", value: <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{selectedIssue.created} ago</span> },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                <span style={{ width: 80, fontSize: 12, color: "var(--text-tertiary)" }}>{label}</span>
                {value}
              </div>
            ))}

            {/* Tags */}
            <div style={{ display: "flex", gap: 4, marginTop: 16, flexWrap: "wrap" }}>
              {selectedIssue.tags.map((t) => (
                <Tag key={t} label={t} color="var(--accent-purple)" />
              ))}
            </div>
          </div>
          <style>{`@keyframes slideIn { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }`}</style>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// REVIEWS VIEW
// ═══════════════════════════════════════════════════════════════
function ReviewsView() {
  const [hoveredId, setHoveredId] = useState(null);
  const statusStyles = {
    pending: { label: "Pending", color: "var(--accent-yellow)", bg: "var(--accent-yellow)18" },
    approved: { label: "Approved", color: "var(--accent-green)", bg: "var(--accent-green)18" },
    changes_requested: { label: "Changes", color: "var(--accent-orange)", bg: "var(--accent-orange)18" },
    draft: { label: "Draft", color: "var(--text-quaternary)", bg: "var(--bg-tertiary)" },
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 0, padding: "0 20px", borderBottom: "1px solid var(--border-subtle)" }}>
        {["All PRs", "Needs Review", "Approved", "Drafts"].map((tab, i) => (
          <div key={tab} style={{
            padding: "10px 14px", fontSize: 12, cursor: "pointer",
            color: i === 0 ? "var(--text-primary)" : "var(--text-tertiary)",
            borderBottom: i === 0 ? "2px solid var(--accent-blue)" : "2px solid transparent",
            fontWeight: i === 0 ? 500 : 400,
          }}>{tab}</div>
        ))}
      </div>

      {REVIEWS.map((pr, i) => {
        const s = statusStyles[pr.status];
        return (
          <div key={pr.id}
            onMouseEnter={() => setHoveredId(pr.id)} onMouseLeave={() => setHoveredId(null)}
            style={{
              display: "flex", alignItems: "center", gap: 14, padding: "14px 20px",
              borderBottom: "1px solid var(--border-subtle)",
              background: hoveredId === pr.id ? "var(--bg-hover)" : "transparent",
              cursor: "pointer", transition: "background 0.12s ease",
              animation: `fadeSlideIn 0.3s ease ${i * 60}ms both`,
            }}>
            <Avatar name={pr.author} size={28} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--accent-blue)", fontWeight: 500 }}>{pr.id}</span>
                <span style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pr.title}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 3 }}>
                <span style={{ fontSize: 11, color: "var(--text-quaternary)" }}>{pr.author}</span>
                <span style={{ fontSize: 10, color: "var(--text-quaternary)" }}>•</span>
                <span style={{ fontSize: 11, color: "var(--text-quaternary)" }}>{pr.issue}</span>
                <span style={{ fontSize: 10, color: "var(--text-quaternary)" }}>•</span>
                <span style={{ fontSize: 11, color: "var(--text-quaternary)" }}>{pr.files} files</span>
              </div>
            </div>
            <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text-tertiary)" }}>{pr.changes}</span>
            <span style={{
              fontSize: 10, fontWeight: 500, padding: "2px 8px", borderRadius: 4,
              background: s.bg, color: s.color,
            }}>{s.label}</span>
          </div>
        );
      })}
      <style>{`@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// PULSE VIEW
// ═══════════════════════════════════════════════════════════════
function PulseView() {
  const { statusDistribution } = PULSE_DATA;
  const totalIssues = Object.values(statusDistribution).reduce((a, b) => a + b, 0);

  const statusColors = {
    done: "var(--accent-green)", "in-review": "var(--accent-blue)", "in-progress": "var(--accent-yellow)",
    todo: "var(--accent-orange)", backlog: "var(--text-quaternary)",
  };
  const statusLabels = {
    done: "Done", "in-review": "In Review", "in-progress": "In Progress", todo: "Todo", backlog: "Backlog",
  };

  return (
    <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Metrics Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[
          { label: "Velocity", value: "28", sub: "+12% vs last week", spark: PULSE_DATA.velocity, color: "var(--accent-blue)" },
          { label: "Burndown", value: "14", sub: "issues remaining", spark: PULSE_DATA.burndown, color: "var(--accent-green)" },
          { label: "Cycle Time", value: "2.4d", sub: "avg resolution", spark: [4, 3.5, 3, 2.8, 3.2, 2.6, 2.5, 2.4], color: "var(--accent-purple)" },
          { label: "Throughput", value: "6/w", sub: "completed per week", spark: [3, 5, 4, 6, 5, 7, 6, 6], color: "var(--accent-orange)" },
        ].map((m) => (
          <div key={m.label} style={{
            padding: 16, borderRadius: 8, border: "1px solid var(--border-subtle)",
            background: "var(--bg-secondary)",
          }}>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 8 }}>{m.label}</div>
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.04em", color: "var(--text-primary)" }}>{m.value}</div>
                <div style={{ fontSize: 11, color: "var(--text-quaternary)", marginTop: 2 }}>{m.sub}</div>
              </div>
              <Sparkline data={m.spark} color={m.color} />
            </div>
          </div>
        ))}
      </div>

      {/* Status Distribution */}
      <div style={{ padding: 16, borderRadius: 8, border: "1px solid var(--border-subtle)", background: "var(--bg-secondary)" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 12 }}>Status Distribution</div>
        {/* Stacked bar */}
        <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", gap: 2, marginBottom: 14 }}>
          {Object.entries(statusDistribution).reverse().map(([status, count]) => (
            <div key={status} style={{ flex: count, background: statusColors[status], borderRadius: 2, transition: "flex 0.5s ease" }} />
          ))}
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {Object.entries(statusDistribution).reverse().map(([status, count]) => (
            <div key={status} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: statusColors[status] }} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{statusLabels[status]}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{count}</span>
              <span style={{ fontSize: 11, color: "var(--text-quaternary)" }}>({Math.round((count / totalIssues) * 100)}%)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Team Activity */}
      <div style={{ padding: 16, borderRadius: 8, border: "1px solid var(--border-subtle)", background: "var(--bg-secondary)" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 14 }}>Team Activity</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            { name: "Gabriel B", completed: 5, inProgress: 2, avatar: "Gabriel B" },
            { name: "Léa M", completed: 4, inProgress: 1, avatar: "Léa M" },
            { name: "Thomas R", completed: 2, inProgress: 2, avatar: "Thomas R" },
            { name: "Clara V", completed: 3, inProgress: 1, avatar: "Clara V" },
            { name: "Nadia K", completed: 1, inProgress: 2, avatar: "Nadia K" },
          ].map((member) => (
            <div key={member.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0" }}>
              <Avatar name={member.avatar} size={24} />
              <span style={{ fontSize: 12, color: "var(--text-primary)", width: 90 }}>{member.name}</span>
              <ProgressBar value={(member.completed / (member.completed + member.inProgress)) * 100} color="var(--accent-green)" />
              <span style={{ fontSize: 11, color: "var(--accent-green)" }}>{member.completed} done</span>
              <span style={{ fontSize: 11, color: "var(--accent-yellow)" }}>{member.inProgress} active</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// PROJECTS VIEW
// ═══════════════════════════════════════════════════════════════
function ProjectsView() {
  const [hoveredId, setHoveredId] = useState(null);
  const statusConfig = {
    "on-track": { label: "On Track", color: "var(--accent-green)" },
    "at-risk": { label: "At Risk", color: "var(--accent-orange)" },
    "off-track": { label: "Off Track", color: "var(--accent-red)" },
  };

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
        {PROJECTS.map((project, i) => {
          const s = statusConfig[project.status];
          return (
            <div key={project.id}
              onMouseEnter={() => setHoveredId(project.id)} onMouseLeave={() => setHoveredId(null)}
              style={{
                padding: 20, borderRadius: 10, border: "1px solid var(--border-subtle)",
                background: hoveredId === project.id ? "var(--bg-hover)" : "var(--bg-secondary)",
                cursor: "pointer", transition: "all 0.2s ease",
                animation: `fadeSlideIn 0.4s ease ${i * 80}ms both`,
              }}>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: project.color, flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.02em", flex: 1 }}>{project.name}</span>
                <span style={{
                  fontSize: 10, fontWeight: 500, padding: "2px 8px", borderRadius: 4,
                  background: `${s.color}18`, color: s.color,
                }}>{s.label}</span>
              </div>

              {/* Progress */}
              <div style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{project.completed}/{project.issues} issues</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: project.color }}>{project.progress}%</span>
                </div>
                <div style={{ width: "100%", height: 4, borderRadius: 2, background: "var(--bg-tertiary)" }}>
                  <div style={{ width: `${project.progress}%`, height: "100%", borderRadius: 2, background: project.color, transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)" }} />
                </div>
              </div>

              {/* Footer */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Avatar name={project.lead} size={20} />
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{project.lead}</span>
                </div>
                <Sparkline data={project.velocity} color={project.color} width={60} height={20} />
              </div>
            </div>
          );
        })}
      </div>
      <style>{`@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}

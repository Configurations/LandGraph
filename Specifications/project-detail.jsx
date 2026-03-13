import { useState, useEffect, useRef } from "react";

// ─── DESIGN TOKENS ─────────────────────────────────────────────
const T = {
  bgPrimary: "#0a0a0c", bgSecondary: "#111114", bgTertiary: "#1a1a1f",
  bgHover: "#1e1e24", bgActive: "#24242c",
  borderSubtle: "#222228", borderStrong: "#2e2e36",
  textPrimary: "#e8e8ec", textSecondary: "#9898a4",
  textTertiary: "#6b6b78", textQuaternary: "#45454f",
  accentBlue: "#5b8def", accentGreen: "#3ecf8e",
  accentOrange: "#f0a050", accentYellow: "#e8c44a",
  accentRed: "#ef5555", accentPurple: "#a78bfa",
};

// ─── ICONS ─────────────────────────────────────────────────────
const Icons = {
  Back: () => <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="10 3 5 8 10 13"/></svg>,
  Circle: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="5"/></svg>,
  CircleDashed: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2"><circle cx="8" cy="8" r="5"/></svg>,
  HalfCircle: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" strokeWidth="1.5"><circle cx="8" cy="8" r="5" stroke="currentColor"/><path d="M8 3a5 5 0 0 1 0 10V3z" fill="currentColor"/></svg>,
  Clock: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="8" cy="8" r="6"/><polyline points="8 5 8 8 10.5 9.5"/></svg>,
  Check: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 8 7 12 13 4"/></svg>,
  Lock: () => <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="8" width="10" height="6" rx="1"/><path d="M5 8V5a3 3 0 0 1 6 0v3"/></svg>,
  Warning: () => <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M8 2L1 14h14L8 2z"/><line x1="8" y1="6" x2="8" y2="10"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/></svg>,
  Link: () => <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M6 10l4-4"/><path d="M9 5h2a3 3 0 0 1 0 6h-1"/><path d="M7 11H5a3 3 0 0 1 0-6h1"/></svg>,
  Settings: () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="8" cy="8" r="2"/><path d="M8 1v2m0 10v2M1 8h2m10 0h2m-2.5-5.5L11 4m-6 8l-1.5 1.5M13.5 13.5L12 12M4 4L2.5 2.5"/></svg>,
  Calendar: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><rect x="2" y="3" width="12" height="11" rx="1"/><line x1="2" y1="7" x2="14" y2="7"/><line x1="5" y1="1" x2="5" y2="4"/><line x1="11" y1="1" x2="11" y2="4"/></svg>,
  Users: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="6" cy="5" r="2.5"/><path d="M1 14c0-3 2.5-5 5-5s5 2 5 5"/><circle cx="11" cy="5" r="2" strokeDasharray="2 1.5"/><path d="M12 9c1.5.5 3 2 3 5" strokeDasharray="2 1.5"/></svg>,
};

// ─── HELPERS ───────────────────────────────────────────────────
const StatusIcon = ({ status, size = 12 }) => {
  const map = {
    backlog: { icon: <Icons.CircleDashed />, color: T.textQuaternary },
    todo: { icon: <Icons.Circle />, color: T.accentOrange },
    "in-progress": { icon: <Icons.HalfCircle />, color: T.accentYellow },
    "in-review": { icon: <Icons.Clock />, color: T.accentBlue },
    done: { icon: <Icons.Check />, color: T.accentGreen },
  };
  const s = map[status] || map.backlog;
  return <span style={{ color: s.color, display: "flex", alignItems: "center", flexShrink: 0 }}>{s.icon}</span>;
};

const Avatar = ({ name, size = 20 }) => {
  const colors = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6","#ec4899","#06b6d4"];
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", background: colors[name.charCodeAt(0) % colors.length], display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.42, fontWeight: 600, color: "#fff", flexShrink: 0 }}>
      {name.split(" ").map(n => n[0]).join("").slice(0, 2)}
    </div>
  );
};

const Tag = ({ label, color }) => (
  <span style={{ fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 3, background: `${color}18`, color, letterSpacing: "0.02em" }}>{label}</span>
);

const PriorityBadge = ({ level }) => {
  const colors = { 1: T.accentRed, 2: T.accentOrange, 3: T.accentYellow, 4: T.textQuaternary };
  return (
    <div style={{ display: "flex", gap: 1, alignItems: "flex-end", height: 12 }}>
      {[1,2,3,4].map(b => <div key={b} style={{ width: 2.5, height: 3 + b*2.5, borderRadius: 1, background: b <= level ? (colors[level]||T.textQuaternary) : T.borderSubtle, opacity: b <= level ? 1 : 0.3 }}/>)}
    </div>
  );
};

const Sparkline = ({ data, color = T.accentBlue, width = 80, height = 24 }) => {
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v,i) => `${(i/(data.length-1))*width},${height-((v-min)/range)*height}`).join(" ");
  return <svg width={width} height={height} style={{ overflow: "visible" }}><polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;
};

// ─── MOCK DATA ─────────────────────────────────────────────────
const PROJECT = {
  id: 1, name: "Infrastructure Modernization", lead: "Gabriel B",
  progress: 65, status: "on-track", team: "ENG", color: "#6366f1",
  description: "Migration complète de l'infrastructure CI/CD, résolution des problèmes de performance critiques, et mise en place des tests end-to-end.",
  startDate: "15 Jan 2026", targetDate: "30 Apr 2026",
  members: [
    { name: "Gabriel B", role: "Lead", tasksTotal: 5, tasksDone: 3 },
    { name: "Léa M", role: "Engineer", tasksTotal: 4, tasksDone: 3 },
    { name: "Thomas R", role: "Engineer", tasksTotal: 3, tasksDone: 2 },
  ],
  velocity: [3,5,4,7,6,8,5,9],
};

const PROJECT_ISSUES = [
  { id: "ENG-421", title: "Pipeline CI/CD — migration vers GitHub Actions", status: "in-progress", priority: 1, assignee: "Gabriel B", tags: ["infra","devops"], created: "2h", isBlocked: false, blockingCount: 2, blockedByCount: 0 },
  { id: "ENG-420", title: "Optimiser les requêtes N+1 sur l'API produits", status: "in-review", priority: 2, assignee: "Léa M", tags: ["perf","api"], created: "5h", isBlocked: false, blockingCount: 1, blockedByCount: 0 },
  { id: "ENG-419", title: "Implémenter le websocket pour les notifications temps réel", status: "todo", priority: 2, assignee: "Thomas R", tags: ["feature"], created: "1d", isBlocked: true, blockingCount: 0, blockedByCount: 2 },
  { id: "ENG-418", title: "Fix memory leak dans le worker de synchronisation", status: "in-progress", priority: 1, assignee: "Gabriel B", tags: ["bug","critical"], created: "30m", isBlocked: false, blockingCount: 1, blockedByCount: 0 },
  { id: "ENG-417", title: "Ajouter les tests e2e pour le flow d'onboarding", status: "backlog", priority: 3, assignee: "Léa M", tags: ["testing"], created: "3d", isBlocked: true, blockingCount: 0, blockedByCount: 1 },
  { id: "ENG-416", title: "Migrer les modèles Prisma vers la v5", status: "todo", priority: 3, assignee: "Thomas R", tags: ["migration"], created: "5d", isBlocked: true, blockingCount: 0, blockedByCount: 1 },
  { id: "ENG-415", title: "Refactorer le service d'authentification", status: "done", priority: 2, assignee: "Gabriel B", tags: ["auth"], created: "7d", isBlocked: false, blockingCount: 0, blockedByCount: 0 },
  { id: "ENG-414", title: "Mise en cache Redis sur les endpoints critiques", status: "done", priority: 2, assignee: "Léa M", tags: ["perf"], created: "8d", isBlocked: false, blockingCount: 0, blockedByCount: 0 },
];

const RELATIONS = [
  { source: "ENG-421", type: "blocks", target: "ENG-419" },
  { source: "ENG-421", type: "blocks", target: "ENG-417" },
  { source: "ENG-418", type: "blocks", target: "ENG-419" },
  { source: "ENG-420", type: "blocks", target: "ENG-416" },
];

const ACTIVITY = [
  { time: "Il y a 30m", user: "Gabriel B", action: "a changé le statut de", issue: "ENG-418", detail: "todo → in-progress" },
  { time: "Il y a 2h", user: "Gabriel B", action: "a commencé", issue: "ENG-421", detail: "" },
  { time: "Il y a 5h", user: "Léa M", action: "a soumis PR-250 pour", issue: "ENG-420", detail: "" },
  { time: "Il y a 1d", user: "Thomas R", action: "a signalé un blocage sur", issue: "ENG-419", detail: "bloqué par ENG-421, ENG-418" },
  { time: "Il y a 2d", user: "Léa M", action: "a terminé", issue: "ENG-414", detail: "" },
  { time: "Il y a 3d", user: "Gabriel B", action: "a terminé", issue: "ENG-415", detail: "" },
];

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════
export default function ProjectDetail() {
  const [loaded, setLoaded] = useState(false);
  const [activeTab, setActiveTab] = useState("issues");
  const [hoveredIssue, setHoveredIssue] = useState(null);
  const [selectedIssue, setSelectedIssue] = useState(null);

  useEffect(() => { setTimeout(() => setLoaded(true), 80); }, []);

  const statusCounts = { backlog: 0, todo: 0, "in-progress": 0, "in-review": 0, done: 0 };
  PROJECT_ISSUES.forEach(i => { statusCounts[i.status]++; });
  const total = PROJECT_ISSUES.length;
  const blockedCount = PROJECT_ISSUES.filter(i => i.isBlocked).length;
  const blockingCount = PROJECT_ISSUES.filter(i => i.blockingCount > 0).length;

  const pipelineSteps = [
    { key: "backlog", label: "Backlog", color: T.textQuaternary },
    { key: "todo", label: "Todo", color: T.accentOrange },
    { key: "in-progress", label: "In Progress", color: T.accentYellow },
    { key: "in-review", label: "In Review", color: T.accentBlue },
    { key: "done", label: "Done", color: T.accentGreen },
  ];

  const font = "'SF Mono','Fira Code','JetBrains Mono','Cascadia Code',monospace";

  return (
    <div style={{
      width: "100%", height: "100vh", background: T.bgPrimary, color: T.textPrimary,
      fontFamily: font, fontSize: 13, overflow: "hidden", display: "flex", flexDirection: "column",
      opacity: loaded ? 1 : 0, transform: loaded ? "none" : "translateY(4px)",
      transition: "opacity 0.4s ease, transform 0.4s ease",
    }}>

      {/* ── PROJECT HEADER ───────────────────────────── */}
      <div style={{ padding: "0 24px", borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        {/* Top bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, height: 46 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: T.textTertiary, padding: "4px 8px", borderRadius: 6, marginLeft: -8 }}>
            <Icons.Back /><span style={{ fontSize: 12 }}>Projects</span>
          </div>
          <div style={{ width: 1, height: 16, background: T.borderSubtle }} />
          <div style={{ width: 10, height: 10, borderRadius: 3, background: PROJECT.color }} />
          <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.02em" }}>{PROJECT.name}</span>
          <span style={{
            fontSize: 10, fontWeight: 500, padding: "2px 8px", borderRadius: 4,
            background: `${T.accentGreen}18`, color: T.accentGreen,
          }}>On Track</span>
          <div style={{ flex: 1 }} />
          <div style={{ color: T.textQuaternary, cursor: "pointer", padding: 4 }}><Icons.Settings /></div>
        </div>

        {/* Meta row */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, paddingBottom: 14, fontSize: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, color: T.textTertiary }}>
            <Avatar name={PROJECT.lead} size={18} />
            <span>{PROJECT.lead}</span>
            <span style={{ color: T.textQuaternary, fontSize: 10 }}>Lead</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, color: T.textTertiary }}>
            <Icons.Calendar />
            <span>{PROJECT.startDate} → {PROJECT.targetDate}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, color: T.textTertiary }}>
            <Icons.Users />
            <span>{PROJECT.members.length} members</span>
          </div>
          {blockedCount > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 3, background: `${T.accentRed}18`, color: T.accentRed, fontWeight: 500 }}>
                <span style={{ marginRight: 3 }}>🔒</span>{blockedCount} blocked
              </span>
            </div>
          )}
          {blockingCount > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 3, background: `${T.accentOrange}18`, color: T.accentOrange, fontWeight: 500 }}>
                <span style={{ marginRight: 3 }}>⚠</span>{blockingCount} blocking
              </span>
            </div>
          )}
        </div>

        {/* ── WORKFLOW PIPELINE ──────────────────────── */}
        <div style={{ display: "flex", gap: 3, marginBottom: 14 }}>
          {pipelineSteps.map(step => {
            const count = statusCounts[step.key];
            const pct = total > 0 ? (count / total) * 100 : 0;
            return (
              <div key={step.key} style={{ flex: Math.max(pct, 4), display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ height: 6, borderRadius: 3, background: count > 0 ? step.color : T.bgTertiary, opacity: count > 0 ? 1 : 0.3, transition: "flex 0.5s ease" }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 10, color: T.textQuaternary }}>{step.label}</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: count > 0 ? step.color : T.textQuaternary }}>{count}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 0 }}>
          {[
            { id: "issues", label: "Issues" },
            { id: "dependencies", label: "Dependencies" },
            { id: "team", label: "Team" },
            { id: "activity", label: "Activity" },
          ].map(tab => (
            <div key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
              padding: "10px 14px", fontSize: 12, cursor: "pointer",
              color: activeTab === tab.id ? T.textPrimary : T.textTertiary,
              borderBottom: activeTab === tab.id ? `2px solid ${T.accentBlue}` : "2px solid transparent",
              fontWeight: activeTab === tab.id ? 500 : 400,
            }}>{tab.label}</div>
          ))}
        </div>
      </div>

      {/* ── CONTENT ──────────────────────────────────── */}
      <div style={{ flex: 1, overflow: "auto", display: "flex" }}>
        {activeTab === "issues" && <IssuesTab hoveredIssue={hoveredIssue} setHoveredIssue={setHoveredIssue} selectedIssue={selectedIssue} setSelectedIssue={setSelectedIssue} />}
        {activeTab === "dependencies" && <DependenciesTab />}
        {activeTab === "team" && <TeamTab />}
        {activeTab === "activity" && <ActivityTab />}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(16px); } to { opacity: 1; transform: translateX(0); } }
      `}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB: ISSUES
// ═══════════════════════════════════════════════════════════════
function IssuesTab({ hoveredIssue, setHoveredIssue, selectedIssue, setSelectedIssue }) {
  const statusOrder = ["in-progress","in-review","todo","backlog","done"];
  const statusLabels = { "in-progress":"In Progress","in-review":"In Review",todo:"Todo",backlog:"Backlog",done:"Done" };
  const groups = {};
  PROJECT_ISSUES.forEach(i => { if (!groups[i.status]) groups[i.status] = []; groups[i.status].push(i); });

  return (
    <div style={{ display: "flex", flex: 1 }}>
      <div style={{ flex: 1, overflow: "auto" }}>
        {statusOrder.filter(s => groups[s]).map(status => (
          <div key={status}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "10px 24px",
              background: T.bgSecondary, borderBottom: `1px solid ${T.borderSubtle}`,
              position: "sticky", top: 0, zIndex: 1,
            }}>
              <StatusIcon status={status} />
              <span style={{ fontSize: 12, fontWeight: 600, color: T.textSecondary }}>{statusLabels[status]}</span>
              <span style={{ fontSize: 11, color: T.textQuaternary }}>{groups[status].length}</span>
            </div>
            {groups[status].map((issue, i) => (
              <div key={issue.id}
                onClick={() => setSelectedIssue(selectedIssue?.id === issue.id ? null : issue)}
                onMouseEnter={() => setHoveredIssue(issue.id)}
                onMouseLeave={() => setHoveredIssue(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "9px 24px",
                  borderBottom: `1px solid ${T.borderSubtle}`,
                  background: selectedIssue?.id === issue.id ? T.bgActive : hoveredIssue === issue.id ? T.bgHover : "transparent",
                  cursor: "pointer", transition: "background 0.12s ease",
                  animation: `fadeIn 0.3s ease ${i * 40}ms both`,
                }}>
                <PriorityBadge level={issue.priority} />
                <span style={{ fontSize: 11, color: T.textQuaternary, fontWeight: 500, width: 64, flexShrink: 0 }}>{issue.id}</span>
                <StatusIcon status={issue.status} />
                {/* Blocked flag */}
                {issue.isBlocked && (
                  <span style={{ color: T.accentRed, display: "flex", alignItems: "center", flexShrink: 0 }}><Icons.Lock /></span>
                )}
                {/* Blocking flag */}
                {issue.blockingCount > 0 && (
                  <span style={{ fontSize: 10, padding: "0 5px", borderRadius: 3, background: `${T.accentOrange}18`, color: T.accentOrange, fontWeight: 500, flexShrink: 0 }}>
                    ⚠ {issue.blockingCount}
                  </span>
                )}
                <span style={{
                  flex: 1, fontSize: 13, color: T.textPrimary,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  opacity: issue.isBlocked ? 0.5 : 1,
                }}>{issue.title}</span>
                <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                  {issue.tags.slice(0,2).map(t => (
                    <Tag key={t} label={t} color={t==="critical"||t==="bug"?T.accentRed:t==="feature"?T.accentBlue:T.accentPurple} />
                  ))}
                </div>
                <Avatar name={issue.assignee} size={20} />
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Detail Panel */}
      {selectedIssue && (
        <div style={{
          width: 320, borderLeft: `1px solid ${T.borderSubtle}`, overflow: "auto",
          background: T.bgSecondary, animation: "slideIn 0.2s ease",
        }}>
          <div style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 11, color: T.textQuaternary, fontWeight: 500 }}>{selectedIssue.id}</span>
              <div style={{ flex: 1 }} />
              <span onClick={() => setSelectedIssue(null)} style={{ cursor: "pointer", color: T.textQuaternary, fontSize: 16 }}>×</span>
            </div>

            {selectedIssue.isBlocked && (
              <div style={{
                padding: "8px 12px", marginBottom: 14, borderRadius: 6,
                background: `${T.accentRed}12`, borderLeft: `3px solid ${T.accentRed}`,
                display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: T.accentRed,
              }}>
                <Icons.Lock />
                <span>Blocked by {selectedIssue.blockedByCount} issue{selectedIssue.blockedByCount > 1 ? "s" : ""}</span>
              </div>
            )}

            <h3 style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.4, margin: "0 0 16px", letterSpacing: "-0.02em" }}>
              {selectedIssue.title}
            </h3>

            {[
              { label: "Status", value: <div style={{ display: "flex", alignItems: "center", gap: 6 }}><StatusIcon status={selectedIssue.status} /><span style={{ fontSize: 12 }}>{selectedIssue.status}</span>{selectedIssue.isBlocked && <span style={{ color: T.accentRed, fontSize: 10 }}>+ blocked</span>}</div> },
              { label: "Priority", value: <div style={{ display: "flex", alignItems: "center", gap: 8 }}><PriorityBadge level={selectedIssue.priority} /><span style={{ fontSize: 12 }}>P{selectedIssue.priority}</span></div> },
              { label: "Assignee", value: <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Avatar name={selectedIssue.assignee} size={18} /><span style={{ fontSize: 12 }}>{selectedIssue.assignee}</span></div> },
              { label: "Created", value: <span style={{ fontSize: 12, color: T.textTertiary }}>{selectedIssue.created} ago</span> },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", padding: "7px 0", borderBottom: `1px solid ${T.borderSubtle}` }}>
                <span style={{ width: 72, fontSize: 12, color: T.textTertiary }}>{label}</span>
                {value}
              </div>
            ))}

            <div style={{ display: "flex", gap: 4, marginTop: 12, flexWrap: "wrap" }}>
              {selectedIssue.tags.map(t => <Tag key={t} label={t} color={T.accentPurple} />)}
            </div>

            {/* Dependencies section */}
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.textSecondary, marginBottom: 10 }}>Dependencies</div>
              {RELATIONS.filter(r => r.source === selectedIssue.id || r.target === selectedIssue.id).map((rel, i) => {
                const isSource = rel.source === selectedIssue.id;
                const otherId = isSource ? rel.target : rel.source;
                const otherIssue = PROJECT_ISSUES.find(x => x.id === otherId);
                const typeLabel = isSource ? "Blocks" : "Blocked by";
                const typeColor = T.accentRed;
                return (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
                    borderBottom: `1px solid ${T.borderSubtle}`,
                  }}>
                    <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 3, background: `${typeColor}18`, color: typeColor, fontWeight: 500, flexShrink: 0 }}>{typeLabel}</span>
                    <span style={{ fontSize: 11, color: T.accentBlue, fontWeight: 500 }}>{otherId}</span>
                    {otherIssue && <StatusIcon status={otherIssue.status} size={10} />}
                    <span style={{ fontSize: 11, color: T.textTertiary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {otherIssue?.title}
                    </span>
                  </div>
                );
              })}
              {RELATIONS.filter(r => r.source === selectedIssue.id || r.target === selectedIssue.id).length === 0 && (
                <span style={{ fontSize: 12, color: T.textQuaternary }}>No dependencies</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB: DEPENDENCIES (graph view)
// ═══════════════════════════════════════════════════════════════
function DependenciesTab() {
  const nodes = PROJECT_ISSUES.map(issue => {
    const x = { backlog: 60, todo: 200, "in-progress": 360, "in-review": 520, done: 680 }[issue.status] || 60;
    const statusGroup = PROJECT_ISSUES.filter(i => i.status === issue.status);
    const idx = statusGroup.indexOf(issue);
    const y = 60 + idx * 80;
    return { ...issue, x, y };
  });

  const statusColors = { backlog: T.textQuaternary, todo: T.accentOrange, "in-progress": T.accentYellow, "in-review": T.accentBlue, done: T.accentGreen };

  return (
    <div style={{ flex: 1, padding: 24, overflow: "auto" }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.textSecondary, marginBottom: 16 }}>Dependency Graph</div>
      <div style={{ background: T.bgSecondary, borderRadius: 10, border: `1px solid ${T.borderSubtle}`, padding: 20, overflow: "auto" }}>
        <svg width="760" height={Math.max(...nodes.map(n => n.y)) + 80} style={{ overflow: "visible" }}>
          {/* Edges */}
          {RELATIONS.map((rel, i) => {
            const from = nodes.find(n => n.id === rel.source);
            const to = nodes.find(n => n.id === rel.target);
            if (!from || !to) return null;
            const dx = to.x - from.x - 100;
            return (
              <g key={i}>
                <path
                  d={`M${from.x + 100},${from.y + 18} C${from.x + 100 + dx * 0.5},${from.y + 18} ${to.x - dx * 0.5},${to.y + 18} ${to.x},${to.y + 18}`}
                  fill="none" stroke={T.accentRed} strokeWidth="1.5" strokeDasharray={rel.type === "blocks" ? "none" : "4 3"} opacity="0.5"
                />
                {/* Arrow */}
                <polygon
                  points={`${to.x},${to.y + 18} ${to.x - 6},${to.y + 14} ${to.x - 6},${to.y + 22}`}
                  fill={T.accentRed} opacity="0.6"
                />
              </g>
            );
          })}

          {/* Nodes */}
          {nodes.map((node, i) => (
            <g key={node.id} style={{ animation: `fadeIn 0.3s ease ${i * 60}ms both` }}>
              <rect x={node.x} y={node.y} width={100} height={36} rx={6}
                fill={T.bgTertiary} stroke={node.isBlocked ? T.accentRed : statusColors[node.status]} strokeWidth={node.isBlocked ? 1.5 : 1} />
              {node.isBlocked && (
                <rect x={node.x} y={node.y} width={100} height={36} rx={6} fill={T.accentRed} opacity="0.06" />
              )}
              <text x={node.x + 10} y={node.y + 15} fontSize="10" fontWeight="600" fill={T.textQuaternary} fontFamily="inherit">{node.id}</text>
              <text x={node.x + 10} y={node.y + 27} fontSize="9" fill={node.isBlocked ? T.accentRed : T.textSecondary} fontFamily="inherit">
                {node.title.length > 14 ? node.title.slice(0, 14) + "…" : node.title}
              </text>
              {node.isBlocked && (
                <g transform={`translate(${node.x + 86}, ${node.y + 4})`}>
                  <circle r="6" fill={T.accentRed} opacity="0.2" />
                  <text x="0" y="3.5" fontSize="8" textAnchor="middle" fill={T.accentRed}>🔒</text>
                </g>
              )}
            </g>
          ))}

          {/* Column headers */}
          {[
            { x: 60, label: "Backlog", color: T.textQuaternary },
            { x: 200, label: "Todo", color: T.accentOrange },
            { x: 360, label: "In Progress", color: T.accentYellow },
            { x: 520, label: "In Review", color: T.accentBlue },
            { x: 680, label: "Done", color: T.accentGreen },
          ].map(col => (
            <text key={col.label} x={col.x + 50} y={40} fontSize="10" fontWeight="600" fill={col.color} textAnchor="middle" fontFamily="inherit" opacity="0.6">{col.label}</text>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 20, marginTop: 14, fontSize: 11, color: T.textTertiary }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 20, height: 2, background: T.accentRed, borderRadius: 1 }} />
          <span>Blocks</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 10, height: 10, borderRadius: 3, border: `1.5px solid ${T.accentRed}`, background: `${T.accentRed}10` }} />
          <span>Blocked issue</span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB: TEAM
// ═══════════════════════════════════════════════════════════════
function TeamTab() {
  return (
    <div style={{ flex: 1, padding: 24 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.textSecondary, marginBottom: 16 }}>Team Workload</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {PROJECT.members.map((member, i) => {
          const memberIssues = PROJECT_ISSUES.filter(x => x.assignee === member.name);
          const blocked = memberIssues.filter(x => x.isBlocked).length;
          return (
            <div key={member.name} style={{
              padding: 16, borderRadius: 8, border: `1px solid ${T.borderSubtle}`, background: T.bgSecondary,
              animation: `fadeIn 0.3s ease ${i * 80}ms both`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                <Avatar name={member.name} size={32} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{member.name}</div>
                  <div style={{ fontSize: 11, color: T.textTertiary }}>{member.role}</div>
                </div>
                <div style={{ flex: 1 }} />
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: T.textPrimary }}>{member.tasksDone}/{member.tasksTotal}</div>
                  <div style={{ fontSize: 10, color: T.textQuaternary }}>completed</div>
                </div>
              </div>

              {/* Progress bar */}
              <div style={{ width: "100%", height: 4, borderRadius: 2, background: T.bgTertiary, marginBottom: 12 }}>
                <div style={{ width: `${(member.tasksDone / member.tasksTotal) * 100}%`, height: "100%", borderRadius: 2, background: T.accentGreen, transition: "width 0.6s ease" }} />
              </div>

              {/* Member's issues */}
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {memberIssues.map(issue => (
                  <div key={issue.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", borderRadius: 4, background: T.bgTertiary }}>
                    <StatusIcon status={issue.status} />
                    {issue.isBlocked && <span style={{ color: T.accentRed, display: "flex" }}><Icons.Lock /></span>}
                    <span style={{ fontSize: 11, color: T.textQuaternary, width: 56, flexShrink: 0 }}>{issue.id}</span>
                    <span style={{ fontSize: 12, color: issue.isBlocked ? T.textQuaternary : T.textSecondary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", opacity: issue.isBlocked ? 0.6 : 1 }}>
                      {issue.title}
                    </span>
                  </div>
                ))}
              </div>
              {blocked > 0 && (
                <div style={{ marginTop: 8, fontSize: 10, color: T.accentRed, display: "flex", alignItems: "center", gap: 4 }}>
                  <Icons.Lock /> {blocked} task{blocked > 1 ? "s" : ""} blocked
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TAB: ACTIVITY
// ═══════════════════════════════════════════════════════════════
function ActivityTab() {
  return (
    <div style={{ flex: 1, padding: 24 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.textSecondary, marginBottom: 16 }}>Recent Activity</div>
      <div style={{ position: "relative", paddingLeft: 20 }}>
        {/* Timeline line */}
        <div style={{ position: "absolute", left: 8, top: 8, bottom: 8, width: 1.5, background: T.borderSubtle, borderRadius: 1 }} />

        {ACTIVITY.map((event, i) => (
          <div key={i} style={{
            position: "relative", paddingBottom: 20,
            animation: `fadeIn 0.3s ease ${i * 60}ms both`,
          }}>
            {/* Dot */}
            <div style={{
              position: "absolute", left: -16, top: 6, width: 9, height: 9, borderRadius: "50%",
              background: T.bgPrimary, border: `2px solid ${T.accentBlue}`,
            }} />

            <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: T.textPrimary }}>{event.user}</span>
              <span style={{ fontSize: 12, color: T.textTertiary }}>{event.action}</span>
              <span style={{ fontSize: 12, fontWeight: 500, color: T.accentBlue }}>{event.issue}</span>
              {event.detail && (
                <span style={{ fontSize: 11, color: T.textQuaternary }}> — {event.detail}</span>
              )}
            </div>
            <div style={{ fontSize: 10, color: T.textQuaternary, marginTop: 2 }}>{event.time}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

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

const font = "'SF Mono','Fira Code','JetBrains Mono','Cascadia Code',monospace";

// ─── ICONS ─────────────────────────────────────────────────────
const Icons = {
  Back: () => <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="10 3 5 8 10 13"/></svg>,
  Sparkle: () => <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1v3M8 12v3M1 8h3M12 8h3M3.5 3.5l2 2M10.5 10.5l2 2M12.5 3.5l-2 2M5.5 10.5l-2 2"/></svg>,
  Send: () => <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2l12 6-12 6V9l8-1-8-1V2z"/></svg>,
  Check: () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 8 7 12 13 4"/></svg>,
  Plus: () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>,
  Calendar: () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><rect x="2" y="3" width="12" height="11" rx="1"/><line x1="2" y1="7" x2="14" y2="7"/><line x1="5" y1="1" x2="5" y2="4"/><line x1="11" y1="1" x2="11" y2="4"/></svg>,
  CircleDashed: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2"><circle cx="8" cy="8" r="5"/></svg>,
  Circle: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="5"/></svg>,
  HalfCircle: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" strokeWidth="1.5"><circle cx="8" cy="8" r="5" stroke="currentColor"/><path d="M8 3a5 5 0 0 1 0 10V3z" fill="currentColor"/></svg>,
  Link: () => <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M6 10l4-4"/><path d="M9 5h2a3 3 0 0 1 0 6h-1"/><path d="M7 11H5a3 3 0 0 1 0-6h1"/></svg>,
  Loader: () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M8 2a6 6 0 1 0 6 6"><animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.8s" repeatCount="indefinite"/></path></svg>,
};

const Avatar = ({ name, size = 20 }) => {
  const colors = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6","#ec4899","#06b6d4"];
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", background: colors[name.charCodeAt(0) % colors.length], display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.42, fontWeight: 600, color: "#fff", flexShrink: 0 }}>
      {name.split(" ").map(n => n[0]).join("").slice(0, 2)}
    </div>
  );
};

// ─── TEAMS DATA ────────────────────────────────────────────────
const TEAMS = [
  { id: "ENG", name: "Engineering", color: "#6366f1", members: ["Gabriel B", "Léa M", "Thomas R"] },
  { id: "DES", name: "Design", color: "#ec4899", members: ["Clara V", "Yann G"] },
  { id: "OPS", name: "Operations", color: "#f59e0b", members: ["Nadia K", "Hugo P"] },
];

// ─── AI MOCK RESPONSES ─────────────────────────────────────────
const AI_RESPONSES = [
  {
    trigger: null, // initial greeting
    text: "Je suis prêt à t'aider à structurer ce projet. Décris-moi ce que tu veux accomplir — les objectifs, les contraintes, le périmètre — et je te proposerai un découpage en issues avec les dépendances.",
  },
  {
    trigger: "default",
    text: "D'après ce que tu me décris, voici comment je structurerais le projet :",
    generates: {
      description: "Migration de l'API monolithique vers une architecture microservices avec gateway centralisé, observabilité, et déploiement progressif.",
      issues: [
        { id: "T-001", title: "Audit de l'API existante — cartographier les endpoints et dépendances", status: "todo", priority: 2, tags: ["audit", "api"] },
        { id: "T-002", title: "Définir le schéma du gateway API (routes, auth, rate-limiting)", status: "todo", priority: 1, tags: ["architecture", "gateway"] },
        { id: "T-003", title: "Extraire le service utilisateurs en microservice autonome", status: "todo", priority: 2, tags: ["migration", "users"] },
        { id: "T-004", title: "Extraire le service produits en microservice autonome", status: "todo", priority: 2, tags: ["migration", "products"] },
        { id: "T-005", title: "Implémenter le gateway API avec Kong/Traefik", status: "todo", priority: 1, tags: ["infra", "gateway"] },
        { id: "T-006", title: "Configurer le tracing distribué (Jaeger/Tempo)", status: "todo", priority: 3, tags: ["observability"] },
        { id: "T-007", title: "Tests de charge et validation de la migration", status: "backlog", priority: 2, tags: ["testing", "perf"] },
        { id: "T-008", title: "Rollout progressif avec feature flags", status: "backlog", priority: 3, tags: ["deployment"] },
      ],
      relations: [
        { source: "T-001", type: "blocks", target: "T-003", reason: "L'audit doit identifier les frontières du service users" },
        { source: "T-001", type: "blocks", target: "T-004", reason: "L'audit doit identifier les frontières du service products" },
        { source: "T-002", type: "blocks", target: "T-005", reason: "Le schéma doit être validé avant l'implémentation" },
        { source: "T-003", type: "blocks", target: "T-007", reason: "Le service doit exister pour être testé" },
        { source: "T-004", type: "blocks", target: "T-007", reason: "Le service doit exister pour être testé" },
        { source: "T-005", type: "blocks", target: "T-007", reason: "Le gateway doit router le trafic pour les tests de charge" },
        { source: "T-007", type: "blocks", target: "T-008", reason: "Les tests doivent passer avant le rollout" },
      ],
    },
    followUp: "Tu veux qu'on ajuste quelque chose ? Je peux ajouter des issues, modifier les priorités, ou revoir les dépendances.",
  },
];

// ═══════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════
export default function CreateProjectFlow() {
  const [step, setStep] = useState("setup"); // "setup" | "ai" | "review"
  const [loaded, setLoaded] = useState(false);

  // Form state
  const [projectName, setProjectName] = useState("");
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [startDate, setStartDate] = useState("");
  const [targetDate, setTargetDate] = useState("");

  // AI state
  const [generatedData, setGeneratedData] = useState(null);

  useEffect(() => { setTimeout(() => setLoaded(true), 80); }, []);

  const canProceedToAI = projectName.trim().length > 0 && selectedTeam;

  return (
    <div style={{
      width: "100%", height: "100vh", background: T.bgPrimary, color: T.textPrimary,
      fontFamily: font, fontSize: 13, overflow: "hidden", display: "flex", flexDirection: "column",
      opacity: loaded ? 1 : 0, transition: "opacity 0.4s ease",
    }}>
      {/* ── TOP BAR ──────────────────────────────────── */}
      <div style={{
        height: 46, minHeight: 46, display: "flex", alignItems: "center", padding: "0 24px",
        borderBottom: `1px solid ${T.borderSubtle}`, gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: T.textTertiary }}>
          <Icons.Back /><span style={{ fontSize: 12 }}>Projects</span>
        </div>
        <div style={{ width: 1, height: 16, background: T.borderSubtle }} />
        <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.02em" }}>New Project</span>
        <div style={{ flex: 1 }} />
        {/* Step indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {[
            { key: "setup", label: "Setup" },
            { key: "ai", label: "AI Planning" },
            { key: "review", label: "Review" },
          ].map((s, i) => {
            const isCurrent = step === s.key;
            const isDone = (s.key === "setup" && (step === "ai" || step === "review")) || (s.key === "ai" && step === "review");
            return (
              <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {i > 0 && <div style={{ width: 20, height: 1, background: isDone || isCurrent ? T.accentBlue : T.borderSubtle }} />}
                <div style={{
                  width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 600,
                  background: isDone ? T.accentBlue : isCurrent ? `${T.accentBlue}22` : T.bgTertiary,
                  color: isDone ? "#fff" : isCurrent ? T.accentBlue : T.textQuaternary,
                  border: isCurrent ? `1.5px solid ${T.accentBlue}` : "1.5px solid transparent",
                }}>
                  {isDone ? <Icons.Check /> : i + 1}
                </div>
                <span style={{ fontSize: 11, color: isCurrent ? T.textPrimary : T.textQuaternary, fontWeight: isCurrent ? 500 : 400 }}>{s.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── CONTENT ──────────────────────────────────── */}
      <div style={{ flex: 1, overflow: "auto", display: "flex" }}>
        {step === "setup" && (
          <SetupStep
            projectName={projectName} setProjectName={setProjectName}
            selectedTeam={selectedTeam} setSelectedTeam={setSelectedTeam}
            startDate={startDate} setStartDate={setStartDate}
            targetDate={targetDate} setTargetDate={setTargetDate}
            canProceed={canProceedToAI}
            onNext={() => setStep("ai")}
          />
        )}
        {step === "ai" && (
          <AIStep
            projectName={projectName}
            selectedTeam={selectedTeam}
            onBack={() => setStep("setup")}
            onGenerated={(data) => setGeneratedData(data)}
            onNext={() => setStep("review")}
            generatedData={generatedData}
          />
        )}
        {step === "review" && (
          <ReviewStep
            projectName={projectName}
            selectedTeam={selectedTeam}
            startDate={startDate}
            targetDate={targetDate}
            generatedData={generatedData}
            onBack={() => setStep("ai")}
          />
        )}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
        input::placeholder { color: ${T.textQuaternary}; }
        input:focus { outline: none; border-color: ${T.accentBlue} !important; }
      `}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 1: SETUP
// ═══════════════════════════════════════════════════════════════
function SetupStep({ projectName, setProjectName, selectedTeam, setSelectedTeam, startDate, setStartDate, targetDate, setTargetDate, canProceed, onNext }) {
  const [hoveredTeam, setHoveredTeam] = useState(null);

  const inputStyle = {
    width: "100%", padding: "10px 14px", fontSize: 13, fontFamily: font,
    background: T.bgTertiary, border: `1px solid ${T.borderSubtle}`, borderRadius: 8,
    color: T.textPrimary, transition: "border-color 0.15s ease",
  };

  return (
    <div style={{ flex: 1, display: "flex", justifyContent: "center", padding: "48px 24px" }}>
      <div style={{ width: 520, animation: "fadeIn 0.4s ease" }}>
        <div style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px", letterSpacing: "-0.03em" }}>Create a new project</h2>
          <p style={{ fontSize: 13, color: T.textTertiary, margin: 0 }}>Set up the basics, then let AI help you plan the details.</p>
        </div>

        {/* Project Name */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: T.textSecondary, marginBottom: 8 }}>
            Project name <span style={{ color: T.accentRed }}>*</span>
          </label>
          <input
            style={inputStyle}
            placeholder="e.g. API Microservices Migration"
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
          />
        </div>

        {/* Team Selection */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: T.textSecondary, marginBottom: 8 }}>
            Team <span style={{ color: T.accentRed }}>*</span>
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            {TEAMS.map(team => {
              const isSelected = selectedTeam?.id === team.id;
              return (
                <div key={team.id}
                  onClick={() => setSelectedTeam(team)}
                  onMouseEnter={() => setHoveredTeam(team.id)}
                  onMouseLeave={() => setHoveredTeam(null)}
                  style={{
                    flex: 1, padding: 14, borderRadius: 8, cursor: "pointer",
                    border: `1.5px solid ${isSelected ? team.color : hoveredTeam === team.id ? T.borderStrong : T.borderSubtle}`,
                    background: isSelected ? `${team.color}10` : T.bgSecondary,
                    transition: "all 0.15s ease",
                  }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 3, background: team.color }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: isSelected ? T.textPrimary : T.textSecondary }}>{team.name}</span>
                  </div>
                  <div style={{ display: "flex", gap: -4 }}>
                    {team.members.slice(0, 3).map((m, i) => (
                      <div key={m} style={{ marginLeft: i > 0 ? -6 : 0, zIndex: 3 - i }}>
                        <Avatar name={m} size={22} />
                      </div>
                    ))}
                    <span style={{ fontSize: 10, color: T.textQuaternary, marginLeft: 6, alignSelf: "center" }}>{team.members.length} members</span>
                  </div>
                  {isSelected && (
                    <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 4, color: team.color, fontSize: 10, fontWeight: 500 }}>
                      <Icons.Check /> Selected
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Dates */}
        <div style={{ display: "flex", gap: 12, marginBottom: 32 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: T.textSecondary, marginBottom: 8 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Icons.Calendar /> Start date</span>
            </label>
            <input style={inputStyle} type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: T.textSecondary, marginBottom: 8 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Icons.Calendar /> Target date</span>
            </label>
            <input style={inputStyle} type="date" value={targetDate} onChange={e => setTargetDate(e.target.value)} />
          </div>
        </div>

        {/* CTA */}
        <button
          onClick={canProceed ? onNext : undefined}
          style={{
            width: "100%", padding: "12px 20px", borderRadius: 8, border: "none", cursor: canProceed ? "pointer" : "not-allowed",
            background: canProceed ? T.accentBlue : T.bgTertiary,
            color: canProceed ? "#fff" : T.textQuaternary,
            fontSize: 13, fontWeight: 600, fontFamily: font,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            transition: "all 0.2s ease",
            opacity: canProceed ? 1 : 0.6,
          }}>
          <Icons.Sparkle />
          Continue with AI Planning
        </button>
        <p style={{ textAlign: "center", fontSize: 11, color: T.textQuaternary, marginTop: 10 }}>
          Or <span style={{ color: T.accentBlue, cursor: "pointer" }}>skip and create empty project</span>
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 2: AI CONVERSATION
// ═══════════════════════════════════════════════════════════════
function AIStep({ projectName, selectedTeam, onBack, onGenerated, onNext, generatedData }) {
  const [messages, setMessages] = useState([
    { role: "ai", text: AI_RESPONSES[0].text },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [hasGenerated, setHasGenerated] = useState(!!generatedData);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!input.trim() || isTyping) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", text: userMsg }]);
    setIsTyping(true);

    // Simulate AI response
    setTimeout(() => {
      const resp = AI_RESPONSES[1];
      setMessages(prev => [...prev, { role: "ai", text: resp.text, generates: resp.generates }]);
      if (resp.generates) {
        onGenerated(resp.generates);
        setHasGenerated(true);
      }
      setIsTyping(false);

      // Follow-up
      setTimeout(() => {
        setMessages(prev => [...prev, { role: "ai", text: resp.followUp }]);
      }, 800);
    }, 2000);
  };

  return (
    <div style={{ flex: 1, display: "flex", animation: "fadeIn 0.3s ease" }}>
      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Chat header */}
        <div style={{
          padding: "12px 24px", borderBottom: `1px solid ${T.borderSubtle}`,
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: `linear-gradient(135deg, ${T.accentPurple}, ${T.accentBlue})`,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Icons.Sparkle />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>AI Project Planner</div>
            <div style={{ fontSize: 10, color: T.textQuaternary }}>Helps you structure "{projectName}" into actionable issues</div>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflow: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              animation: `slideUp 0.3s ease ${Math.min(i * 100, 300)}ms both`,
            }}>
              <div style={{
                maxWidth: msg.generates ? "90%" : "70%",
                padding: "10px 14px", borderRadius: 12,
                background: msg.role === "user" ? T.accentBlue : T.bgSecondary,
                color: msg.role === "user" ? "#fff" : T.textPrimary,
                border: msg.role === "ai" ? `1px solid ${T.borderSubtle}` : "none",
                fontSize: 13, lineHeight: 1.5,
              }}>
                <div>{msg.text}</div>

                {/* Generated issues preview */}
                {msg.generates && (
                  <div style={{ marginTop: 14, borderTop: `1px solid ${T.borderSubtle}`, paddingTop: 12 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: T.textSecondary, marginBottom: 8 }}>
                      {msg.generates.issues.length} issues generated
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {msg.generates.issues.map((issue, j) => (
                        <div key={issue.id} style={{
                          display: "flex", alignItems: "center", gap: 8,
                          padding: "6px 10px", borderRadius: 6, background: T.bgTertiary,
                          animation: `fadeIn 0.2s ease ${j * 60}ms both`,
                        }}>
                          <span style={{ fontSize: 10, color: T.textQuaternary, fontWeight: 500, width: 40, flexShrink: 0 }}>{issue.id}</span>
                          <StatusIconMini status={issue.status} />
                          <PriorityDots level={issue.priority} />
                          <span style={{ fontSize: 12, color: T.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {issue.title}
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* Relations preview */}
                    <div style={{ marginTop: 10, fontSize: 11, fontWeight: 600, color: T.textSecondary, marginBottom: 6 }}>
                      {msg.generates.relations.length} dependencies
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      {msg.generates.relations.map((rel, j) => (
                        <div key={j} style={{
                          display: "flex", alignItems: "center", gap: 6, fontSize: 11,
                          padding: "4px 8px", borderRadius: 4, background: `${T.accentRed}08`,
                        }}>
                          <span style={{ color: T.accentBlue, fontWeight: 500 }}>{rel.source}</span>
                          <span style={{ color: T.accentRed, fontSize: 10 }}>→ blocks →</span>
                          <span style={{ color: T.accentBlue, fontWeight: 500 }}>{rel.target}</span>
                          <span style={{ color: T.textQuaternary, marginLeft: 4 }}>{rel.reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {isTyping && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, animation: "fadeIn 0.2s ease" }}>
              <div style={{
                padding: "10px 14px", borderRadius: 12, background: T.bgSecondary,
                border: `1px solid ${T.borderSubtle}`, display: "flex", gap: 4,
              }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: "50%", background: T.textQuaternary,
                    animation: `pulse 1s ease ${i * 200}ms infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div style={{ padding: "12px 24px", borderTop: `1px solid ${T.borderSubtle}` }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 14px", borderRadius: 10,
            background: T.bgSecondary, border: `1px solid ${T.borderSubtle}`,
          }}>
            <input
              style={{
                flex: 1, background: "transparent", border: "none", color: T.textPrimary,
                fontSize: 13, fontFamily: font, outline: "none",
              }}
              placeholder="Describe your project scope, goals, constraints..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSend()}
            />
            <div onClick={handleSend} style={{
              width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
              background: input.trim() ? T.accentBlue : T.bgTertiary,
              color: input.trim() ? "#fff" : T.textQuaternary,
              cursor: input.trim() ? "pointer" : "default",
              transition: "all 0.15s ease",
            }}>
              <Icons.Send />
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
            <button onClick={onBack} style={{
              padding: "8px 16px", borderRadius: 6, border: `1px solid ${T.borderSubtle}`,
              background: "transparent", color: T.textSecondary, fontSize: 12, fontFamily: font, cursor: "pointer",
            }}>← Back to Setup</button>
            {hasGenerated && (
              <button onClick={onNext} style={{
                padding: "8px 20px", borderRadius: 6, border: "none",
                background: T.accentGreen, color: "#fff", fontSize: 12, fontWeight: 600,
                fontFamily: font, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
              }}>
                Review & Create <span style={{ fontSize: 14 }}>→</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Side panel — live project preview */}
      <div style={{
        width: 300, borderLeft: `1px solid ${T.borderSubtle}`, background: T.bgSecondary,
        overflow: "auto", padding: 20,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textQuaternary, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>
          Project Preview
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <div style={{ width: 10, height: 10, borderRadius: 3, background: selectedTeam?.color || T.textQuaternary }} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>{projectName || "Untitled"}</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 20, fontSize: 12, color: T.textTertiary }}>
          <div style={{ width: 8, height: 8, borderRadius: 2, background: selectedTeam?.color || T.textQuaternary }} />
          <span>{selectedTeam?.name || "No team"}</span>
        </div>

        {generatedData ? (
          <>
            <div style={{ fontSize: 11, color: T.textTertiary, marginBottom: 8 }}>{generatedData.description}</div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSecondary, marginBottom: 8 }}>
                Pipeline ({generatedData.issues.length} issues)
              </div>
              {/* Mini pipeline */}
              <div style={{ display: "flex", gap: 2, marginBottom: 12 }}>
                {["backlog","todo","in-progress","in-review","done"].map(s => {
                  const count = generatedData.issues.filter(i => i.status === s).length;
                  const colors = { backlog: T.textQuaternary, todo: T.accentOrange, "in-progress": T.accentYellow, "in-review": T.accentBlue, done: T.accentGreen };
                  return <div key={s} style={{ flex: Math.max(count, 0.5), height: 4, borderRadius: 2, background: count > 0 ? colors[s] : T.bgTertiary, opacity: count > 0 ? 1 : 0.3 }} />;
                })}
              </div>

              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSecondary, marginBottom: 6 }}>
                Dependencies ({generatedData.relations.length})
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {generatedData.relations.map((r, i) => (
                  <span key={i} style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3, background: `${T.accentRed}12`, color: T.accentRed }}>
                    {r.source} → {r.target}
                  </span>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div style={{ padding: "30px 0", textAlign: "center" }}>
            <div style={{ color: T.textQuaternary, marginBottom: 8 }}><Icons.Sparkle /></div>
            <div style={{ fontSize: 12, color: T.textQuaternary }}>Describe your project to the AI to generate a structure</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 3: REVIEW
// ═══════════════════════════════════════════════════════════════
function ReviewStep({ projectName, selectedTeam, startDate, targetDate, generatedData, onBack }) {
  const [hoveredIssue, setHoveredIssue] = useState(null);

  if (!generatedData) return null;

  const blockedIds = new Set();
  generatedData.relations.forEach(r => { if (r.type === "blocks") blockedIds.add(r.target); });

  return (
    <div style={{ flex: 1, padding: "32px 48px", overflow: "auto", animation: "fadeIn 0.4s ease" }}>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 6px", letterSpacing: "-0.03em" }}>Review your project</h2>
        <p style={{ fontSize: 13, color: T.textTertiary, margin: "0 0 28px" }}>Everything looks good? You can still edit before creating.</p>

        {/* Summary card */}
        <div style={{
          padding: 20, borderRadius: 10, border: `1px solid ${T.borderSubtle}`,
          background: T.bgSecondary, marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: selectedTeam?.color }} />
            <span style={{ fontSize: 16, fontWeight: 700 }}>{projectName}</span>
          </div>
          <div style={{ fontSize: 12, color: T.textTertiary, marginBottom: 12 }}>{generatedData.description}</div>
          <div style={{ display: "flex", gap: 16, fontSize: 12, color: T.textTertiary }}>
            <span>{selectedTeam?.name}</span>
            {startDate && <span>Start: {startDate}</span>}
            {targetDate && <span>Target: {targetDate}</span>}
            <span style={{ color: T.accentBlue }}>{generatedData.issues.length} issues</span>
            <span style={{ color: T.accentRed }}>{generatedData.relations.length} dependencies</span>
          </div>
        </div>

        {/* Issues list */}
        <div style={{
          borderRadius: 10, border: `1px solid ${T.borderSubtle}`,
          background: T.bgSecondary, overflow: "hidden", marginBottom: 20,
        }}>
          <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.borderSubtle}`, fontSize: 12, fontWeight: 600, color: T.textSecondary }}>
            Issues ({generatedData.issues.length})
          </div>
          {generatedData.issues.map((issue, i) => {
            const isBlocked = blockedIds.has(issue.id);
            const blockingCount = generatedData.relations.filter(r => r.source === issue.id && r.type === "blocks").length;
            return (
              <div key={issue.id}
                onMouseEnter={() => setHoveredIssue(issue.id)}
                onMouseLeave={() => setHoveredIssue(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "10px 20px",
                  borderBottom: `1px solid ${T.borderSubtle}`,
                  background: hoveredIssue === issue.id ? T.bgHover : "transparent",
                  animation: `fadeIn 0.3s ease ${i * 40}ms both`,
                }}>
                <PriorityDots level={issue.priority} />
                <span style={{ fontSize: 10, color: T.textQuaternary, fontWeight: 500, width: 40 }}>{issue.id}</span>
                <StatusIconMini status={issue.status} />
                {isBlocked && <span style={{ color: T.accentRed, display: "flex", fontSize: 10 }}>🔒</span>}
                {blockingCount > 0 && <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: `${T.accentOrange}18`, color: T.accentOrange, fontWeight: 500 }}>⚠ {blockingCount}</span>}
                <span style={{
                  flex: 1, fontSize: 13, color: T.textPrimary,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  opacity: isBlocked ? 0.5 : 1,
                }}>{issue.title}</span>
                <div style={{ display: "flex", gap: 3 }}>
                  {issue.tags.map(t => (
                    <span key={t} style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: `${T.accentPurple}15`, color: T.accentPurple }}>{t}</span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Dependencies */}
        <div style={{
          borderRadius: 10, border: `1px solid ${T.borderSubtle}`,
          background: T.bgSecondary, overflow: "hidden", marginBottom: 32,
        }}>
          <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.borderSubtle}`, fontSize: 12, fontWeight: 600, color: T.textSecondary }}>
            Dependencies ({generatedData.relations.length})
          </div>
          {generatedData.relations.map((rel, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 20px",
              borderBottom: `1px solid ${T.borderSubtle}`, fontSize: 12,
              animation: `fadeIn 0.3s ease ${i * 40}ms both`,
            }}>
              <span style={{ color: T.accentBlue, fontWeight: 500 }}>{rel.source}</span>
              <span style={{ padding: "1px 8px", borderRadius: 3, background: `${T.accentRed}15`, color: T.accentRed, fontSize: 10, fontWeight: 500 }}>blocks</span>
              <span style={{ color: T.accentBlue, fontWeight: 500 }}>{rel.target}</span>
              <span style={{ flex: 1 }} />
              <span style={{ color: T.textQuaternary, fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 300 }}>{rel.reason}</span>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onBack} style={{
            padding: "10px 20px", borderRadius: 8, border: `1px solid ${T.borderSubtle}`,
            background: "transparent", color: T.textSecondary, fontSize: 13, fontFamily: font, cursor: "pointer",
          }}>← Back to AI</button>
          <button style={{
            padding: "10px 28px", borderRadius: 8, border: "none",
            background: T.accentGreen, color: "#fff", fontSize: 13, fontWeight: 600,
            fontFamily: font, cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
          }}>
            <Icons.Check /> Create Project
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Mini components ───────────────────────────────────────────
function StatusIconMini({ status }) {
  const map = {
    backlog: { icon: <Icons.CircleDashed />, color: T.textQuaternary },
    todo: { icon: <Icons.Circle />, color: T.accentOrange },
    "in-progress": { icon: <Icons.HalfCircle />, color: T.accentYellow },
    "in-review": { icon: <Icons.HalfCircle />, color: T.accentBlue },
    done: { icon: <Icons.Check />, color: T.accentGreen },
  };
  const s = map[status] || map.backlog;
  return <span style={{ color: s.color, display: "flex", alignItems: "center", flexShrink: 0 }}>{s.icon}</span>;
}

function PriorityDots({ level }) {
  const colors = { 1: T.accentRed, 2: T.accentOrange, 3: T.accentYellow, 4: T.textQuaternary };
  return (
    <div style={{ display: "flex", gap: 1, alignItems: "flex-end", height: 10, flexShrink: 0 }}>
      {[1,2,3,4].map(b => <div key={b} style={{ width: 2, height: 2 + b*2, borderRadius: 1, background: b <= level ? (colors[level]||T.textQuaternary) : T.borderSubtle, opacity: b <= level ? 1 : 0.25 }} />)}
    </div>
  );
}

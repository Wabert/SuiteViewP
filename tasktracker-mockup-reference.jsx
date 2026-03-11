import { useState, useMemo, useRef, useCallback } from "react";

const MOCK_CONTACTS = [
  { name: "John Martinez", email: "john.martinez@company.com" },
  { name: "Sarah Chen", email: "sarah.chen@company.com" },
  { name: "Mike Thompson", email: "mike.thompson@company.com" },
  { name: "Lisa Patel", email: "lisa.patel@company.com" },
  { name: "David Kim", email: "david.kim@company.com" },
  { name: "Rachel Woods", email: "rachel.woods@company.com" },
  { name: "James Taylor", email: "james.taylor@company.com" },
];

const MOCK_TASKS = [
  {
    id: "TSK-001", title: "Review Q4 mortality assumptions for Group Term Life block — actuarial team flagged inconsistencies in the 65+ age band. Need full review and comparison against SOA tables, focus on 65-70 and 70-75 bands.", status: "open", createdDate: "2026-02-03",
    assignees: [{ name: "John Martinez", email: "john.martinez@company.com" }],
    emailSent: true, lastActivity: "2h ago", lastActivitySort: 2, lastActivityFrom: "John Martinez",
    emails: [
      { from: "You", to: "john.martinez@company.com", date: "Feb 3, 2:15 PM", dateSort: 20260203.1415, subject: "[TSK-001] Review Q4 mortality assumptions", body: "John, please review the Q4 mortality assumptions for the Group Term Life block. The actuarial team flagged some inconsistencies in the 65+ age band. Let me know your findings by EOW.", type: "sent", hasAttachment: false },
      { from: "John Martinez", to: "You", date: "Feb 3, 4:30 PM", dateSort: 20260203.1630, subject: "Re: [TSK-001] Review Q4 mortality assumptions", body: "Got it. I pulled the data and I'm seeing a ~12% deviation from expected in the 65-70 band. Running a deeper cut now. Should have full analysis by Thursday. I've attached the preliminary data extract for your review.", type: "received", hasAttachment: true },
    ],
  },
  {
    id: "TSK-002", title: "Update policyholder data extract script to handle new UL product codes (UL-2026-A through UL-2026-F). They aren't being picked up by the daily extract. Update the WHERE clause and add codes to lookup table.", status: "open", createdDate: "2026-02-04",
    assignees: [], emailSent: false, lastActivity: null, lastActivitySort: 999, lastActivityFrom: null, emails: [],
  },
  {
    id: "TSK-003", title: "Reconcile premium variance report — Jan actuals vs forecast off by $340K. Suspect it's the group renewal batch that posted late. Identify top contributing policies and trace the timing discrepancy.", status: "open", createdDate: "2026-02-05",
    assignees: [{ name: "Sarah Chen", email: "sarah.chen@company.com" }],
    emailSent: true, lastActivity: "1d ago", lastActivitySort: 24, lastActivityFrom: "You",
    emails: [
      { from: "You", to: "sarah.chen@company.com", date: "Feb 5, 9:00 AM", dateSort: 20260205.0900, subject: "[TSK-003] Reconcile premium variance report", body: "Sarah, the January premium variance report is showing $340K gap between actuals and forecast. Can you dig into this and identify the top contributing policies? Check if it's the group renewal batch that came in late.", type: "sent", hasAttachment: false },
    ],
  },
  {
    id: "TSK-004", title: "Fix DB2 connection timeout in the daily claims summary job. Likely a connection pooling issue — check pool size and add retry logic. Has been timing out intermittently.", status: "closed", createdDate: "2026-01-28",
    assignees: [{ name: "Mike Thompson", email: "mike.thompson@company.com" }],
    emailSent: true, lastActivity: "5d ago", lastActivitySort: 120, lastActivityFrom: "Mike Thompson",
    emails: [
      { from: "You", to: "mike.thompson@company.com", date: "Jan 28, 11:00 AM", dateSort: 20260128.1100, subject: "[TSK-004] Fix DB2 connection timeout", body: "Mike, the daily claims summary job has been timing out intermittently on the DB2 connection. Can you look at the connection pooling config and see if we need to adjust the timeout parameters?", type: "sent", hasAttachment: false },
      { from: "Mike Thompson", to: "You", date: "Jan 29, 2:00 PM", dateSort: 20260129.1400, subject: "Re: [TSK-004] Fix DB2 connection timeout", body: "Found the issue — the connection pool was maxing out at 5 concurrent connections. Bumped it to 15 and added retry logic. Tested it this morning and it ran clean. Pushing the fix to prod tonight.", type: "received", hasAttachment: false },
    ],
  },
  {
    id: "TSK-005", title: "Prepare experience study data pull for 2020-2025 term life lapse rates. Include all term products, seriatim level, with policy year and duration fields. Output to shared actuarial drive.", status: "open", createdDate: "2026-02-06",
    assignees: [], emailSent: false, lastActivity: null, lastActivitySort: 999, lastActivityFrom: null, emails: [],
  },
  {
    id: "TSK-006", title: "Send TAI data to Jordan for the reinsurance review. Pull from the RI schema and format per the template he sent last week. Jordan needs it for annual review.", status: "open", createdDate: "2026-02-07",
    assignees: [{ name: "Lisa Patel", email: "lisa.patel@company.com" }, { name: "David Kim", email: "david.kim@company.com" }],
    emailSent: true, lastActivity: "Just now", lastActivitySort: 0, lastActivityFrom: "You",
    emails: [
      { from: "You", to: "lisa.patel@company.com", date: "Feb 7, 10:00 AM", dateSort: 20260207.1000, subject: "[TSK-006] Send TAI data to Jordan", body: "Lisa, can you pull the TAI data for Jordan? He needs it for the annual reinsurance review. Use the RI schema and the template he sent last week.", type: "sent", hasAttachment: true },
    ],
  },
];

const C = {
  blue: "#1a3a7a", blueLight: "#2a4fa0", blueMid: "#263f6a", bluePale: "#e8edf6", blueBg: "#2c4a80",
  blueListBg: "#1e3d6f",
  gold: "#c8a415", goldPale: "#faf6e8", goldBorder: "#d4be5a",
  border: "#c5cee0", borderOnDark: "#3d6098",
  text: "#1a2332", textMid: "#4a5568", textLight: "#7a8599",
  white: "#ffffff",
  green: "#1a8a4a",
  red: "#c53030", redCard: "#f9d4d4", redBorder: "#e8a0a0", redDark: "#b91c1c",
  yellowDot: "#d4a017", greenDot: "#1a8a4a",
};

const font = "'Segoe UI', 'Tahoma', sans-serif";
const mono = "'Cascadia Code', 'Consolas', monospace";

const COL = { id: 80, date: 100, activity: 110 };

const isLastFromOther = (task) => task.lastActivityFrom && task.lastActivityFrom !== "You";

const ActivityDot = ({ task }) => {
  if (!task.emailSent) return null;
  const color = isLastFromOther(task) ? C.greenDot : C.yellowDot;
  return <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0, marginRight: 4 }} />;
};

const SectionBox = ({ label, children, bg, mb = 12, pad = "12px 16px" }) => (
  <div style={{ border: `1px solid ${C.border}`, borderRadius: 4, background: bg || C.white, marginBottom: mb }}>
    {label && <div style={{ padding: "6px 16px", background: C.bluePale, borderBottom: `1px solid ${C.border}`, fontSize: 13, fontWeight: 700, color: C.blue, textTransform: "uppercase", letterSpacing: "0.5px" }}>{label}</div>}
    <div style={{ padding: pad }}>{children}</div>
  </div>
);

export default function TaskTracker() {
  const [tasks, setTasks] = useState(MOCK_TASKS);
  const [statusFilter, setStatusFilter] = useState("open");
  const [search, setSearch] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [detailTab, setDetailTab] = useState("details");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [showAssignDropdown, setShowAssignDropdown] = useState(false);
  const [assignSearch, setAssignSearch] = useState("");
  const [contacts, setContacts] = useState(MOCK_CONTACTS);
  const [editingDescription, setEditingDescription] = useState(false);
  const [editDescValue, setEditDescValue] = useState("");
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [expandedEmails, setExpandedEmails] = useState({});
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState("");
  const [detailWidth, setDetailWidth] = useState(420);
  const [emailSearch, setEmailSearch] = useState("");
  const resizing = useRef(false);

  const handleMouseDown = useCallback((e) => {
    e.preventDefault(); resizing.current = true;
    const startX = e.clientX, startW = detailWidth;
    const onMove = (ev) => { if (!resizing.current) return; setDetailWidth(Math.max(320, Math.min(700, startW + (startX - ev.clientX)))); };
    const onUp = () => { resizing.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp);
  }, [detailWidth]);

  const handleSort = (col) => { if (sortCol === col) setSortDir(sortDir === "asc" ? "desc" : "asc"); else { setSortCol(col); setSortDir("asc"); } };
  const sortArrow = (col) => { if (sortCol !== col) return <span style={{ opacity: 0.4, marginLeft: 3 }}>⇅</span>; return <span style={{ marginLeft: 3 }}>{sortDir === "asc" ? "▲" : "▼"}</span>; };

  const filtered = useMemo(() => {
    let result = tasks.filter((t) => {
      if (t.status !== statusFilter) return false;
      if (search.trim()) { const s = search.toLowerCase(); return t.id.toLowerCase().includes(s) || t.title.toLowerCase().includes(s) || t.assignees.map(a => a.name).join(" ").toLowerCase().includes(s); }
      return true;
    });
    if (sortCol) {
      result = [...result].sort((a, b) => {
        let va, vb;
        switch (sortCol) { case "id": va = a.id; vb = b.id; break; case "date": va = a.createdDate; vb = b.createdDate; break; case "activity": va = a.lastActivitySort ?? 999; vb = b.lastActivitySort ?? 999; break; case "assignee": va = (a.assignees[0]?.name || "zzz").toLowerCase(); vb = (b.assignees[0]?.name || "zzz").toLowerCase(); break; default: return 0; }
        if (va < vb) return sortDir === "asc" ? -1 : 1; if (va > vb) return sortDir === "asc" ? 1 : -1; return 0;
      });
    }
    return result;
  }, [tasks, statusFilter, search, sortCol, sortDir]);

  const sortedEmails = useMemo(() => {
    if (!selectedTask) return [];
    let emails = [...selectedTask.emails].sort((a, b) => b.dateSort - a.dateSort);
    if (emailSearch.trim()) { const s = emailSearch.toLowerCase(); emails = emails.filter(e => e.body.toLowerCase().includes(s) || e.subject.toLowerCase().includes(s) || e.from.toLowerCase().includes(s) || e.to.toLowerCase().includes(s)); }
    return emails;
  }, [selectedTask, emailSearch]);

  const nextTaskId = () => `TSK-${String(Math.max(...tasks.map(t => parseInt(t.id.split("-")[1])), 0) + 1).padStart(3, "0")}`;

  const handleNewTask = () => {
    if (!newTaskTitle.trim()) return;
    setTasks([{ id: nextTaskId(), title: newTaskTitle.trim(), status: "open", createdDate: new Date().toISOString().split("T")[0], assignees: [], emailSent: false, lastActivity: null, lastActivitySort: 999, lastActivityFrom: null, emails: [] }, ...tasks]);
    setNewTaskTitle("");
  };

  const handleDeleteTask = () => { if (!selectedTask) return; setTasks(tasks.filter(t => t.id !== selectedTask.id)); setSelectedTask(null); setConfirmDelete(false); };

  const filteredContacts = contacts.filter(c => { if (!assignSearch.trim()) return true; const s = assignSearch.toLowerCase(); return c.name.toLowerCase().includes(s) || c.email.toLowerCase().includes(s); }).filter(c => !selectedTask || !selectedTask.assignees.find(a => a.email === c.email));

  const handleAssign = (contact) => { if (!selectedTask || selectedTask.assignees.find(a => a.email === contact.email)) return; const u = { ...selectedTask, assignees: [...selectedTask.assignees, contact] }; setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); setAssignSearch(""); };

  const handleAssignFreeform = () => {
    if (!assignSearch.trim() || !selectedTask) return;
    const input = assignSearch.trim(), isEmail = input.includes("@");
    const contact = { name: isEmail ? input.split("@")[0] : input, email: isEmail ? input : "" };
    if (contact.email && !contacts.find(c => c.email === contact.email)) setContacts([...contacts, contact]);
    if (!selectedTask.assignees.find(a => a.name === contact.name)) { const u = { ...selectedTask, assignees: [...selectedTask.assignees, contact] }; setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); }
    setAssignSearch("");
  };

  const handleRemoveAssignee = (email, name) => { if (!selectedTask) return; const u = { ...selectedTask, assignees: selectedTask.assignees.filter(a => email ? a.email !== email : a.name !== name) }; setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); };

  const handleSendEmail = () => {
    if (!selectedTask || selectedTask.assignees.length === 0) return;
    const newEmails = selectedTask.assignees.filter(a => a.email).map(a => ({ from: "You", to: a.email, date: "Just now", dateSort: 99999999.9999, subject: `[${selectedTask.id}] ${selectedTask.title.slice(0, 60)}`, body: "Task assigned. Please review and respond with your progress.", type: "sent", hasAttachment: false }));
    const u = { ...selectedTask, emailSent: true, lastActivity: "Just now", lastActivitySort: 0, lastActivityFrom: "You", emails: [...selectedTask.emails, ...newEmails] };
    setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u);
  };

  const handleSendReply = () => {
    if (!replyText.trim() || replyingTo === null || !selectedTask) return;
    const orig = sortedEmails[replyingTo];
    const replyTo = orig.type === "received" ? orig.from : orig.to;
    const u = { ...selectedTask, lastActivity: "Just now", lastActivitySort: 0, lastActivityFrom: "You", emails: [...selectedTask.emails, { from: "You", to: replyTo, date: "Just now", dateSort: 99999999.9999, subject: `Re: ${orig.subject}`, body: replyText.trim(), type: "sent", hasAttachment: false }] };
    setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); setReplyText(""); setReplyingTo(null);
  };

  const handleToggleStatus = () => { if (!selectedTask) return; const u = { ...selectedTask, status: selectedTask.status === "open" ? "closed" : "open" }; setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); };

  const toggleDetail = (task) => {
    if (selectedTask?.id === task.id) setSelectedTask(null);
    else { setSelectedTask(task); setDetailTab("details"); setEditingDescription(false); setShowAssignDropdown(false); setAssignSearch(""); setConfirmDelete(false); setReplyingTo(null); setReplyText(""); setExpandedEmails({}); setEmailSearch(""); }
  };

  const cardBg = (task) => {
    const needsAttention = isLastFromOther(task);
    if (needsAttention) return C.redCard;
    if (task.status === "closed") return "rgba(255,255,255,0.6)";
    return C.white;
  };

  const cardBorder = (task) => {
    if (selectedTask?.id === task.id) return C.gold;
    if (isLastFromOther(task)) return C.redBorder;
    return "rgba(255,255,255,0.25)";
  };

  const cardBorderLeft = (task) => {
    if (selectedTask?.id === task.id) return C.gold;
    if (isLastFromOther(task)) return C.redDark;
    if (task.status === "closed") return "#8ac4a0";
    return "rgba(200,164,21,0.6)";
  };

  const handleEmailDoubleClick = (email) => { alert(`In the desktop app, this would open the email in Outlook:\n\nSubject: ${email.subject}\nFrom: ${email.from}`); };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: font, background: C.blueListBg, color: C.text, fontSize: 16, overflow: "hidden" }}>

      {/* LEFT PANEL */}
      <div style={{ flex: 1, minWidth: 400, display: "flex", flexDirection: "column", background: C.blueListBg }}>

        {/* CONTROL SECTION */}
        <div style={{ background: C.white, borderBottom: `3px solid ${C.gold}`, boxShadow: "0 2px 12px rgba(0,0,0,0.2)" }}>
          <div style={{ padding: "10px 16px", background: `linear-gradient(135deg, ${C.blue}, ${C.blueLight})`, display: "flex", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 28, height: 28, borderRadius: 4, background: C.gold, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.blue, fontSize: 16, fontWeight: 800 }}>T</span>
              </div>
              <span style={{ color: "#fff", fontSize: 20, fontWeight: 700 }}>TaskTracker</span>
              <span style={{ color: C.gold, fontSize: 12, fontWeight: 600, opacity: 0.7 }}>SuiteView</span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", background: C.goldPale, borderBottom: `1px solid ${C.goldBorder}` }}>
            <button onClick={handleNewTask} style={{ width: 36, height: 36, background: C.gold, color: C.blue, border: "none", borderRadius: 4, fontSize: 20, fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>+</button>
            <input value={newTaskTitle} onChange={(e) => setNewTaskTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleNewTask()}
              placeholder="New task — type and press Enter or click [+]"
              style={{ flex: 1, padding: "7px 10px", border: `1px solid ${C.gold}`, borderRadius: 4, fontSize: 15, fontFamily: font, outline: "none", background: C.white, boxSizing: "border-box" }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: C.bluePale }}>
            <div style={{ display: "flex" }}>
              {[{ key: "open", label: "Open" }, { key: "closed", label: "Closed" }].map((f, i) => (
                <button key={f.key} onClick={() => setStatusFilter(f.key)} style={{
                  padding: "5px 18px", border: `1px solid ${statusFilter === f.key ? C.blue : C.border}`,
                  background: statusFilter === f.key ? C.blue : C.white, color: statusFilter === f.key ? "#fff" : C.textMid,
                  fontSize: 14, fontWeight: 600, cursor: "pointer", marginRight: -1,
                  borderRadius: i === 0 ? "4px 0 0 4px" : "0 4px 4px 0",
                }}>{f.label}</button>
              ))}
            </div>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tasks..."
              style={{ flex: 1, padding: "5px 10px", border: `1px solid ${C.border}`, borderRadius: 4, fontSize: 14, fontFamily: font, outline: "none", background: C.white }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", padding: "6px 10px 6px 14px", borderTop: `1px solid ${C.border}`, background: C.bluePale, fontSize: 12, fontWeight: 700, color: C.blue, textTransform: "uppercase", letterSpacing: "0.5px", userSelect: "none" }}>
            <span style={{ width: COL.id, flexShrink: 0, cursor: "pointer" }} onClick={() => handleSort("id")}>Task ID{sortArrow("id")}</span>
            <span style={{ width: COL.date, flexShrink: 0, cursor: "pointer" }} onClick={() => handleSort("date")}>Created{sortArrow("date")}</span>
            <span style={{ width: COL.activity, flexShrink: 0, cursor: "pointer" }} onClick={() => handleSort("activity")}>Activity{sortArrow("activity")}</span>
            <span style={{ flex: 1, cursor: "pointer" }} onClick={() => handleSort("assignee")}>Assignee{sortArrow("assignee")}</span>
          </div>
        </div>

        {/* TASK LIST */}
        <div style={{ flex: 1, overflowY: "auto", padding: "6px 8px" }}>
          {filtered.length === 0 && <div style={{ textAlign: "center", padding: "30px", color: "rgba(255,255,255,0.5)", fontSize: 15 }}>No tasks found</div>}
          {filtered.map((task) => (
            <div key={task.id} style={{
              border: `1px solid ${cardBorder(task)}`,
              borderLeft: `4px solid ${cardBorderLeft(task)}`,
              borderRadius: 4, marginBottom: 5, background: cardBg(task), cursor: "pointer",
              opacity: task.status === "closed" ? 0.7 : 1,
              boxShadow: selectedTask?.id === task.id ? `0 0 0 2px ${C.gold}` : "0 1px 3px rgba(0,0,0,0.15)",
            }}
              onClick={() => toggleDetail(task)}
              onMouseEnter={(e) => { e.currentTarget.style.boxShadow = selectedTask?.id === task.id ? `0 0 0 2px ${C.gold}` : "0 2px 8px rgba(0,0,0,0.25)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.boxShadow = selectedTask?.id === task.id ? `0 0 0 2px ${C.gold}` : "0 1px 3px rgba(0,0,0,0.15)"; }}
            >
              <div style={{ display: "flex", alignItems: "center", padding: "6px 10px 2px" }}>
                <span style={{ width: COL.id, flexShrink: 0, fontFamily: mono, fontSize: 14, fontWeight: 700, color: C.blue }}>{task.id}</span>
                <span style={{ width: COL.date, flexShrink: 0, fontSize: 14, color: C.text, fontWeight: 600 }}>{task.createdDate}</span>
                <span style={{ width: COL.activity, flexShrink: 0, display: "flex", alignItems: "center", fontSize: 13, color: C.textMid }}>
                  <ActivityDot task={task} />{task.lastActivity || "—"}
                </span>
                <span style={{ flex: 1, display: "flex", flexWrap: "wrap", gap: 4, overflow: "hidden" }}>
                  {task.assignees.length === 0 && <span style={{ fontSize: 13, color: C.textLight, fontStyle: "italic" }}>—</span>}
                  {task.assignees.map((a, i) => (
                    <span key={i} style={{ fontSize: 12, color: C.blue, background: "rgba(232,237,246,0.8)", padding: "1px 7px", borderRadius: 3, border: `1px solid #a0b4d4`, fontWeight: 600, whiteSpace: "nowrap" }}>{a.name}</span>
                  ))}
                </span>
              </div>
              <div style={{ padding: "2px 10px 6px", fontSize: 15, color: C.textMid, lineHeight: 1.3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {task.title.length > 95 ? task.title.slice(0, 95) + "…" : task.title}
              </div>
            </div>
          ))}
        </div>

        <div style={{ padding: "5px 12px", borderTop: `1px solid ${C.borderOnDark}`, background: "rgba(0,0,0,0.15)", fontSize: 12, color: "rgba(255,255,255,0.6)", display: "flex", justifyContent: "space-between" }}>
          <span>{filtered.length} task{filtered.length !== 1 ? "s" : ""}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ display: "inline-block", width: 12, height: 8, background: C.white, border: `1px solid rgba(255,255,255,0.4)`, borderRadius: 2 }} /> Normal</span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ display: "inline-block", width: 12, height: 8, background: C.redCard, border: `1px solid ${C.redBorder}`, borderRadius: 2 }} /> Needs Attention</span>
          </span>
          <span>TaskTracker v1.0</span>
        </div>
      </div>

      {/* RESIZE + RIGHT PANEL */}
      {selectedTask && (
        <>
          <div onMouseDown={handleMouseDown} style={{ width: 6, cursor: "col-resize", background: `linear-gradient(180deg, ${C.gold}, ${C.blue})`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, userSelect: "none" }}>
            <div style={{ width: 2, height: 40, background: "rgba(255,255,255,0.4)", borderRadius: 1 }} />
          </div>

          <div style={{ width: detailWidth, flexShrink: 0, display: "flex", flexDirection: "column", background: C.bluePale, overflow: "hidden" }}>
            <div style={{ padding: "10px 16px", background: `linear-gradient(135deg, ${C.blue}, ${C.blueLight})`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ color: "#fff", fontSize: 18, fontWeight: 700 }}>Task Details</span>
                <span style={{ fontFamily: mono, fontSize: 16, color: C.gold, fontWeight: 700 }}>{selectedTask.id}</span>
              </div>
              <button onClick={() => setSelectedTask(null)} style={{ padding: "5px 10px", background: "rgba(255,255,255,0.15)", color: "#fff", border: "none", borderRadius: 4, fontSize: 15, cursor: "pointer" }}>✕</button>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 16px", background: C.white, borderBottom: `1px solid ${C.border}` }}>
              <span style={{ fontSize: 13, color: C.textMid }}><strong style={{ color: C.text }}>Created:</strong> {selectedTask.createdDate}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>Status:</span>
                <button onClick={handleToggleStatus} style={{ padding: "3px 14px", borderRadius: 4, fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none", background: selectedTask.status === "open" ? C.red : C.blue, color: "#fff" }}>
                  {selectedTask.status === "open" ? "OPEN" : "CLOSED"}
                </button>
              </div>
            </div>

            <div style={{ display: "flex", background: C.white, borderBottom: `1px solid ${C.border}` }}>
              {[{ key: "details", label: "Details" }, { key: "emails", label: `Email Trail (${selectedTask.emails.length})` }].map((tab) => (
                <button key={tab.key} onClick={() => { setDetailTab(tab.key); setReplyingTo(null); setReplyText(""); }} style={{
                  padding: "8px 18px", border: "none", background: detailTab === tab.key ? C.goldPale : "transparent",
                  borderBottom: detailTab === tab.key ? `3px solid ${C.gold}` : "3px solid transparent",
                  fontSize: 14, fontWeight: 700, color: detailTab === tab.key ? C.blue : C.textLight, cursor: "pointer",
                }}>{tab.label}</button>
              ))}
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column" }}>
              {detailTab === "details" && (
                <div style={{ flex: 1 }}>
                  <SectionBox label="Description">
                    {editingDescription ? (
                      <div>
                        <textarea autoFocus value={editDescValue} onChange={(e) => setEditDescValue(e.target.value)}
                          style={{ width: "100%", minHeight: 80, padding: "8px 10px", border: `1px solid ${C.gold}`, borderRadius: 4, fontSize: 14, fontFamily: font, resize: "vertical", outline: "none", boxSizing: "border-box", lineHeight: 1.5 }} />
                        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                          <button onClick={() => { const u = { ...selectedTask, title: editDescValue }; setTasks(tasks.map(t => t.id === selectedTask.id ? u : t)); setSelectedTask(u); setEditingDescription(false); }}
                            style={{ padding: "4px 12px", background: C.blue, color: "#fff", border: "none", borderRadius: 3, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Save</button>
                          <button onClick={() => setEditingDescription(false)} style={{ padding: "4px 12px", background: C.white, color: C.textMid, border: `1px solid ${C.border}`, borderRadius: 3, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <div onClick={() => { setEditDescValue(selectedTask.title); setEditingDescription(true); }} style={{ fontSize: 14, lineHeight: 1.6, color: C.textMid, cursor: "pointer", minHeight: 40 }}>
                        {selectedTask.title}
                        <div style={{ fontSize: 11, color: C.textLight, marginTop: 4, fontStyle: "italic" }}>Click to edit</div>
                      </div>
                    )}
                  </SectionBox>

                  <SectionBox label="Assigned To">
                    {selectedTask.assignees.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                        {selectedTask.assignees.map((a, i) => (
                          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 7px 3px 9px", background: C.bluePale, border: `1px solid ${C.border}`, borderRadius: 20, fontSize: 12, fontWeight: 600, color: C.blue }}>
                            <div style={{ width: 20, height: 20, borderRadius: "50%", background: C.white, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 8, fontWeight: 700, color: C.blue }}>
                              {a.name.split(" ").map(n => n[0]).join("")}
                            </div>
                            <span>{a.name}</span>
                            <button onClick={() => handleRemoveAssignee(a.email, a.name)} style={{ background: "none", border: "none", color: C.red, fontSize: 13, cursor: "pointer", padding: "0 2px", lineHeight: 1, fontWeight: 700 }}>×</button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ position: "relative" }}>
                      <input value={assignSearch} onChange={(e) => { setAssignSearch(e.target.value); setShowAssignDropdown(true); }} onFocus={() => setShowAssignDropdown(true)}
                        onKeyDown={(e) => { if (e.key === "Enter" && filteredContacts.length > 0) handleAssign(filteredContacts[0]); else if (e.key === "Enter" && assignSearch.trim()) handleAssignFreeform(); }}
                        placeholder={selectedTask.assignees.length > 0 ? "Add another person..." : "Type a name or email to assign..."}
                        style={{ width: "100%", padding: "6px 10px", border: `1px solid ${C.gold}`, borderRadius: 4, fontSize: 13, fontFamily: font, outline: "none", boxSizing: "border-box", background: C.goldPale }} />
                      {showAssignDropdown && assignSearch.trim() && (
                        <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 2, background: C.white, border: `1px solid ${C.border}`, borderRadius: 4, boxShadow: "0 4px 16px rgba(0,0,0,0.12)", zIndex: 10, maxHeight: 200, overflowY: "auto" }}>
                          {filteredContacts.map((c, i) => (
                            <div key={i} onClick={() => handleAssign(c)} style={{ padding: "7px 12px", cursor: "pointer", borderBottom: `1px solid ${C.bluePale}`, fontSize: 13 }}
                              onMouseEnter={e => e.currentTarget.style.background = C.goldPale} onMouseLeave={e => e.currentTarget.style.background = C.white}>
                              <span style={{ fontWeight: 600 }}>{c.name}</span> <span style={{ fontSize: 11, color: C.textLight, marginLeft: 4 }}>{c.email}</span>
                            </div>
                          ))}
                          {filteredContacts.length === 0 && <div onClick={handleAssignFreeform} style={{ padding: "7px 12px", cursor: "pointer", fontSize: 13, color: C.blue, fontWeight: 600 }} onMouseEnter={e => e.currentTarget.style.background = C.goldPale} onMouseLeave={e => e.currentTarget.style.background = C.white}>+ Assign to "{assignSearch.trim()}"</div>}
                          {filteredContacts.length > 0 && <div onClick={handleAssignFreeform} style={{ padding: "5px 12px", cursor: "pointer", fontSize: 11, color: C.textLight, borderTop: `1px solid ${C.border}` }} onMouseEnter={e => e.currentTarget.style.background = C.goldPale} onMouseLeave={e => e.currentTarget.style.background = C.white}>+ Use "{assignSearch.trim()}" as new contact</div>}
                        </div>
                      )}
                    </div>
                  </SectionBox>

                  {selectedTask.assignees.length > 0 && (
                    <SectionBox label="Email Actions" bg={C.goldPale}>
                      {!selectedTask.emailSent ? (
                        <div>
                          <button onClick={handleSendEmail} style={{ padding: "6px 16px", background: C.gold, color: C.blue, border: "none", borderRadius: 4, fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                            ✉ SEND TASK TO {selectedTask.assignees.length === 1 ? selectedTask.assignees[0].name.split(" ")[0].toUpperCase() : `${selectedTask.assignees.length} PEOPLE`}
                          </button>
                          <div style={{ fontSize: 11, color: C.textLight, marginTop: 4 }}>Subject includes [{selectedTask.id}] for tracking</div>
                        </div>
                      ) : (
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: C.green }}>✓ Email sent — tracking via [{selectedTask.id}]</div>
                          <div style={{ fontSize: 11, color: C.textLight, marginTop: 3 }}>{selectedTask.emails.length} email{selectedTask.emails.length !== 1 ? "s" : ""} in thread</div>
                        </div>
                      )}
                    </SectionBox>
                  )}

                  <div style={{ marginTop: 16, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                    {!confirmDelete ? (
                      <button onClick={() => setConfirmDelete(true)} style={{ padding: "5px 14px", background: C.white, color: C.red, border: `1px solid ${C.red}`, borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>🗑 Delete Task</button>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, color: C.red, fontWeight: 600 }}>Delete {selectedTask.id}?</span>
                        <button onClick={handleDeleteTask} style={{ padding: "4px 12px", background: C.red, color: "#fff", border: "none", borderRadius: 4, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>Yes</button>
                        <button onClick={() => setConfirmDelete(false)} style={{ padding: "4px 12px", background: C.white, color: C.textMid, border: `1px solid ${C.border}`, borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {detailTab === "emails" && (
                <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                  <div style={{ marginBottom: 8 }}>
                    <input value={emailSearch} onChange={(e) => setEmailSearch(e.target.value)} placeholder="Search emails..."
                      style={{ width: "100%", padding: "5px 10px", border: `1px solid ${C.border}`, borderRadius: 4, fontSize: 13, fontFamily: font, outline: "none", background: C.white, boxSizing: "border-box" }} />
                  </div>

                  {selectedTask.emails.length === 0 ? (
                    <div style={{ border: `1px dashed ${C.border}`, borderRadius: 4, padding: "30px 14px", textAlign: "center", color: C.textLight }}>
                      <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.4 }}>✉</div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>No emails yet</div>
                      <div style={{ fontSize: 12 }}>Assign someone and send to start tracking</div>
                    </div>
                  ) : sortedEmails.length === 0 ? (
                    <div style={{ textAlign: "center", padding: "20px", color: C.textLight, fontSize: 13 }}>No emails match your search</div>
                  ) : (
                    <div style={{ flex: replyingTo !== null ? "none" : 1, overflowY: "auto" }}>
                      {sortedEmails.map((email, i) => {
                        const isExpanded = expandedEmails[i];
                        const preview = email.body.length > 70 ? email.body.slice(0, 70) + "…" : email.body;
                        return (
                          <div key={i} style={{ border: `1px solid ${C.border}`, borderLeft: `3px solid ${email.type === "sent" ? C.blue : C.gold}`, borderRadius: 4, marginBottom: 6, background: C.white }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 10px 2px", cursor: "default" }}
                              onDoubleClick={() => handleEmailDoubleClick(email)}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, minWidth: 0 }}>
                                <span style={{ fontWeight: 700, color: email.type === "sent" ? C.blue : C.gold, flexShrink: 0 }}>{email.from}</span>
                                <span style={{ color: C.textLight, flexShrink: 0 }}>→</span>
                                <span style={{ color: C.textLight, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{email.to}</span>
                                {email.hasAttachment && <span title="Has attachment" style={{ fontSize: 14, flexShrink: 0 }}>📎</span>}
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                                <span style={{ fontSize: 11, color: C.textLight }}>{email.date}</span>
                                <button onClick={(e) => { e.stopPropagation(); setReplyingTo(i); setReplyText(""); }}
                                  style={{ padding: "2px 8px", background: C.blue, color: "#fff", border: "none", borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: "pointer" }}>Reply</button>
                              </div>
                            </div>
                            <div onClick={() => setExpandedEmails(prev => ({ ...prev, [i]: !prev[i] }))}
                              style={{ padding: "2px 10px 5px", fontSize: 13, color: C.textMid, cursor: "pointer", lineHeight: 1.5 }}>
                              {isExpanded ? <div>{email.body}</div> : <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{preview}</div>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {replyingTo !== null && (
                    <div style={{ borderTop: `2px solid ${C.gold}`, marginTop: 8, paddingTop: 10, flexShrink: 0 }}>
                      <div style={{ fontSize: 12, color: C.textMid, fontWeight: 600, marginBottom: 6 }}>
                        Replying to: <span style={{ color: C.blue }}>{sortedEmails[replyingTo]?.from === "You" ? sortedEmails[replyingTo]?.to : sortedEmails[replyingTo]?.from}</span>
                      </div>
                      <textarea autoFocus value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Type your response..."
                        style={{ width: "100%", minHeight: 80, padding: "8px 10px", border: `1px solid ${C.gold}`, borderRadius: 4, fontSize: 13, fontFamily: font, resize: "vertical", outline: "none", boxSizing: "border-box", lineHeight: 1.5 }} />
                      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                        <button onClick={handleSendReply} style={{ padding: "5px 14px", background: C.blue, color: "#fff", border: "none", borderRadius: 4, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>✉ Send Reply</button>
                        <button onClick={() => { setReplyingTo(null); setReplyText(""); }} style={{ padding: "5px 14px", background: C.white, color: C.textMid, border: `1px solid ${C.border}`, borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const API_BASE = "";

const API_ENDPOINTS = {
    dashboard: () => "/api/student/dashboard",
    courses: () => "/api/student/courses",
    courseScenarios: (courseId) => `/api/student/course-scenarios/${courseId}`,
    scenarioDetails: (scenarioId) => `/api/student/scenario-details/${scenarioId}`,
    scenarioSteps: (scenarioId) => `/api/student/scenario-steps/${scenarioId}`,
    startScenario: (scenarioId) => `/api/student/start/${scenarioId}`,
    endScenario: (sessionId) => `/api/student/end/${sessionId}`,
    submitStep: () => "/api/student/submit-step",
    sessionProgress: (sessionId) => `/api/student/session-progress/${sessionId}`,
    rdpDownload: (sessionId) => `/api/student/rdp/${sessionId}`,
};

async function apiFetch(path, options = {}) {
    const res = await fetch(API_BASE + path, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        },
        ...options
    });

    let data = null;
    try { data = await res.json(); } catch (e) {}

    if (!res.ok) {
        const msg = (data && data.detail) ? data.detail : `HTTP ${res.status}`;
        throw new Error(msg);
    }

    return data;
}

function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatDate(value) {
    if (!value) return "-";
    try {
        return new Date(value).toLocaleString("ar");
    } catch {
        return String(value);
    }
}

function formatDuration(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds || 0));
    const hours = String(Math.floor(s / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const seconds = String(s % 60).padStart(2, "0");
    return `${hours}:${minutes}:${seconds}`;
}

async function logout() {
    if (!confirm("هل تريد تسجيل الخروج؟")) return;

    try {
        await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (e) {}

    window.location.href = "/static/login.html";
}
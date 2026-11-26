const API_BASE = "";

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
    try {
        data = await res.json();
    } catch (e) {}

    if (!res.ok) {
        const msg = data?.detail || `HTTP ${res.status}`;
        throw new Error(msg);
    }

    return data;
}

function showError(err) {
    alert(err?.message || "حدث خطأ غير متوقع");
}

function escapeHtml(str) {
    return String(str ?? "")
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

async function logout() {
    if (!confirm("هل تريد تسجيل الخروج؟")) return;

    try {
        await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (e) {}

    window.location.href = "/static/login.html";
}
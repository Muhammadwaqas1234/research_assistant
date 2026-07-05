const chatBox = document.getElementById("chat");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

const SECTION_TITLES = [
    "ABSTRACT", "INTRODUCTION", "LITERATURE REVIEW", "METHODOLOGY",
    "PROPOSED APPROACH", "RESULTS", "CONCEPTUAL RESULTS", "DISCUSSION",
    "LIMITATIONS", "CONCLUSION", "FUTURE WORK", "REFERENCES",
];

const TOOL_LABELS = {
    topic_finder: "Topic discovery",
    research_gap_finder: "Gap analysis",
    paper_writer: "Paper writer",
    paper_reviewer: "Paper reviewer",
    final_paper_for_topic: "Research pipeline",
    error: "Error",
};

/* ---------- status ---------- */

async function checkHealth() {
    const pill = document.getElementById("statusPill");
    const text = document.getElementById("statusText");
    try {
        const res = await fetch("/health");
        const data = await res.json();
        if (data.agent_ready) {
            pill.className = "pill online";
            text.textContent = `Agent ready · ${data.model}`;
        } else {
            pill.className = "pill offline";
            text.textContent = "Agent offline";
        }
    } catch {
        pill.className = "pill offline";
        text.textContent = "API unreachable";
    }
}

function useExample(text) {
    userInput.value = text;
    autosize();
    userInput.focus();
}

/* ---------- messages ---------- */

function removeWelcome() {
    const w = document.getElementById("welcome");
    if (w) w.remove();
}

function parseToolTag(text) {
    const m = text.match(/^\[([a-z_]+)\]\s*\n?/i);
    if (!m) return { tool: null, body: text };
    return { tool: m[1], body: text.slice(m[0].length) };
}

function appendMessage(text, sender, isError = false) {
    const div = document.createElement("div");
    div.classList.add("chat-message", sender);
    if (isError) div.classList.add("error");

    if (sender === "ai") {
        const { tool, body } = parseToolTag(text);
        if (tool && TOOL_LABELS[tool]) {
            const badge = document.createElement("span");
            badge.className = "tool-badge";
            badge.textContent = TOOL_LABELS[tool];
            div.appendChild(badge);
            div.appendChild(document.createElement("br"));
            if (tool === "error") div.classList.add("error");
            renderBody(body, div);
        } else {
            renderBody(text, div);
        }
    } else {
        div.textContent = text;
    }

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
}

function renderBody(text, container) {
    if (SECTION_TITLES.some((t) => text.toUpperCase().includes(t))) {
        appendPaperSections(text, container);
    } else {
        container.appendChild(document.createTextNode(text));
    }
}

function splitPaperSections(text) {
    const pattern = new RegExp(
        SECTION_TITLES.map((t) => `^${t.replace(/\//g, "\\/")}\\s*$`).join("|"),
        "gmi"
    );

    const matches = [];
    let match;
    while ((match = pattern.exec(text)) !== null) {
        matches.push({ index: match.index, title: match[0].trim().toUpperCase() });
    }

    if (matches.length === 0) return [{ title: null, content: text }];

    const sections = [];
    for (let i = 0; i < matches.length; i++) {
        const start = matches[i].index + matches[i].title.length;
        const end = i < matches.length - 1 ? matches[i + 1].index : text.length;
        sections.push({ title: matches[i].title, content: text.substring(start, end).trim() });
    }
    return sections;
}

function appendPaperSections(text, container) {
    splitPaperSections(text).forEach(({ title, content }) => {
        if (title) {
            const titleEl = document.createElement("div");
            titleEl.classList.add("section-title");
            titleEl.textContent = title;
            container.appendChild(titleEl);
        }
        const contentEl = document.createElement("div");
        contentEl.textContent = content;
        container.appendChild(contentEl);
    });
}

/* ---------- typing indicator ---------- */

let typingEl = null;

function showTyping() {
    typingEl = document.createElement("div");
    typingEl.className = "chat-message ai";
    typingEl.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    chatBox.appendChild(typingEl);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function hideTyping() {
    if (typingEl) typingEl.remove();
    typingEl = null;
}

/* ---------- send ---------- */

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const message = userInput.value.trim();
    if (!message || sendBtn.disabled) return;

    removeWelcome();
    appendMessage(message, "user");
    userInput.value = "";
    autosize();
    sendBtn.disabled = true;
    showTyping();

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: message }),
        });

        hideTyping();
        const data = await res.json();
        if (res.ok) {
            appendMessage(data.response || "No response", "ai");
        } else {
            appendMessage(data.detail || `Request failed (${res.status})`, "ai", true);
        }
    } catch {
        hideTyping();
        appendMessage("Cannot reach the server. Is the backend running?", "ai", true);
    } finally {
        sendBtn.disabled = false;
        userInput.focus();
    }
});

function autosize() {
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
}

userInput.addEventListener("input", autosize);
userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});

window.addEventListener("load", checkHealth);

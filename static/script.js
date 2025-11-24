const chatBox = document.getElementById("chat");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");

const SECTION_TITLES = [
    "ABSTRACT","INTRODUCTION","LITERATURE REVIEW","METHODOLOGY",
    "PROPOSED APPROACH","RESULTS","CONCEPTUAL RESULTS","DISCUSSION",
    "LIMITATIONS","CONCLUSION","FUTURE WORK","REFERENCES"
];

function appendMessage(text, sender) {
    const div = document.createElement("div");
    div.classList.add("chat-message", sender);

    if (sender === "ai") {
        if (SECTION_TITLES.some(title => text.toUpperCase().includes(title))) {
            appendPaperSections(text, div);
        } else {
            div.textContent = text;
            chatBox.appendChild(div);
        }
    } else {
        div.textContent = text;
        chatBox.appendChild(div);
    }

    chatBox.scrollTop = chatBox.scrollHeight;
}

function splitPaperSections(text) {
    const pattern = new RegExp(
        SECTION_TITLES.map(t => `^${t.replace(/\//g, '\\/')}\\s*$`).join("|"),
        "gmi"
    );

    let matches = [];
    let match;
    while ((match = pattern.exec(text)) !== null) {
        matches.push({ index: match.index, title: match[0].trim().toUpperCase() });
    }

    if (matches.length === 0) return [{ title: "FULL TEXT", content: text }];

    let sections = [];
    for (let i = 0; i < matches.length; i++) {
        let start = matches[i].index + matches[i].title.length;
        let end = (i < matches.length - 1 ? matches[i + 1].index : text.length);
        sections.push({ title: matches[i].title, content: text.substring(start, end).trim() });
    }
    return sections;
}

function appendPaperSections(text, container) {
    const sections = splitPaperSections(text);

    sections.forEach(({ title, content }) => {
        const titleEl = document.createElement("div");
        titleEl.classList.add("section-title");
        titleEl.textContent = title;

        const contentEl = document.createElement("div");
        contentEl.textContent = content;
        contentEl.style.whiteSpace = "pre-wrap";

        container.appendChild(titleEl);
        container.appendChild(contentEl);
    });

    chatBox.appendChild(container);
}

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const message = userInput.value.trim();
    if (!message) return;

    appendMessage(message, "user");
    userInput.value = "";
    userInput.style.height = "auto";

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: message }),
        });

        const data = await res.json();
        appendMessage(data.response || "No response", "ai");
    } catch {
        appendMessage("⚠️ Server error", "ai");
    }
});

userInput.addEventListener("input", () => {
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
});

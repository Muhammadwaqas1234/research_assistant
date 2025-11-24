Here is a clean, professional, GitHub-ready **README.md** for your repository.
It fully explains the system, tools, architecture, instructions, API details, and deployment steps.

---

# **AI Research Assistant – Agentic Academic Research System (FastAPI + LLaMA 3.2)**

This project is a **cleaned, modular, single-file implementation** of an **Agentic AI Research Assistant**.
It automates academic research tasks such as topic generation, literature review, gap analysis, research topic recommendation, full paper writing, and paper refinement.

The system is built using **FastAPI**, **ChatOllama (LLaMA 3.2)**, and **Semantic Scholar API**, and exposes a unified `/ask` endpoint for interacting with the agent.

---

## 🚀 **Key Features**

### ✔️ **Simple Tool System — No LangChain decorators**

All tools are implemented as **plain Python functions**, making the code easier to maintain and extend.

### ✔️ **End-to-end Research Pipeline**

Automatically performs:

1. Literature Extraction
2. Gap Analysis
3. Gap → Research Topic Mapping
4. Full Paper Draft Generation
5. Paper Review & Polishing

### ✔️ **Robust LLM Handling**

* Safe wrapper for model invocation
* Automatic fallback parsing
* JSON extraction helper
* Fault-tolerant pipeline with extensive logging

### ✔️ **Multi-tool Agentic Reasoning**

The assistant decides:

* which tool to use
* when to use a pipeline
* when to write a paper
* when to generate topics
* when to review long text

### ✔️ **Semantic Scholar Search Integration**

Fetches real academic papers using:

* title
* abstract
* year
* authors
* URLs

### ✔️ **FastAPI Backend & Optional Frontend**

* `/ask` endpoint for research queries
* `/health` for uptime monitoring
* Auto-serves `templates/index.html` if present

---

# 🧪 **What the Tools Do**

The agent uses the following internal tools:

### **1. `topic_finder(field)`**

Generates 12 high-quality research topics by:

* Fetching relevant papers
* Creating a text corpus
* Asking the LLM to extract research areas

### **2. `literature_extractor(topic)`**

Retrieves papers related to the topic and produces a structured **literature review**.

### **3. `research_gap_finder(summary)`**

Analyzes the literature summary and identifies:

* Limitations
* Underexplored areas
* Methodological gaps
* Future opportunities
* Thesis titles
* Research questions

### **4. `gap_to_topic(gap_text)`**

Converts research gaps into **one optimal publication-ready topic**.

### **5. `paper_writer(topic)`**

Generates a **full 5,000–10,000 word academic paper** with:

* Abstract
* Literature Review
* Methodology
* Results
* Discussion
* Conclusion
* References (APA)

### **6. `paper_reviewer(draft)`**

Improves grammar, flow, and academic tone.

### **7. `orchestrate_research_pipeline(query)`**

Runs all steps end-to-end automatically.

---

## 🧠 **System Architecture Overview**

```
User Query
     ↓
Classifier: RESEARCH or NON-RESEARCH?
     ↓
Tool Selection Logic
     ├── Short query → topic_finder
     ├── Gap keywords → research_gap_finder
     ├── Literature keywords → pipeline (full research)
     ├── Write intent → paper_writer
     ├── Long text → paper_reviewer
     └── Default → full pipeline
```

The system behaves as an **autonomous research agent**, choosing tools dynamically based on the query.

---

# 📡 **API Usage**

### **POST /ask**

**Request**

```json
{
  "query": "Explain research gaps in federated learning"
}
```

**Response**

```json
{
  "response": "...."
}
```

---

### **GET /health**

Simple uptime check.

```json
{
  "status": "ok"
}
```

---

### **GET /**

If `templates/index.html` exists → serves frontend
Otherwise → shows a minimal instruction page.

---

# ⚙️ **Setup & Installation**

### **1. Install dependencies**

```bash
pip install fastapi uvicorn requests langchain_ollama pydantic jinja2
```

### **2. Install and Run Ollama (Local LLaMA 3.2)**

```bash
ollama pull llama3.2
ollama run llama3.2
```

Make sure the FastAPI app can reach your local Ollama server.

---

# 🔑 **Environment Variables**

If using a remote model or additional APIs, configure environment variables such as:

```
LLM_BASE_URL=
LLM_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=   (optional)
```

---

# ▶️ **Run the Server**

```bash
uvicorn research_assistant_app_cleaned:app --host 0.0.0.0 --port 8000
```

Open:

```
http://localhost:8000
```

---

# 📁 **Project Structure (Single-File Clean Architecture)**

```
project/
│
├── research_assistant_app_cleaned.py   ← main implementation
├── templates/
│   └── index.html   (optional)
└── README.md
```

---



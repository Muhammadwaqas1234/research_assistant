"""
Research Assistant Agentic AI - Cleaned & Improved Single-file Implementation
- Simplifies tool usage (no langchain @tool wrappers)
- Robust error handling
- Clearer pipeline and modular helper functions
- Uses ChatOllama wrapper with safe response extraction
- Keeps FastAPI endpoints and simple frontend-serving capability

Note: configure your environment variables / API keys for LLM provider and
ensure the Semantic Scholar API is reachable.
"""

import logging
import re
import json
from typing import Optional, Dict, Any, List

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Replace these imports if you use a different client for the LLM
from langchain_ollama import ChatOllama
from fastapi.staticfiles import StaticFiles

# --------------------------
# Logging
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research_assistant")

# --------------------------
# FastAPI app & CORS
# --------------------------
app = FastAPI(
    title="AI Research Assistant",
    description="A multi-tool academic research agent powered by FastAPI + LLMs",
    version="2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# --------------------------
# LLM Initialization
# --------------------------
# Configure model name / options as required for your environment
llm = ChatOllama(model="llama3.2", temperature=0.2)
llm_reasoner = ChatOllama(model="llama3.2", temperature=0.2)

# --------------------------
# Pydantic models
# --------------------------
class QueryModel(BaseModel):
    query: str

# --------------------------
# Helper utilities
# --------------------------

def safe_llm_invoke(client: ChatOllama, prompt: str, timeout: int = 120) -> str:
    """
    Invoke the LLM client and return plain text content. Handles common shapes
    of return values from different LLM wrappers.
    """
    try:
        resp = client.invoke(prompt)
        # Many wrappers place text under .content or .text
        content = None
        if isinstance(resp, dict):
            # If wrapper returned a dict
            content = resp.get("content") or resp.get("text") or json.dumps(resp)
        else:
            content = getattr(resp, "content", None) or getattr(resp, "text", None) or str(resp)
        return content if content is not None else ""
    except Exception as e:
        logger.exception("LLM invocation failed")
        return f"ERROR: LLM invocation failed: {str(e)}"


def clean_json(text: Optional[str]) -> Optional[Any]:
    """
    Extract JSON object or list from freeform text if present.
    Returns parsed JSON object/list or None.
    """
    if not text:
        return None
    # strip code fences
    t = re.sub(r"```(?:json)?", "", text).strip("` \n\t")
    # direct parse attempt
    try:
        return json.loads(t)
    except Exception:
        pass
    # find first {...} or [...] block
    m = re.search(r"(\{[\s\S]*\})", t)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\[[\s\S]*\])", t)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None

# --------------------------
# External Research helpers (Semantic Scholar)
# --------------------------

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch_papers_from_semanticscholar(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Returns a list of paper dicts from Semantic Scholar (best-effort).
    If the API fails, returns an empty list.
    """
    try:
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,authors,url"
        }
        resp = requests.get(SEMANTIC_SCHOLAR_BASE, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) or []
    except Exception:
        logger.exception("Semantic Scholar fetch failed")
        return []

# --------------------------
# Core "tools" implemented as regular functions
# --------------------------

def topic_finder(field: str) -> Dict[str, Any]:
    field = (field or "").strip()
    if len(field) < 2:
        return {"error": "Field unclear or too short."}

    papers = fetch_papers_from_semanticscholar(field, limit=20)
    if not papers:
        return {"error": "No research papers found for this field."}

    # create lightweight corpus
    text_corpus = "\n".join((p.get("title", "") + "\n" + (p.get("abstract") or "")) for p in papers)

    prompt = f"""
Extract 12 high-quality research topics from the following scholarly text.
Return a JSON list of topic names only.

Text:
{text_corpus}

Output requirements:
- Return only a JSON list of clean topic names (strings).
- Avoid duplicates and vague topics.
- Prefer recent and emerging areas.
"""
    resp_text = safe_llm_invoke(llm, prompt)
    parsed = clean_json(resp_text)
    if isinstance(parsed, list):
        topics = [t for t in parsed if isinstance(t, str) and t.strip()]
    else:
        # fallback: split on newlines and pick lines
        topics = [ln.strip() for ln in resp_text.splitlines() if ln.strip()][:12]
    return {"field": field, "topics": topics[:12]}


def literature_extractor(topic: str) -> Dict[str, Any]:
    topic = (topic or "").strip()
    if len(topic) < 2:
        return {"error": "Topic too short or unclear."}

    papers = fetch_papers_from_semanticscholar(topic, limit=15)
    if not papers:
        return {"error": "No papers found for this topic."}

    formatted = []
    for p in papers:
        title = p.get("title", "No Title")
        year = p.get("year", "N/A")
        abstract = p.get("abstract", "")
        authors = ", ".join(a.get("name", "") for a in p.get("authors", []))
        url = p.get("url", "")
        formatted.append({
            "title": title,
            "authors": authors,
            "year": year,
            "url": url,
            "abstract": abstract
        })

    # Build a concise prompt for LLM
    paper_text = "\n\n".join(f"Title: {p['title']}\nAuthors: {p['authors']}\nYear: {p['year']}\nURL: {p['url']}\nAbstract: {p['abstract']}" for p in formatted)

    prompt = f"""
You are a research expert. Summarize the following papers into a concise literature review.
Return 8-12 bullet points. Each bullet should include: main contribution, methods used, key findings, and relevance to the topic "{topic}".

Papers:
{paper_text}
"""
    summary_text = safe_llm_invoke(llm, prompt)
    return {"topic": topic, "literature_review": summary_text}


def research_gap_finder(lit_summary: str) -> Dict[str, Any]:
    lit_summary = (lit_summary or "").strip()
    if len(lit_summary) < 10:
        return {"error": "Input too short to analyze."}

    prompt = f"""
You are an academic researcher. Based on the literature summary below, identify:
1) Key limitations in current research
2) Under-explored areas
3) Methodological gaps
4) Future research opportunities
5) 4 strong potential thesis titles (6-12 words)
6) 3–5 research questions

Literature Summary:
{lit_summary}

Return a clean structured plain-text response with labeled sections.
"""
    resp = safe_llm_invoke(llm, prompt)
    return {"input": lit_summary, "research_gaps": resp}


def gap_to_topic(gap_text: str) -> Dict[str, Any]:
    gap_text = (gap_text or "").strip()
    if not gap_text:
        return {"error": "Empty gap text."}

    prompt = f"""
You are an academic researcher. Given the following research gaps, produce ONE concise publication-ready research topic (6-12 words) and a one-sentence rationale.
Return JSON only in this form: {{"topic": "<Title>", "reason": "<rationale>"}}

Gaps:
{gap_text}
"""
    resp = safe_llm_invoke(llm, prompt)
    parsed = clean_json(resp)
    if isinstance(parsed, dict) and parsed.get("topic"):
        return {"topic": parsed.get("topic"), "reason": parsed.get("reason", "")}
    # fallback parse by regex
    m = re.search(r'"?topic"?\s*[:=]\s*"(.*?)"', resp, re.IGNORECASE | re.DOTALL)
    reason = ""
    if m:
        topic = m.group(1).strip()
        m2 = re.search(r'"?reason"?\s*[:=]\s*"(.*?)"', resp, re.IGNORECASE | re.DOTALL)
        if m2:
            reason = m2.group(1).strip()
        return {"topic": topic, "reason": reason}
    # last resort
    first_line = next((ln.strip() for ln in resp.splitlines() if ln.strip()), "")
    return {"topic": first_line[:200], "reason": ""}


def paper_writer(topic: str) -> str:
    topic = (topic or "").strip()
    if not topic:
        return "ERROR: Empty topic provided"

    prompt = f"""
You are an expert academic researcher and writer. Write a **complete, well-structured academic research paper** on the topic: "{topic}".

The paper MUST include ALL of the following sections in proper order and format:

1. Abstract  
2. Introduction  
3. Literature Review  
4. Methodology  
5. Proposed Approach  
6. Results / Conceptual Results  
7. Discussion  
8. Limitations  
9. Conclusion  
10. Future Work  
11. References (APA style)

Guidelines:
- Length: 5000–10000 words
- Tone: Formal academic writing
- Avoid bullet points unless required by structure
- Ensure coherence, clarity, and logical flow between sections
- Create realistic but non-fabricated citations (APA style)
- No placeholders like “Lorem ipsum”
- Make sure each section is fully developed and not just a few lines

Now write the full research paper.
"""
    return safe_llm_invoke(llm, prompt)



def paper_reviewer(draft: str) -> str:
    draft = (draft or "").strip()
    if not draft:
        return "ERROR: Empty draft provided"

    prompt = f"""
You are an academic editor. Improve the following draft for clarity, flow, grammar, and academic tone. Keep the meaning but make the text more concise and rigorous.

---START DRAFT---
{draft}
---END DRAFT---

Return only the improved paper.
"""
    return safe_llm_invoke(llm, prompt)

# --------------------------
# Orchestrator
# --------------------------

def orchestrate_research_pipeline(user_topic_query: str) -> Dict[str, Any]:
    """
    Orchestrates a simple research pipeline and returns a dictionary with results.
    Steps:
      1) literature_extractor
      2) research_gap_finder
      3) gap_to_topic
      4) paper_writer
      5) paper_reviewer
    """
    try:
        user_topic_query = (user_topic_query or "").strip()
        if not user_topic_query:
            return {"status": "error", "error": "Empty query"}

        logger.info("Pipeline start for query: %s", user_topic_query)

        # 1) literature
        lit_out = literature_extractor(user_topic_query)
        if isinstance(lit_out, dict) and lit_out.get("error"):
            return {"status": "error", "error": f"Literature extractor error: {lit_out.get('error')}"}
        lit_summary = lit_out.get("literature_review", "")
        if len((lit_summary or "").strip()) < 20:
            return {"status": "error", "error": "Literature extraction produced insufficient summary."}

        # 2) gaps
        gap_out = research_gap_finder(lit_summary)
        if isinstance(gap_out, dict) and gap_out.get("error"):
            return {"status": "error", "error": f"Gap finder error: {gap_out.get('error')}"}
        gap_text = gap_out.get("research_gaps", "")
        if len((gap_text or "").strip()) < 20:
            return {"status": "error", "error": "Gap finder returned insufficient data."}

        # 3) gap -> topic
        gap_topic_out = gap_to_topic(gap_text)
        if isinstance(gap_topic_out, dict) and gap_topic_out.get("error"):
            return {"status": "error", "error": f"Gap->Topic error: {gap_topic_out.get('error')}"}
        chosen_topic = gap_topic_out.get("topic") or user_topic_query
        topic_reason = gap_topic_out.get("reason", "")

        # 4) write paper
        paper_draft = paper_writer(chosen_topic)
        if paper_draft.startswith("ERROR") or len(paper_draft.strip()) < 200:
            return {"status": "error", "error": "Paper writer returned insufficient draft."}

        # 5) review
        refined = paper_reviewer(paper_draft)
        final_paper_text = refined if refined and not refined.startswith("ERROR") else paper_draft

        logger.info("Pipeline finished successfully for topic: %s", chosen_topic)
        return {
            "status": "ok",
            "topic": chosen_topic,
            "reason": topic_reason,
            "final_paper": final_paper_text
        }

    except Exception as e:
        logger.exception("orchestrate_research_pipeline failed")
        return {"status": "error", "error": str(e)}

# --------------------------
# Simple classifier
# --------------------------

def classify_query(query: str) -> str:
    text = (query or "").lower().strip()
    RESEARCH_KEYWORDS = [
        "research", "paper", "topic", "literature", "review", "gap", "methodology",
        "thesis", "experiment", "analysis", "systematic review", "citation"
    ]
    if any(k in text for k in RESEARCH_KEYWORDS):
        return "RESEARCH"

    # fallback: ask LLM briefly (fast prompt)
    prompt = f"Classify the following query as RESEARCH or NON_RESEARCH.\nQuery: {query}\nReturn only RESEARCH or NON_RESEARCH."
    resp = safe_llm_invoke(llm_reasoner, prompt)
    resp = (resp or "").upper()
    if "RESEARCH" in resp:
        return "RESEARCH"
    return "NON_RESEARCH"

# --------------------------
# Main ask_agent function
# --------------------------

def ask_agent(query: str) -> str:
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide a non-empty research query."

    # classify
    label = classify_query(query_clean)
    if label == "NON_RESEARCH":
        return (
            "⚠️ I am a dedicated Academic Research Assistant.\n"
            "I can help with:\n- Research topics\n- Literature reviews\n- Research gaps\n- Paper writing\n- Paper reviewing\n\n"
            "Please provide a research-related query."
        )

    words = query_clean.split()
    word_count = len(words)
    lower = query_clean.lower()

    # SHORT QUERY -> topics
    if word_count <=1 and "\n" not in query_clean:
        try:
            out = topic_finder(query_clean)
            return "[topic_finder]\n" + json.dumps(out, indent=2, ensure_ascii=False)
        except Exception:
            logger.exception("topic_finder invocation failed in ask_agent")
            return "[error]\nTopic finder failed."

    # GAP related
    GAP_KEYWORDS = ["gap", "gaps", "research gap", "limitations", "future work"]
    if any(k in lower for k in GAP_KEYWORDS):
        try:
            gap_out = research_gap_finder(query_clean)
            return "[research_gap_finder]\n" + (gap_out.get("research_gaps") if isinstance(gap_out, dict) else str(gap_out))
        except Exception:
            logger.exception("research_gap_finder invocation failed in ask_agent")
            return "[error]\nGap finder failed."

    # LITERATURE request trigger
    LIT_WORDS = ["literature", "review", "related work", "summarize papers"]
    if any(k in lower for k in LIT_WORDS):
        pipeline_res = orchestrate_research_pipeline(query_clean)
        if pipeline_res.get("status") == "ok":
            return f"[final_paper_for_topic]\nTopic: {pipeline_res.get('topic')}\n\n{pipeline_res.get('final_paper')}"
        else:
            return "[error]\n" + pipeline_res.get("error", "Unknown orchestration error.")

    # WRITE PAPER intent
    WRITE_WORDS = ["write", "generate", "create", "paper", "draft", "research paper"]
    if any(k in lower for k in WRITE_WORDS) or (5 <= word_count <= 12):
        try:
            paper = paper_writer(query_clean)
            return "[paper_writer]\n" + str(paper)
        except Exception:
            logger.exception("paper_writer invocation failed in ask_agent")
            return "[error]\nPaper writer failed."

    # LONG text -> review
    if word_count > 60 or "\n" in query_clean:
        try:
            reviewed = paper_reviewer(query_clean)
            return "[paper_reviewer]\n" + str(reviewed)
        except Exception:
            logger.exception("paper_reviewer invocation failed in ask_agent")
            return "[error]\nPaper reviewer failed."

    # DEFAULT -> run pipeline
    pipeline_res = orchestrate_research_pipeline(query_clean)
    if pipeline_res.get("status") == "ok":
        return f"[final_paper_for_topic]\nTopic: {pipeline_res.get('topic')}\n\n{pipeline_res.get('final_paper')}"
    else:
        return "[error]\n" + pipeline_res.get("error", "Unknown orchestration error.")

# --------------------------
# FastAPI endpoints
# --------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    # Serve templates/index.html if present; otherwise return a small instructional page
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        html = """
        <!doctype html>
        <html><head><meta charset=\"utf-8\"><title>Research Assistant</title></head>
        <body>
        <h2>Research Assistant Backend</h2>
        <p>Use POST /ask with JSON {"query": "..."}</p>
        </body></html>
        """
        return HTMLResponse(content=html, status_code=200)


@app.post("/ask")
async def ask_api(body: QueryModel):
    try:
        result = ask_agent(body.query)
        return {"response": result}
    except Exception as e:
        logger.exception("ask_api failed")
        raise HTTPException(status_code=500, detail=f"Agent failed: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok"}


# --------------------------
# If used as a script
# --------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("research_assistant_app_cleaned:app", host="127.0.0.1", port=8000, log_level="info")

class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response
app.mount("/static", StaticFiles(directory="static"), name="static")

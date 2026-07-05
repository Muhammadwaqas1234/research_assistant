"""AI Research Assistant — agentic academic research over a local LLM.

Tools (plain functions, no framework decorators):
  topic_finder · literature_extractor · research_gap_finder ·
  gap_to_topic · paper_writer · paper_reviewer

The /ask endpoint routes each query to the right tool or to the full
research pipeline. The LLM (Ollama) is initialized lazily so the server
runs — and reports status honestly — even when Ollama is down.
"""

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research_assistant")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

app = FastAPI(
    title="AI Research Assistant",
    description="A multi-tool academic research agent powered by FastAPI + a local LLM",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_HTML = Path(__file__).resolve().parent / "templates" / "index.html"

# --------------------------
# LLM — lazy singleton
# --------------------------

_lock = threading.Lock()
_llm = None
_llm_error = None


def _get_llm():
    global _llm, _llm_error
    if _llm is not None or _llm_error is not None:
        return _llm
    with _lock:
        if _llm is not None or _llm_error is not None:
            return _llm
        try:
            from langchain_ollama import ChatOllama

            _llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.2)
            logger.info("LLM ready (model=%s)", OLLAMA_MODEL)
        except Exception as exc:
            _llm_error = str(exc)
            logger.exception("Failed to initialize LLM")
    return _llm


class AgentUnavailable(RuntimeError):
    pass


def safe_llm_invoke(prompt: str) -> str:
    """Invoke the LLM and return plain text, tolerating wrapper shapes."""
    llm = _get_llm()
    if llm is None:
        raise AgentUnavailable(
            f"LLM unavailable: {_llm_error}. Is Ollama running with "
            f"the '{OLLAMA_MODEL}' model pulled?"
        )
    resp = llm.invoke(prompt)
    if isinstance(resp, dict):
        return resp.get("content") or resp.get("text") or json.dumps(resp)
    return getattr(resp, "content", None) or getattr(resp, "text", None) or str(resp)


def clean_json(text: Optional[str]) -> Optional[Any]:
    """Extract a JSON object or list from freeform LLM output."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text).strip("` \n\t")
    try:
        return json.loads(t)
    except Exception:
        pass
    for pattern in (r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"):
        m = re.search(pattern, t)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                continue
    return None


# --------------------------
# Semantic Scholar
# --------------------------

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch_papers_from_semanticscholar(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(
            SEMANTIC_SCHOLAR_BASE,
            params={"query": query, "limit": limit, "fields": "title,abstract,year,authors,url"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("data", []) or []
    except Exception:
        logger.exception("Semantic Scholar fetch failed")
        return []


# --------------------------
# Tools
# --------------------------

def topic_finder(field: str) -> Dict[str, Any]:
    field = (field or "").strip()
    if len(field) < 2:
        return {"error": "Field unclear or too short."}

    papers = fetch_papers_from_semanticscholar(field, limit=20)
    if not papers:
        return {"error": "No research papers found for this field."}

    text_corpus = "\n".join(
        (p.get("title", "") + "\n" + (p.get("abstract") or "")) for p in papers
    )

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
    resp_text = safe_llm_invoke(prompt)
    parsed = clean_json(resp_text)
    if isinstance(parsed, list):
        topics = [t for t in parsed if isinstance(t, str) and t.strip()]
    else:
        topics = [ln.strip() for ln in resp_text.splitlines() if ln.strip()][:12]
    return {"field": field, "topics": topics[:12]}


def literature_extractor(topic: str) -> Dict[str, Any]:
    topic = (topic or "").strip()
    if len(topic) < 2:
        return {"error": "Topic too short or unclear."}

    papers = fetch_papers_from_semanticscholar(topic, limit=15)
    if not papers:
        return {"error": "No papers found for this topic."}

    formatted = [
        {
            "title": p.get("title", "No Title"),
            "authors": ", ".join(a.get("name", "") for a in p.get("authors", [])),
            "year": p.get("year", "N/A"),
            "url": p.get("url", ""),
            "abstract": p.get("abstract", ""),
        }
        for p in papers
    ]

    paper_text = "\n\n".join(
        f"Title: {p['title']}\nAuthors: {p['authors']}\nYear: {p['year']}\n"
        f"URL: {p['url']}\nAbstract: {p['abstract']}"
        for p in formatted
    )

    prompt = f"""
You are a research expert. Summarize the following papers into a concise literature review.
Return 8-12 bullet points. Each bullet should include: main contribution, methods used,
key findings, and relevance to the topic "{topic}".

Papers:
{paper_text}
"""
    return {"topic": topic, "literature_review": safe_llm_invoke(prompt)}


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
6) 3-5 research questions

Literature Summary:
{lit_summary}

Return a clean structured plain-text response with labeled sections.
"""
    return {"input": lit_summary, "research_gaps": safe_llm_invoke(prompt)}


def gap_to_topic(gap_text: str) -> Dict[str, Any]:
    gap_text = (gap_text or "").strip()
    if not gap_text:
        return {"error": "Empty gap text."}

    prompt = f"""
You are an academic researcher. Given the following research gaps, produce ONE concise
publication-ready research topic (6-12 words) and a one-sentence rationale.
Return JSON only in this form: {{"topic": "<Title>", "reason": "<rationale>"}}

Gaps:
{gap_text}
"""
    resp = safe_llm_invoke(prompt)
    parsed = clean_json(resp)
    if isinstance(parsed, dict) and parsed.get("topic"):
        return {"topic": parsed.get("topic"), "reason": parsed.get("reason", "")}

    m = re.search(r'"?topic"?\s*[:=]\s*"(.*?)"', resp, re.IGNORECASE | re.DOTALL)
    if m:
        m2 = re.search(r'"?reason"?\s*[:=]\s*"(.*?)"', resp, re.IGNORECASE | re.DOTALL)
        return {"topic": m.group(1).strip(), "reason": m2.group(1).strip() if m2 else ""}

    first_line = next((ln.strip() for ln in resp.splitlines() if ln.strip()), "")
    return {"topic": first_line[:200], "reason": ""}


def paper_writer(topic: str) -> str:
    topic = (topic or "").strip()
    if not topic:
        return "ERROR: Empty topic provided"

    prompt = f"""
You are an expert academic researcher and writer. Write a **complete, well-structured
academic research paper** on the topic: "{topic}".

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
- Length: 5000-10000 words
- Tone: Formal academic writing
- Avoid bullet points unless required by structure
- Ensure coherence, clarity, and logical flow between sections
- Create realistic but non-fabricated citations (APA style)
- No placeholders like "Lorem ipsum"
- Make sure each section is fully developed and not just a few lines

Now write the full research paper.
"""
    return safe_llm_invoke(prompt)


def paper_reviewer(draft: str) -> str:
    draft = (draft or "").strip()
    if not draft:
        return "ERROR: Empty draft provided"

    prompt = f"""
You are an academic editor. Improve the following draft for clarity, flow, grammar,
and academic tone. Keep the meaning but make the text more concise and rigorous.

---START DRAFT---
{draft}
---END DRAFT---

Return only the improved paper.
"""
    return safe_llm_invoke(prompt)


# --------------------------
# Orchestrator
# --------------------------

def orchestrate_research_pipeline(user_topic_query: str) -> Dict[str, Any]:
    """literature → gaps → topic → draft → review"""
    user_topic_query = (user_topic_query or "").strip()
    if not user_topic_query:
        return {"status": "error", "error": "Empty query"}

    logger.info("Pipeline start for query: %s", user_topic_query)

    lit_out = literature_extractor(user_topic_query)
    if lit_out.get("error"):
        return {"status": "error", "error": f"Literature extractor error: {lit_out['error']}"}
    lit_summary = lit_out.get("literature_review", "")
    if len(lit_summary.strip()) < 20:
        return {"status": "error", "error": "Literature extraction produced insufficient summary."}

    gap_out = research_gap_finder(lit_summary)
    if gap_out.get("error"):
        return {"status": "error", "error": f"Gap finder error: {gap_out['error']}"}
    gap_text = gap_out.get("research_gaps", "")
    if len(gap_text.strip()) < 20:
        return {"status": "error", "error": "Gap finder returned insufficient data."}

    gap_topic_out = gap_to_topic(gap_text)
    if gap_topic_out.get("error"):
        return {"status": "error", "error": f"Gap->Topic error: {gap_topic_out['error']}"}
    chosen_topic = gap_topic_out.get("topic") or user_topic_query

    paper_draft = paper_writer(chosen_topic)
    if paper_draft.startswith("ERROR") or len(paper_draft.strip()) < 200:
        return {"status": "error", "error": "Paper writer returned insufficient draft."}

    refined = paper_reviewer(paper_draft)
    final_paper_text = refined if refined and not refined.startswith("ERROR") else paper_draft

    logger.info("Pipeline finished for topic: %s", chosen_topic)
    return {
        "status": "ok",
        "topic": chosen_topic,
        "reason": gap_topic_out.get("reason", ""),
        "final_paper": final_paper_text,
    }


# --------------------------
# Query routing
# --------------------------

RESEARCH_KEYWORDS = [
    "research", "paper", "topic", "literature", "review", "gap", "methodology",
    "thesis", "experiment", "analysis", "systematic review", "citation",
]


def classify_query(query: str) -> str:
    text = (query or "").lower().strip()
    if any(k in text for k in RESEARCH_KEYWORDS):
        return "RESEARCH"

    prompt = (
        "Classify the following query as RESEARCH or NON_RESEARCH.\n"
        f"Query: {query}\nReturn only RESEARCH or NON_RESEARCH."
    )
    resp = (safe_llm_invoke(prompt) or "").upper()
    return "RESEARCH" if "RESEARCH" in resp else "NON_RESEARCH"


def ask_agent(query: str) -> str:
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide a non-empty research query."

    if classify_query(query_clean) == "NON_RESEARCH":
        return (
            "I am a dedicated Academic Research Assistant.\n"
            "I can help with:\n- Research topics\n- Literature reviews\n"
            "- Research gaps\n- Paper writing\n- Paper reviewing\n\n"
            "Please provide a research-related query."
        )

    words = query_clean.split()
    word_count = len(words)
    lower = query_clean.lower()

    # Single keyword → discover topics in that field
    if word_count <= 1 and "\n" not in query_clean:
        out = topic_finder(query_clean)
        return "[topic_finder]\n" + json.dumps(out, indent=2, ensure_ascii=False)

    # Gap analysis intent
    if any(k in lower for k in ["gap", "gaps", "research gap", "limitations", "future work"]):
        gap_out = research_gap_finder(query_clean)
        return "[research_gap_finder]\n" + gap_out.get("research_gaps", str(gap_out))

    # Literature review intent → full pipeline
    if any(k in lower for k in ["literature", "review", "related work", "summarize papers"]):
        pipeline_res = orchestrate_research_pipeline(query_clean)
        if pipeline_res.get("status") == "ok":
            return (
                f"[final_paper_for_topic]\nTopic: {pipeline_res['topic']}\n\n"
                f"{pipeline_res['final_paper']}"
            )
        return "[error]\n" + pipeline_res.get("error", "Unknown orchestration error.")

    # Paper writing intent
    if any(k in lower for k in ["write", "generate", "create", "paper", "draft"]) or (
        5 <= word_count <= 12
    ):
        return "[paper_writer]\n" + paper_writer(query_clean)

    # Long text → review/polish
    if word_count > 60 or "\n" in query_clean:
        return "[paper_reviewer]\n" + paper_reviewer(query_clean)

    # Default → full pipeline
    pipeline_res = orchestrate_research_pipeline(query_clean)
    if pipeline_res.get("status") == "ok":
        return (
            f"[final_paper_for_topic]\nTopic: {pipeline_res['topic']}\n\n"
            f"{pipeline_res['final_paper']}"
        )
    return "[error]\n" + pipeline_res.get("error", "Unknown orchestration error.")


# --------------------------
# API
# --------------------------

class QueryModel(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    if INDEX_HTML.exists():
        return INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(
        "<h2>Research Assistant Backend</h2><p>Use POST /ask with JSON {\"query\": \"...\"}</p>"
    )


@app.post("/ask")
async def ask_api(body: QueryModel):
    try:
        return {"response": ask_agent(body.query)}
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("ask_api failed")
        raise HTTPException(status_code=500, detail=f"Agent failed: {exc}")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_ready": _get_llm() is not None,
        "agent_error": _llm_error,
        "model": OLLAMA_MODEL,
    }


app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info")

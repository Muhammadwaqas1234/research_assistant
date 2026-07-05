"""Capture the research assistant UI with a staged conversation."""
from playwright.sync_api import sync_playwright

OUT = r"C:\Users\raiwa\research_assistant\docs\ui.png"

STAGE = """
document.getElementById('statusPill').className = 'pill online';
document.getElementById('statusText').textContent = 'Agent ready · llama3.2';
removeWelcome();
appendMessage('Find research gaps in federated learning for healthcare', 'user');
appendMessage(`[research_gap_finder]
KEY LIMITATIONS
Current studies rely on small, single-institution cohorts and rarely evaluate on truly non-IID clinical data. Privacy guarantees are often assumed rather than measured.

UNDER-EXPLORED AREAS
Cross-silo personalization for rare diseases, communication-efficient training on edge medical devices, and fairness auditing across demographic subgroups.

METHODOLOGICAL GAPS
Few works combine differential privacy with secure aggregation under realistic hospital network constraints; benchmark datasets remain fragmented.

POTENTIAL THESIS TITLES
1. Fairness-Aware Federated Learning for Multi-Site Clinical Prediction
2. Communication-Efficient Personalization in Cross-Silo Medical FL
3. Measuring Real Privacy Leakage in Federated Health Models
4. Benchmarking Non-IID Robustness for Hospital Federations`, 'ai');
appendMessage('machine learning', 'user');
appendMessage(`[topic_finder]
1. Parameter-efficient fine-tuning for foundation models
2. Retrieval-augmented generation for scientific reasoning
3. Continual learning under distribution shift
4. Mechanistic interpretability of transformers
5. Federated learning with differential privacy
6. Graph neural networks for drug discovery`, 'ai');
document.getElementById('chat').scrollTop = 0;
"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    page.wait_for_timeout(800)
    page.evaluate(STAGE)
    page.wait_for_timeout(500)
    page.screenshot(path=OUT, full_page=True)
    print("captured ui.png")
    browser.close()

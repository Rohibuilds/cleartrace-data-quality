"""ClearTrace — Functional Grounded LLM Assistant.

Provides evidence-grounded natural language explanations for data quality findings,
business rules, and mathematical discrepancies.

Strict Safety & Architectural Principles:
1. Never uses an LLM as an authoritative calculator.
2. The LLM is strictly read-only: it cannot independently approve or apply repairs.
3. If no local or hosted model is configured, returns an honest 'unavailable' status
   instead of fake, simulated AI responses.
4. Validates that model citations strictly match retrieved evidence references.
5. Defends against prompt injection by isolating untrusted evidence in structured contexts.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cleartrace.models import Evidence, GroundedAnswer
from cleartrace.retrieval import EvidenceIndex, prepare_grounding

REF_PATTERN = re.compile(r"\[Source:\s*([^\]]+)\]")


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM service is disabled, unconfigured, or unreachable."""
    pass


def get_llm_status() -> Dict[str, Any]:
    """Check live status of the configured LLM provider without making heavy requests."""
    opt_in = os.environ.get("CLEARTRACE_LOCAL_LLM_OPT_IN", "").strip().lower() == "yes"
    model = os.environ.get("CLEARTRACE_OLLAMA_MODEL", "llama3.2")
    raw_url = os.environ.get("CLEARTRACE_OLLAMA_URL", "http://127.0.0.1:11434")

    if not opt_in:
        return {
            "available": False,
            "provider": "ollama-local",
            "model": model,
            "status": "disabled",
            "message": "Local LLM is disabled by default. Set CLEARTRACE_LOCAL_LLM_OPT_IN=yes to enable.",
        }

    # Verify endpoint is local loopback
    u = urlparse(raw_url)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost"):
        return {
            "available": False,
            "provider": "ollama-local",
            "model": model,
            "status": "invalid_endpoint",
            "message": "Only local loopback endpoints (http://127.0.0.1:11434) are permitted.",
        }

    # Ping Ollama endpoint
    try:
        req = Request(raw_url.rstrip("/") + "/api/tags", headers={"Content-Type": "application/json"}, method="GET")
        with build_opener().open(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed_models = [m.get("name") for m in data.get("models", [])]
            return {
                "available": True,
                "provider": "ollama-local",
                "model": model,
                "endpoint": raw_url,
                "status": "ready",
                "installed_models": installed_models,
                "message": f"Ollama is reachable at {raw_url} with model '{model}'.",
            }
    except Exception as exc:
        return {
            "available": False,
            "provider": "ollama-local",
            "model": model,
            "status": "unreachable",
            "message": f"Local Ollama is not responding at {raw_url}: {exc}. To use LLM features, run 'ollama serve' and pull a model.",
        }


def ask_knowledge_assistant(
    question: str,
    index: EvidenceIndex,
    *,
    limit: int = 5,
) -> GroundedAnswer:
    """Query the knowledge index and generate an evidence-grounded answer.
    
    If the LLM is unconfigured or unavailable, returns the verified source evidence
    directly with an honest status explanation rather than hallucinating.
    """
    matches = index.search(question, limit=limit)
    if not matches:
        return GroundedAnswer(
            answer="No relevant evidence or records matching your query were found in the active session dataset.",
            references=[],
            provider="none",
            status="insufficient_evidence",
            evidence_matches=[],
        )

    evidence_dicts = [
        {
            "score": m[0],
            "ref": m[1].ref,
            "title": m[1].title,
            "text": m[1].text,
            "source_type": m[1].source_type,
        }
        for m in matches
    ]

    llm_status = get_llm_status()
    if not llm_status["available"]:
        # Honest fallback: synthesize factual summary directly from verified evidence
        top_match = matches[0][1]
        summary_lines = [
            f"**Verified Evidence Retrieved ({len(matches)} source passages found):**\n"
        ]
        for score, ev in matches[:3]:
            summary_lines.append(f"- **[{ev.title}]** (`{ev.ref}`): {ev.text}")

        summary_lines.append(
            f"\n*Note on AI Status: {llm_status['message']} "
            "ClearTrace provides verified source citations directly without generative hallucination.*"
        )

        return GroundedAnswer(
            answer="\n".join(summary_lines),
            references=[m[1].ref for m in matches],
            provider="retrieval-deterministic",
            status="llm_unavailable_evidence_presented",
            evidence_matches=evidence_dicts,
        )

    # LLM is opted-in and available: execute local inference
    prompt, allowed_refs = prepare_grounding(question, matches)
    model = llm_status.get("model", "llama3.2")
    raw_url = os.environ.get("CLEARTRACE_OLLAMA_URL", "http://127.0.0.1:11434")

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = Request(
        raw_url.rstrip("/") + "/api/generate",
        payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    class DenyRedirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise HTTPError(req.full_url, code, "Redirect refused for local security", headers, fp)

    opener = build_opener(DenyRedirects())

    try:
        with opener.open(req, timeout=40) as response:
            raw_resp = response.read(1024 * 1024 + 1)
            if len(raw_resp) > 1024 * 1024:
                raise LLMUnavailableError("Model response exceeded 1 MB limit.")
            text = str(json.loads(raw_resp.decode("utf-8")).get("response", "")).strip()
    except (URLError, TimeoutError, ValueError) as exc:
        return GroundedAnswer(
            answer=f"Error communicating with local model: {exc}. Please verify Ollama runtime.",
            references=allowed_refs,
            provider="ollama-local",
            status="error",
            evidence_matches=evidence_dicts,
        )

    # Validate citations
    cited_refs = [ref for ref in REF_PATTERN.findall(text) if ref in allowed_refs]
    if not cited_refs:
        status = "uncited_model_output_review_required"
    else:
        status = "cited_model_output"

    return GroundedAnswer(
        answer=text,
        references=list(dict.fromkeys(cited_refs or allowed_refs)),
        provider=f"ollama:{model}",
        status=status,
        evidence_matches=evidence_dicts,
    )

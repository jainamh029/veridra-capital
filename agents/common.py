"""Shared plumbing for the task-specialized agents.

Architecture note: the extraction/fraud hub is the ONE fine-tuned model
(`capitalcall-extract` / `capitalcall-fraud`). These satellite agents are
prompt-specialized wrappers around a general instruct model served by the SAME
local Ollama (`qwen2.5:3b-instruct`) — the narrow JSON fine-tune would be poor
at prose planning/forecasting narratives. No extra models are trained.
"""

import json
import os
import sqlite3
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "synthetic_data", "output", "accounting.db")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
NARRATIVE_MODEL = os.environ.get("CC_NARRATIVE_MODEL", "qwen2.5:3b-instruct")

# Fixed "as of" date for the synthetic world (data spans 2021-01-05 .. 2025-12-30).
# Q3-2025 close: ~4.75y of history plus Q4-2025 obligations still ahead.
AS_OF = os.environ.get("CC_AS_OF", "2025-09-30")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ask_llm(system: str, prompt: str, *, temperature: float = 0.2, num_predict: int = 500,
            timeout: int = 600) -> str:
    body = json.dumps({
        "model": NARRATIVE_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body)
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return resp["message"]["content"].strip()
    except Exception as e:  # narrative is a nicety; never let it break the agent
        return f"[narrative unavailable: {e}]"


def fund_row(fund_id: str):
    with db() as c:
        r = c.execute(
            "select distinct fund_id, fund_name, gp_entity_name from capital_calls where fund_id=?",
            (fund_id,),
        ).fetchone()
    if not r:
        raise ValueError(f"unknown fund_id {fund_id!r}")
    return dict(r)


def list_funds():
    with db() as c:
        return [dict(r) for r in c.execute(
            "select distinct fund_id, fund_name from capital_calls order by fund_id")]


def usd(x) -> str:
    return f"${x:,.0f}"

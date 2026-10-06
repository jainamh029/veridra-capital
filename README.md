# Veridra Capital

**An operating system for fund finance.** Veridra Capital verifies every capital call notice for wire fraud, routes each decision through human approval, plans cash, forecasts the next call, and matches every Schedule K-1 to the right fund and LP, all in one console.

> **Synthetic data only.** Every fund, LP, bank, notice, and balance in this repo is generated. No real financial or personal data appears anywhere.

**Demo video:** [brag-output/Veridra Capital.mp4](brag-output/Veridra%20Capital.mp4) (about 70 seconds, narrated walkthrough of every module)

---

## The problem

A capital call notice tells an investor where to wire a large sum. Fraudsters imitate these notices: they alter one routing digit, swap in a different bank, spoof the sender's domain, or push a "last-minute bank change." A single missed detail can send real money to the wrong place.

## What it does

One notice goes in as raw text. One decision comes out.

```
raw notice
  → extraction      fine-tuned local model pulls entity, bank, routing, amount, due date
  → rules layer     ABA checksum + exact compare of bank / routing / GP name / sender domain
                    against the fund's locked baseline. Every check runs, none short-circuit.
  → model layer     fine-tuned wire-fraud model gives an independent second opinion
  → decision        PASS / REVIEW / BLOCK, severity = the maximum across all findings
  → approver alert  names every failed check, with observed vs. on-file values
  → human decision  Approve / Reject / Needs info. The platform never sends a wire.
```

### The five modules

| # | Module | What it does |
|---|---|---|
| 1 | **Fraud Verification** | Extraction, deterministic rules, and a fine-tuned fraud model reconciled into one PASS / REVIEW / BLOCK decision with a named, specific alert. |
| 2 | **Payment Approvals** | Every notice, cleared or flagged, opens a tracked approval record. Append-only audit log, decisions are immutable (only reversible by opening a new record), per-record locking, and a mock notification hook. |
| 3 | **Cash Planning** | Confirmed cash (historical ledger plus only APPROVED calls) reported separately from near-term pending obligations. The two numbers are never merged, and a reconciliation check runs per fund. |
| 4 | **Forecasting** | A deterministic projection of each fund's next expected call from its own history (mean gap plus recent amounts). It is shown as a visibly tentative third tier, clearly labelled an estimate and never summed with actuals. |
| 5 | **K-1 Routing** | Reads a Schedule K-1, identifies the fund and LP with deterministic fuzzy matching, and routes it. If it can't match confidently it goes to NEEDS_REVIEW rather than guessing. If the model is down it waits in AWAITING_EXTRACTION instead of silently downgrading. |

### Design principles

- **Deterministic where it counts.** Baseline comparisons are exact string checks in code. They are never left to a model to eyeball. (The fraud model's own "identical / not identical" claims are ignored and recomputed in code.)
- **Human approval, always.** There is no code path that executes a payment.
- **Every check runs.** The verdict is a function of the full set of failed checks, so there is no first-match-wins ordering bug. Regression tests assert order-independence and pairwise severity.
- **Honest about limits.** Numbers below are on synthetic data and are labelled that way.

---

## Results (synthetic data)

| | |
|---|---|
| Extraction model, held-out (200 notices) | JSON valid 200/200; field exact-match 99.5–100% on all 9 fields |
| End-to-end batch, 33 unseen notices (15 clean, 18 fraud) | precision 1.000, recall 1.000, 0/15 false positives, 0 errors |
| Fraud types covered | altered routing digit, wrong bank (valid checksum), misspelled GP name, look-alike sender domain, unverified last-minute bank change, and combined attacks |

These show the pipeline works on synthetic notices built to resemble real ones. They do **not** show performance on real, messy documents (OCR noise, legitimate bank changes, multi-bank funds), which is a different and untested claim. The rules layer's 100% is a synthetic-data ceiling, not a product claim. See [PIPELINE_DEMO_RESULTS.md](PIPELINE_DEMO_RESULTS.md) and [BUILD_LOG.md](BUILD_LOG.md) for the full record, including the wire-fraud model's four fine-tune iterations and the bugs found along the way.

---

## Repository layout

```
agents/          FastAPI app (agents/app.py) + narrative agents + original static demo pages
verification/    Rules, verdict/severity engine, report reconciliation, end-to-end pipeline
approvals/       Approval state machine, append-only store, notification hook
cash_planning/   Confirmed vs. near-term cash, reconciliation
forecasting/     Next-call projection
k1_routing/      K-1 extraction, matching, tracking
synthetic_data/  Fund / LP / notice / fraud / ledger generator
training/        Fine-tuning data prep, prompts, LoRA configs, Modelfiles, eval scripts
demo_batch/      The 33-notice leak-free evaluation batch
tests/           Regression and contract tests
frontend/        React + Three.js site and live console
brag-output/     Hyperframes project and render for the demo video
```

## Tech stack

- **Backend:** Python, FastAPI, SQLite, RapidFuzz
- **Models:** Qwen2.5-1.5B-Instruct, LoRA fine-tuned with MLX (`mlx-lm`), served by Ollama. A general `qwen2.5:3b-instruct` handles narratives and K-1 extraction.
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Framer Motion, React Three Fiber, Recharts
- **Video:** Hyperframes (HTML to MP4) with Kokoro TTS narration

---

## Running it locally

The fine-tuned model weights are **not** in this repo (they are large and gitignored). You need Ollama and the models below to run the full pipeline. See "Reproducing the models".

**1. Backend**

```bash
python3 -m venv capital-call-env && source capital-call-env/bin/activate
pip install -r requirements.txt
python -m synthetic_data.run_pipeline      # regenerate the synthetic dataset (~112 MB, gitignored)
uvicorn agents.app:app --port 8000
```

API docs: http://localhost:8000/docs

The pipeline calls Ollama at `http://localhost:11434` and expects these models:

- `capitalcall-extract`: fine-tuned field extraction
- `capitalcall-fraud`: fine-tuned wire-fraud second opinion
- `qwen2.5:3b-instruct`: narratives and K-1 extraction

**2. Frontend**

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev          # http://localhost:5173
```

The home page is the animated marketing site. The live console is at `/console`: Overview, Fraud Verification, Payment Approvals, Cash Planning, Forecasting, and K-1 Routing. The console calls the API at `http://localhost:8000` (override with `VITE_API_BASE`). If you run Vite on a different port, add that origin to the CORS list in [agents/app.py](agents/app.py).

To try it: open **Console → Fraud Verification**, load a sample notice (one clean, two fraudulent), and run it through the pipeline. Then open **Payment Approvals** to act on the record it created.

**3. Tests**

```bash
./predeploy.sh      # import check + full regression suite; the gate before shipping a model or pipeline change
```

## Reproducing the models

The training data and configs are included.

1. Prepare data: `training/prepare_data.py` (extraction), `training/prepare_fraud_data.py` and `training/augment_domain_data.py` (fraud)
2. Fine-tune with `mlx_lm.lora` using [training/lora_config.yaml](training/lora_config.yaml) and [training/fraud_lora_config.yaml](training/fraud_lora_config.yaml) (QLoRA on `mlx-community/Qwen2.5-1.5B-Instruct-4bit`)
3. Fuse the adapters (`mlx_lm.fuse --dequantize`), then `ollama create` from [training/Modelfile](training/Modelfile) and [training/Modelfile.fraud](training/Modelfile.fraud)

Training was done on an 8 GB MacBook Air (M3). [BUILD_LOG.md](BUILD_LOG.md) documents the memory-pressure crash and the settings that avoid it.

## Known limitations

- No authentication. This is a local demo surface, not a production system.
- Notifications are logged to a file only (a real email or Slack sender is a future plug-in).
- The approval store is a JSONL file with in-process locking, so it is safe in a single process only.
- All accuracy figures are on synthetic data (see Results).
- The older single-fund endpoints in [agents/](agents/) (`/forecast/{id}`, `/k1/route`) coexist with the newer modules and are slated for consolidation.

## License

No license has been chosen yet. Until one is added, all rights are reserved by default.

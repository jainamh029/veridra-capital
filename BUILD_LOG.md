# Build Log — Capital Call Verification Platform (local, synthetic-data-only)

This log tracks real state, not aspirational state. Update it after every phase.

## Environment

- MacBook Air, Apple M3, 8GB RAM, arm64.
- Python 3.14.6 (Homebrew) — only Python available on the system; no 3.11/3.12 installed.
  mlx-lm 0.31.3 and all deps installed cleanly against 3.14, no compatibility issues hit.
- Ollama 0.32.3 already installed prior to this build.
- Disk: started at 6GB free (critical). Freed ~6.7GB by removing unused pre-existing models
  (`llama3:latest`, `llama3.2:3b`) with user's confirmation. ~12GB free at start of Phase 2.
  **Disk remains a constraint for Phase 3** (base model download + fused copy + GGUF copy).
  Will re-check before starting fine-tuning and flag if tight again.

## Phase 1 — Environment setup: DONE

- Created venv `capital-call-env` in project root.
- Installed: mlx-lm, pandas, numpy, faker, python-dotenv, fastapi, uvicorn (+ transitive deps).
- Verified: all imports work, `mx.array` computes on Metal backend.
- Ollama sanity check: pulled `qwen2.5:1.5b` (986MB), ran `ollama run qwen2.5:1.5b "Say OK and nothing else."` → returned `OK`. Serving path confirmed working before touching fine-tuned weights.

## Phase 2 — Synthetic data generation: DONE

- Built `/synthetic_data/` pipeline: `config.py`, `banks.py` (valid-ABA-checksum synthetic bank
  directory), `fund_generator.py`, `notice_templates.py` (4 styles: formal PDF-style, casual bullet
  email, fund-admin email, messy GP email), `capital_call_generator.py` (ties call events to an
  investment/fee/expense schedule per fund, not random), `fraud_injector.py`, `ledger_generator.py`,
  `validate.py`, `run_pipeline.py`.
- Generated: **10 funds** (Fund II-IV, buyout/growth equity, $150M-$600M target size, 15-25 LPs
  each), **32,259 capital call records** over the 2021-01-05 to 2025-12-30 window (spec said
  "roughly 26,000" — actual count landed higher because LP rosters + call cadence were tuned before
  seeing the real output; same order of magnitude, internally consistent, not re-tuned down since
  more data only helps Phase 3 fine-tuning).
- Fraud subset: **2,258 records (7.0%)**, within the 5-10% spec band, roughly evenly split across
  the 5 fraud types (altered routing digit, wrong-bank-valid-checksum, misspelled entity name,
  spoofed sender domain, last-minute bank change with no prior notice). Each fraud record carries
  `fraud_type` + `fraud_reasoning`.
- GL ledger: 3,250 transactions across 7 chart-of-accounts codes (cash, LP contributions,
  distributions, investment proceeds, investment deployments, mgmt fee expense, fund expenses),
  18,210 daily cash balance rows (10 funds x ~1821 days).
- Outputs in `synthetic_data/output/`: `funds.json`, `capital_calls.jsonl` (full, incl. notice
  text), `extraction_dataset.jsonl` (input/output pairs for Phase 3 fine-tuning),
  `capital_calls.csv`, `chart_of_accounts.csv`, `gl_transactions.csv`, `cash_balances_daily.csv`,
  `fee_schedule.csv`, `fraud_summary.csv`, `accounting.db` (SQLite, for Phase 5 agents to query).
  Total ~112MB.
- **Validation (`python -m synthetic_data.validate`): PASSED**, all 9 checks green — no duplicate
  call IDs, due_date >= call_date, dates within window, capital calls reconcile exactly to GL
  capital-contribution postings, daily balances never go negative, fraud records actually differ
  from their fund's known-good baseline in the field(s) their fraud_type claims to alter, clean
  records match baseline, fraud rate in band, per-LP amounts sum to event totals.
- Bugs caught and fixed during this phase (both real bugs, not spec issues): (1) fund names had a
  duplicated "Partners" ("Sagebrush Partners Partners IV") from a naming-template collision — fixed
  by removing "Partners" from the interchangeable middle-word list; (2) the entity-misspelling typo
  generator could silently produce a no-op when it transposed two identical adjacent letters (e.g.
  the double "o" in "Bramblewood") — fixed by only transposing adjacent letter pairs that differ,
  with a fallback mutation if none exist. Caught by the validation script, not manual inspection —
  exactly what it was built to catch.
- Disk: ~10GB free remaining after the ~112MB of output (down from ~12GB at start of Phase 2).

## Phase 3 — Fine-tune extraction + wire-fraud models: DONE (with one documented ML ceiling)

### Crash recovery note
A first fine-tune attempt (bf16 LoRA on Qwen2.5-1.5B-Instruct, seq 1024, no grad checkpointing)
drove this 8GB machine into a **system-wide memory-pressure kernel panic** (`watchdog timeout: no
checkins from watchdogd in 94 seconds`, 11 swapfiles) ~7 min in, before the first checkpoint —
zero adapter weights saved. Not a code bug: MLX/Metal GPU allocations show as *wired* memory and,
stacked with VS Code + browsers + Ollama, exhausted RAM. Fix applied to every run since: 4-bit
QLoRA base + `grad_checkpoint: true` + right-sized `max_seq_length` + run with heavy apps closed.
Training peak held at ~2.4-2.8GB thereafter, no further panics.

### 3a. Extraction model — DONE
- Data: `training/prepare_data.py` -> `training/data/{train,valid,test}.jsonl` (1200/300/200),
  class-balanced across the 5 fraud types, Qwen ChatML format, `mask_prompt` on.
- Fine-tune: `mlx_lm.lora` QLoRA on `mlx-community/Qwen2.5-1.5B-Instruct-4bit`, 8 layers, seq 768,
  `training/lora_config.yaml`. Converged fast (val loss 0.27 -> 0.011 by iter 50); stopped at the
  converged iter-200 checkpoint (train loss 0.004).
- Fuse: `mlx_lm.fuse --dequantize` -> fp16 standalone (mlx_lm GGUF export doesn't support qwen2).
- Held-out eval (`training/evaluate.py`, 200 unseen test notices): **JSON valid 200/200 (100%);
  field exact-match 99.5-100% on all 9 fields** (entity 199/200, everything else 200/200).
  fraud_flag on this model alone: precision 0.66 / recall 0.45 — weak, expected, superseded by 3b.
- Served: Ollama `capitalcall-extract` (`training/Modelfile`, q4_K_M, ~986MB). Verified structured
  JSON on held-out clean + fraud notices via `/api/chat`.

### 3b. Wire-fraud model — DONE, **v3.1 deployed** (four fine-tune iterations)

DEPLOYED: `capitalcall-fraud` in Ollama is **v3.1** (id 0985aa77e9c0, q8_0, ~1.6GB).
`training/fraud_adapters/` holds the v3.1 MLX adapter (iter-200). Only v3.1's prep/prompt/
config files are on disk; earlier versions live in this log.

Iteration history (all QLoRA, 4-bit base, 8 layers, grad-checkpointed, stopped at converged
iter-200/300; held-out eval = `training/evaluate_fraud.py` / `training/eval_v3_targeted.py`):

| ver | schema | precision | recall | spoofed_domain | misspelled_entity | altered_routing |
|-----|--------|-----------|--------|----------------|-------------------|-----------------|
| v1  | holistic MATCH/DIFF, baseline in prompt | 0.95 | 0.60 | 8% | 57% | 42% |
| v2  | CoT, char-spaced routing+domain | 1.000 | 0.695 | 12% | 65% | 72% |
| v3  | + forced per-field identical YES/NO, char-spaced ALL fields, "flag any diff" | 0.916 | 0.65 | 30% | **42%** | 98% |
| **v3.1** | **word-split entity/bank, char-spaced routing, domain+lengths, softened instruction** | **1.000** | **0.93** | **95%** | **90%** | 88% |

(v3.1 recall is on a hard-weighted 190-row sample: 40 clean + 40 each routing/entity/domain +
15 each wrong-bank/last-minute; on the natural distribution it is higher.)

Key findings across the four rounds:
- **char-spacing helps 9-digit routing numbers (42→98%) but HURTS long entity names** (v3: 65→42%)
  — the model loses the thread over a 60-token spaced string.
- **word-split comparison** (compare names token-by-token; a 2-char typo lands in one 11-char
  word) is what cracked misspelled_entity (→90%).
- **explicit length fields** on the domain catch ~59% of typosquats for free (`.co` vs `.com`,
  inserted hyphen); the rest need the char scan. Together: 12→95%.
- v3's "set identical=NO on ANY difference" instruction caused 22.5% false positives (the model
  flags its own char-spacing copy errors). v3.1's "NO only when a concrete diff position / word
  / length mismatch is located" restored precision to 1.000 / 0 false positives.
- q4_K_M measurably degrades the brittle comparison; **q8_0** is the serving quant.
- Ollama safetensors importer assigns a null pass-through template (`TEMPLATE {{ .Prompt }}`)
  that drops the system prompt + ChatML framing — both Modelfiles carry an explicit Qwen2.5
  ChatML `TEMPLATE` byte-matching `apply_chat_template`.
- Ollama `create` leaves multi-GB f16 GGUF temp blobs unreferenced by any manifest after
  repeated imports; ~9-12GB reclaimed twice by GC'ing blobs not in `models/manifests/`.

Deployed smoke test (`training/fraud_smoketest.log`): **7/7** — 2 clean PASS, all 5 fraud types
correct flag + type, including spoofed_sender_domain (v2 missed this one).
- Ollama gotcha fixed: its safetensors importer assigns a null pass-through template
  (`TEMPLATE {{ .Prompt }}`) that drops the system prompt + ChatML framing. Both Modelfiles now
  carry an explicit Qwen2.5 ChatML `TEMPLATE` byte-matching `apply_chat_template` from training.
- Disk: recovered ~12GB of orphaned f16 GGUF blobs left by repeated `ollama create` runs
  (unreferenced by any manifest). Removed Phase-1 scratch `qwen2.5:1.5b`. ~10GB free now.

### Phase 3c — spoofed-domain OOD gap investigation (v3.2 attempt)

Trigger: on out-of-domain funds (F2 = Thistlewood, `prairiehatch-fundadmin.com` vs
`prairiehatchfundadmin.com`) the deployed model's OWN fraud flag missed the domain typosquat;
only the rules layer caught it.

**Root cause (measured, not guessed):**
- NOT class imbalance — v3.1 training had 340 examples of every fraud type.
- NOT schema — `sender_domain` is an explicit input field, `domain_check` an explicit output field.
- NOT prompt mismatch (though see Modelfile bug below).
- **Domain-vocabulary narrowness.** All 340 v3.1 spoofed-domain training rows compared against
  the SAME 10 fund GP domains. Standalone catch rate: **98% in-distribution (10 known domains),
  67% out-of-distribution** (12 invented funds). Failures clustered on hyphen insert/remove and
  the subtlest single-char swaps — cases where the model emitted `identical: "YES"`.

Bug found & fixed along the way: `training/Modelfile.fraud` had a hardcoded SYSTEM prompt that
was never regenerated after v2 — every Ollama deploy since v2 served v3.x weights with the v2
prompt. Only `ollama run` (no system override) was affected; all eval/pipeline paths pass the
prompt explicitly from `fraud_system_prompt.py`, so prior numbers stand. Modelfile.fraud is now
regenerated from `fraud_system_prompt.py` on every deploy.

**v3.2 data changes:** `training/augment_domain_data.py` — spoofed-domain + matching clean rows
over **150 distinct synthetic company domains** (vs 10), split by company (held-out domains never
in train). Over-weighted hyphen / subtle-swap techniques; added combined domain-spoof + entity-
typo rows. System prompt: added a "compare observed_length to baseline_length FIRST" rule.
Rebalanced counts (train): spoofed_sender_domain 340 -> **900**; other 4 fraud types 340 each
(unchanged, Phase-2 pool cap); clean 1700 -> 2260.

**v3.2 Step-5 result — the fix OVER-CORRECTED, do NOT ship as-is:**
| metric (standalone model, no rules) | v3.1 | v3.2 |
|---|---|---|
| spoofed-domain caught, held-out fresh domains | ~67% (OOD) | **99%** |
| spoofed-domain, 12 hand-built OOD cases | 8/12 | 9/12 |
| F2's own model flag | MISS | **CATCH** |
| **false positives on CLEAN, held-out (overall)** | ~0% | **40%** |
| false positives on CLEAN, realistic .com domains only | ~0% | **10%** |
| false positives on CLEAN, non-.com TLDs (.io/.fund/.capital) | ~0% | 33-100% |

v3.2 closes the detection gap (99% / F2 model-flag now fires) but trades it for a 10% (realistic)
to 40% (broad) false-positive rate on legitimate notices — the model learned a "flag domains,
especially non-.com" bias from the 2.65x spoofed over-representation + weird training TLDs + the
length-first instruction it can't actually execute (it emits `identical: NO` as a default).

6-case pipeline batch (rules + v3.2 reconciled) is still 6/6 correct incl. F2 now BLOCK/high
(both layers) — but that's the reconciled system; the isolated-model FP rate is the real result.

### v3.3 — corrected (DEPLOYED)

`capitalcall-fraud` in Ollama is now **v3.3** (id a52e1673c4f2, q8_0). Fixes vs v3.2:
- domain_check schema: dropped the `observed_length`/`baseline_length` fields and the
  "compare lengths FIRST" instruction (the model could not execute them and defaulted to
  `identical:"NO"`, which over-flagged). Back to v3.1's plain observed/baseline/first_diff/identical.
- system prompt adds one explicit clause: an unusual-looking domain (hyphens, long name, .net/.org)
  that *equals* the authorized domain is still `identical:"YES"`.
- augmentation rebalanced: spoofed_sender_domain train 900 -> **610** (1.8x, not 2.65x);
  **900 hard clean negatives** (unusual-but-matching authorized domains: hyphenated .com, compound
  names, .net/.org — observed == baseline); realistic TLDs only (.com-heavy + .net/.org, NO
  .io/.fund/.capital), SAME distribution for clean and spoofed so TLD carries no fraud signal;
  187 distinct spoofed baseline domains; train clean:spoofed = 4.3:1.

**v3.3 Step-5 (standalone model, no rules):**
| metric | v3.1 | v3.2 | **v3.3** |
|---|---|---|---|
| spoofed-domain caught, held-out fresh domains | ~67% (OOD) | 99% | **92% (46/50)** |
| spoofed-domain, 12 hand-built OOD cases | 8/12 | 9/12 | **10/12** |
| **false positives on CLEAN, held-out** | ~0% | 40% | **4% (5/125)** |
| F2's own model flag | MISS | CATCH | **context-dependent** |

v3.3 is the right balance: +25pt OOD spoof detection (67 -> 92%) for +4pt clean FP (0 -> 4%),
vs v3.2's unusable 40% FP. **Honest remaining gap:** hyphen-insertion/removal typosquats
specifically (e.g. F2 `prairiehatch-fundadmin.com`) sit right at the model's capability boundary
— caught ~50% of the time, context-dependent (caught in the formal-template probe, missed with
the casual notice + real baseline in the 6-case batch). `bright-pinevc.com` and
`hollowmereequity.com` in the OOD set are the other two misses, both hyphen edits. This is a
subword-tokenization limit, not a data problem — a 7th fine-tune is not expected to clear it.

6-case pipeline batch (rules + v3.3 reconciled): 6/6 correct decisions. F2 -> BLOCK (rules
flag; model flag did not fire that run -> confidence "medium"). The rules layer remains the
fraud authority (100% on synthetic incl. all hyphen cases); v3.3 is a much stronger independent
second opinion than v3.1 (92% vs 67% OOD) but not a complete one on hyphens.

Also fixed: `verification/pipeline.py` fraud-model `num_predict` 400 -> 512 (v3.3's CoT output
occasionally hit the 400 cap and failed to parse -> a spurious model_flag=None).

### v3.4 — the two diagnosed bugs (final automatic iteration)

**Bug 1 (architectural, pipeline-only — no retrain needed for it):** `identical` /
`first_diff_position` were FREE-FORM MODEL GENERATION, not code-derived — `pipeline.py` read
`p["fraud_flag"]` directly. And `domain_check.identical` is **87% YES** in training (all four
checks 78-91% YES), so under uncertainty the model emits YES; it also sometimes "auto-corrects"
a typosquat when echoing it back. Fix: `verification/pipeline._derive_verdict()` — recomputes
the string-equality verdict deterministically from the values we hold (extracted observed fields
+ locked baseline + parsed envelope domain), applies the decision rules in code, and uses the
model only for `bank_change_announced`. Domain compare is EXACT (lowercase + trim only — must
NOT normalise away hyphens/dots/TLDs, which is what a typosquat changes).

**Bug 2 (data + retrain):** `spoofed_sender_domain` training was **68% one formal template**
(414/610) vs ~25%/template for the other four fraud types. The augment generator emitted a
single style. Fix: augment `notice()` now rotates all four templates (formal_pdf / casual_bullet
/ fund_admin / messy_gp); verified ~25% each for every fraud type in v3.4 train. Also reduced
spoofed over-weight 1.8x -> **1.5x** (510 vs 340).

**v3.4 Step-4 (standalone model + Bug-1 derived verdict, rules bypassed):**
| check | target | v3.3 | **v3.4** |
|---|---|---|---|
| held-out spoofed caught (strict `spoofed_sender_domain` label, 36 fresh-domain rows) | >=90% | 92% | **86% (31/36)** |
| held-out spoofed BLOCKED (any fraud label) | - | - | **100% (36/36)** — the 5 non-"spoofed" are combined domain+entity attacks blocked as `misspelled_entity_name` |
| 12 hand-built OOD cases (derived) | - | 10/12 | **12/12 (100%)** — incl. 3 hyphen/lookalike the raw model still misses |
| **false positives on CLEAN (100 held-out)** | <=2% | 4% | **0/100 (0%)** |
| F2 formal vs casual template | consistent | template-dependent | **consistent (both CATCH)** |
| `identical` self-contradiction | resolved | still generative | **now computed in code, deterministic** |
| 6-case pipeline batch (rules + model reconciled) | - | 6/6 decisions | **6/6 decisions; F2 model_flag now fires -> BLOCK/high** |

(raw model standalone on the same held-out set: 81% spoofed / 16% clean FP — the template
rebalance helped a little but the model alone is still not reliable; the Bug-1 code verdict is
what makes the deployed path solid.)

**Targets: FP <=2% HIT (0%). Catch >=90% NOT strictly hit** on the per-type label (86%, -4pts) —
though spoofed BLOCK rate and the 12 OOD cases are both 100% and F2 is now consistent. Diagnosis
of the 86%: v3.4's held-out set has ~20% combined domain+entity attacks; `_derive_verdict`
labels those `misspelled_entity_name` (branch priority) — they are blocked, just under the
co-occurring typo. On a pure domain-only spoof, every row has domain != baseline so the derived
verdict blocks 100% by construction.

Per the run's STOP CONDITION this was the final automatic iteration — no v3.5. **DECISION (user):
accept v3.4 as the final version for this gap.** Deployed: `capitalcall-fraud` id f5465daaab7d
(q8) + the Bug-1 `_derive_verdict` pipeline fix.

**Documented known limitation (spoofed_sender_domain):** on a *combined* attack that spoofs the
sender domain AND misspells the GP entity in the same notice (~20% of the synthetic
spoofed-domain population), the model path's `_derive_verdict` labels it `misspelled_entity_name`
(it checks entity before domain) rather than `spoofed_sender_domain`. The wire is still BLOCKED —
only the fraud_type tag differs. Pure domain-only spoofs are labeled and blocked correctly at
100% (exact string compare in code). If a downstream consumer needs the precise
`spoofed_sender_domain` tag on a combined attack, the deterministic rules layer is the backstop:
it evaluates all four checks independently and will report the domain typosquat regardless of a
co-occurring entity typo. Standalone strict per-type catch on the v3.4 held-out set: 86%
(31/36); the other 5 are these combined attacks, all blocked.

`training/fraud_adapters/` now holds the **v3.4** adapter.

### Wire-fraud model — consolidated before/after (v3.1 -> v3.4), spoofed-domain focus

All numbers standalone (rules layer bypassed); "v3.4 derived" = model + Bug-1 code verdict.

| | v3.1 | v3.2 | v3.3 | v3.4 (raw model) | **v3.4 (Bug-1 derived)** |
|---|---|---|---|---|---|
| spoofed caught — in-distribution (10 known domains) | 98% | 99% | ~98% | — | — |
| spoofed caught — held-out fresh domains | ~67% | 99% | 92% | 81% | **86% type / 100% blocked** |
| spoofed caught — 12 hand-built OOD | 8/12 | 9/12 | 10/12 | 9/12 | **12/12** |
| clean false-positive rate (held-out) | ~0% | 40% | 4% | 16% | **0%** |
| F2 (formal vs casual template) | miss / — | catch / catch | catch / miss | — | **catch / catch** |
| `identical` field | generative | generative | generative | generative | **deterministic (code)** |

Net across the four iterations: the durable fix for the spoofed-domain gap turned out to be
**architectural** (Bug 1 — move the string-equality verdict out of the model into code), not more
training data. Data-side changes (domain diversity, template balance, ratio tuning) improved the
raw model modestly (67% -> 81-92% depending on version) but never made it reliable standalone,
and v3.2 showed data over-correction is easy (40% FP). The v3.4 derived path is 0% FP / 100%
blocked because an exact string compare in code cannot be fooled by a hyphen the model can't see.

### Phase 3 open / not done
- GGUF path: used Ollama's native safetensors import, NOT llama.cpp (`gguf` pkg + llama.cpp not
  installed; disk was tight). Equivalent result.
- fp16 fused models deleted after import to save disk; re-create with `mlx_lm.fuse` from the kept
  adapters (`training/adapters/`, `training/fraud_adapters/`) if needed. NOTE: `training/
  fraud_adapters/` currently holds the **v3.4** adapter; earlier fraud adapters were overwritten
  in place each iteration (the Ollama GGUF blobs are the only artifact of v2/v3.1/v3.2/v3.3).

## Phase 4 — Rules-based verification layer: DONE

Package `verification/` (pure Python, no LLM dependency):
- `aba.py` — ABA routing-number checksum.
- `baseline.py` — loads each fund's locked baseline from `funds.json` (GP entity, bank,
  routing, account, GP domain, + derived fund-administrator domain); `resolve_by_fund_name`
  (safe key — no fraud type alters the fund name).
- `rules.py` — `run_rules(...)` -> `RulesResult`. Checks: ABA checksum; routing == baseline;
  bank name vs baseline (token_sort_ratio >= 90); entity vs baseline (normalized-exact match,
  else rapidfuzz ratio >= 80 => misspelling); sender domain vs the fund's authorized set
  {GP domain, fund-admin domain} (exact => ok; unauthorized + >=80% similar to GP domain =>
  typosquat); bank-change language regex. Classifies into the 5 fraud types by priority.
- `report.py` — `build_report(...)` reconciles extraction + rules + model flag into one
  `VerificationReport` (decision PASS / REVIEW / BLOCK, fraud_type from rules when it fires,
  confidence from model/rules agreement). Policy: BLOCK if rules OR model flags; REVIEW if
  only the model flags (no baseline mismatch found).
- `pipeline.py` — `verify(notice_text, ...)`: extraction (Ollama) -> baseline resolve ->
  rules -> optional Ollama fraud model -> reconciled report. Degrades to rules-only if Ollama
  is unreachable. System prompts loaded from `training/` so they can't drift.
- `evaluate.py` — the mandatory Phase 4 eval.

**Eval (`python -m verification.evaluate`, all 32,259 records, rules fed ground-truth parsed
fields = assumes correct extraction, separately measured at 99.5-100%):**
`precision 1.0000, recall 1.0000, f1 1.0000, fraud_type exact 100%, 0 false positives on
30,001 clean.` Per type: all five at 100%.

Honest caveats:
- This is a **synthetic-data ceiling**. The frauds are exact field mutations against a known
  baseline, so deterministic comparison against that baseline catches them perfectly. Real
  notices bring OCR noise, legitimate formatting drift, multi-bank funds, and M&A name changes
  that would lower this.
- `spoofed_sender_domain` on `fund_admin_email`-format notices: the injected typosquat lives
  only in the record's structured `sender_domain`, not in the notice body (a Phase-2 generator
  quirk). The rules layer catches these only because it is given the envelope domain directly
  — which is realistic (the mail server provides it) but means the number isn't "from text".
- The architecture still keeps rules as the fraud authority (100% on synthetic, deterministic).
  The v3.1 fine-tuned model is now a strong independent second opinion (model-alone ~0.93 recall
  on hard-weighted held-out, precision 1.000) rather than a weak one — useful redundancy and
  cover if a baseline is missing/stale, plus the semantic `last_minute_bank_change` wording.

## Phase 5 — Task-specialized agents: DONE

Package `agents/` — prompt-specialized wrappers, no new training. The narrow JSON fine-tune
would be poor at prose, so these wrap a general instruct model on the SAME Ollama
(`qwen2.5:3b-instruct`); the fine-tuned models stay the extraction/fraud hub. Fixed synthetic
"as of" date 2025-09-30. Each agent returns structured facts + an LLM narrative; the narrative
call fails soft (never breaks the agent).
- `common.py` — Ollama chat helper, SQLite handle, shared date/format helpers.
- `cash_planning.py` — `cash_position(fund_id)`: latest cash balance, 90d inflow/outflow by GL
  category, quarterly management fee, upcoming capital calls (next 90d, event-level), net
  projection + narrative.
- `forecasting.py` — `forecast(fund_id)`: quarterly capital-call history, naive projection
  (mean of last 4 quarters + linear drift — explicitly "not a model") + narrative. On the
  synthetic data this correctly shows early-vintage investment calls tapering to fee/expense
  calls by 2025.
- `payment_approval.py` — `draft_alert(report)`: takes a Phase-4 VerificationReport, returns a
  subject line + short alert naming the specific anomaly and a per-type recommended action.
- `k1_routing.py` — **light stub, labeled**. Generates synthetic Schedule K-1 (Form 1065) text
  from the fund/LP roster, extracts fields via the LLM (deterministic regex fallback), routes
  to a synthetic tax-team contact by LP type. Smoke-tested: correct field extraction + routing.
- `app.py` — FastAPI surface: `/funds`, `/cash/{id}`, `/forecast/{id}`, `/verify`, `/pipeline`
  (Phase 6), `/approve` via pipeline, `/k1/route`, `/k1/samples`, `/health`.
  *(Later: `/cash/{id}` was retired — now 410 → `/cash-planning/{id}` — when Module 3 landed;
  see the Module 3 follow-up section.)*

All four agents smoke-tested end to end against Ollama (`agents/smoketest.log`).

## Phase 6 — End-to-end demo: DONE

`demo.py` — raw synthetic notice -> extraction (`capitalcall-extract`) -> baseline resolve ->
deterministic rules -> fraud model (`capitalcall-fraud`) -> reconciled VerificationReport ->
approver alert. `python demo.py --n 5` runs 5 clean + 5 fraud (one per fraud type, spread
across the 4 notice formats) and prints the full pipeline output for each.

**Result: 10/10 correct** (`demo_output.log`). 5 clean -> PASS; 5 fraud -> BLOCK with the right
fraud_type. With v3.1, `spoofed_sender_domain` now comes back BLOCK / confidence **"high"**
(model AND rules agree — under v2 it was "medium", rules-only). Reconciled system eval
(`verification/evaluate.py --sample N --with-model`): precision/recall 1.00 on the sample.

### Phase 6b — single entry point + leak-free batch run

- **Single entry point:** `verification/demo_pipeline.run_pipeline(notice_text, sender_domain=…)`
  and `POST /decision`. Raw notice -> extraction -> rules -> model (v3.4 + Bug-1 derived verdict)
  -> PASS/REVIEW/BLOCK -> deterministic approver alert. Returns one object: extracted fields,
  every individual check, both layers, decision, alert. Does NOT raise on an unresolved
  baseline — returns `status="NEEDS_ONBOARDING"` routed to an approver.
- **Batch:** `demo_batch/` — 33 notices (`build_batch.py`), leak-free (excludes all 5,136
  call_ids consumed by the extraction + v3.4 fraud train/valid/test sets). 15 clean (4 templates,
  9 funds) + 18 fraud: 3x each of the 5 Phase-2 fraud types + 3 combined domain+entity attacks
  synthesised from unseen clean notices (Phase 2 has no combined attacks).
- **`python -m demo_batch.run_and_score`: precision 1.000 / recall 1.000 / F1 1.000, 0/15
  false positives on clean, 0/33 pipeline errors.** All 5 single-fraud types 3/3 flagged AND
  3/3 exact type label. All 18 alerts name a check that genuinely explains the fraud.
- Write-up for an external reader: `PIPELINE_DEMO_RESULTS.md` (kept no more confident than this
  log — states plainly that it proves the pipeline works on synthetic notices, not on real
  unseen fund documents).

### Phase 6c — first-match-wins fixed structurally (multi-label, severity-ranked verdict)

The "combined-attack label gap" flagged in Phase 6b was **not** a domain+entity quirk. It was a
structural property: `run_rules` and `_derive_verdict` classified by a priority-ordered `if/elif`
that **`return`ed on the first failed check**. Any notice failing 2+ checks surfaced only one,
and which one was an artifact of code order — so `fraud_type`, the alert wording, and the urgency
tier all inherited a single (often the milder) label. Adding fraud types later (e.g. K-1 reuse)
would reintroduce the same under-reporting for other combinations.

**Fix (no decision logic changed, no model changed):**
- `verification/severity.py` — explicit, reviewable per-check severity table
  (`routing_checksum` / `baseline_routing_match` / `baseline_bank_match` / `sender_domain_match`
  = high; `entity_name_match` = medium — a name typo alone is lower-confidence; `bank_change_
  language` = medium-low). `max_severity()` is a pure function of the failed SET.
- `verification/verdict.py` — `evaluate_checks()` runs **every** check, no short-circuit, and
  returns a `Verdict`: `checks` (all of them), `failed_checks` (full list), `labels` (every
  implicated fraud_type), `primary_label` (highest-severity, tie-broken by a fixed table — never
  code order), `overall_severity` (= MAX over failed_checks), `flag`.
- `rules.py` / `pipeline._derive_verdict` are now thin wrappers over `evaluate_checks`;
  `RulesResult` / `model_layer` keep their old single-`fraud_type` fields for back-compat and
  add `.verdict`. `report.build_report` unions failed_checks + labels across rules and model,
  takes max severity, keeps `fraud_type` = primary label; `VerificationReport.as_dict()` now
  also carries `fraud_labels`, `failed_checks`, `overall_severity`.
- `verification/demo_pipeline._alert` rebuilt from `failed_checks` (all) + `overall_severity`:
  names every finding, uses the wording/urgency tier of the **highest**-severity finding.
- `agents/payment_approval.draft_alert` updated to use the multi-label fields when present.

**Regression tests** (`tests/test_verdict.py`, gated by `./predeploy.sh`):
- combinatorial: for **every pair** of check types, a notice failing both -> assert
  `overall_severity == max(sev_a, sev_b)` and both in `failed_checks`.
- order-independence: shuffle / reverse the check list -> `failed_checks` set and
  `overall_severity` and `primary_label` identical. If this can fail, first-match-wins isn't gone.
- decisions-unchanged reference cases (clean -> no flag; each single fraud -> flag).
- 34 tests, all green.

**Re-run of the 33-notice batch (`demo_batch/run.log`):** decisions **unchanged** —
precision/recall/F1 = 1.000, 0/15 false positives, 0 errors. Every single-fraud type 3/3 flagged
with the correct primary label; **the 3 combined attacks now name BOTH sub-labels at severity
`high`** (was: one label, medium wording). Severity tiers land right: single name-typo = medium,
everything else = high.

**Other single-label assumptions found (Step-3 audit) — lower risk, not all changed this phase:**
- `verification/evaluate.py` (Phase-4 rules eval) and `demo.py` (old Phase-6 script) score
  `rr.fraud_type == gold`. Both run only on `capital_calls.jsonl`, which has **no combined
  attacks** (one injected `fraud_type` per record) -> primary_label == that label -> scoring
  unaffected today. Would under-count if combined records were added to that corpus.
- Legacy `POST /pipeline` endpoint uses `agents.payment_approval.draft_alert` — now multi-label
  aware, but the newer `POST /decision` (`demo_pipeline.run_pipeline`) is the intended surface.
- `agents/k1_routing.py` (K-1 stub) does its own extraction and does not touch the verdict path
  yet — when it grows it must call `evaluate_checks`, not reintroduce ordered `if/elif`.

### OOD structural sanity check — Allvue / ILPA template (one document, NOT a metric)

Manual one-off, 2026-09-03. A capital-call notice built on the **real Allvue "US Capital Call
Template" (ILPA Capital Call & Distribution Standard) structure** — a layout the model has never
seen (two-part letter + numbered ILPA sections 2.1-2.22, a narrative paragraph, a bank-address
block, dollar figures at four different scales: $320M commitment, $4.5M prose, $1.045M fund-level,
$154,513 LP call). Values are fictitious; the file was **not** added to the repo or any dataset
(kept in scratch). This is a single hand-made document — it is a structural smoke test only and
does **not** move the held-out numbers in either direction.

- **v3.4 extraction (standalone), field-by-field vs the document:** entity `Vertice Buyout GP,
  LLC` ✅ · fund `Vertice Buyout Fund I, LP` ✅ · LP `Big Bear Retirement Fund` ✅ (dropped the
  "/INV00005" id suffix) · amount `154513` ✅ (correctly took the LP call amount, not the
  commitment / prose / fund-level figures) · due_date `2021-09-30` ✅ (ISO-normalised from
  "09-30-2021") · bank `Cascade Pacific Bank & Trust` ✅ (ignored the address lines) · routing
  `011401533` ✅ · account `8840-2291-7734` ✅. Sender domain is not in the model schema;
  `pipeline.parse_sender_domain` regex got `verticecapital.com` from the `From:` line. **8/8
  requested fields correct on an unseen layout.**
- **Verification layer:** `status = NEEDS_ONBOARDING`, `decision = REVIEW` — correct. The fund is
  not one of the 10 onboarded baselines, so `resolve_by_fund_name` returns None and the pipeline
  routes to approver onboarding rather than PASSing (unsafe — nothing to verify against) or
  BLOCKing (wrong — no fraud signal, just an unknown payee). Alert: "Route to approver for payee
  onboarding."

## Module 2 — Payment Approvals: BUILT

Turns a verification verdict into a **tracked human decision**. It never executes a payment —
that is a hard architectural boundary, not a stub. Every notice that clears the hub (PASS,
REVIEW, **and** BLOCK alike) opens exactly one `PENDING_APPROVAL` record and must be explicitly
acted on. What happens after `APPROVED` (an actual wire) is permanently out of scope for this
project.

### Data model (`approvals/`)
- `model.py` — `ApprovalState` (PENDING_APPROVAL / APPROVED / REJECTED / NEEDS_MORE_INFO),
  `ApprovalRecord` (frozen): `approval_id`, `verification_report_id` (a **reference** to the
  stored hub output — the report is not copied into the record), `fund_id` / `fund_name`,
  `assigned_approver`, `created_at`, small denormalised display scalars (`hub_status`,
  `hub_decision`, `hub_severity`), `state`, `decision_by` / `decision_at` / `decision_note`,
  `supersedes`.
- `store.py` — two **append-only** JSONL logs (`approvals/data/`): `verification_reports.jsonl`
  (one line per hub output, keyed by `report_id`) and `approval_events.jsonl` (one line per
  `CREATED` / `DECIDED` / `REVERSAL` event). Nothing rewrites or deletes a line. Current state
  is derived by replaying events.
- `service.py` — `ingest_pipeline_output()`, `list_pending()` (each item carries the FULL
  verification report + per-check breakdown, not a one-liner), `get_record()`,
  `record_decision()` (appends a `DECIDED` event; **raises `AlreadyDecidedError` if the record
  is not PENDING** — a decision is never edited or overwritten), `reverse_decision()` (creates
  a NEW `PENDING_APPROVAL` record with `supersedes` -> the old record's events are untouched;
  the old record gains a derived `superseded_by` back-link).

### Fund -> approver mapping
Added `assigned_approver` (`{name, email, role}`) to the existing fund/onboarding config —
`synthetic_data/fund_generator.py` (so regeneration includes it), the current
`synthetic_data/output/funds.json` (patched in place), and `verification.baseline.Baseline`
(new optional field; the verdict/verification logic never reads it). 4 synthetic approvers
round-robined across the 10 funds. No parallel config system.

### Unresolved-fund routing gap — found by test, fixed structurally
**Original behaviour (actually run, not assumed):** a capital call for a fund with **no
baseline on file** — the hub correctly returns `status="NEEDS_ONBOARDING"` / `decision=REVIEW`
with no `fund_baseline` block — was ingested **without crashing and without being dropped**, but
`_resolve_approver()` returned `None` and `ingest_pipeline_output()` passed that straight through:
the record was created `PENDING_APPROVAL` with **`assigned_approver = None`** and `fund_id = None`.
It showed up in `list_pending()` but was **owned by nobody**, and the notification fired as
`NOTIFY[NEW] UNASSIGNED APPROVER <?>` — a non-routable recipient. So the one case the hub itself
calls higher-attention (an entirely unknown payee) was the one routed to no one.

**Root cause:** the fund→approver design assumed every fund is pre-registered in `funds.json`
with an `assigned_approver`; there was no path for "fund not recognised". Same shape as the
earlier verdict/severity bugs — a case the rest of the system already signals cleanly
(`NEEDS_ONBOARDING`) but the downstream module had no explicit handling for, so it fell through
to `None`.

**Fix (`approvals/service.py`):** a standing `ONBOARDING_REVIEW_APPROVER` bucket
(`onboarding-review@synthetic-ops.example`, role "Payee onboarding / unrecognized-fund review").
`_resolve_approver()` now returns this bucket whenever **no baseline resolves** — a catch-all for
*any* unrecognised fund, not a hardcoded fund name. The record still gets `hub_status =
"NEEDS_ONBOARDING"` as its distinguishing marker; routing is decided in code, not the model. The
notification hook is unchanged and still fires exactly once — now `NOTIFY[NEW] Onboarding Review
Queue <onboarding-review@synthetic-ops.example>`, a real monitored address.

**Verification (`tests/test_unknown_fund_approvals.py`, 4 tests, Ollama-free, in `predeploy.sh`):**
- unknown-fund notice → visible `PENDING_APPROVAL` record routed to the bucket, one `NOTIFY[NEW]`
  line to the queue address (no `UNASSIGNED` / `<?>`).
- that record survives `decide` → `REJECTED` → double-decide refused → `reverse` (new PENDING,
  still routed to the bucket, `NOTIFY[REVERSAL]` fires) — full lifecycle, not just creation.
- **negative proof:** `test_negative_proof_fallback_is_load_bearing` monkeypatches
  `ONBOARDING_REVIEW_APPROVER = None` and asserts the positive contract then raises
  (`unresolved-fund record has no approver (ownerless)`) and the notification degrades to `<?>`.
  Separately, reverting the fallback at source and re-running made
  `test_unknown_fund_creates_visible_notified_record` and `..._survives_decide_and_reversal`
  **fail** with that same assertion — the tests are not accidentally green.
- **regression:** `test_known_funds_still_resolve_to_real_approver` (3 onboarded funds → their
  real `assigned_approver`, never the bucket); the full 33-notice `approvals/test_batch.py`
  still green with all 33 resolving to real approvers, plus a new step-5 block that runs one
  unknown-fund notice through hub→ingest→decide.

### Wiring
`POST /decision` now calls `approvals.ingest_pipeline_output()` after `run_pipeline()` and
returns an `approval` block (`approval_id`, `state`, `assigned_approver`). New endpoints:
`GET /approvals/pending`, `GET /approvals`, `GET /approvals/{id}`,
`POST /approvals/{id}/decide`, `POST /approvals/{id}/reverse`. The v3.4 model and the
verification pipeline logic were **not modified** (only consumed).

### Test batch (`approvals/test_batch.py`, log `approvals/test_batch.log`)
All 33 Phase-6 notices re-run through the **live hub** -> approvals (scratch data dir):
- **33 notices -> 33 `PENDING_APPROVAL` records** (15 from PASS, 18 from BLOCK) — PASS not
  skipped; every record has a resolved approver and a report reference.
- Simulated decisions: 4 APPROVED, 4 REJECTED, 1 NEEDS_MORE_INFO — `decision_by` /
  `decision_at` / `decision_note` recorded; decided records leave the pending queue (23 remain).
- **Double-decide refused** (`AlreadyDecidedError`); the original APPROVED decision is unchanged
  and the events log still holds exactly one `DECIDED` event for it.
- **Reversal** of a REJECTED record opened a new `PENDING_APPROVAL` record with `supersedes`
  set; the old record is still `REJECTED` and now links forward via `superseded_by`.
- **No payment path:** `grep` across `approvals/` and `agents/` for
  `send_payment|execute_wire|transfer_funds|initiate_payment|disburse|remit_funds|…` -> nothing.
  REJECTED / NEEDS_MORE_INFO records carry no field that could be actioned as a payment.
- 10 fast state-machine unit tests in `tests/test_approvals.py`, added to `./predeploy.sh`.

### Notification hook (`approvals/notify.py`) — added on top, mock only
- `NotificationSender` (ABC, one method `notify(approval_record)`) is the pluggable seam.
  `LoggedNotificationSender` is the **only** implementation: it appends one human-readable line
  per new record to a log (`approvals/notifications.log` in prod; `<data_dir>/notifications.log`
  under a scratch/test run) and echoes to stderr. No network, no `smtplib`/`requests`/`slack_sdk`.
- **A real email/Slack provider is intentionally deferred.** There is no real approver or real
  fund yet, so a provider integration would be infrastructure with nothing to connect to. When
  there is a real fund/approver, a second `NotificationSender` is written and handed to
  `approvals.service.set_notifier(...)` — nothing else in the module changes.
- Wired in at **both** points that create a new `PENDING_APPROVAL` record —
  `ingest_pipeline_output()` (a fresh notice) and `reverse_decision()` (a decided record sent
  back for another look). Each triggers **exactly one** `notify` call via the same
  `NotificationSender` path. The line carries an event tag: `NOTIFY[NEW]` vs `NOTIFY[REVERSAL]`,
  and a reversal line also names the record it supersedes, so the two are never
  indistinguishable duplicates.
  - **Correction to an earlier note in this log:** the first cut wired notification into
    `ingest_pipeline_output()` only and this log said reversal "deliberately does not notify."
    That was a **bug, not a design choice** — a reversed record is a fresh thing that needs a
    human decision, i.e. exactly the case notification exists for, and it was the one case that
    stayed silent. Fixed: `reverse_decision()` now calls the same `_notify_new_record(...)`.
- 33-notice batch re-run (`approvals/test_batch.log`): **33 notification lines on ingest**, one
  per record, correct approver email + `verdict=` (15 PASS, 18 BLOCK) + severity; the batch's
  one reversal then adds a **34th** `NOTIFY[REVERSAL]` line naming the superseded record.
- 7 fast tests in `tests/test_notifications.py` (pluggability, one-line-per-record, PASS
  included, reversal emits one *distinguishable* line, mock-is-the-only-impl).

### UI API contract test (`tests/test_ui_contract.py`)
- The minimal UI reads specific fields out of `GET /approvals/pending`'s JSON. This test parses
  the field names **directly out of `approvals.html`'s JS** (regex over `rec.*`, `vr.*`,
  `appr.*`, `alert.*`, and the `fieldRows()` `order` table) and asserts the live endpoint
  response — via `fastapi.testclient` against an isolated temp store — contains every one, in
  the right place in the object graph (`rec` / `verification_report` / `assigned_approver` /
  `alert` / `extracted`).
- **Risk it closes:** a future change to the response shape (e.g. `service.get_record` /
  `store` renaming or dropping `assigned_approver.email`, `verification_report.alert`,
  `extracted.routing_number`, …) would silently break the page — the only prior check was one
  manual pass. This now fails immediately in `./predeploy.sh`. Because the field list is read
  from the page, the test can't drift out of sync with it. No browser automation.

`./predeploy.sh` now at **60 tests** (34 verdict + 10 approvals + 7 notifications + 1 UI contract
+ 4 unknown-fund routing + 5 concurrency).

### Minimal demo UI (`agents/static/approvals.html`, served at `GET /ui/approvals`)
- One static page, vanilla HTML/JS, no framework, same-origin with the API (no CORS, no build).
- Lists `GET /approvals/pending`: fund, assigned approver, verdict + severity badges, extracted
  fields, failed checks, and the approver-alert subject/body. Per-card **Approve / Reject /
  Needs More Info** buttons + optional note, each calling `POST /approvals/{id}/decide`.
- After a decision the page **refetches** `/approvals/pending` (reflects the real server-side
  state change, not a client-side hide); a 409 double-decide surfaces as an inline error.
- Verified by hand against a live `uvicorn agents.app:app`: seeded 3 pending records, approved
  one + rejected one via the same endpoints the page calls, pending queue went 3 -> 1,
  `GET /approvals/{id}` confirmed the state persisted, second decide returned 409.
- **Not production:** no auth / login, no real notification delivery, single approver view. It is
  a local demo surface a non-technical controller can sit in front of, nothing more.

### Pending-count badge (frontend only, `approvals.html`)
- A bell + count in the header showing the number of `PENDING_APPROVAL` records. The count is
  literally `GET /approvals/pending`'s array length — **no new backend endpoint, no data-model
  change**; it reuses the endpoint the list already calls.
- `setInterval(pollBadge, 7000)` re-fetches that endpoint and updates only the badge (not the
  list, so a half-typed note isn't wiped). The badge also updates immediately after any
  decide, because `load()` calls `setBadge(recs.length)`. Bell pulses when the count rises.
- Plain JS, consistent with the rest of the page — no dependency, no build step.
- Verified against a live server: `pollBadge` read 8; seeded 1 record via `run_pipeline` ->
  `ingest_pipeline_output` -> `pollBadge` read 9 (+1, no page refresh); `POST /decide` the way
  the UI does it -> `pollBadge` read 8 (-1).

### Concurrency: simultaneous decisions on one record — was broken, now fixed
**Actual behaviour BEFORE the fix** (40/40 runs, two threads + a barrier calling
`record_decision` on the same PENDING record):
- **both calls returned success** — neither got a 409;
- the events log got **two `DECIDED` events for the same record** (one record "decided" twice,
  by two people, to two different states);
- the two events **collided on the same `seq`** (`[1, 2, 2]`).
- The JSONL file was *not* line-corrupted — `store._LOCK` already serialised the raw `write()`,
  so no torn/interleaved lines — but the audit trail was logically corrupted.

**Root cause:** check-then-append race in `record_decision` (read state → check PENDING →
append) with nothing atomic between read and write; plus a non-atomic `seq = count + 1` in
`store.append_event`.

**Fix (hardening only, no state-machine / data-model change):**
- `approvals.service._record_lock(approval_id)` — one `threading.Lock` per approval id, created
  on demand — wraps the check-and-append in both `record_decision` and `reverse_decision`
  (the latter keyed on the *old* id). Different records take different locks, so unrelated
  decisions still run in parallel.
- `store.append_event` now computes `seq` and writes the line inside one `_LOCK` hold.
- **Single-process only, stated in both module docstrings.** A JSONL file store has no
  cross-process compare-and-set; two API processes sharing one data dir can still race. Not
  over-promised.

**Negative proof** (`tests/test_concurrency_approvals.py`, 5 tests, in `predeploy.sh`):
- after the fix, the same-record race is **one `200` + one `409`**, exactly **one `DECIDED`
  event**, `seq` unique+contiguous — held over 25 repeats; also checked at the HTTP layer via
  `TestClient` from two threads.
- `test_different_records_decided_concurrently` parks one thread *inside* the locked section
  (holding `_record_lock(a1)`) and asserts a decision on `a2` still completes immediately —
  proves the lock doesn't over-serialise.
- `test_negative_proof_record_lock_is_load_bearing` monkeypatches `_record_lock` to a no-op and
  confirms the race **reappears** (double success or two `DECIDED` events within 30 runs) — the
  concurrency tests are not passing regardless of whether the fix exists.
- Full 33-notice `approvals/test_batch.py` still `STEP 5 PASSED`.

### Telegram — still deferred, not started, not abandoned
No Telegram code exists in the repo (grep-checked). It remains a *future* second
`NotificationSender` implementation — the mock `LoggedNotificationSender` and the
`set_notifier()` seam are what it would plug into. This task did not touch it, per its ground
rules. The in-app badge above is an independent, backend-free indicator, not a replacement for
a real delivery channel.

### Handoff doc
The prompt's module table / "Section 13" handoff doc is not in this repo (only `BUILD_LOG.md`
and `PIPELINE_DEMO_RESULTS.md`). Recording the state here instead; update the external handoff
doc's payment-approvals (Section 13) row to: **backend + notification hook (mock/logged only) +
a minimal demoable local UI with a polling pending-count badge — explicitly not production-ready
(no auth, no real delivery, single approver view). Unknown-fund (`NEEDS_ONBOARDING`) notices
route to a standing `ONBOARDING_REVIEW_APPROVER` bucket instead of landing ownerless. Concurrent
decisions on one record are now safe within a single process (per-record lock; one wins with
409) — not safe across multiple API processes on one data dir. Telegram delivery remains
deferred (no code yet).**

Cash planning (Module 3) row: **deterministic layer (confirmed balance = historical ledger +
APPROVED calls only; near-term = PENDING calls due within a configurable window, reported
separately and never merged) with a full-dataset reconciliation check + negative proof;
optional model narrative that only describes the computed numbers; `GET /cash-planning` and
`GET /cash-planning/{fund_id}` endpoints (thin wrappers, no math) + a `GET /ui/cash-planning`
demo page matching the approvals page style, cross-linked with it; contract test on the UI/API
field shape. Synthetic data only, no auth — same "not production-ready" framing as payment
approvals.**

Scenario / forecasting (Module 4) row: **deterministic next-expected-call projection — a
simple historical extrapolation (mean gap between past confirmed calls + mean of recent
amounts), pure function, not a model; `< 2` calls → no projection. `GET /forecasting`,
`GET /forecasting/{fund_id}` (payload self-labelled `type: projected_estimate`, always ships
the `history_used` it was derived from, `?as_of=` point-in-time), optional model narrative that
only describes the computed projection, and a `GET /ui/forecasting` page showing three
deliberately-unequal-weight tiers (confirmed / pending / projected-as-dashed-tentative), never
summed, cross-linked with the other two pages. Cross-module integration test asserts the
projection's historical basis matches cash planning / ledger exactly. Synthetic data only, no
auth. The older `agents/forecasting.py` (`/forecast/{id}`, quarterly volume off raw notices)
still exists separately — future consolidation item.**

K-1 routing (Module 5) row — **this is the last of the original six modules marked BUILT**:
**identifies which fund + LP a Schedule K-1 belongs to and routes it (no fraud check, no wire,
no approve/reject workflow). Extraction: the general-purpose `qwen2.5:3b-instruct` (documented
choice — not the fraud model, not a new fine-tune; K-1s are lower-stakes). **No silent
degradation:** if the model is unreachable the document lands in `AWAITING_EXTRACTION` and is
retried (`POST /k1-routing/retry-pending`) — never downgraded to a lower-quality method. The
regex code is retained as `regex_extract_explicit` for deliberate/test use only. Matching:
deterministic `rapidfuzz` reusing the hub's `_norm_name` + `fuzz.ratio` ≥ 85 approach against
the existing fund/LP roster (no parallel list); can't identify → `NEEDS_REVIEW`. Append-only
tracking log (`RECEIVED` → `ROUTED` / `NEEDS_REVIEW` / `AWAITING_EXTRACTION`), per-doc lock on
the retry check-then-append. `POST /k1-routing/ingest`, `POST /k1-routing/retry-pending`,
`GET /k1-routing`, `GET /k1-routing/{fund_id}`, `GET /ui/k1-routing` — the four module pages are
now a full nav mesh. Matching accuracy 10/10 on 10 synthetic docs (fast tests inject a
deterministic extractor; opt-in live `qwen2.5:3b-instruct` path also 10/10). Synthetic data
only, no auth. Old `agents/k1_routing.py` stub (`/k1/route`) coexists unused — future
consolidation item.**

## Module 3 — Cash Planning: BUILT (deterministic layer + optional narrative + HTTP/UI)

Answers, per fund: the real **confirmed** cash position now, and the capital calls **known to be
coming due soon** — two separate numbers, never merged. New package `cash_planning/`
(`core.py` deterministic, `narrative.py` optional prose). The hub, payment approvals, the
notification hook and the UI were **not touched** — this module only reads their output. (The
pre-existing `agents/cash_planning.py` narrative agent + its `/cash/{id}` endpoint were later
removed and consolidated onto this module — see the follow-up section below.)

### The one rule
Only an **APPROVED** capital call is real cash. `PENDING_APPROVAL` = a known upcoming
obligation, reported under `near_term_obligations`, **never added to the balance**. `REJECTED`
and `NEEDS_MORE_INFO` are not incoming cash at all — surfaced only as
`excluded_from_balance` counts. Enforced in `core.approved_call_lines` (filters
`state == "APPROVED"`) and covered by explicit tests, not left implicit.

### Data model (read-only sources, nothing re-derived)
- `synthetic_data/output/accounting.db :: gl_transactions` — historical ledger, one row per
  cash movement, `amount` = signed cash impact. `historical_gl_lines(fund, as_of)` returns them
  row-by-row.
- `… :: cash_balances_daily` — the generator's own running balance. It equals the cumulative
  sum of `gl_transactions` for **all 18,210 fund/date points** (verified) — that equality is the
  cross-source reconciliation, the ABA-checksum-equivalent for this module.
- `approvals.service` — `APPROVED` records become positive cash lines; `PENDING_APPROVAL`
  become `Obligation`s.
- Pure functions: `sum_lines`, `confirmed_balance(historical_balance, approved_lines)`,
  `within_window(obligations, reference_date, horizon_days)` (default `NEAR_TERM_HORIZON_DAYS`
  = 30, configurable), `reconcile(...)`. Orchestrator `cash_position(fund_id, …)` returns
  `confirmed_cash_balance`, `confirmed_components`, `near_term_obligations` (separate, labeled
  "not yet realized"), `excluded_from_balance`, `reconciliation`. No model import anywhere in
  `core.py` (AST-checked by a test).

### Reconciliation (Step 3) — the load-bearing check
`sum(every individual line) == reported confirmed balance`, for **every fund**, run against the
full synthetic dataset. `reported_balance` is derived a *different* way (historical part from
`cash_balances_daily`, not from re-summing the GL rows), so it is a real cross-check, not
`x == x`. `tests/test_cash_planning.py` (10 tests, in `predeploy.sh`):
- `test_reconciliation_holds_for_every_fund_empty_approvals` — 10 funds × 3 `as_of` dates,
  `delta == 0.0`.
- `test_reconciliation_holds_with_seeded_approved_calls` — balance moves by exactly the
  approved amounts, recon still exact.
- `test_gl_lines_sum_equals_generated_running_balance` — the full ~18k-point GL-vs-running-
  balance sweep, 0 mismatches.
- **Negative proof (Step 3):** `test_negative_proof_reconciliation_fails_when_an_approved_line_is_dropped`
  computes a balance that omits one APPROVED line while that line is still in the itemized
  ledger → `reconcile(...).ok is False` and `delta == the dropped amount`. Same for a dropped
  GL line (`…_when_a_gl_line_is_dropped`). The check demonstrably fails when the data is wrong.

### Step 5 — behaviour against the full dataset
- `test_only_approved_calls_enter_the_balance` — FUND-05 seeded with 2 APPROVED + 2 PENDING
  (1 near / 1 far) + 1 REJECTED + 1 NEEDS_MORE_INFO: balance == historical + the 2 approved
  only; the near pending appears in `near_term_obligations` and is **not** in the balance; the
  far pending is `pending_outside_window`.
- `test_rejected_and_needs_more_info_have_zero_balance_effect` — snapshot the balance, then
  drive a record to REJECTED (and separately NEEDS_MORE_INFO); balance byte-identical. Tested
  explicitly, not inferred from the filter.
- `test_near_term_window_is_configurable_and_never_touches_balance` — horizon 7/30/60 changes
  which pendings are listed (`{7:0, 30:1, 60:2}`); `confirmed_cash_balance` is identical across
  all three.
- `test_pending_call_due_today_still_not_in_balance` — a $50M pending due on the reference date
  changes the near-term list, not the balance.

### Step 4 — optional narrative (`cash_planning/narrative.py`)
`describe(pos, enabled=…)` feeds the **already-computed** numbers to the existing narrative
model (`qwen2.5:3b-instruct` via `agents.common.ask_llm`) as text and asks for 3-4 sentences.
It computes nothing. `enabled=False` → no model call; Ollama down → `generated=False` with the
reason, deterministic dict untouched. Verified live: for a $2,150,000 confirmed / $2,000,000
near-term case it produced an accurate summary using exactly those figures.

### HTTP endpoints + UI — parity with payment approvals (follow-up task)
Thin exposure layer only. **No computation was added or changed** — verified: the endpoint
response is byte-identical to `core.cash_position()` for all 10 funds, and the overview
endpoint equals `[core.cash_position(f) for f in funds]`.
- `GET /cash-planning/{fund_id}` — one fund's `cash_position()`; 404 on unknown fund.
- `GET /cash-planning` — every fund, for the overview list.
- Both take `?narrative=true` (default **false** — so the endpoint has no Ollama dependency
  unless asked). When set, each item gets a `narrative` block from `narrative.describe()`;
  Ollama down → `{"generated": false, "reason": …}`, endpoint does not crash.
- `agents/static/cash-planning.html`, served at `GET /ui/cash-planning` — same header / card /
  badge style as `approvals.html`. Confirmed balance is a solid green box; near-term
  obligations are a **separate** amber box with a dashed rule and the caption "Known upcoming —
  NOT included in the balance above". The two numbers are never summed anywhere on the page.
  Nav links both ways (`approvals.html` ⇄ `cash-planning.html`) so they read as one product.
- No new dependency, no build step. No auth (deferred, per the standing decision).

Contract test `tests/test_cash_planning_ui_contract.py` (same pattern as
`tests/test_ui_contract.py`): scrapes the field names the page's JS actually reads
(`fund.*`, `comp.*`, `near.*`, `obl.*`, `excl.*`, `recon.*`, `nar.*`) and asserts the live
`GET /cash-planning` response carries every one, at the right nesting. **Negative proof:**
`test_negative_proof_contract_fails_when_a_field_is_dropped` deletes one nested field
(`confirmed_components.historical_ledger_balance`) and one top-level container
(`reconciliation`) from a real response and confirms the contract assertion then raises.

Hand-verified against a live server: both UI pages serve (200) and cross-link; `GET
/cash-planning` renders FUND-01 (one near-term $3.2M call due 2026-09-20, shown separately from
its $0.00 confirmed balance) and FUND-02 (no near-term call) correctly; every fund reconciles
(`delta == 0.0`) through the endpoint.

Numbers are synthetic-dataset only; `as_of` defaults to the last ledger date (2025-12-30),
where these fully-deployed synthetic funds sit near $0 until APPROVED calls are added.

`./predeploy.sh` at **72 tests** after this task; **84** after the consolidation/point-in-time/
integration follow-up below.

### Follow-up — endpoint consolidation, point-in-time, live-decision integration test

**Fix 1 — duplicate cash endpoint (investigated first).** Searched the repo for `/cash/` and
`agents.cash_planning` usage: **nothing depended on the old path** — no test, no UI, no other
module; only `agents/app.py` imported `agents/cash_planning.py`, and only `BUILD_LOG.md`
mentioned the URL. The two paths computed genuinely different things (the old one was *not*
approval-gated and ran an LLM narrative by default), so a still-working stub was a real
drift risk, not just clutter. **Decision: removed it.** `agents/cash_planning.py` is deleted;
`GET /cash/{fund_id}` now returns **410 Gone** with `{"use": "/cash-planning/{fund_id}"}`.
One source of truth: `cash_planning/core.py`.

**Fix 2 — point-in-time (`?as_of`).** Checked core first: `cash_position(as_of=…)` is **real**,
not a hardcoded default — `historical_gl_lines` and `ledger_running_balance` both filter
`WHERE date <= as_of`, and reconciliation was already tested at several dates. So this was pure
plumbing: `?as_of=YYYY-MM-DD` (and `?reference_date=`) added to `GET /cash-planning` and
`GET /cash-planning/{fund_id}`, defaulting to latest ledger date / today. Endpoint-level
date validation added (garbage `as_of` → **422**, not silently "latest" via SQL string
compare). Verified live: FUND-01 `?as_of=2022-12-31` → $5,124,165.65 vs `?as_of=2023-12-31`
→ $13,637,694.04, each identical to `core.cash_position(fid, as_of=…)`, both reconcile.
Tests: `tests/test_cash_planning_endpoint.py`.

**Fix 3 — cross-module integration test (`tests/test_cash_approvals_integration.py`, in
`predeploy.sh`).** Drives the real flow through HTTP: seed PENDING →
`GET /cash-planning/{fund}` → `POST /approvals/{id}/decide` → re-query, for APPROVE / REJECT /
NEEDS_MORE_INFO / reverse. **It found a real bug:** after a reversal the old record stays
`state=APPROVED` (approvals leaves it, adds `superseded_by` + a new PENDING record), and
`cash_planning` kept counting that superseded APPROVED call — so the balance did *not* drop
back and the amount was double-represented (still in the balance *and* the replacement pending
in near-term). **Fixed in `cash_planning/core.py`** (not approvals): `approved_call_lines` and
`_excluded_counts` now skip any record with `superseded_by`. Verified end to end: APPROVE
raises the balance by exactly the amount and drops it from near-term; REJECT / NEEDS_MORE_INFO
move nothing and show up only in `excluded_from_balance`; reverse drops the balance back by the
amount and the new pending reappears in near-term; reconciliation holds at every step. Also
added core unit test `test_reversed_approval_stops_counting_as_cash`. This is now an
always-run automated test, not a one-time manual walkthrough.

`./predeploy.sh` now at **84 tests** (72 + 9 endpoint + 2 integration + 1 core reversal).

## Module 4 — Scenario / Forecasting: BUILT (deterministic projection + optional narrative + HTTP/UI)

Per fund, estimates the **next expected capital call** — a date window and an amount — from the
fund's own past cadence. New package `forecasting/` (`core.py` deterministic, `narrative.py`
optional). The hub, payment approvals and cash planning were **not modified** — this module
reads their output.

### The method — say it plainly: simple historical extrapolation, not a model
`project_next_call(history, as_of)` is a **pure function**. Given the fund's history of
**confirmed** capital calls it computes:
- **next-call date window** = last call date + the *mean gap* between successive past calls,
  ± the *population standard deviation* of those gaps (a rough band, **not** a confidence
  interval). Plus a `point_estimate_date` at the mean.
- **estimated amount** = the *mean of the last 4* call amounts; `amount_trend` = sign of
  (last recent − first recent).
- `< 2` past calls → `sufficient_history: false`, no projection, no invented numbers.

That is the entire method — average interval, average recent amount. It is **not** ML, not a
forecasting model, not a black box, and is not described as more than that anywhere (a test,
`test_method_and_notes_never_oversell_the_projection`, greps the `method`/`note` strings for
"machine learning", "neural", "sophisticated", … and fails if any appear). Deterministic and
order-independent: `test_projection_is_byte_identical_on_repeat_and_order_independent`.

**History source** (read-only, not re-derived): the fund's confirmed capital-call events —
`gl_transactions` rows with `account_code='3001'` (one event per `related_event_id`) **plus**
`APPROVED` records from payment approvals via `cash_planning.core.approved_call_lines`
(superseded ones already excluded). Same confirmed-inflow set cash planning builds its balance
from. Raw unverified notices are never used.

**No model in the math** — `test_projection_math_has_no_model_dependency` AST-parses
`forecasting.core` and asserts it imports no narrative/Ollama/`agents.common` path and never
calls `ask_llm`. Optional `forecasting/narrative.py` (`describe(proj, enabled=…)`) is handed the
finished projection and asked for prose only; `enabled=False` → no call; Ollama down →
`{"generated": false, "reason": …}`, the projection dict untouched (verified live: the
deterministic fields are byte-identical with and without `?narrative=true`).

### Endpoints
- `GET /forecasting/{fund_id}` — the projection **plus `history_used`**, the actual dated call
  amounts it was derived from (a projection is never returned without its basis), plus `basis`
  (avg interval, spread, trend, span) and a read-only `context` block carrying cash planning's
  confirmed-balance and near-term-total for that fund.
- `GET /forecasting` — same for every fund (overview).
- Both self-label the payload: top-level `"type": "projected_estimate"` and a `note` on
  `next_expected_call` — a future API consumer can't mistake it for confirmed data.
- `?as_of=YYYY-MM-DD` (point-in-time; history filtered to `date <= as_of`, default = latest
  ledger date; garbage → 422) and `?narrative=true` (default false, no Ollama dependency).
- `GET /ui/forecasting`.

### UI — three tiers, deliberately unequal weight (`agents/static/forecasting.html`)
Same header/card style as the other two pages; **full nav mesh** — links added so
approvals ⇄ cash-planning ⇄ forecasting.
1. **Confirmed cash balance** — solid green box (cash planning's number, unchanged).
2. **Known pending obligations** — amber box, dashed left rule ("known, not in the balance").
3. **Projected next call** — visibly the *least* solid: dashed border all round, muted grey,
   smaller number, italic caption *"Estimate based on this fund's past pattern only. Simple
   historical extrapolation, not a forecasting model, and not a real obligation."* Shows the
   last 10 history rows + the method string inline.
The three numbers are **never summed** anywhere — `test_three_tiers_are_reported_separately_never_merged`
asserts no value equal to tier1+tier2+tier3 appears anywhere in the payload.

### Tests (12 new, all in `./predeploy.sh`)
- `tests/test_forecasting.py` (8) — determinism/order-independence; **direction check** (this
  module's reconciliation-equivalent): a larger recent amount moves the estimate **up**, a
  smaller one **down**, wider gaps push the window **later**; insufficient history → no
  projection, no crash; don't-oversell string check; no-model AST check; narrative optional;
  adapter reads real data.
- `tests/test_forecasting_ui_contract.py` (2) — scrapes the field names `forecasting.html`'s JS
  reads (`fund.*`, `ctx.*`, `nx.*`, `basis.*`, `hp.*`, `nar.*`), asserts the live `/forecasting`
  response carries every one; **negative proof** drops `next_expected_call.window_start` and the
  `context` block and confirms the check then fails.
- `tests/test_forecasting_integration.py` (2) — **cross-module**: the projection's
  `history_used` ledger part == an independent `sum`/`count(distinct related_event_id)` on
  `gl_transactions` account 3001; its approvals part == `cash_planning.core.approved_call_lines`
  exactly (a seeded APPROVED call appears, a seeded REJECTED one never does); the tier-1 number
  the UI shows == `cash_planning.cash_position()`'s own `confirmed_cash_balance`. These can't
  silently diverge.

### Hand-verified
All three UI pages serve (200) with a full nav mesh. FUND-01 renders three distinct tiers —
$0.00 confirmed / $3,200,000 pending (1 call) / ~$279,609.70 projected (window 2026-01-01 →
2026-01-17, from 147 historical calls, 9.9-day avg gap) — and the sum of the three
($3,479,609.70) appears nowhere in the response. `?as_of=2023-06-30` → 62 historical calls and
a 2023-07 window (real point-in-time, not a hardcoded default).

### Honest limitations
One method only: mean gap + mean of last 4 amounts. No seasonality / quarter-end effects, no
weighting of recent vs old calls, no regime-change detection. The ± band is the population
stdev of past gaps, not a statistical confidence interval. It is labelled "estimate" in the
payload, the UI, and here.

### Not consolidated (future item)
The older `agents/forecasting.py` + `GET /forecast/{fund_id}` (naive **quarterly volume**
projection off the raw `capital_calls` table — unverified notices, different output shape)
still exists. Nothing depends on it (grep: only `agents/app.py` and this log). Left in place
this task; a future pass could retire it the way `/cash/{id}` was, or fold its quarterly view
into this module.

`./predeploy.sh` now at **96 tests** (84 + 8 forecasting core + 2 UI contract + 2 integration).

### Follow-up — four edge-case gaps investigated

**Gap 1 — reversed approval in forecasting history: NOT a bug (verified, not assumed).**
`forecasting.core.approved_call_history` calls `cash_planning.core.approved_call_lines`, which
was fixed once (for cash planning) to drop superseded/reversed approvals. Ran it end to end
through HTTP: approve a call → it appears in `history_used` (count 148); reverse it →
**it is dropped** (back to 147), the new PENDING record does not count either, and the
projection window/estimate recalculate. The fix propagates automatically because forecasting
reuses that one function. Locked in by `test_forecasting_drops_a_reversed_approval_from_its_history`
(`tests/test_forecasting_integration.py`). No code change.

**Gap 2 — UI for `< 2` calls: already unambiguous, wording tightened.** The
`!sufficient_history` branch in `forecasting.html` already showed a text message and never a
`$0` — but the heading read "Projected next call (estimate)". Changed to "Projected next call —
none available" with body *"No projection for this fund. … Nothing is estimated — this is not a
$0 projection, it is the absence of one."* (own `.tier-none` style, no number rendered). Note:
all 10 synthetic funds have decades of ledger history, so this state is only reachable via
`?as_of=<before the fund's first call>`. Tests: `test_api_returns_no_projection_before_a_fund_has_history`
+ a static check that the branch renders the explicit message and references no `nx.*`/`basis.*`
number (`tests/test_forecasting_ui_contract.py`).

**Gap 3 — narrative fabricating a forecast: REAL, fixed structurally.** With `?narrative=true`
on a `sufficient_history: false` fund, `describe()` still called the model, and the model
**invented a date** ("occurring in 2023-06-01" for a fund whose one call was 2025-01-01) even
while saying the estimate "carries no weight". Fixed: `forecasting/narrative.py::describe` now
**short-circuits before any model call** when `not sufficient_history`, returning a fixed
`NO_PROJECTION_MESSAGE` ("Not enough historical data for this fund to generate a projection. No
estimate is produced.") with `generated: false, reason: "insufficient_history"`. Regression test
`test_narrative_does_not_call_the_model_when_there_is_no_projection` monkeypatches `ask_llm` to
raise and asserts `describe()` still returns the fixed message (model never reached) and the
message contains no digit.

**Gap 4 — zero-width window on thin/regular data: REAL (but not where the prompt guessed),
fixed.** Exactly 2 calls was already fine — the code falls back to `avg_interval * 0.5` when
there is only one gap, so the window is non-zero. The actual trap: **≥ 3 *identical* gaps**
(e.g. exact monthly cadence) → `pstdev([30,30,30]) == 0` → zero-width window, looking maximally
confident on thin data. Fix in `forecasting/core.py`: `spread = max(raw_spread, avg_interval *
0.25)` — the ± band is never less than a quarter of the average gap — plus explicit
`basis.interval_sample_size`, `basis.low_confidence` (`< 3` gaps) and
`next_expected_call.confidence` ("low"/"moderate", never "high"), surfaced in the UI as a
"⚠ Low confidence" line and in the narrative facts. Real funds are unaffected (FUND-01: pstdev
8.0 > floor 2.5, still `moderate`). Tests: `test_exactly_two_calls_window_is_not_zero_width_and_flagged_low_confidence`
(locks the exact 2-call geometry), `test_identical_gaps_never_produce_a_zero_width_window`,
`test_low_confidence_is_purely_a_function_of_gap_count`.

`./predeploy.sh` now at **103 tests** (96 + 1 Gap-1 integration + 2 Gap-2 UI + 1 Gap-3 narrative
+ 3 Gap-4 core). Hub / payment approvals / cash planning code paths unchanged — Gap 4's fix is
in `forecasting/core.py` only.

## Module 5 — K-1 Routing: BUILT (last of the original six modules)

Reads an annual Schedule K-1 and identifies **which fund + which LP** it belongs to, then routes
it. A K-1 is a tax document, not a payment instruction — **no wire to verify, no fraud model,
no approve/reject workflow**. Can't identify confidently → `NEEDS_REVIEW` (same discipline as the
hub's `NEEDS_ONBOARDING` and payment approvals' unresolved-fund fallback). New package
`k1_routing/` (`core.py`, `store.py`, `service.py`, `synthetic.py`). The hub, payment approvals,
cash planning and forecasting were **not modified**.

### Step 1 — model choice, decided and documented
Extraction uses the **existing general-purpose local model `qwen2.5:3b-instruct`** (via
`agents.common.ask_llm`), **not** the fine-tuned fraud model and **not** a newly fine-tuned one.
Reasoning: a K-1 carries no fraud risk and no wire to protect, this module is deliberately more
standalone in the original architecture, and the task is plain field extraction from a
well-structured form — fine-tuning for it would be disproportionate. A deterministic regex
fallback (`_regex_extract`) keeps it working with Ollama down and is what the fast test suite
uses. This is a deliberate, reasoned inconsistency with the hub's fine-tuned approach, not an
oversight.

### Step 2 — synthetic K-1 documents (`k1_routing/synthetic.py`, 10 docs)
Every doc's text carries `*** SYNTHETIC TEST DOCUMENT — not a real Schedule K-1 ***`. Fund names
are copied verbatim from the existing `funds.json` roster. Ground truth per doc (fund_id/name,
lp_id/name, tax_year, figures, `expect`, `expect_reason`, `case`). Coverage: **6 clean** (exact
roster fund + LP), **1 LP typo** ("Haas Group Retirement Sytem"), **1 LP formatting difference**
("VELEZ-CHARLES   FAMILY   OFFICE"), **1 unknown fund** ("Aetheric Growth Partners IX" — not in
the system), **1 unknown LP** (real fund, bogus partner). `synthetic.write_jsonl()` dumps them
to `synthetic_data/output/k1_test_documents.jsonl` for inspection.

### Step 3 — extraction + deterministic matching
`core.extract_k1(text, *, extractor=None)` pulls fund name, LP name, tax year, ordinary business
income, guaranteed payments (see Follow-up 1: the production path has no regex fallback —
`extractor` is a DI seam). `core.route_extracted(extracted)` is **deterministic code, no
model**: `_best_match` does exact-on-`verification.verdict._norm_name` else the single best
`rapidfuzz.fuzz.ratio` ≥ **85** (same threshold family as `resolve_by_fund_name` / the hub's
`ENTITY_NEARMISS`) — the hub's approach reused, not a second algorithm. Match fund first, then
LP **within that fund's roster**; route only if both clear the bar, else `NEEDS_REVIEW` with
`review_reason` (`fund_not_matched` / `lp_not_matched`) and a detail string.

### Step 4 — tracking record (`k1_routing/store.py`, append-only)
One JSONL log. Per document: `RECEIVED` event then `ROUTED` (with matched fund/LP + recipient) /
`NEEDS_REVIEW` (with reason) / `AWAITING_EXTRACTION` (with the model error; see Follow-up 1).
State is a replay (last outcome wins); nothing is rewritten. Event kinds are exactly
`{RECEIVED, ROUTED, NEEDS_REVIEW, AWAITING_EXTRACTION}` — no decision/approve/reject kind exists.

### Step 5 — endpoints + UI
`POST /k1-routing/ingest` (extract → match → record), `GET /k1-routing` (overview: `documents` +
`summary{total, routed, needs_review}`), `GET /k1-routing/{fund_id}` (that fund's routed docs;
404 on unknown fund), `GET /ui/k1-routing`. `agents/static/k1-routing.html` matches the other
three pages' style; **the four pages are now a full nav mesh** (every page links to the other
three). ROUTED cards are green / left-bordered and "settled"; NEEDS_REVIEW cards are red-bordered
with the reason called out — immediately distinguishable, like BLOCK vs PASS on the approvals
page.

### Step 6 — tests (`tests/test_k1_routing.py` 10 + `tests/test_k1_routing_ui_contract.py` 3,
all in `predeploy.sh`, Ollama-free by injecting `extractor=regex_extract_explicit`)
- **Matching accuracy: 10/10** on the synthetic batch — all 6 clean route to the right fund+LP
  (exact); the typo case routes via fuzz (LP score 98.2, `exact: false`); the formatting case
  routes (100 after `_norm_name`); the unknown fund → `NEEDS_REVIEW / fund_not_matched` with no
  false match; the unknown LP → `NEEDS_REVIEW / lp_not_matched` with the fund still identified.
- **Contract test** — scrapes the field names `k1-routing.html`'s JS reads (`doc.*`, `ext.*`,
  `rt.*`, `sm.*`, and the shared `m.*` matchLine helper split into fund/LP keys), asserts the
  live `/k1-routing` response carries every one; negative-proof drops `extracted.lp_name` and
  `summary.needs_review` and confirms the check fails.
- **Roster consistency** — `test_fund_roster_is_the_existing_one_no_parallel_list`:
  `set(k1_core.fund_candidates()) == set(load_baselines())` and every name equals both the
  baseline roster's and `cash_planning.core.fund_name()` — no drift, no parallel list. Every
  routed doc resolves to a real roster fund_id and one of that fund's real lp_ids.
- **Live model path** (hand-verified, not in predeploy): the same 10 docs through the real
  `qwen2.5:3b-instruct` extraction → **10/10**, `extraction_source: "model"` on every one.

### Coexistence note
The old `agents/k1_routing.py` + `POST /k1/route` / `GET /k1/samples` (the "light stub" that
generated K-1 text on the fly and routed by LP-type keyword) still exists. Nothing depends on it
(grep: only `agents/app.py` and this log). Left in place — a future consolidation item, same as
the old `/cash/{id}` and `/forecast/{id}`.

`./predeploy.sh` now at **115 tests** (103 + 10 K-1 routing + 2 K-1 UI contract).

### Follow-up 1 — no silent quality degradation when the model is down

**The regex fallback was removed from the production path.** Previously `extract_k1` tried the
model and, on any failure, silently returned a regex-based result labelled
`extraction_source: "regex_fallback"` — a lower-confidence result that looked, in the tracking
record, almost the same as a full-quality one. That is exactly the failure mode this follow-up
forbids: a person must get either a real model-quality result or an explicit "not processed
yet", never an unmarked degraded one.

Changes:
- `core.extract_k1(text, *, extractor=None)` now runs the extractor and **raises
  `ExtractionUnavailable` on any failure — no automatic fallback.** `extractor` is a clean,
  explicit DI seam (default = the real model); it is never set from production code.
- The regex code is kept as `core.regex_extract_explicit()` — callable only deliberately
  (offline inspection, or injected as a test double). It is **never** invoked from `extract_k1`
  or `ingest_document`; a test (`test_ingest_document_never_auto_invokes_regex`) monkeypatches it
  to a spy and asserts the ingest path with the model "down" never touches it. Its output is
  tagged `extraction_source: "regex_explicit"` so a regex-derived record can't be mistaken for
  a model one.
- **New state `AWAITING_EXTRACTION`** (added to `{RECEIVED, ROUTED, NEEDS_REVIEW}`). When the
  model call fails, `ingest_document` writes `RECEIVED` (with the raw text, for retry) then an
  `AWAITING_EXTRACTION` event carrying the error — and stores **nothing regex-derived**
  (`extracted` is `None`). The HTTP request still returns 200.
- **`service.retry_pending()` + `POST /k1-routing/retry-pending`** — re-attempts extraction for
  every `AWAITING_EXTRACTION` record. Manual / periodic trigger, not a background job. On
  success the record proceeds exactly as if the model had been up the first time; the earlier
  `AWAITING_EXTRACTION` event stays in the append-only log, superseded by the outcome (replay =
  last outcome wins). `retry_count` is derived from the number of outcome events − 1.
- **UI** — `AWAITING_EXTRACTION` cards are amber, left-bordered, headed "Not processed yet",
  state plainly "has not been routed or reviewed, and no lower-quality extraction was
  substituted", and show the last error — visually distinct from ROUTED (green) and
  NEEDS_REVIEW (red), and with no extracted-fields table (there are none).
- **Test suite no longer depends on the removed fallback.** All fast tests inject
  `extractor=core.regex_extract_explicit`; the suite runs Ollama-free. One opt-in live test,
  `tests/test_k1_routing_live.py`, is `skipif K1_LIVE_OLLAMA != "1"` — skipped in `predeploy.sh`,
  run explicitly to re-confirm the real `qwen2.5:3b-instruct` path (ran it: **10/10**, 31 s).

Failure / recovery test evidence (`tests/test_k1_extraction_failure.py`):
- model down → `status == "AWAITING_EXTRACTION"`, `extracted is None`, `matched_fund/lp is None`,
  event log is exactly `["RECEIVED", "AWAITING_EXTRACTION"]`, no substring "regex" anywhere on
  the record.
- `retry_pending` with the model back → the two seeded AWAITING docs resolve to their **correct**
  final states (one `ROUTED` → FUND-01/LP-001, one `NEEDS_REVIEW` / `fund_not_matched`);
  event log becomes `["RECEIVED", "AWAITING_EXTRACTION", "ROUTED"]`, `retry_count == 1`.
- retry while still down → stays `AWAITING_EXTRACTION`.

### Follow-up 2, Item A — actual per-case results (not a count)

Matching accuracy on the 10 synthetic K-1s (deterministic regex extractor injected; the live
`qwen2.5:3b-instruct` path gives the identical outcomes — verified):

| doc | case | status | matched fund | matched LP | LP score | review_reason |
|---|---|---|---|---|---|---|
| K1-0001 | clean | ROUTED | FUND-01 | LP-001 Haas Group Retirement System | 100.0 (exact) | — |
| K1-0002 | clean | ROUTED | FUND-01 | LP-002 Barnett Inc University Endowment | 100.0 (exact) | — |
| K1-0003 | clean | ROUTED | FUND-02 | LP-001 Walton-Holt University Endowment | 100.0 (exact) | — |
| K1-0004 | clean | ROUTED | FUND-02 | LP-002 Frost Hobbs and Dominguez University Endowment | 100.0 (exact) | — |
| K1-0005 | clean | ROUTED | FUND-03 | LP-001 Velez-Charles Family Office | 100.0 (exact) | — |
| K1-0006 | clean | ROUTED | FUND-03 | LP-002 Parrish Group Family Office | 100.0 (exact) | — |
| K1-0007 | **lp_typo** ("Haas Group Retirement **Sytem**") | **ROUTED** | FUND-01 | **LP-001** Haas Group Retirement System | **98.2 (fuzzy, ≥ 85 threshold)** | — |
| K1-0008 | **lp_formatting** ("VELEZ-CHARLES   FAMILY   OFFICE") | **ROUTED** | FUND-03 | **LP-001** Velez-Charles Family Office | 100.0 (exact after `_norm_name`) | — |
| K1-0009 | **unknown_fund** ("Aetheric Growth Partners IX") | **NEEDS_REVIEW** | none | none | — | **`fund_not_matched`** |
| K1-0010 | **unknown_lp** (real fund, "Nonexistent Pension Trust of Nowhere") | **NEEDS_REVIEW** | FUND-02 (fund still identified) | none | — | **`lp_not_matched`** |

- The typo case **does** clear the fuzzy threshold: LP score **98.2 ≥ 85**, `exact: false`,
  routed to the right LP-001. Not a false match, not a miss.
- Both unknown cases land in `NEEDS_REVIEW`, not a false match — `fund_not_matched` (no fund
  identified) and `lp_not_matched` (fund identified, LP not).

**Contract negative-proof (Item A.2)** — `tests/test_k1_routing_ui_contract.py::
test_negative_proof_contract_fails_when_a_field_is_dropped` now drops three real fields from a
live `/k1-routing` response and asserts each makes the contract check raise:
`extracted.lp_name` → `AssertionError: K1-0001: extracted missing ['lp_name']`;
`summary.needs_review` → `AssertionError: summary missing ['needs_review']`;
`matched_fund.fund_id` (ROUTED branch) → `AssertionError: K1-0001: matched_fund missing ['fund_id']`.
It genuinely fails when a field is missing.

**Fund roster integration (Item A.3)** — `test_fund_roster_is_the_existing_one_no_parallel_list`,
actual values: `set(k1_core.fund_candidates() ids) == set(load_baselines())` → **True**
(`FUND-01 … FUND-10`); name mismatches vs the baseline roster **and**
`cash_planning.core.fund_name()` → **NONE**. No parallel or drifted list.

### Follow-up 2, Item B — concurrency on the K-1 store

**Scenario tested** (most realistic): two simultaneous `retry-pending` calls hitting the same
`AWAITING_EXTRACTION` document (a periodic retry firing while someone also triggers one), and
separately, two simultaneous `ingest_document` calls for the same `doc_id` (duplicate submit).
Genuine threads + a barrier.

**Finding — it needed a fix, and got one (the payment-approvals approach, reused).** The
locked `append_event` (already reused from the approvals-store pattern) prevents torn writes /
`seq` collisions — but the **retry mechanism this follow-up adds introduces a new check-then-
append** ("is this doc still AWAITING? if so, extract + append an outcome"), which is the same
race class as payment approvals' double-decide. Without a guard, two concurrent retries both
saw AWAITING and both appended an outcome. Fixed with a **per-document lock**
(`service._doc_lock`, one `threading.Lock` per `doc_id`, created on demand) around the
check-then-append in `_attempt_extraction` and the RECEIVED-once check in `ingest_document` —
`approvals.service._record_lock` reused verbatim in spirit. Single-process only (a JSONL store
has no cross-process CAS), documented in the module.

Test evidence (`tests/test_k1_extraction_failure.py`):
- 2× concurrent `retry_pending` on one AWAITING doc → **exactly one** outcome event
  (`["RECEIVED", "AWAITING_EXTRACTION", "ROUTED"]`), final state `ROUTED`, `seq` unique +
  contiguous, both callers observe it resolved (idempotent).
- 2× concurrent `ingest_document(doc_id="DUP")` → **exactly one** `RECEIVED` + **one** `ROUTED`
  event, one record.
- **Negative proof** — `test_negative_proof_removing_the_lock_reintroduces_the_double_resolve`
  monkeypatches `_doc_lock` to a no-op and confirms the double-resolve reappears within 20
  concurrent runs — the lock is load-bearing.
- **`_doc_lock` is per-`doc_id`, not global — confirmed directly**
  (`test_doc_lock_is_scoped_per_document_not_a_global_lock`): one thread holds `_doc_lock("D1")`
  for a deliberate 500 ms (D1 mid-retry) while another thread runs a direct retry on a
  *different* AWAITING doc D2. Observed, stable over 3 runs:

  | event | wall time |
  |---|---|
  | D1 lock acquired (held 500 ms) | ~0.1 ms |
  | **D2 retry finished** (~1 ms of work) → `ROUTED FUND-01/LP-002` | **~1.2 ms** |
  | D1 lock released | ~505 ms |

  D2 completed **~504 ms before** D1's unrelated lock released. A single global lock would have
  stalled D2 for the full ~500 ms; it didn't. D1 stays `AWAITING_EXTRACTION` throughout (D2's
  retry never touches it). Unrelated retries run in parallel.

`./predeploy.sh` now at **124 tests + 1 skipped** (115 + 9 extraction-failure/retry/concurrency;
the +1 skipped is the opt-in live-Ollama test).

## Overall status

All 6 phases run end to end on synthetic data. Two genuinely fine-tuned local models
(extraction 99.5-100% fields; wire-fraud **v3.1** 100% precision / ~0.93 recall on hard-weighted
held-out — four iterations, per-type breakdown in Phase 3b), a deterministic rules layer
(100% / 100% on the synthetic fraud set), four prompt-specialized agents, a FastAPI surface, and
a working end-to-end demo (10/10).

Open / stubbed / caveats:
- K-1 routing: Module 5 (`k1_routing/`, `/k1-routing`) is BUILT — general-purpose model
  extraction + deterministic fuzzy matching against the existing roster + append-only tracking +
  UI. The old `agents/k1_routing.py` "light stub" (`/k1/route`) still coexists, unused (future
  consolidation item).
- Forecasting: the old `agents/forecasting.py` (`/forecast/{id}`) is naive quarterly-volume
  trend extrapolation by design. Module 4 (`forecasting/`, `/forecasting/{id}`) is a separate,
  deterministic next-call projection — also deliberately simple (mean gap + mean recent
  amount), labelled "estimate" throughout, not a model.
- All accuracy numbers are on synthetic data whose frauds are clean field mutations against a
  known baseline — a real deployment (OCR noise, legitimate name/bank drift, multi-bank funds)
  would be lower. The rules layer's 100% is a synthetic-data ceiling, not a product claim.
- GGUF: used Ollama's native safetensors import, not llama.cpp (not installed).
- fp16 fused models deleted post-import to save disk; re-fuse from `training/{adapters,
  fraud_adapters}/` if needed.

## Architecture decision (confirmed with user before Phase 2)

One LoRA fine-tune (Qwen2.5-1.5B-Instruct) on the extraction+fraud-flag task, fused and served
through Ollama as a REST endpoint. All other agents (cash planning, forecasting, payment approval,
K-1 routing) are system-prompt-specialized wrappers around that same served model — not separately
trained models. Fraud-detection rules (routing checksum, fuzzy name match, domain typosquat) are
plain deterministic Python, independent of the LLM.

Amendment during Phase 3 (confirmed with user): a SECOND small fine-tune was added for wire fraud
specifically (`capitalcall-fraud`, chain-of-thought, baseline-aware) after the single extraction
model proved weak at fraud typing. Still one hub concept — extraction + fraud — now two adapters.
Satellite agents wrap `qwen2.5:3b-instruct` (served by the same Ollama), not the narrow fine-tune.

## Data rule

Everything in this repo is synthetic. No real fund, LP, or wire data. All generated records carry
`synthetic: true`.

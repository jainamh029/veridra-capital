# Capital Call Verification — End-to-End Pipeline Demo Results

*Synthetic data only. No real fund, LP, or bank details appear anywhere in this project.*

---

## What was tested

One capital call notice goes in as raw text; one decision comes out:

```
raw notice
  → field extraction (fine-tuned local model)
  → rules layer      (routing-number checksum, compare bank / routing / GP name /
                      sender domain against the fund's onboarded file, urgency-language check)
  → model layer      (fine-tuned wire-fraud model; its verdict is recomputed in code so it
                      cannot be fooled by a character it fails to notice — see "Known limitation")
  → decision         PASS / REVIEW / BLOCK
  → approver alert    naming the specific check that failed and the observed vs. on-file value
```

**Batch:** 33 notices drawn from the project's synthetic dataset, **none of which were used to
train or tune either model** (verified against the recorded data-split IDs).

| | Count | Detail |
|---|---|---|
| Clean notices | 15 | across all 4 notice styles (formal PDF-style, casual email, fund-admin email, messy GP email) and 9 different funds |
| Fraud notices | 18 | 3 each of: altered routing number · wrong receiving bank (valid checksum) · misspelled GP name · look-alike sender domain · unverified last-minute bank change · **combined domain + name attack** |

Ground truth for every notice was written down before the run (`demo_batch/ground_truth.csv`).

---

## Results

| Metric | Value |
|---|---|
| Precision (fraud) | **1.000** |
| Recall (fraud) | **1.000** |
| F1 | **1.000** |
| **False-positive rate on the 15 clean notices** | **0 / 15 (0%)** |
| Pipeline errors / notices that failed to process | **0 / 33** |

Every fraud notice was flagged for the approver; every clean notice passed.

### Per fraud type

| Fraud type | Flagged | Label / severity |
|---|---|---|
| Altered routing number | 3 / 3 | correct label · severity **high** |
| Wrong receiving bank (valid checksum) | 3 / 3 | correct label · severity **high** |
| Misspelled GP name | 3 / 3 | correct label · severity **medium** (a name typo alone is lower-confidence — typos happen) |
| Look-alike sender domain | 3 / 3 | correct label · severity **high** |
| Unverified last-minute bank change | 3 / 3 | correct label · severity **high** |
| **Combined domain + name attack** | **3 / 3** | **both findings named** (`spoofed sender domain` **and** `misspelled entity name`) · severity **high** (the max of the two, not the lower one) |

For all 18 flagged notices, the alert named **every** check that explains the fraud — not a
vague "something looks off", and not just the first one detected.

---

## Three real outputs (verbatim from the run)

### 1. Clean notice → PASS

Notice: fund-admin email for *Highmark Equity Partners III*, $15,193.06 operating-expense call.

**Extracted:** entity `Highmark Equity Management, LLC` · fund `Highmark Equity Partners III` ·
amount `15193.06` · due `2025-06-27` · bank `Northgate Commercial Bank` · routing `052995192` ·
account `7932365454` · purpose `fund_expense`

**Checks:** routing checksum ✅ valid · routing vs file ✅ `052995192` = `052995192` ·
bank name ✅ match · GP name ✅ match · sender domain ✅ `highmarkequity.com` is on the fund's
authorized list `[highmarkequity.com, standishfundservices.com]` · no bank-change language

**Decision: PASS** (confidence high). No alert generated.

### 2. Wrong receiving bank → BLOCK

Notice: casual email for *Fieldstone Equity Partners II*, $114,932.64 follow-on investment.

**Extracted:** bank `Summit Peak Bank` · routing `114727651` · account `9280796110`

**Checks:** routing checksum ✅ valid — **routing vs file ❌ `114727651` ≠ `013710895`** ·
**bank name ❌ `Summit Peak Bank` ≠ `Meridian Trust Bank` (57% similar)** · GP name ✅ ·
sender domain ✅ · no bank-change language

**Decision: BLOCK** · type `wrong_bank_valid_checksum` · confidence high

**Alert (verbatim):**
> **BLOCK: capital call for Fieldstone Equity Partners II ($114,932.64) — wrong bank valid checksum**
>
> Decision: BLOCK (confidence: high).
> What failed:
> - Routing number 114727651 does not match the fund's file (013710895).
> - Receiving bank 'Summit Peak Bank' does not match the fund's file ('Meridian Trust Bank').
>
> Recommended action: Do not release payment. The receiving bank differs from the fund's onboarded
> instructions. An approver must reconfirm the bank and account directly with the GP before any wire.
>
> This is an advisory flag for the approver. The platform does not stop or send wires on its own —
> payment proceeds only if an approver reviews this and overrides.

### 3. Combined attack (look-alike domain **and** misspelled GP name) → BLOCK

Notice: fund-admin email for *Thornbury Ventures Partners III*, $13,082.88 operating-expense call.
Sender domain `thornbur-yventures.com` (a hyphen inserted into `thornburyventures.com`); GP name
written `Thronbury Ventures Management, LLC` (two letters transposed).

**Checks:** routing checksum ✅ · routing vs file ✅ · bank name ✅ —
**GP name ❌ near-miss of the name on file (97% similar)** —
**sender domain ❌ not on the authorized list, 98% similar to the GP domain**

**Decision: BLOCK** · findings `spoofed_sender_domain` + `misspelled_entity_name` ·
**overall severity: high** · confidence high

**Alert (verbatim):**
> **BLOCK (high): capital call for Thornbury Ventures Partners III ($13,082.88) — spoofed sender domain, misspelled entity name**
>
> Decision: BLOCK  |  severity: high  |  confidence: high.
>
> What failed (2 findings):
> - Sender GP name 'Thronbury Ventures Management, LLC' is a near-miss of the name on file
>   ('Thornbury Ventures Management, LLC'), similarity 97%.
> - Sender domain 'thornbur-yventures.com' is not an authorized domain
>   (meridianfundadministration.com, thornburyventures.com), similarity 98%.
>
> Recommended action: Do not release payment. Because the sender's GP name is a near-miss of the
> name on file; and the sender domain is not one of the fund's authorized domains, an approver
> must confirm this request with the GP through a known, separate channel (e.g. a
> previously-verified phone number) before any payment. Treat this as phishing.
>
> This is an advisory flag for the approver. The platform does not stop or send wires on its own —
> payment proceeds only if an approver reviews this and overrides.

The alert names **both** findings, and the severity and wording tier match the **more serious**
of the two (the domain spoof — "treat as phishing"), not the milder one. An earlier version of
this pipeline reported only whichever check happened to be listed first in the code and inherited
that one label's (lower) urgency; that was fixed structurally — see the note below.

---

## A structural fix, not a one-off

The first version of the demo pipeline picked a single label by checking conditions in a fixed
order and stopping at the first failure. On a notice that fails two checks, only one surfaced,
and *which* one was an accident of code ordering, not of which issue was more serious. That was
replaced with a design where **every check runs and reports independently**, the alert is built
from the **full** list of failed checks, and overall severity is the **maximum** across them.
Regression tests now assert this for **every pair** of checks in the system and assert the result
is identical no matter what order the checks run in, so the same class of bug can't come back
silently when new checks are added later. (`tests/test_verdict.py`, run by `./predeploy.sh`.)

---

## What this batch does and does not prove

It shows the pipeline runs end to end and, on **synthetic notices built to resemble real capital
call notices**, catches every injected fraud with no false alarms on legitimate notices; it does
**not** yet show performance on real, messy, previously-unseen fund documents (varied PDF layouts,
scans/OCR, forwarded threads, legitimate mid-life bank changes), which is a different and so far
untested claim.

---

*Run artifacts: `demo_batch/batch.jsonl` (inputs + ground truth), `demo_batch/results.jsonl`
(full decision object per notice), `demo_batch/run.log` (scoring output). Entry point:
`verification/demo_pipeline.run_pipeline()` / `POST /decision`.*

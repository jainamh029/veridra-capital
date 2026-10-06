"""Fast v3 check: 40 clean + weighted fraud sample, focused on the 3 weak types."""
import collections
import json
import re
import time

import mlx.core as mx
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

rows = [json.loads(l) for l in open("training/fraud_data/test.jsonl")]
def gt(r): return json.loads(r["messages"][2]["content"])

want = {"spoofed_sender_domain": 40, "misspelled_entity_name": 40, "altered_routing_digit": 40,
        "wrong_bank_valid_checksum": 15, "last_minute_bank_change": 15}
sel, cnt, clean = [], collections.Counter(), 0
for r in rows:
    g = gt(r)
    if not g["fraud_flag"]:
        if clean < 40:
            sel.append(r); clean += 1
    elif cnt[g["fraud_type"]] < want.get(g["fraud_type"], 0):
        sel.append(r); cnt[g["fraud_type"]] += 1
print(f"selected {len(sel)}  clean={clean}  {dict(cnt)}", flush=True)

model, tok = load("mlx-community/Qwen2.5-1.5B-Instruct-4bit", adapter_path="training/fraud_adapters")
sampler = make_sampler(temp=0.0)

def pj(t):
    m = re.search(r"\{.*\}", t or "", re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None

tp = fp = tn = fn = 0
tot, hit, exact = collections.Counter(), collections.Counter(), collections.Counter()
t0 = time.time()
for i, r in enumerate(sel):
    m = r["messages"]; g = gt(r)
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": m[0]["content"]},
         {"role": "user", "content": m[1]["content"]}], add_generation_prompt=True)
    out = generate(model, tok, prompt=prompt, max_tokens=480, sampler=sampler, verbose=False)
    mx.clear_cache()
    p = pj(out)
    G, GT = bool(g["fraud_flag"]), g["fraud_type"]
    P = bool(p.get("fraud_flag")) if p else False
    PT = p.get("fraud_type") if p else None
    if G:
        tot[GT] += 1
    if G and P:
        tp += 1; hit[GT] += 1; exact[GT] += (PT == GT)
    elif G and not P:
        fn += 1
    elif not G and P:
        fp += 1
    else:
        tn += 1
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(sel)}  {(time.time()-t0)/(i+1):.1f}s/row", flush=True)

prec = tp / (tp + fp) if tp + fp else 0
rec = tp / (tp + fn) if tp + fn else 0
print("\n==== v3 TARGETED ====")
print(f"TP={tp} FP={fp} TN={tn} FN={fn}  precision={prec:.3f} recall={rec:.3f}")
print(f"false positives on clean: {fp}/{clean}")
for t in ["altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
          "spoofed_sender_domain", "last_minute_bank_change"]:
    if tot[t]:
        print(f"  {t:26s} caught {hit[t]}/{tot[t]} ({hit[t]/tot[t]:.0%})  type-exact {exact[t]}/{tot[t]}")
print("DONE")

"""Samples a stratified, class-balanced subset of the Phase 2 extraction
dataset and writes it out in mlx_lm's chat format ({"messages": [...]}) for
LoRA fine-tuning. Balanced (not natural 7% fraud rate) so a small number of
training iterations still gives the model real exposure to every fraud type.
"""

import json
import os
import random

from system_prompt import EXTRACTION_SYSTEM_PROMPT

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(REPO_ROOT, "synthetic_data", "output", "extraction_dataset.jsonl")
OUT_DIR = os.path.join(REPO_ROOT, "training", "data")

SEED = 20260830
FRAUD_TYPES = [
    "altered_routing_digit",
    "wrong_bank_valid_checksum",
    "misspelled_entity_name",
    "spoofed_sender_domain",
    "last_minute_bank_change",
]

SPLIT_COUNTS = {
    # split: (clean_count, per_fraud_type_count)
    "train": (700, 100),
    "valid": (150, 30),
    "test": (100, 20),
}


def load_records():
    clean, by_fraud_type = [], {t: [] for t in FRAUD_TYPES}
    with open(SRC_PATH) as f:
        for line in f:
            rec = json.loads(line)
            if rec["extraction"]["fraud_flag"]:
                by_fraud_type[rec["extraction"]["fraud_type"]].append(rec)
            else:
                clean.append(rec)
    return clean, by_fraud_type


def to_chat_example(rec):
    extraction = dict(rec["extraction"])
    return {
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": rec["notice_text"]},
            {"role": "assistant", "content": json.dumps(extraction)},
        ],
        "call_id": rec["call_id"],
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = random.Random(SEED)

    clean, by_fraud_type = load_records()
    rng.shuffle(clean)
    for t in FRAUD_TYPES:
        rng.shuffle(by_fraud_type[t])

    clean_used = 0
    fraud_used = {t: 0 for t in FRAUD_TYPES}
    held_out_ids = {"train": [], "valid": [], "test": []}

    for split, (clean_n, fraud_n) in SPLIT_COUNTS.items():
        examples = []
        for rec in clean[clean_used: clean_used + clean_n]:
            examples.append(to_chat_example(rec))
        clean_used += clean_n

        for t in FRAUD_TYPES:
            start = fraud_used[t]
            for rec in by_fraud_type[t][start: start + fraud_n]:
                examples.append(to_chat_example(rec))
            fraud_used[t] += fraud_n

        rng.shuffle(examples)
        held_out_ids[split] = [e["call_id"] for e in examples]

        out_path = os.path.join(OUT_DIR, f"{split}.jsonl")
        with open(out_path, "w") as f:
            for e in examples:
                f.write(json.dumps({"messages": e["messages"]}) + "\n")
        print(f"{split}: {len(examples)} examples -> {out_path}")

    # Keep call_ids for each split so Phase 3's held-out sanity check and Phase 6's
    # demo can pull the exact same records (with full notice_text + fraud_reasoning)
    # back out of the Phase 2 output later.
    with open(os.path.join(OUT_DIR, "split_call_ids.json"), "w") as f:
        json.dump(held_out_ids, f, indent=2)

    print(f"\nclean records used: {clean_used} / {len(clean)} available")
    for t in FRAUD_TYPES:
        print(f"{t}: {fraud_used[t]} / {len(by_fraud_type[t])} available")


if __name__ == "__main__":
    main()

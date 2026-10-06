# Brag Plan: Veridra Capital

## What is this app?
Veridra Capital's internal operating platform for fund finance: five live modules — wire-fraud verification, payment approvals, cash planning, forecasting, and K-1 routing — driven by fine-tuned local models, deterministic rules, and a mandatory human approval step, all in one console.

## The angle
This is a serious fintech product, not a joke — the angle is "prove it, don't sell it." The video plays it straight: cold ink-and-gold visual identity, real numbers (1.000 precision / recall, 0% false positives on a 33-notice batch), and every module shown actually doing its job, not just named in a feature list. The reveal is that the platform explicitly refuses to act alone — every decision, PASS or BLOCK, still lands in front of a human. That restraint *is* the pitch.

## Hook (first 2-3 seconds)
Pure ink black. The gold torus-knot begins assembling out of thin strands of light, rotating into form as the wordmark "VERIDRA CAPITAL" resolves beneath it. No text yet but the mark itself — this is the same opening the real site uses, so brand recognition is immediate for anyone who's seen it.

## Key moments (the middle)
- The Fraud Verification screen catching a real fraud pattern: a notice comes in, checks run one by one, a routing number turns red, and the decision lands on BLOCK with a plain-English reason.
- The Approvals queue proving the platform never acts alone: a flagged record sits PENDING, and an Approve/Reject/Needs-info row is the only way anything moves forward.
- Cash Planning's two-box discipline: a solid green "confirmed" balance and a separate dashed amber "near-term, not yet real" box that never gets added to it.
- The closing stat card: 1.000 precision, 1.000 recall, 0% false positives — the numbers the whole video has been building toward.

## Outro / punchline
Wordmark returns, full scale, on black. Tagline settles under it: "The operating system for fund finance." Narration's last line and the type land together, then hold in silence for a beat before cutting to black.

## User flow worth showing
Entry → key action → result, shown once per module since the ask is "explain everything," not one deep flow:
1. **Verification:** raw notice text → extraction + rules + model checks run → BLOCK decision + named reason.
2. **Approvals:** flagged record appears in the queue → approver reviews → Approve/Reject/Needs-info.
3. **Cash Planning:** fund selected → confirmed balance renders → near-term obligations render separately alongside it.
4. **Forecasting:** call history → projected next-call estimate renders as a visibly dashed, tentative third tier.
5. **K-1 Routing:** K-1 text ingested → fund/LP match resolves → ROUTED badge with the delivery target.

## Tone
- Preset: polished
- Creative direction: quiet premium fintech product film — restraint as the flex, gold on ink, confident holds instead of fast cuts
- Interpretation: Fewer, longer holds even though duration is extended to ~60s for the user's "explain everything" ask — this means each module gets one unhurried, fully-read beat rather than many rushed ones. Narration carries authority; type appears once and settles, no flashing. Motion stays smooth and minimal (crossfades, slow slides) so the gold accent and the product's own real numbers do the impressing, not the edit.

## Format: landscape — 1920x1080
## Duration: 60 seconds (explicit user override of the default 15–25s range, to cover the hero plus all five modules)

## Visual identity (from the project)
- Background: `#0a0d14` (ink-900), with `#06070b` (ink-950) and `#10141d` (ink-800) for depth/cards
- Accent: `#cba135` (gold-500), highlight `#f1dca3` (gold-300)
- Text: `#f3efe4` (ivory-100) primary, `#9aa0a8` (ivory-500) muted
- Semantic (console screens): `#2fbf82` emerald (pass/routed), `#d99a2b` amber (review/pending), `#e0555c` crimson (block/needs-review)
- Display font: Fraunces (serif, used italic for the warm accent word in headlines, e.g. "fund finance.")
- Body font: Inter
- Monospace (for check details / figures): JetBrains Mono
- Strongest visual element: the gold torus-knot 3D hero mark on pure black — this is the identity, open and close on it

## Share copy (draft)
Veridra Capital: one console for fund finance — wire-fraud verification, payment approvals, cash planning, forecasting, and K-1 routing, live end to end. 1.000 precision, 0% false positives.

## Audio direction
- Role: sparse professional accents under a restrained voiceover — narration is the lead, music and SFX support without competing
- Music: low, warm, cinematic-corporate bed — no genre cliché, more "quiet confidence" than "startup hype"; bundled Hyperframes track selected at composition time for closest match to this mood
- Music treatment: enters under the hook at low volume, stays low and steady through the module beats (ducked under narration), small swell into the closing stat card and outro, fades out on the final hold
- Music cue guidance: to be detected at composition time (`npx hyperframes beats` or preset if the chosen bundled track has one); target one gentle emphasis cue at the BLOCK decision reveal (~scene 4) and one swell cue entering the closing stat card (~scene 9)
- Audio-reactive treatment: subtle — at most a faint presence/glow breathing on the gold mark tied to music energy in the hook and outro; never waveform bars, never anything busy under narration
- SFX posture: sparse, motion-matched, professional restraint — soft whoosh on major scene transitions, a single soft "check" tick per verification check as it resolves, one quiet UI-tap sound on the Approve button
- Audio-coupled moments: the verification checks resolving one by one (tick per check), the stat card numbers landing (soft count-up tick), the Approve button tap
- Restraint rule: audio must never fight the narration for attention — no dense layering, no SFX during any line of voiceover except the quiet checks/tap moments the narration is actively describing

## Storyboard

### Scene 1 — Hook / mark assembly — 5s
Pure `#0a0d14` black. The gold torus-knot resolves out of faint particle light, slowly rotating into full form; "VERIDRA CAPITAL" wordmark fades in beneath it, letter-spaced, small.
Sequential/interaction: none
Audio intent: quiet, confident open — a single low tone/swell as the mark resolves
Audio-coupled idea: the mark's final "lock into place" moment gets a soft chime
Music: low cinematic-corporate bed, just entering
Narration: "Every capital call notice is a target for fraud."
Transition mood: soft crossfade → Scene 2

### Scene 2 — Hero reveal — 6s
Headline recreation: "The operating system for / fund finance." (Fraunces, "fund finance." in gold italic), with the four stat chips beneath it (1.000 fraud F1 score · 0% false positives · 10 funds onboarded · 32,259 notices evaluated) settling in.
Sequential/interaction: yes — the four stat chips arrive one by one, left to right, each with a quiet soft tick
Audio intent: measured confidence building
Audio-coupled idea: stat chips tick in on the beat grid
Music: steady, low, under narration
Narration: "Veridra Capital built the platform that catches it — before the wire goes out. One console. Five modules. All of them live."
Transition mood: clean slide → Scene 3

### Scene 3 — Module 1: Fraud Verification — 8s
Recreate the verification result card: a notice snippet at top, then the check rows resolving one by one — routing checksum ✅, bank name ❌ (crimson, "does not match fund's file"), sender domain ✅ — ending on a BLOCK badge and one plain-English reason line.
Sequential/interaction: yes — checks resolve one by one, BLOCK badge lands last, emphasized
Audio intent: focus tightens toward the flag
Audio-coupled idea: one soft tick per check resolving; slightly heavier tick/chime on the BLOCK badge landing
Music: ducked lower under this beat
Narration: "Paste a raw notice. Extraction, deterministic rules, and a fine-tuned fraud model check it against the fund's file — and reconcile into one decision, every time."
Transition mood: soft crossfade → Scene 4

### Scene 4 — Module 2: Payment Approvals — 7s
Recreate one approval card: fund name, PENDING APPROVAL badge, BLOCK/severity badges, and the Approve / Reject / Needs-info button row — cursor taps toward Approve but the card stays queued, reinforcing "a human decides."
Sequential/interaction: yes — simulated cursor tap on the approval row
Audio intent: procedural, deliberate
Audio-coupled idea: one quiet UI-tap sound on the simulated tap
Music: steady low bed
Narration: "Every notice — cleared or flagged — opens a tracked approval. A human always decides. The platform never sends a wire on its own."
Transition mood: soft crossfade → Scene 5

### Scene 5 — Module 3: Cash Planning — 7s
Two stacked boxes recreate the real design: a solid green "Confirmed cash balance" box with a dollar figure, and directly beneath it a separate dashed amber "Known upcoming — not in the balance above" box — visually never touching/merging.
Sequential/interaction: yes — confirmed box settles first, amber box slides in beneath a beat later
Audio intent: calm, precise
Audio-coupled idea: none additional — let the two-box reveal read in near-silence to emphasize the separation
Music: low bed, unchanged
Narration: "Cash planning keeps confirmed balance and pending obligations separate — reconciled, and never merged."
Transition mood: soft crossfade → Scene 6

### Scene 6 — Module 4: Forecasting — 6s
Three-tier stack recreation: solid "confirmed" tier, dashed amber "pending" tier, then a visibly lighter dashed "projected next call" tier with a small bar-chart history underneath it.
Sequential/interaction: yes — the three tiers stack in top to bottom, the projected tier visibly lighter/looser than the other two
Audio intent: same calm register, slight lift into the next beat
Audio-coupled idea: none
Music: low bed
Narration: "Forecasting projects the next call from the fund's own history — clearly marked as an estimate, never an obligation."
Transition mood: soft crossfade → Scene 7

### Scene 7 — Module 5: K-1 Routing — 6s
Recreate a K-1 document card resolving: extracted fund + LP fields appear, then a green "ROUTED" badge lands with the matched fund/LP and delivery queue underneath.
Sequential/interaction: yes — extracted fields populate first, ROUTED badge and match lands after
Audio intent: light resolution, satisfying close to the module tour
Audio-coupled idea: soft chime on the ROUTED badge landing
Music: begins to lift slightly into the next scene
Narration: "And K-1 routing matches every tax document to the right fund and LP — deterministically, or flags it for review."
Transition mood: clean slide → Scene 8

### Scene 8 — Proof / stat card — 8s
Cut to black, then the closing numbers land big and centered, one at a time: "1.000 precision" / "1.000 recall" / "0% false positives" — each in Fraunces, gold on black, with a small "33-notice batch" caption beneath the set once complete.
Sequential/interaction: yes — three numbers land in sequence with a count-up tick each, then hold together
Audio intent: the swell — this is the payoff beat
Audio-coupled idea: soft count-up tick per stat landing; music swell begins here
Music: swell starts, still restrained (not a drop)
Narration: "Measured against thirty-three real notices: perfect precision, perfect recall, zero false alarms."
Transition mood: dramatic hold, soft crossfade → Scene 9

### Scene 9 — Outro / mark — 7s
Return to the Scene 1 mark, full scale, centered on black. Tagline settles beneath: "The operating system for fund finance." Hold in near-silence before cutting to black.
Sequential/interaction: none
Audio intent: settle and release — the swell resolves into quiet
Audio-coupled idea: none — let the final hold breathe
Music: fades out through the hold
Narration: "Veridra Capital. Every module, live."
Transition mood: — (final scene)

**Total: 5+6+8+7+7+6+6+8+7 = 60s**

**Music mood for this video:** cinematic, restrained, confident — a quiet premium product film, not a hype reel
**Audio summary:** A low, steady cinematic-corporate bed carries the whole piece under a clear narration lead, gently ducking for each module beat, lifting once into a soft swell at the closing stat card, and fading to silence on the final wordmark hold — accented only by sparse, motion-matched ticks and chimes on checks resolving, the approve tap, and badges landing.

## Voiceover script

1. "Every capital call notice is a target for fraud."
2. "Veridra Capital built the platform that catches it — before the wire goes out. One console. Five modules. All of them live."
3. "Paste a raw notice. Extraction, deterministic rules, and a fine-tuned fraud model check it against the fund's file — and reconcile into one decision, every time."
4. "Every notice — cleared or flagged — opens a tracked approval. A human always decides. The platform never sends a wire on its own."
5. "Cash planning keeps confirmed balance and pending obligations separate — reconciled, and never merged."
6. "Forecasting projects the next call from the fund's own history — clearly marked as an estimate, never an obligation."
7. "And K-1 routing matches every tax document to the right fund and LP — deterministically, or flags it for review."
8. "Measured against thirty-three real notices: perfect precision, perfect recall, zero false alarms."
9. "Veridra Capital. Every module, live."

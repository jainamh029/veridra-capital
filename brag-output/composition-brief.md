# Hyperframes Composition Brief: Veridra Capital

## Objective
Create a ~60-70 second, narrated, polished launch/explainer video for Veridra Capital's fund-finance platform — covering the marketing hero and all five live console modules.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 70.25s (set by the generated voiceover track — see "Locked timeline" below; user explicitly requested ~1 minute covering the hero + all 5 modules, overriding the default 15–25s brag length)

## Source Material
- Project root: `/Users/jainamshah/capital-call-platform`
- Primary files read: `frontend/src/index.css` (design tokens), `frontend/src/pages/Home.tsx` + `frontend/src/components/home/*` (marketing site copy/structure), `frontend/src/pages/console/*` (module screens), `PIPELINE_DEMO_RESULTS.md` (the 33-notice batch numbers)
- Product name: Veridra Capital
- Tagline / strongest claim: "The operating system for fund finance." / "1.000 precision, 1.000 recall, 0% false positives" (33-notice batch)
- Key UI or visual moment to recreate: the gold torus-knot 3D hero mark on ink black (from the real hero section); the Fraud Verification result card (check rows + BLOCK badge); the Approvals card (Approve/Reject/Needs-info row); Cash Planning's two-box confirmed/near-term split; Forecasting's three-tier stack; K-1 Routing's ROUTED match card
- Copy that must appear verbatim:
  - "The operating system for fund finance."
  - "1.000" / "0%" / "10" / "32,259" (the hero stat row)
  - "BLOCK" (decision badge)
  - "PENDING APPROVAL"
  - "Confirmed cash balance"
  - "Projected next call — estimate, not an obligation"
  - "ROUTED"
  - "1.000 precision · 1.000 recall · 0% false positives"

## Creative Direction
- Tone preset: polished
- Creative direction: quiet premium fintech product film — restraint as the flex, gold on ink, confident holds instead of fast cuts
- Interpretation: fewer, longer holds per idea; narration carries authority; type appears once and settles (no flashing); motion stays smooth and minimal (crossfades, slow slides)
- Angle: "Prove it, don't sell it." Real numbers, every module actually shown doing its job, and the explicit reveal that the platform never acts without a human approving.
- Hook: pure ink black; the gold torus-knot assembles out of light and rotates into form as "VERIDRA CAPITAL" resolves beneath it
- Outro / punchline: the same mark returns full-scale on black, tagline settles beneath it, narration's last line lands with the type, then a silent hold before cutting to black
- Avoid:
  - Generic SaaS language ("streamline your workflow," etc.)
  - Abstract filler visuals — every scene must reference a real screen, real copy, or the real hero mark
  - Unrelated visual redesign — stay inside the project's actual ink/gold + console light-slate palettes

## Visual Identity
- Background: `#0a0d14` (ink-900) for marketing scenes; `#f8fafc`-range slate for console-screen scenes (the real console UI is light, not dark — reproduce that contrast deliberately, it's true to the product)
- Text: `#f3efe4` (ivory-100) on dark scenes; `#0f172a`-range slate-900 on light console scenes
- Accent: `#cba135` (gold-500), highlight `#f1dca3` (gold-300) — used throughout both light and dark scenes as the one consistent brand thread
- Semantic (console scenes only): `#2fbf82` emerald (pass/routed), `#d99a2b` amber (review/pending), `#e0555c` crimson (block/needs-review)
- Display font: Fraunces (Google Fonts) — headlines, module names, the closing stat numbers
- Body font: Inter (Google Fonts) — body copy, UI labels
- Monospace: JetBrains Mono (Google Fonts) — check detail lines, figures, doc IDs
- Visual references from the project: the hero's torus-knot + stat-chip row; the four module-card grid from the marketing "Platform" section; the light-mode console cards (rounded-2xl, soft shadow, colored left-border tiers) from Cash Planning/Forecasting

## Storyboard
Use `brag-output/brag-plan.md` as the full creative contract. Scene summary with **locked timings** (durations already set to match the generated voiceover — do not change scene durations; the audio dictates the pace):

1. Hook / mark assembly — 0.00s–4.50s (4.50s) — ink-black screen, gold torus-knot assembles and rotates into form, "VERIDRA CAPITAL" wordmark resolves beneath it. Narration starts at 0.60s.
2. Hero reveal — 4.50s–13.11s (8.61s) — headline "The operating system for / fund finance." (gold italic on "fund finance."), then 4 stat chips arrive one by one (1.000 fraud F1 · 0% false positives · 10 funds onboarded · 32,259 notices evaluated).
3. Module 1 — Fraud Verification — 13.11s–24.81s (11.70s) — **beat-locked entrance** (see Audio). Notice snippet, check rows resolve one by one (routing ✅, bank name ❌ crimson "does not match fund's file", sender domain ✅), BLOCK badge lands last, emphasized, with one plain-English reason line.
4. Module 2 — Payment Approvals — 24.81s–34.31s (9.50s) — approval card: fund name, PENDING APPROVAL badge, BLOCK/severity badges, Approve/Reject/Needs-info row; simulate a cursor tap that does NOT resolve the card (it stays queued — reinforces "a human decides").
5. Module 3 — Cash Planning — 34.31s–41.51s (7.20s) — solid green "Confirmed cash balance" box settles first; a separate dashed amber "Known upcoming — not in the balance above" box slides in beneath it a beat later, visually never touching.
6. Module 4 — Forecasting — 41.51s–49.41s (7.90s) — three tiers stack top to bottom: solid confirmed, dashed amber pending, then a visibly lighter/looser dashed "projected next call" tier with a small bar-chart history beneath it.
7. Module 5 — K-1 Routing — 49.41s–58.31s (8.90s) — extracted fund/LP fields populate first, then a green ROUTED badge lands with the matched fund/LP and delivery queue.
8. Proof / stat card — 58.31s–66.01s (7.70s) — cut to black, three numbers land in sequence with a count-up feel: "1.000 precision" / "1.000 recall" / "0% false positives", small "33-notice batch" caption once the set completes.
9. Outro / mark — 66.01s–70.25s (4.24s) — the Scene 1 mark returns full scale, centered, tagline "The operating system for fund finance." settles beneath it, hold in near-silence, cut to black.

## Audio
- Audio role: sparse professional accents under a lead voiceover — narration carries the piece; music and SFX support without ever competing with it
- Audio arc: low steady bed under the whole piece, ducked further under every narration line, one soft lift starting into Scene 8 (the stat payoff), fade to silence through the Scene 9 hold
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` ("polished/cinematic" candidate per the brag skill's own library) — use only the first ~71s of the track (trim/fade out, do not loop)
- Music treatment: enter at low volume (≈0.12–0.18, polished-tone level) under Scene 1, hold steady and ducked under narration throughout, small swell (still restrained, not a drop) entering Scene 8, fade to silence by the end of Scene 9's hold
- Music cue guidance: full rich cue JSON copied to `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json` (tempo ≈110 BPM, `beats[]` + `strongCues[]` cover the full 117s track, not just the bundled 25s summary — read the JSON directly for cues past 25s). One strong cue is already locked into the timeline below; treat any other cue alignment as optional and skip it if it would fight narration pacing.
  - **Locked:** Scene 3's entrance (BLOCK-reveal scene) starts at **13.11s**, matching `strongCues` entry `{time: 13.11, intensity: 0.98}` exactly — mark this tween `// beat-locked: 13.11s` in the composition.
  - Optional/unforced nearby cues if useful and non-disruptive: `24.56s` (intensity 0.99, near Scene 4's 24.81s start — within ~0.25s, use only if it doesn't shift narration sync), `61.10s` (intensity 0.98, inside Scene 8 — a natural candidate for the swell/lift moment, not a hard lock).
- Audio-reactive treatment: subtle — a faint presence/glow breathing on the gold torus-knot mark (Scenes 1 and 9 only) tied to music RMS; never on console-screen scenes; never waveform/equalizer visuals
- Audio-coupled moments:
  - Scene 2 — the 4 stat chips arrive one by one — accent with a soft tick per chip (interface/drop or ui/click family, whichever reads as lightest)
  - Scene 3 — each check row resolving gets a soft tick; the BLOCK badge landing (at the beat-locked 13.11s scene entrance and again as it settles) gets a slightly heavier single accent — do not overdo it, one clear moment, not a flourish
  - Scene 4 — the simulated cursor tap on the approval row gets one quiet UI-tap sound
  - Scene 7 — the ROUTED badge landing gets a soft, warm chime (success-family, not a triumphant sting — stay restrained)
  - Scene 8 — each of the 3 stat numbers landing gets a soft count-up tick; this is the closest thing to a "big moment" in the video — one slightly more present accent is fine here, still not loud
- SFX selection guidance: pull from the `interface/` and `ui/` families for the "polished" tone's minimal-but-present energy (2–3 audible cues total is the right ceiling per the brag skill's own tone guidance — treat the per-scene ticks above as options to select from, not a mandate to use every single one; prefer under-using to over-using). Consult `sfx-analysis.md`/`.json` in the brag skill's `assets/sfx/` directory and prefer low/medium high-frequency-risk files since this video repeats similar accent types across 9 scenes.
- Exact SFX choice: Hyperframes should choose exact filenames, timestamps, density, and volume based on the implemented animation — copy chosen files into `composition/assets/sfx/...` before referencing them.
- Voiceover: **already generated and final** — `composition/assets/voiceover.wav` (70.25s, mono, 24kHz, Kokoro `am_michael`). This is the authoritative timeline; every scene duration listed above was derived directly from this file's silence gaps and must not be changed. Wire it as its own `<audio>` track starting at `data-start="0"`. Music ducks to ~0.12–0.15 under it per the standard voiceover-ducking pattern; SFX accents above are brief enough to sit alongside it without masking words.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render) — to build `brag-output/composition/`. This is a `/brag` run: do not enter the generic `hyperframes` entry-point intent interview or its default promo/launch-video workflow.

Requirements:
- Show real UI, copy, and visual elements from the source project in every module scene (not abstract filler) — see "Key UI or visual moment to recreate" above.
- Keep all text readable — every line has its reading-floor hold per the brag plan (short labels ≈0.8s settled, sentences ≈0.3s/word) — the scene durations above already budget for this against the real voiceover lines in `brag-plan.md`'s Voiceover script section.
- Total duration is fixed at 70.25s by the voiceover track — do not compress to the default 15–25s brag range; this was an explicit user override.
- Wire `assets/voiceover.wav` as described above; do not regenerate or re-time it.
- Wire the music bed with the treatment and (single) beat-lock described above.
- Run `npx hyperframes check` before render — it is the single gate.
- Render to `brag-output/brag.mp4`.

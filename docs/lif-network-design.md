# Sally Cibote — LIF network design (sketch)

**Status:** architecture only — not implemented yet  
**Date:** 2026-11-07  
**License target:** MIT (original). Pestinha is **inspiration only** (GPL) — do not copy code/topology/weights.  
**Today’s stub:** `src/sally_cibote/memory/lif.py` only tracks stage + confirm/reject JSONL. This doc describes the full brain sketch that replaces LLM-as-decision-maker over time.

---

## 1. Goal

Sally’s **decision brain** is a small, handmade **LIF** (Leaky Integrate-and-Fire) network:

- Learns routines from Daniel’s feedback (confirm / reject / caress-like reward).
- Suggests and later auto-fires actions (music, reminders, face, speak cues).
- Does **not** need a large LLM to decide *what to do*. An LLM (or TTS templates) may still help with *how to say it* — optional and gated by motors.

**Scale (sketch):** ~450 neurons, ~12–15k synapses (hand-wired groups, not trained end-to-end like a deep net).

---

## 2. Signal flow

```text
 World / Daniel
   │
   ├─ Voice events (STT phrases, barge-in, silence)
   ├─ Time (hour, weekday, morning/evening bands)
   └─ Calendar / n8n context (event density, next event, free slot)
               │
               ▼
        Sensory channels (0..1)  ──► Poisson / rate coding into LIF sensory pools
               │
               ▼
        Interneurons (focus, social, urgency, play, calm, frustrate, …)
               │
               ▼
        Motor pools (Hz)
               ├─ Expression  → face / mood UI
               ├─ Speech gate → when / whether to speak (templates or optional LLM)
               └─ Action      → n8n hands (music, reminder, calendar ask, …)
               │
               ▼
        Rules / thresholds (stage-dependent) decide *allowed* actions
               │
               ▼
        Learning: reward · conditioning · episodic bandit
               │
               ▼
        Persist: network weights + episodic table + stage (JSON/JSONL)
```

**Principle:** network outputs **tendencies (Hz)**; **program rules** decide permission, safety, and execution (same spirit as Pestinha’s “network vs rules” split, redesigned for a voice assistant).

---

## 3. Stages (growth)

| Stage | Rough meaning | What the network is allowed to do |
|-------|---------------|-----------------------------------|
| `newborn` | Suggest only | Motors can **propose**; never auto-dispatch n8n. Always ask “confirma?” |
| `toddler` | Semi-autonomy | Auto-run only **high-confidence, low-risk** routines after repeated confirms |
| `helper` | Calibrated autonomy | Dispatch without ask if weight/confidence high; always log + easy opt-out |

Promotion (sketch, aligns with today’s stub):

- `newborn → toddler` after ~3 confirms on the same routine family  
- `toddler → helper` after ~8 confirms and low reject rate  

Reject / “para de fazer isso” lowers weights and can demote confidence without wiping the whole net.

---

## 4. Neuron groups (sketch counts ≈ 450)

### 4.1 Sensory pools (~180 neurons)

| Channel | Role for Sally |
|---------|----------------|
| `VOICE_ON` | Speech detected / listening window |
| `UTTER_GREET` | Greeting-like STT |
| `UTTER_CONFIRM` / `UTTER_REJECT` | “confirma”, “ok Sally”, “cancela”, … |
| `UTTER_MUSIC` / `UTTER_REMIND` / `UTTER_AGENDA` | Intent keywords / cheap classifiers |
| `BARGE_IN` | User interrupted TTS |
| `SILENCE` | No speech for a while |
| `TIME_MORNING` / `TIME_AFTERNOON` / `TIME_EVENING` / `TIME_NIGHT` | Time-of-day bands |
| `WEEKDAY` / `WEEKEND` | Calendar shape |
| `CAL_BUSY` / `CAL_FREE` / `CAL_NEXT_SOON` | From n8n / Google Calendar digest |
| `REWARD_POS` | Explicit praise / caress-analogue (voice “obrigada”, UI like) |
| `REWARD_NEG` | Dismiss / reject / “para” |
| `N8N_OK` / `N8N_FAIL` | Last hand action outcome |

Each channel: small pool (≈6) with optional **habituation** (repeated spam loses punch; rewards/confirm don’t habituate the same way).

### 4.2 Interneurons (~150)

| Population | Job |
|------------|-----|
| `ALERT` | Something needs attention (soon event, barge-in) |
| `FOCUS` | Task / reminder mode |
| `SOCIAL` | Conversation / companionship |
| `PLAY` | Music / light mood |
| `CALM` | Settled, low urgency |
| `URGENCY` | Next calendar event soon |
| `FRUSTRATION` | Rejects, failed n8n, barge-in storms |
| `INHIB` | Global brake so motors don’t all fire |

### 4.3 Motors (~120)

**Expression (face / UI)**

| Motor | Effect |
|-------|--------|
| `FACE_IDLE` / `FACE_LISTEN` / `FACE_SPEAK` / `FACE_HAPPY` / `FACE_SAD` / `FACE_THINK` | Rostinho |

**Speech gate**

| Motor | Effect |
|-------|--------|
| `SPEAK_SHORT` | Allow one short TTS reply |
| `ASK_CONFIRM` | Ask before acting |
| `STAY_QUIET` | Suppress chatter |

**Actions (n8n / local hands)**

| Motor | Effect |
|-------|--------|
| `ACT_MUSIC` | Spotify / music flow (Slice-style) |
| `ACT_REMIND` | Create / fire reminder |
| `ACT_AGENDA_READ` | Pull / summarize calendar |
| `ACT_SUGGEST_ROUTINE` | Propose a new habit (“quer que eu toque música às 9?”) |
| `ACT_OPT_OUT` | Disable a routine |

Stage gates which action motors can cross threshold without `ASK_CONFIRM`.

---

## 5. Learning mechanisms (original design)

### A) Reward / three-factor style (caress analogue)

- Eligibility trace (~few seconds) of active sensory context when Daniel gives **positive** feedback (`REWARD_POS`, confirm).
- Strengthen synapses toward `PLAY` / `CALM` / successful `ACT_*` that were co-active.
- **Negative** feedback strengthens `FRUSTRATION` paths and weakens the failed `ACT_*`.

### B) Classical conditioning

Cue → outcome associations **outside** the core LIF (small Rescorla–Wagner table), fed back as sensory channels:

| Cue | Typical outcome |
|-----|-----------------|
| Morning + free calendar | Music suggestion |
| `CAL_NEXT_SOON` | Reminder / quiet / focus |
| Voice “confirma” after suggestion | Dispatch success |

Extinction if cue repeats without outcome.

### C) Episodic memory (contextual bandit)

When `ACT_SUGGEST_ROUTINE` or `ACT_MUSIC` wants to fire, a small table picks **which** routine/playlist family:

- Context key ≈ `time_band|cal_busy|stage`
- Actions ≈ discrete routine IDs
- Update from confirm/reject and n8n success/fail (−1..+1)

LIF decides **whether** to act; episodic table decides **which** variant.

---

## 6. Interface (future modules — names only)

Proposed layout under `src/sally_cibote/` (not built yet):

```text
memory/
  lif.py              # existing stage JSONL (keep)
  neuronal.py         # LIFBrain: stimulate / step / motor_activity / save
  conditioning.py     # cue→outcome table
  episodic.py         # routine bandit
  sensors.py          # voice/time/calendar → channel intensities
  motors.py           # Hz → face / speak gate / n8n dispatch
docs/
  lif-network-design.md   # this file
```

**API sketch:**

```text
stimulate(channels: dict[str, float])   # 0..1
step(dt_ms)
motors() -> dict[str, float]            # Hz
on_reward(+1|-1)
on_confirm(routine_id) / on_reject(routine_id)
snapshot() / save() / load()
```

Voice session loop later: STT → sensors → `step` → motors → maybe TTS / n8n → reward from Daniel’s next utterance.

---

## 7. Relation to LLM / Ollama

| Layer | Owner |
|-------|--------|
| *Should I act? Which routine?* | LIF + episodic + stage rules |
| *What exact words to say?* | Short templates first; optional Ollama later if `SPEAK_SHORT` high |
| *Calendar / Spotify / WhatsApp execution* | n8n (hands) |

This matches the MVP plan: software first, LIF baby learning, n8n as hands — without depending 100% on a large model for intelligence.

---

## 8. Implementation order (later)

1. Port stage stub → wire `ASK_CONFIRM` / confirm-reject into real reward hooks (already partially in `session.py`).  
2. Minimal `neuronal.py` with ~3 sensors × ~2 motors (smoke test).  
3. Grow topology to ~450; add conditioning + episodic.  
4. Connect calendar digest from n8n into `CAL_*`.  
5. Gate Slice music workflow behind `ACT_MUSIC`.  
6. Face UI driven by expression motors.

---

## 9. Non-goals (this sketch)

- No copy of Pestinha source, synapse tables, or pet behaviors.  
- No on-device training of a deep network.  
- No autonomous n8n spam in `newborn`.  
- No claim that LIF replaces natural language understanding entirely — only the **habit / autonomy** core.

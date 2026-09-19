# Decisions

Each one: what we chose, what we didn't, and why.

### 1. One brain, two voice participants
- **Chose:** one worker job per room that listens and decides, plus two lightweight LiveKit
  connections (`ai-dost`, `ai-sathi`) that only speak.
- **Not:** two independent agent workers, one per bot.
- **Why:** preventing overlap needs one shared lock. Inside one process that's a plain
  `asyncio.Lock`. Across two processes it needs Redis or message passing, and both bots would
  hear and try to answer every question.

### 2. Our own per-human listener instead of LiveKit `AgentSession`
- **Chose:** one Sarvam STT stream per human microphone.
- **Not:** `AgentSession`, which the first version used.
- **Why:** `AgentSession` links to a *single* participant, so it can't hear two humans. A stream
  per mic also gives exact speaker attribution: we know whose track the audio came from.

### 3. Rule-based routing with a relevance gate
- **Chose:** regex rules: named → follow-up → unnamed question → otherwise silence.
- **Not:** asking an LLM "who should answer?" on every turn.
- **Why:** instant, free, predictable, and fully unit-tested. An LLM router adds latency and
  can pick differently for the same sentence.

### 4. A speaking floor (lock) held for the whole plan
- **Chose:** acquire once per turn and hand it from Dost to Sathi for two-bot requests.
- **Why:** makes overlap impossible by construction, and stops another user's question from
  landing between "the answer" and "the example".

### 5. Sarvam for STT and TTS
- **Why:** built for Indian languages. Saaras handles Hinglish in `codemix` mode (Hindi in
  Devanagari, English words stay in Latin, as people actually speak). Bulbul v3 has natural
  Indian voices: `shubh` (male) for Dost and `simran` (female) for Sathi. English words like
  "cloud" and "mic" sound native, not foreign-accented.
- **How the voice was picked:** 5 male voices said the same sentence (room, mic, technology,
  decision, network). All passed a TTS → STT round trip word for word; `shubh` was chosen by
  listening for the most natural pace and tone. For Sathi, 6 female options were compared the
  same way; `simran` won because Bulbul v3 barely honours the `pace` setting (priya at +15% was
  only 3% shorter), so choosing a naturally quicker voice was the real way to match Dost. ElevenLabs was also evaluated, but its Indian
  library voices need a paid API plan.

### 6. Gemini 3.5 Flash Lite, with automatic failover
- **Why:** benchmarked on the same Hinglish questions. 3.5 Flash Lite gave natural replies
  with no hidden "thinking" tokens and answered 4/4, while older Flash-Lite timed out on 2.
  Full Flash spent ~140 thinking tokens per reply (which truncated answers) and returned 503s.
  Each model gets 5 s; on failure the same turn moves to `gemini-flash-lite-latest`, and the
  failed model is skipped for 60 s. The brain only sees `reply(persona, prompt)`.

### 7. Sentence-by-sentence TTS
- **Why:** the first sentence starts playing while the next is synthesized, so the user hears
  audio sooner. On barge-in only about one sentence is queued, so the bot goes quiet quickly.

### 8. Bounded memory with per-speaker facts
- **Why:** the last 12 turns keep the prompt small and the cost flat. Self-facts survive the
  window, so "maine kya bataya tha?" works later, and they're shown only to their owner.

### 9. Fail soft, never crash
- **Why:** a voice room can't show a stack trace. LLM down → the bot apologizes in Hinglish.
  TTS down → the reply still appears as text. STT down → the stream restarts. Every path
  releases the floor.

### 10. One style guide in the prompt, checked by tests
- **Chose:** the assignment's own "avoid / prefer" examples go into the prompt verbatim, plus
  rules (Hinglish even for English questions, 1–3 sentences, digits, no markdown), and each
  bot uses its own grammatical gender ("batata" vs "batati").
- **Checked by:** a style checker (formal-word list, Roman script, has Hindi glue words, length,
  markdown, stock phrases) run against real Gemini replies for Scenarios 1–7.
- **Why:** the style is the biggest rubric area (20 points). A test catches regressions that
  eyeballing misses, and it caught "Ek useful detail ye hai…" repeated in 4 replies, and a
  made-up year.

### 11. Rolling summary for long sessions
- **Chose:** a 12-turn window, plus a background LLM summary of everything older.
- **Not:** sending the full history (cost and latency grow without limit), or plain truncation
  (a recap would forget the start of the session).
- **Why:** flat prompt size and a complete recap. Off the critical path, so no delay is added.

### 12. Word-list moderation
- **Chose:** a regex list of clear slurs in Roman and Devanagari. The bot gives a calm fixed
  reply, the LLM is never called, and the text is masked in memory and the chat transcript.
- **Not:** an LLM or ML classifier on every turn (extra latency and cost on every sentence).
- **Trade-off:** a word list can't read context ("Harami" the film title is flagged). Mild words
  like "pagal" and "bakwas" are deliberately allowed. Documented in a test.

### 13. Privacy by default
- **Why:** no audio stored, and no conversation text in logs unless explicitly turned on
  for a demo.

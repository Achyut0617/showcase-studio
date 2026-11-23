# Voice Sample Recording Guide

The voice clone can only sound as good as the recordings it learns from. This guide
gets you clean, consistent samples in about an hour. Do it once, in Stage 0, so the
samples are ready when voice work starts in Stage 3.

## Target

- **Total:** 30 minutes of clean speech, in 3 sessions of about 10 minutes each.
- **Style:** your natural "explaining code to a friend" voice, the voice you want in
  the videos. Not a reading-aloud voice.
- **Language:** English for v1 (Marathi/Hindi samples can come later for those versions).

## Setup

1. **Room:** small, quiet room with soft things around (bed, curtains, cupboard of
   clothes). Avoid empty rooms with echo. Turn off fans and AC; close windows.
2. **Mic:** a wired earphone mic or USB mic is fine. Keep it 10–15 cm from your mouth,
   slightly to the side so breaths don't hit it directly. Laptop built-in mics are a
   last resort.
3. **Software:** Audacity (free) or any recorder that saves WAV.
4. **Format:** WAV, 44.1 kHz or 48 kHz, 16-bit or 24-bit, **mono**.
5. **Level:** speak normally and check the meter peaks around −12 dB; never hitting 0 dB (red).

## What to read

Mix these in each session so the model hears your full range:

- **Explaining your own projects** (unscripted is best): walk through how NearbyConnect,
  StealthLedger or Smartscholar works, as if to an interviewer.
- **Technical sentences** with terms the videos will use: "The orchestrator runs each
  stage inside a Docker container with the network disabled." / "We parse the code
  with tree-sitter and build a dependency graph."
- **Numbers, versions and names:** "Python 3.12", "port 8080", "GitHub", "PostgreSQL",
  "API", "JSON", "CUDA".
- **Different moods:** calm explanation, a slightly excited "and this is the cool part",
  a question ("so why does this matter?").

## Recording rules

- Record each session in one sitting, same mic position, same room.
- Leave 1 second of silence at the start and end.
- If you stumble, pause, then repeat the sentence. Cut the mistake later; don't stop the recording.
- Drink water; avoid recording with a cold or right after shouting.

## Files

```
voice-samples/
  session-01.wav
  session-02.wav
  session-03.wav
  notes.txt        # date, mic, room, anything unusual
```

`voice-samples/` is in `.gitignore`: **your voice never goes to GitHub.** Keep a
private backup (an external drive or private cloud folder).

## Checklist

- [ ] Quiet room, fan/AC off
- [ ] WAV, mono, 44.1 or 48 kHz
- [ ] Peaks around −12 dB, no clipping
- [ ] 3 sessions × ~10 min
- [ ] Mistakes trimmed, long silences cut to under 1 s
- [ ] Files named as above, backed up privately
- [ ] Mark task **T0.4** done: commit `T0.4 done` or set it in the tracker

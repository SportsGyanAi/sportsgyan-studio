# sportsgyan-studio

Render engine for The Sports Gyan AI. Brain (Cloudflare) creates jobs; this repo's Action claims them, renders, uploads.

```
engine/
  config.py        canvas, palette, fonts
  render.py        motion graphics (smooth Ken Burns bg, neon glow text, counters, record tables, captions, flash/glitch transitions)
  sfx.py           procedurally generated whoosh/impact/tick/riser + music bed (no copyright)
  tts.py           OmniVoice Hindi VO (CPU) -> edge-tts fallback
  cover.py         1080x1920 cover, text in 1080x1350 safe area
  brain_client.py  claim -> render -> upload -> report
  run.py           entry: `python -m engine.run job.json out/` or `--poll`
assets/fonts, assets/bg
samples/demo.json  example job (scene types: hook, stat, point, record, cta)
```
Local test: `SG_TTS=edge python -m engine.run samples/demo.json /tmp/out`

"""Hindi voiceover. Primary: OmniVoice (k2-fsa). Fallback: edge-tts so a reel never fails."""
import asyncio, subprocess, os, logging
from pathlib import Path
from .hindi_text import for_voice
log = logging.getLogger("tts")
_MODEL = None
VOICE_INSTRUCT = os.getenv("SG_VOICE_INSTRUCT", "male, young adult, moderate pitch")
REF_AUDIO = os.getenv("SG_REF_AUDIO")  # optional: assets/voice/ref.wav for a fixed brand voice
REF_TEXT = os.getenv("SG_REF_TEXT")

def _to_wav48(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "48000",
                    "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                    str(dst)], check=True)

def _omnivoice(text, out):
    global _MODEL
    import torch, soundfile as sf
    from omnivoice import OmniVoice, OmniVoiceGenerationConfig
    if _MODEL is None:
        _MODEL = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu", dtype=torch.float32)
        _MODEL.eval()
    cfg = OmniVoiceGenerationConfig(num_step=32, guidance_scale=2.0)
    kw = dict(text=text, generation_config=cfg)
    if REF_AUDIO and Path(REF_AUDIO).exists():
        kw.update(ref_audio=REF_AUDIO, ref_text=REF_TEXT)
    else:
        kw.update(instruct=VOICE_INSTRUCT)
    try:
        audio = _MODEL.generate(**kw)
    except TypeError:  # API variants
        kw.pop("generation_config", None); audio = _MODEL.generate(**kw)
    tmp = Path(out).with_suffix(".raw.wav"); sf.write(tmp, audio[0], 24000)
    _to_wav48(tmp, out); tmp.unlink(missing_ok=True)

async def _edge(text, out, voice="hi-IN-MadhurNeural"):
    import edge_tts
    tmp = Path(out).with_suffix(".mp3")
    await edge_tts.Communicate(text, voice, rate="+8%", pitch="+0Hz").save(str(tmp))
    _to_wav48(tmp, out); tmp.unlink(missing_ok=True)

def speak(text, out, engine=os.getenv("SG_TTS", "omnivoice")):
    text = for_voice(text)
    if engine == "omnivoice":
        try:
            _omnivoice(text, out); return "omnivoice"
        except Exception as e:  # never fail the reel because of TTS
            log.warning("OmniVoice failed (%s); falling back to edge-tts", e)
    asyncio.run(_edge(text, out)); return "edge"

def duration(wav):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())

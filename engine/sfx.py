"""Procedurally generated SFX + music bed (royalty-free, no copyright risk)."""
import numpy as np
from .config import SR

def _env(n, a=0.005, r=0.3):
    t = np.linspace(0, 1, n)
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(r, 1e-4) * 3)
    return e

def whoosh(d=0.6):
    n = int(SR * d); noise = np.random.randn(n)
    # band sweep via moving average of varying width
    out = np.zeros(n); w0, w1 = 40, 4
    for i in range(0, n, 256):
        w = int(w0 + (w1 - w0) * i / n); seg = noise[i:i + 256]
        out[i:i + 256] = np.convolve(seg, np.ones(w) / w, "same")
    t = np.linspace(0, 1, n); env = np.sin(np.pi * t) ** 2
    return (out * env / (np.abs(out).max() + 1e-9) * 0.55).astype(np.float32)

def impact(d=0.9):
    n = int(SR * d); t = np.arange(n) / SR
    f = 120 * np.exp(-t * 6) + 40
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)
    s += np.random.randn(n) * np.exp(-t * 40) * 0.4
    return (s / np.abs(s).max() * 0.8).astype(np.float32)

def tick(d=0.05):
    n = int(SR * d); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120)
    return (s * 0.35).astype(np.float32)

def riser(d=1.2):
    n = int(SR * d); t = np.arange(n) / SR
    f = 200 + 1600 * (t / d) ** 2
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / d) ** 2 * 0.25
    s += np.random.randn(n) * (t / d) ** 3 * 0.12
    return s.astype(np.float32)

def music_bed(d, bpm=100):
    """Dark sporty pulse: kick + sub bass + pad. Ducked later under voice."""
    n = int(SR * d); t = np.arange(n) / SR; out = np.zeros(n, np.float32)
    beat = 60 / bpm
    roots = [55.0, 55.0, 49.0, 65.4]  # A A G C (Hz)
    for k in range(int(d / beat) + 1):
        st = int(k * beat * SR); L = min(int(0.35 * SR), n - st)
        if L <= 0: break
        tt = np.arange(L) / SR
        kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
        out[st:st + L] += kick * 0.5
        bar = (k // 4) % 4; f = roots[bar]
        bass = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 3) * 0.25
        out[st:st + L] += bass
        if k % 2 == 1:  # hat
            Lh = min(int(0.04 * SR), n - st)
            out[st:st + Lh] += np.random.randn(Lh) * np.exp(-np.arange(Lh) / SR * 90) * 0.08
    pad = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6)) * 0.03
    pad *= 0.6 + 0.4 * np.sin(2 * np.pi * t / 8)
    out += pad
    fade = int(SR * 1.5); out[-fade:] *= np.linspace(1, 0, fade); out[:fade // 3] *= np.linspace(0, 1, fade // 3)
    return out

"""Synthesise the royalty-free 120 BPM music bed for the VitalWatch film.

Usage: python music.py OUT.wav INTRO_SECONDS DASHBOARD_SECONDS OUTRO_SECONDS

Everything is generated here from sine waves and noise, so there is no licence
to track. The dashboard section is mixed 10 dB lower so the captions lead.
"""
import sys
import wave

import numpy as np

SR = 48000
BPM = 120
BEAT = 60.0 / BPM


def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n, attack, release):
    e = np.ones(n)
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.minimum(e[-r:], np.linspace(1, 0, r))
    return e


def add(buf, start, sig):
    i = int(start * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 50 + 100 * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(phase) * np.exp(-t * 9)


def hat(rng):
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = np.diff(np.diff(x, prepend=0), prepend=0)  # crude high-pass
    return x / 4 * np.exp(-t * 60)


def bass(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return s * np.exp(-t * 3.5) * env(n, 0.005, 0.05)


def pad(freqs, dur, detune):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for f in freqs:
        for d in (-detune, detune):
            s += np.sin(2 * np.pi * f * (1 + d) * t)
    return s / (2 * len(freqs)) * env(n, 0.35, 0.5)


def pluck(freq):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t) + 0.1 * np.sin(6 * np.pi * freq * t)
    return s * np.exp(-t * 9) * env(n, 0.003, 0.05)


def main():
    out = sys.argv[1]
    intro, dash, outro = (float(x) for x in sys.argv[2:5])
    total = intro + dash + outro
    n = int(total * SR) + SR
    rng = np.random.default_rng(7)
    L = np.zeros(n)
    R = np.zeros(n)
    # A minor, F major, C major, G major; one chord per bar (4 beats)
    chords = [(57, [69, 72, 76]), (53, [65, 69, 72]), (48, [64, 67, 72]), (55, [62, 67, 71])]
    k = kick()
    beats = int(total / BEAT) + 1
    for b in range(beats):
        t0 = b * BEAT
        bar, pos = divmod(b, 4)
        root, tones = chords[bar % 4]
        in_dash = intro <= t0 < intro + dash
        add(L, t0, 0.55 * k)
        add(R, t0, 0.55 * k)
        h = hat(rng)
        add(L, t0 + BEAT / 2, 0.10 * h)
        add(R, t0 + BEAT / 2 + 0.004, 0.10 * h)
        if pos in (0, 2):
            s = bass(note(root - 12), BEAT * 2)
            add(L, t0, 0.30 * s)
            add(R, t0, 0.30 * s)
        if pos == 0:
            p = pad([note(m) for m in tones], BEAT * 4 + 0.4, 0.0025)
            add(L, t0, 0.20 * p)
            p2 = pad([note(m) for m in tones], BEAT * 4 + 0.4, 0.0035)
            add(R, t0, 0.20 * p2)
        if not in_dash:
            arp = tones + [tones[1]]
            for e in range(2):
                f = note(arp[(pos * 2 + e) % 4] + 12)
                pl = pluck(f)
                add(L, t0 + e * BEAT / 2, 0.07 * pl)
                add(R, t0 + e * BEAT / 2 + 0.006, 0.07 * pl)
    # section gain: dashboard 10 dB lower, with 0.8 s ramps
    t = np.arange(n) / SR
    low = 10 ** (-10 / 20)
    g = np.ones(n)
    ramp = 0.8
    a, b = intro, intro + dash
    g = np.where((t > a) & (t < a + ramp), 1 + (low - 1) * (t - a) / ramp, g)
    g = np.where((t >= a + ramp) & (t <= b - ramp), low, g)
    g = np.where((t > b - ramp) & (t < b), low + (1 - low) * (t - (b - ramp)) / ramp, g)
    # fade in and the final fade out
    g *= np.clip(t / 0.3, 0, 1)
    g *= np.clip((total - t) / 3.0, 0, 1)
    L *= g
    R *= g
    peak = max(np.abs(L).max(), np.abs(R).max())
    scale = 10 ** (-1 / 20) / peak
    data = np.stack([L, R], axis=1)[: int(total * SR)] * scale
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {out}: {total:.2f} s")


if __name__ == "__main__":
    main()

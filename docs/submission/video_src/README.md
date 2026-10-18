# Demo video source

`../VitalWatch_demo.mp4` (2 min 49 s, 1920x1080, 30 fps, H.264 + AAC) is built from three parts:

| Time | Part | How it is made |
|---|---|---|
| 0:00-0:37 | Intro: the problem, the VitalWatch wordmark, and one shape that tells the story (ECG line, risk trend, alert, reasons, SBAR note, acknowledgement, audit chain, 24-bed ward, 10,000 beds, IBM Telum chip) | `film.html?intro`, rendered frame by frame |
| 0:37-2:15 | The real dashboard, recorded live with captions | Playwright screen recording of `python -m vitalwatch demo` on the x86 reference machine, synthetic patients |
| 2:15-2:49 | Outro: results, benchmark race, audit tamper check, why IBM Z, end card | `film.html?outro`, rendered frame by frame |

Every number in the motion graphics is copied from the measured results in the README (synthetic test patients; x86 reference machine for the benchmarks).

## Files

- `film.html`: the motion graphics. One paused GSAP timeline per part; `window.seekTo(t)` draws the exact frame for time `t`, so the render is deterministic.
- `render.mjs`: renders a part to MP4 with Playwright and FFmpeg, or renders stills for checking.
- `music.py`: synthesises the 120 BPM music bed from sine waves and noise (no third-party audio). The dashboard section is mixed 10 dB lower.

## Rebuild

```bash
cd docs/submission/video_src
node render.mjs intro intro.mp4 30
node render.mjs outro outro.mp4 30
python music.py music.wav 37.5 97.5 34.0
# dash.mp4: the dashboard recording, trimmed to 97.5 s and scaled to 1920x1080 at 30 fps
ffmpeg -i intro.mp4 -i dash.mp4 -i outro.mp4 -i music.wav \
  -filter_complex "[0:v]settb=1/30,setpts=N/30/TB[a];[1:v]settb=1/30,setpts=N/30/TB[b];[2:v]settb=1/30,setpts=N/30/TB[c];[a][b][c]concat=n=3:v=1:a=0[v]" \
  -map "[v]" -map 3:a -c:v libx264 -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -shortest -movflags +faststart VitalWatch_demo.mp4
```

`film.html` loads GSAP 3.12.5 from cdnjs. To render offline, get the same file from npm (`npm pack gsap@3.12.5`) and run with `GSAP_FILE=/path/to/package/dist/gsap.min.js`. Playwright is found at `/opt/node22/lib/node_modules/playwright` by default; set `PW_MODULE` to use another install.

The visual direction (one continuous shape, 120 BPM, something on every beat, no crossfades) follows the "Product Launch Motion Film" prompt style shared publicly by @0xnicc0; all code, music and content here are our own.

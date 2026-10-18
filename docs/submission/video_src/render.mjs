// Render film.html deterministically, frame by frame.
// Usage: node render.mjs <intro|outro> <out.mp4> [fps]      -> video
//        node render.mjs <intro|outro> --stills <dir> t1,t2  -> PNG stills
import { createRequire } from 'module';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_MODULE || '/opt/node22/lib/node_modules/playwright');
const here = path.dirname(fileURLToPath(import.meta.url));
const [part, outArg, third, fourth] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
// Optional offline mode: GSAP_FILE=/path/to/gsap.min.js serves GSAP locally instead of from cdnjs.
if (process.env.GSAP_FILE) await page.route('**/gsap.min.js', r => r.fulfill({ path: process.env.GSAP_FILE, contentType: 'application/javascript' }));
await page.goto('file://' + path.join(here, 'film.html') + '?' + part);
await page.waitForFunction(() => window.ready === true);
const dur = await page.evaluate(() => window.duration());
if (outArg === '--stills') {
  for (const t of fourth.split(',').map(Number)) {
    await page.evaluate(t => window.seekTo(t), t);
    await page.screenshot({ path: path.join(third, `${part}_${t.toFixed(2)}.png`) });
  }
} else {
  const fps = Number(third || 30);
  const n = Math.round(dur * fps);
  const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(fps), outArg], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let i = 0; i < n; i++) {
    await page.evaluate(t => window.seekTo(t), i / fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log(JSON.stringify({ part, frames: n, seconds: dur }));
}
if (errors.length) console.log('PAGE ERRORS', errors);
await browser.close();

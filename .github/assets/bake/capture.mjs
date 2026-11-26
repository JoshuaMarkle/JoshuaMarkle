// Capture the halo from joshuamarkle.com frame by frame, on a fake clock, so every frame is exactly
// 1/FPS after the last no matter how long the GPU (or SwiftShader) takes to draw it.
//
// usage: node capture.mjs URL OUTDIR [frames=360] [fps=50] [width=1920] [height=1080] [scheme JSON]
// scheme: the site's look settings (localStorage jm-scheme), e.g. '{"grain":0}' to leave its grain out
// Needs the site running (npm run dev in ../joshuamarkle) and chromium on PATH.
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const [url, out, frames = 360, fps = 50, W = 1920, H = 1080, scheme = '{}'] = process.argv.slice(2);
const N = +frames, DT = 1000 / +fps;
mkdirSync(out, { recursive: true });
const port = 9400 + Math.floor(Math.random() * 400);
const prof = join(tmpdir(), `halo-bake-${port}`);
const ch = spawn('chromium', ['--headless=new', `--remote-debugging-port=${port}`, `--window-size=${W},${H}`, '--hide-scrollbars', '--force-device-scale-factor=1', `--user-data-dir=${prof}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
for (let i = 0; i < 100; i++) { try { await fetch(`http://127.0.0.1:${port}/json/version`); break; } catch { await sleep(200); } }

const tab = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const call = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id;
  ws.addEventListener('message', function h(e) {
    const m = JSON.parse(e.data);
    if (m.id !== i) return;
    ws.removeEventListener('message', h);
    m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result);
  });
  ws.send(JSON.stringify({ id: i, method, params }));
});
const js = async (expression) => (await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })).result.value;

// time stands still until we move it; the page's own animation frames wait in a queue for us
await call('Page.enable');
await call('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
  let now = 0; const q = []; const t0 = Date.now(); const raf = window.requestAnimationFrame.bind(window);
  performance.now = () => now; Date.now = () => t0 + now;
  window.requestAnimationFrame = (cb) => (q.push(cb), q.length);
  window.cancelAnimationFrame = () => {};
  // move the clock on and let everything that was waiting draw; resolve once the frame is on screen
  window.__step = (dt) => new Promise((res) => { now += dt; for (const cb of q.splice(0)) cb(now); raf(() => raf(() => res(now))); });
  // the scheme is set here, not remembered from a visit before
  try { localStorage.clear(); localStorage.setItem('jm-scheme', ${JSON.stringify(scheme)}); } catch {}
})();` });
await call('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
await call('Page.navigate', { url });
await sleep(4000);
// only the name: no menu, no line under it
await js(`(() => { const s = document.createElement('style'); s.textContent = '#nav,.skip,.line,.reel,.more,footer,.foot{visibility:hidden!important}'; document.head.append(s); })()`);
// let it wake: two seconds of its own time for the light to come up and settle
for (let i = 0; i < 100; i++) await js(`__step(${DT})`);

const r = await js(`(() => { const b = document.querySelector('h1.halo').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; })()`);
// the name with its light round it, as wide as the page
const padY = r[3] * 0.16;
const clip = { x: 0, y: Math.max(0, Math.round(r[1] - padY)), width: +W, height: Math.round(r[3] + 2 * padY), scale: 1 };
writeFileSync(join(out, 'clip.json'), JSON.stringify({ clip, fps: +fps, frames: N }));
console.log('clip', clip);

const t = Date.now();
for (let f = 0; f < N; f++) {
  await js(`__step(${DT})`);
  const shot = await call('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: false });
  writeFileSync(join(out, `f${String(f).padStart(4, '0')}.png`), Buffer.from(shot.data, 'base64'));
  if (f % 25 === 0) console.log(`frame ${f}/${N}  ${((Date.now() - t) / 1000).toFixed(0)}s`);
}
ws.close();
// let chromium finish writing its profile before it goes
await new Promise((r) => { ch.on('exit', r); ch.kill(); });
try { rmSync(prof, { recursive: true, force: true, maxRetries: 5 }); } catch {}
console.log('done');

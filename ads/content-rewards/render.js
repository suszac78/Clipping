// Renders ad.html frame by frame into frames/ then call ffmpeg.
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const FPS = +(process.env.FPS || 30);
const out = process.argv[2] || path.join(__dirname, 'frames');
const only = process.argv[3]; // optional: comma list of seconds for stills
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.addInitScript(() => { window.__RENDERING = true; });
  await p.goto('file://' + path.join(__dirname, 'ad.html'));
  await p.waitForTimeout(300);
  const dur = await p.evaluate(() => window.DURATION);
  const times = only ? only.split(',').map(Number) : [...Array(Math.round(dur*FPS)).keys()].map(i => i / FPS);
  for (let i = 0; i < times.length; i++) {
    await p.evaluate(t => render(t), times[i]);
    const name = only ? `still_${times[i]}.png` : `f${String(i).padStart(5,'0')}.jpg`;
    await p.screenshot({ path: path.join(out, name), type: only ? 'png' : 'jpeg', quality: only ? undefined : 95 });
  }
  await b.close();
})();

// Measure the rendered page against Figma geometry from `figma2aem verify-spec`.
//
//   npm install            (once, in this folder: installs playwright-core)
//   AEM_USER=… AEM_PASSWORD=… node verify/probe.mjs build/verify-spec.json [--css local.css] [--shots dir]
//
// --css FILE         serve FILE in place of every stylesheet URL matching --css-match,
//                    to test compiled CSS before deploying it (nothing is written to AEM)
// --css-match REGEX  which stylesheet to replace, e.g. "clientlib-mysite\.lc-.*\.css"
// --shots DIR        save a full-page screenshot per viewport
// CHROME_PATH        Chromium/Chrome binary (otherwise Playwright's default)
// Exit code 1 when any check differs from Figma by more than the spec tolerance.
import { readFileSync, mkdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const args = process.argv.slice(2);
const specPath = args.find(a => !a.startsWith('--'));
const opt = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
if (!specPath) { console.error('usage: node verify/probe.mjs <verify-spec.json> [--css file --css-match regex] [--shots dir]'); process.exit(2); }

const spec = JSON.parse(readFileSync(specPath, 'utf8'));
const executablePath = process.env.CHROME_PATH || undefined;
const auth = process.env.AEM_USER
  ? 'Basic ' + Buffer.from(`${process.env.AEM_USER}:${process.env.AEM_PASSWORD}`).toString('base64')
  : null;

const browser = await chromium.launch({ executablePath });
const context = await browser.newContext();
// Send the AEM login only to the AEM origin. A global Authorization header is
// also sent to third parties (e.g. Typekit font requests), which then fail the
// CORS preflight and the page silently renders in the fallback font.
if (auth) {
  const origin = new URL(spec.url).origin;
  await context.route(url => url.origin === origin, route =>
    route.continue({ headers: { ...route.request().headers(), authorization: auth } }));
}
if (opt('css')) {
  const pattern = new RegExp(opt('css-match') || 'clientlib-.*\\.css');
  await context.route(pattern, route => route.fulfill({ path: opt('css'), contentType: 'text/css' }));
}

let failures = 0;
for (const viewport of spec.viewports) {
  const page = await context.newPage();
  await page.setViewportSize({ width: viewport.width, height: 900 });
  await page.goto(spec.url, { waitUntil: 'load', timeout: 90000 });
  // Trigger lazy images, then settle.
  await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise(r => setTimeout(r, 50)); } scrollTo(0, 0); });
  await page.waitForTimeout(1500);
  if (opt('shots')) { mkdirSync(opt('shots'), { recursive: true }); await page.screenshot({ path: `${opt('shots')}/${viewport.width}.png`, fullPage: true }); }

  const measured = await page.evaluate(checks => checks.map(c => {
    const el = document.querySelectorAll(c.selector)[c.index || 0];
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y + scrollY), Math.round(b.width), Math.round(b.height)];
  }), viewport.checks);
  const docWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  // Which families actually rendered, so a fallback font is visible in the report.
  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    const loaded = [...document.fonts].filter(f => f.status === 'loaded').map(f => `${f.family} ${f.weight}`);
    const failed = [...document.fonts].filter(f => f.status === 'error').map(f => `${f.family} ${f.weight}`);
    return { loaded: [...new Set(loaded)], failed: [...new Set(failed)] };
  });
  const offset = viewport.headerOffset || 0; // live header height minus Figma nav height

  console.log(`\n## ${viewport.width}px  (Figma frame ${viewport.figmaFrame})${docWidth > viewport.width ? `  ⚠ horizontal overflow: ${docWidth}px` : ''}`);
  console.log(`fonts loaded: ${fonts.loaded.join(', ') || 'none'}${fonts.failed.length ? `  ⚠ failed: ${fonts.failed.join(', ')}` : ''}${offset ? `  (header offset ${offset}px applied)` : ''}`);
  console.log('check'.padEnd(22), 'figma [x,y,w,h]'.padEnd(26), 'page [x,y,w,h]'.padEnd(26), 'Δ');
  viewport.checks.forEach((check, i) => {
    const got = measured[i];
    if (!got) { failures++; console.log(check.label.padEnd(22), JSON.stringify(check.expected).padEnd(26), 'MISSING'.padEnd(26), `selector ${check.selector}`); return; }
    const expected = [check.expected[0], check.expected[1] + offset, check.expected[2], check.expected[3]];
    const delta = got.map((v, k) => v - expected[k]);
    const bad = delta.some(d => Math.abs(d) > spec.tolerance);
    if (bad) failures++;
    console.log(check.label.padEnd(22), JSON.stringify(expected).padEnd(26), JSON.stringify(got).padEnd(26), JSON.stringify(delta), bad ? '✗' : '✓');
  });
  if (docWidth > viewport.width) failures++;
  await page.close();
}
await browser.close();
console.log(failures ? `\n${failures} check(s) outside ±${spec.tolerance}px` : `\nAll checks within ±${spec.tolerance}px`);
process.exit(failures ? 1 : 0);

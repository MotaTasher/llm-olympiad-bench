// Optional browser regression check. Requires playwright-core and Chrome.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const base = process.argv[2] || 'http://127.0.0.1:8765';
const local = base.startsWith('http://127.0.0.1:');
const root = path.resolve(__dirname, '../public_results');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'reasoning-code-qa-'));
const competition = 'algo-cup-2026-qualifying';

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true, permissions: ['clipboard-read', 'clipboard-write'] });
      if (local) await context.route('**/problems**', route => {
        const parts = new URL(route.request().url()).pathname.split('/').filter(Boolean);
        if (parts[0] !== 'problems' || route.request().resourceType() !== 'document') return route.continue();
        const shell = parts.length === 1 ? 'competitions' : parts.length === 2 ? 'problem-set' : parts.length === 4 ? 'solution' : parts[2].startsWith('task') ? 'task' : 'model';
        return route.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(root, shell + '.html')) });
      });
      const page = await context.newPage(); const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/?competition=${competition}`, { waitUntil: 'domcontentloaded' });
      await page.locator('.team-row .result-cell a').first().waitFor();
      assert.equal(await page.locator('.team-row .result-cell a').count(), 12);
      assert.equal(await page.locator('.model-row').count(), 10);
      assert((await page.locator('.model-row td').allTextContents()).every(text => text.trim() === '—'));
      assert.deepEqual(await page.locator('.team-row .rank-cell').allTextContents(), ['01', '02', '03']);
      const solutionUrl = await page.locator('.team-row .result-cell a').first().getAttribute('href');
      const teamUrl = await page.locator('.team-row .participant-cell-link').first().getAttribute('href');
      const taskUrl = await page.locator('.task-header-link').first().getAttribute('href');
      const modelUrl = await page.locator('.model-row .participant-cell-link').first().getAttribute('href');
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(output, `leaderboard-${width}.png`) });
      await page.goto(base + solutionUrl, { waitUntil: 'domcontentloaded' });
      await page.locator('#solution-text pre code.hljs').waitFor({ state: 'attached' });
      const source = await page.locator('#solution-text pre code').textContent();
      assert(source.includes('#include'));
      assert((await page.locator('#solution-text .hljs-keyword').count()) > 0);
      assert((await page.locator('#solution-judge-metrics').textContent()).includes('239 мс'));
      assert((await page.locator('#solution-judge-metrics').textContent()).includes('C++23 (GCC 14.1)'));
      assert((await page.locator('#solution-judge-metrics').textContent()).includes('МиБ'));
      assert.equal(await page.locator('#solution-verdict').textContent(), 'Принято · OK');
      await page.locator('[data-reading-section="model"]').evaluate(node => { node.open = true; });
      await page.locator('[data-copy-code]').click();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), source);
      const downloadEvent = page.waitForEvent('download');
      await page.locator('[data-download-code]').click();
      const download = await downloadEvent;
      const filename = path.join(output, `download-${width}.cpp`);
      await download.saveAs(filename);
      assert.equal(fs.readFileSync(filename, 'utf8'), source);
      assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= width);
      await page.screenshot({ path: path.join(output, `solution-${width}.png`), fullPage: true });
      await page.goto(base + teamUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.querySelectorAll('.code-viewer').length === 4);
      assert.equal(await page.locator('.judge-metrics').count(), 4);
      assert.equal(await page.locator('#model-points').textContent(), '4');
      await page.goto(base + taskUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.querySelectorAll('.code-viewer').length === 3);
      assert.equal(await page.locator('[data-model-id]').count(), 13);
      assert.equal((await page.locator('.task-verdict').allTextContents()).filter(text => text.includes('Не запускалась')).length, 10);
      await page.goto(base + modelUrl, { waitUntil: 'domcontentloaded' });
      assert.equal(await page.locator('#model-rank').textContent(), '—');
      assert.equal(await page.locator('.code-viewer').count(), 0);

      // Synthetic Python source stays in this browser response; it is never saved/published.
      const python = 's = "<script>window.CODE_XSS = true</script> $value"\r\nprint(s)\r\n';
      await context.route('**/code/solutions/*.json', async route => {
        const document = await (await route.fetch()).json();
        document.source = { language: 'python', filename: 'solution.py', code: python };
        document.judge.compiler_name = 'Python 3.13';
        return route.fulfill({ json: document });
      });
      await page.goto(base + solutionUrl, { waitUntil: 'domcontentloaded' });
      await page.locator('#solution-text pre code.hljs').waitFor({ state: 'attached' });
      // HTML parsing inside the highlighter normalizes CRLF for display only.
      assert.equal(await page.locator('#solution-text pre code').textContent(), python.replaceAll('\r\n', '\n'));
      assert((await page.locator('#solution-text .hljs-string').count()) > 0);
      assert.equal(await page.evaluate(() => Boolean(window.CODE_XSS)), false);
      assert.equal(await page.locator('#solution-text .katex').count(), 0);
      await page.locator('[data-reading-section="model"]').evaluate(node => { node.open = true; });
      await page.locator('[data-copy-code]').click();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), python);
      const pythonDownloadEvent = page.waitForEvent('download');
      await page.locator('[data-download-code]').click();
      const pythonDownload = await pythonDownloadEvent;
      const pythonFilename = path.join(output, `download-${width}.py`);
      await pythonDownload.saveAs(pythonFilename);
      assert.equal(fs.readFileSync(pythonFilename, 'utf8'), python);
      assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= width);
      await page.screenshot({ path: path.join(output, `python-${width}.png`), fullPage: true });
      await context.unroute('**/code/solutions/*.json');
      await page.goto(`${base}/?competition=math-cup-2026-final`, { waitUntil: 'domcontentloaded' });
      const mathUrl = await page.locator('.model-row .result-cell a').first().getAttribute('href');
      await page.goto(base + mathUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.querySelector('#solution-text').textContent.length > 100);
      assert.equal(await page.locator('.code-viewer').count(), 0);
      assert.equal(await page.locator('#solution-judge-metrics').isHidden(), true);
      assert.deepEqual(errors, []);
      console.log(JSON.stringify({ width, teamSolutions: 12, cpp: 'ok', python: 'ok', copyDownload: 'exact', math: 'ok' }));
      await context.close();
    }
    console.log('Browser artifacts: ' + output);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

// Convert SVG drawing sheets to PDF (+ PNG preview). Usage: node svg2pdf.js a.svg b.svg ...
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1120, height: 860 } });
  for (const f of process.argv.slice(2)) {
    await page.goto('file://' + path.resolve(f));
    await page.pdf({ path: f.replace(/\.svg$/, '.pdf'), width: '1120px', height: '860px', printBackground: true });
    await page.screenshot({ path: f.replace(/\.svg$/, '.png') });
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });

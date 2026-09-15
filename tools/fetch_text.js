// Витягує текст сторінки через headless Chromium (для сайтів, що рендеряться JS, напр. so.supreme.court.gov.ua).
// Використання: node tools/fetch_text.js "https://..."  (потрібен пакет playwright)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({executablePath:'/opt/pw-browsers/chromium'}).catch(async e=>{return await chromium.launch();});
  const p = await b.newPage({userAgent:'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36'});
  await p.goto(process.argv[2], {waitUntil:'networkidle', timeout:60000});
  await p.waitForTimeout(3000);
  console.log(await p.evaluate(()=>document.body.innerText));
  await b.close();
})();

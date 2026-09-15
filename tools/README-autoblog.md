# Автопублікація новин у блозі

Сайт — статичний (GitHub Pages, репозиторій `pravo0001/main-clod-tax-advocate.com.ua`). Стаття = окремий файл
`blog/<slug>.html` + картка у `blog.html` + рядок у `sitemap.xml` / `sitemap.txt` + запис
у реєстрі `blog/published.json`.

## Як публікується стаття

1. Підготувати `article.json` (формат — `tools/article.example.json`): slug, topic
   (`ppr` / `onlyfans` / `pn-rk`), заголовок, SEO-заголовок, meta-опис, анонс, дата,
   лід, `body_html` (розділи `<h2>`, абзаци, списки), джерела, `source_ids`
   (ідентифікатори новини: `case:<номер справи>`, `sc-news:<id>`, `dps-news:<id>`,
   `bill:<номер>`, `law:<номер>` тощо), CTA.
2. `python3 tools/blog_publish.py article.json --check` — перевірка дублікатів.
3. `python3 tools/blog_publish.py article.json` — генерація сторінки, картки, sitemap, реєстру.
4. `git add -A && git commit -m "Блог: <заголовок>" && git push origin main`.

## Захист від повторної публікації

`blog_publish.py` відмовляє (код виходу 3), якщо:
- такий slug або файл уже існує;
- будь-який новинний URL із `sources` уже використано в опублікованій статті
  (довідкові посилання на zakon.rada.gov.ua не враховуються);
- будь-який `source_id` уже є в реєстрі.

Коміт атомарний: якщо push не вдався, наступний запуск починається з чистого клону,
тому «половинної» публікації не буває. Якщо push вдався, новина є в реєстрі і
повторно не опублікується.

## Розклад

Щотижнева задача в Claude (Cowork, scheduled task) — вівторок 10:00 за Києвом.
Призупинити/поновити: у Claude → «Scheduled tasks» (або попросити Claude вимкнути задачу).

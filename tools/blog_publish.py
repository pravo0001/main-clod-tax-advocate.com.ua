#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Публікація статті в блог сайту tax-advocate.com.ua (статичний сайт, GitHub Pages).

Використання:
    python3 tools/blog_publish.py article.json            # опублікувати
    python3 tools/blog_publish.py article.json --check    # лише перевірити дублікати, нічого не змінювати
    python3 tools/blog_publish.py article.json --dry-run  # згенерувати HTML у stdout без запису

Що робить:
  1. Перевіряє реєстр blog/published.json — відмовляє, якщо slug, файл або будь-яке
     джерело (source_url / source_id) уже публікувалися (захист від повторної публікації).
  2. Створює blog/<slug>.html за шаблоном оформлення сайту.
  3. Додає картку статті на початок списку в blog.html і оновлює лічильники.
  4. Додає URL у sitemap.xml та sitemap.txt, оновлює lastmod для blog.html.
  5. Записує статтю в реєстр blog/published.json.

Формат article.json — див. tools/article.example.json.
Скрипт нічого не комітить: git add / commit / push робить той, хто його запускає.
"""
import html
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://tax-advocate.com.ua"
REGISTRY = os.path.join(ROOT, "blog", "published.json")

TOPICS = {
    "ppr": {
        "label": "ППР",
        "service_link": "../oskarzhennya-ppr.html",
        "service_label": "Оскарження ППР",
    },
    "onlyfans": {
        "label": "OnlyFans та іноземні доходи",
        "service_link": "../podatkovi-spory.html",
        "service_label": "Податкові спори",
    },
    "pn-rk": {
        "label": "Зупинення реєстрації ПН/РК",
        "service_link": "../podatkovi-spory.html",
        "service_label": "Податкові спори",
    },
}

MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
              "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def fail(msg, code=2):
    print("ПОМИЛКА: " + msg, file=sys.stderr)
    sys.exit(code)


def esc(s):
    return html.escape(str(s), quote=True)


def uk_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS_GEN[m - 1]} {y}"


def dot_date(iso):
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def load_registry():
    if not os.path.exists(REGISTRY):
        return {"articles": []}
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")


# Довідкові URL (тексти законів), які повторюються з статті в статтю і не є «новиною»
REFERENCE_HOSTS = ("zakon.rada.gov.ua", "tax.gov.ua/zakonodavstvo", "zir.tax.gov.ua")


def is_reference(url):
    return any(h in url.lower() for h in REFERENCE_HOSTS)


def news_source_urls(a):
    """URL джерел, що беруть участь у перевірці дублікатів (без довідкових і без dedup:false)."""
    return [s["url"] for s in a["sources"] if s.get("dedup", True) and not is_reference(s["url"])]


def norm_url(u):
    u = u.strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


def validate(a):
    req = ["slug", "topic", "title", "seo_title", "meta_description", "excerpt",
           "eyebrow", "date", "lead", "body_html", "sources", "source_ids"]
    for k in req:
        if k not in a or not a[k]:
            fail(f"у article.json відсутнє або порожнє поле «{k}»")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a["slug"]):
        fail("slug має містити лише латиницю, цифри та дефіси")
    if a["topic"] not in TOPICS:
        fail("topic має бути одним із: " + ", ".join(TOPICS))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a["date"]):
        fail("date має бути у форматі YYYY-MM-DD")
    date.fromisoformat(a["date"])
    for s in a["sources"]:
        if "title" not in s or "url" not in s:
            fail("кожне джерело має містити title і url")
    if not isinstance(a["source_ids"], list):
        fail("source_ids має бути списком")
    if not news_source_urls(a):
        fail("серед sources немає жодного новинного першоджерела (лише довідкові посилання на закони)")
    if len(a["body_html"]) < 1500:
        fail("body_html занадто короткий (< 1500 символів) — стаття неповна")


def check_duplicates(a, reg):
    problems = []
    slug = a["slug"]
    if os.path.exists(os.path.join(ROOT, "blog", slug + ".html")):
        problems.append(f"файл blog/{slug}.html уже існує")
    urls = {norm_url(u) for u in news_source_urls(a)}
    ids = {str(i).strip().lower() for i in a["source_ids"]}
    for art in reg["articles"]:
        if art["slug"] == slug:
            problems.append(f"slug «{slug}» уже є в реєстрі ({art['date']})")
        hit_urls = urls & {norm_url(u) for u in art.get("source_urls", [])}
        if hit_urls:
            problems.append(f"джерело вже використано у статті «{art['title']}» ({art['date']}): {', '.join(sorted(hit_urls))}")
        hit_ids = ids & {str(i).lower() for i in art.get("source_ids", [])}
        if hit_ids:
            problems.append(f"новина з ідентифікатором {', '.join(sorted(hit_ids))} уже опублікована: «{art['title']}» ({art['date']})")
    return problems


def render_article(a):
    t = TOPICS[a["topic"]]
    url = f"{SITE}/blog/{a['slug']}.html"
    cta = a.get("cta") or {}
    cta_heading = cta.get("heading") or "Потрібна консультація податкового адвоката?"
    cta_text = cta.get("text") or "Розберемо вашу ситуацію, документи та реальний маршрут захисту — від відповіді на запит до суду."
    service_link = cta.get("service_link") or t["service_link"]
    service_label = cta.get("service_label") or t["service_label"]
    keywords = a.get("keywords") or ""
    ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": a["title"],
        "description": a["meta_description"],
        "datePublished": a["date"],
        "dateModified": a["date"],
        "author": {"@type": "Person", "name": "Андрій Глазунов"},
        "publisher": {"@type": "Organization", "name": "tax-advocate.com.ua"},
        "mainEntityOfPage": url,
    }
    sources_li = "\n".join(
        f'            <li><a href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer">{esc(s["title"])}</a>'
        + (f' — {esc(s["note"])}' if s.get("note") else "") + "</li>"
        for s in a["sources"]
    )
    keywords_meta = f'\n  <meta name="keywords" content="{esc(keywords)}">' if keywords else ""
    return f'''<!doctype html>
<html lang="uk">
<head>
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=AW-18141894337"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());

    gtag('config', 'AW-18141894337');
  </script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(a["seo_title"])} | Блог</title>
  <meta name="description" content="{esc(a["meta_description"])}">{keywords_meta}
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{url}">
  <meta property="og:locale" content="uk_UA">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{esc(a["title"])}">
  <meta property="og:description" content="{esc(a["excerpt"])}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{SITE}/images/advocate.jpg">
  <meta property="article:published_time" content="{a["date"]}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../styles.css">
  <link rel="icon" href="../images/favicon-32.png" type="image/png" sizes="32x32">
  <link rel="apple-touch-icon" href="../images/apple-touch-icon.png">
  <script type="application/ld+json">
  {json.dumps(ld, ensure_ascii=False, indent=4)}
  </script>
</head>
<body class="premium-site theme-day uniform-page-bg">
  <a class="skip-link" href="#main-content">Перейти до контенту</a>
  <header class="header">
    <div class="container nav">
      <a href="../index.html" class="brand">Адвокат<span>Андрій Глазунов</span></a>
      <nav class="menu" id="site-menu" aria-label="Головна навігація">
        <a href="../services.html">Послуги</a>
        <a href="../Glazunov-Andrii-Romanovych.html">Про адвоката</a>
        <a href="../faq.html">FAQ</a>
        <a href="../court-decisions.html">Кейси</a>
        <a href="../blog.html">Блог</a>
        <a href="../contact.html">Контакти</a>
      </nav>
      <button class="menu-toggle" type="button" aria-label="Відкрити меню" aria-expanded="false" aria-controls="site-menu">≡</button>
      <div class="nav-actions">
        <button class="btn btn-toggle" id="theme-toggle" type="button" aria-pressed="false" aria-label="Увімкнути нічну тему" title="Увімкнути нічну тему">Ніч</button>
        <a class="btn btn-light" href="../contact.html#consultation-form">Зв’язок</a>
      </div>
    </div>
  </header>

  <main id="main-content" class="section">
    <div class="container article-layout">
      <article class="article-wrap">
        <div class="breadcrumbs"><a href="../index.html">Головна</a><span>/</span><a href="../blog.html">Блог</a><span>/</span><span>{esc(a.get("breadcrumb") or t["label"])}</span></div>
        <p class="eyebrow">{esc(a["eyebrow"])} · <time datetime="{a["date"]}">{dot_date(a["date"])}</time></p>
        <h1 class="article-title">{esc(a["title"])}</h1>
        <p class="article-lead">{a["lead"]}</p>

{a["body_html"].rstrip()}

        <div class="inline-cta">
          <strong>{esc(cta_heading)}</strong>
          <p>{esc(cta_text)}</p>
          <div class="article-actions">
            <a class="btn btn-primary" href="../contact.html#consultation-form">Записатися</a>
            <a class="btn btn-ghost" href="{esc(service_link)}">{esc(service_label)}</a>
          </div>
        </div>

        <section class="legal-refs" aria-labelledby="legal-refs-{esc(a["slug"])}">
          <h2 id="legal-refs-{esc(a["slug"])}">Першоджерела та офіційні документи</h2>
          <ul>
{sources_li}
          </ul>
          <p class="legal-disclaimer">Матеріал має інформаційний характер станом на {dot_date(a["date"])} і не є юридичною консультацією. Застосування норм і висновків суду залежить від обставин конкретної справи та чинної на момент події редакції законодавства.</p>
        </section>
      </article>
    </div>
  </main>

  <footer class="footer">
    <div class="container footer-inner">
      <div class="footer-grid">
        <div><a href="../index.html" class="brand">Адвокат<span>Андрій Глазунов</span></a><p>Блог з посиланнями на офіційні тексти законів.</p></div>
        <div><p class="eyebrow">Навігація</p><nav class="footer-nav" aria-label="Footer navigation"><a href="../services.html">Послуги</a><a href="../Glazunov-Andrii-Romanovych.html">Про адвоката</a><a href="../faq.html">FAQ</a><a href="../court-decisions.html">Кейси</a><a href="../blog.html">Блог</a><a href="../contact.html">Контакти</a></nav></div>
        <div><p class="eyebrow">Контакти</p><nav class="footer-nav" aria-label="Footer contacts"><a href="tel:+380770170707">+38 (077) 017-07-07</a><a href="mailto:contact@taxlawyer.com.ua">contact@taxlawyer.com.ua</a></nav></div>
      </div>
      <p>&copy; <span data-current-year></span> Андрій Глазунов. Всі права захищено.</p>
    </div>
  </footer>

  <a class="btn btn-primary floating-cta" href="tel:+380770170707" aria-label="Подзвонити адвокату">Подзвонити</a>



  <script src="../script.js" defer></script>
</body>
</html>
'''


def render_feed_item(a):
    return f'''              <li class="blog-feed-item" id="blog-{esc(a["slug"])}">
                <a href="blog/{esc(a["slug"])}.html" class="blog-feed-link">
                  <span class="blog-feed-icon-wrap">
                    <span class="blog-feed-icon blog-feed-icon--doc" aria-hidden="true">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/><path d="M14 2v6h6M8 13h8M8 17h6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>
                    </span>
                  </span>
                  <span class="blog-feed-body">
                    <span class="blog-feed-title">{esc(a["title"])}</span>
                    <span class="blog-feed-excerpt">{esc(a["excerpt"])}</span>
                    <span class="blog-feed-row-meta">
                      <span class="blog-feed-cal" aria-hidden="true">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="1.35"/></svg>
                      </span>
                      <time datetime="{a["date"]}">{uk_date(a["date"])}</time>
                    </span>
                  </span>
                  <span class="blog-feed-go" aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </span>
                </a>
              </li>
'''


def update_blog_index(a):
    path = os.path.join(ROOT, "blog.html")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    marker = '<ul class="blog-feed-list">\n'
    if marker not in src:
        fail("у blog.html не знайдено <ul class=\"blog-feed-list\">")
    if f'id="blog-{a["slug"]}"' in src:
        fail(f"картка blog-{a['slug']} уже є в blog.html")
    src = src.replace(marker, marker + render_feed_item(a), 1)
    total = src.count('class="blog-feed-item"')
    # лічильники у футері стрічки
    src = re.sub(r'title="У каталозі зараз \d+ матеріалів"', f'title="У каталозі зараз {total} матеріалів"', src)
    src = re.sub(r'<p class="blog-feed-range">1–\d+ з \d+</p>',
                 f'<p class="blog-feed-range">1–{min(total, 15)} з {total}</p>', src)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return total


def update_sitemaps(a):
    url = f"{SITE}/blog/{a['slug']}.html"
    xml_path = os.path.join(ROOT, "sitemap.xml")
    with open(xml_path, encoding="utf-8") as f:
        xml = f.read()
    if url in xml:
        fail("URL уже є в sitemap.xml")
    entry = f"  <url>\n    <loc>{url}</loc>\n    <lastmod>{a['date']}</lastmod>\n  </url>\n"
    m = re.search(r"  <url>\n    <loc>https://[^<]+/blog\.html</loc>\n(?:    <lastmod>[^<]+</lastmod>\n)?  </url>\n", xml)
    if m:
        blog_entry = re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{a['date']}</lastmod>", m.group(0))
        if "<lastmod>" not in blog_entry:
            blog_entry = blog_entry.replace("</loc>\n", f"</loc>\n    <lastmod>{a['date']}</lastmod>\n")
        xml = xml[:m.start()] + blog_entry + entry + xml[m.end():]
    else:
        xml = xml.replace("</urlset>", entry + "</urlset>")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml)

    txt_path = os.path.join(ROOT, "sitemap.txt")
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        if url not in lines:
            idx = next((i for i, l in enumerate(lines) if l.endswith("/blog.html")), len(lines) - 1)
            lines.insert(idx + 1, url)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    flags = {x for x in sys.argv[1:] if x.startswith("--")}
    if not args:
        fail("вкажіть шлях до article.json", 1)
    with open(args[0], encoding="utf-8") as f:
        a = json.load(f)
    validate(a)
    reg = load_registry()
    problems = check_duplicates(a, reg)
    if problems:
        print("ДУБЛІКАТ — публікацію зупинено:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        sys.exit(3)
    if "--check" in flags:
        print(f"OK: дублікатів не знайдено, slug «{a['slug']}» вільний")
        return
    page = render_article(a)
    if "--dry-run" in flags:
        sys.stdout.write(page)
        return
    out = os.path.join(ROOT, "blog", a["slug"] + ".html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    total = update_blog_index(a)
    update_sitemaps(a)
    reg["articles"].insert(0, {
        "slug": a["slug"],
        "date": a["date"],
        "topic": a["topic"],
        "title": a["title"],
        "source_urls": news_source_urls(a),
        "source_ids": a["source_ids"],
    })
    save_registry(reg)
    print(f"Опубліковано: blog/{a['slug']}.html")
    print(f"Картку додано в blog.html (усього матеріалів: {total}); sitemap.xml/sitemap.txt оновлено; реєстр blog/published.json оновлено.")
    print("Далі: git add -A && git commit && git push")


if __name__ == "__main__":
    main()

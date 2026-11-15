"""Build the blog from public Markdown content. No server or database required."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from email.utils import format_datetime
from html import escape, unescape
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import xml.etree.ElementTree as ET

import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.util import AtomicString

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"
CONFIG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
E = lambda value: escape(str(value), quote=True)
ASSET_VERSIONS = {name: hashlib.sha256((ROOT / "public/assets" / name).read_bytes()).hexdigest()[:10]
                  for name in ("style.css", "site.js")}


def bilingual(zh, en):
    return f'<span data-zh="{E(zh)}" data-en="{E(en)}">{E(zh)}</span>'


class BareLink(InlineProcessor):
    def handleMatch(self, match, data):
        url = match.group(1).rstrip("。，；！、")
        node = ET.Element("a", {"href": url})
        node.text = AtomicString(url)
        return node, match.start(1), match.start(1) + len(url)


class LinkExtension(Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(BareLink(r"(?<![\w\"'=])(https?://[^\s<>]+)", md), "barelink", 75)


def read_content():
    records = []
    for file in sorted((ROOT / "src/content").glob("*.md")):
        text = file.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError(f"Missing metadata: {file}")
        header, body = text[4:].split("\n---\n", 1)
        record = json.loads(header)
        if record.get("type") not in ("post", "page"):
            raise ValueError(f"Unsupported public content type: {file}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", record["slug"]):
            raise ValueError(f"Use an English slug with letters, numbers or hyphens: {file}")
        if any(c not in CONFIG["categories"] for c in record["categories"]):
            raise ValueError(f"Category missing from site.json: {file}")
        datetime.fromisoformat(record["date"])
        datetime.fromisoformat(record["updated"])
        record["body"] = body.strip()
        record["url"] = "/about/" if record["type"] == "page" else f"/posts/{quote(record['slug'], safe='-')}/"
        record["date_short"] = record["date"][:10]
        # Structural formatting only: preserve the source Markdown on disk.
        body = re.sub(r"^={3,}\s*$", "\n---\n", body, flags=re.M)
        original_body = body
        body = re.sub(r"^(第[一二三四五六七八九十]+部分[、，].+)$",
            lambda m: m[0] if original_body.count(m[0]) > 1 and m.start() == original_body.find(m[0])
            else "## " + m[0], body, flags=re.M)
        body = re.sub(r"^(第\s*\d+\s*章[：:、].+)$", r"### \1", body, flags=re.M)
        md = markdown.Markdown(extensions=["extra", "sane_lists", "nl2br", "toc", LinkExtension()],
                               extension_configs={"toc": {"permalink": False}})
        record["html"] = md.convert(body)
        record["html"] = re.sub(r'<img\b[^>]*>', lambda m: '<a class="image-link" href="'
            + re.search(r'src="([^"]+)"', m[0])[1] + '" target="_blank" rel="noopener" title="查看原图（新窗口）">'
            + m[0] + '</a><span class="figure-hint">点击图片查看原图 ↗</span>', record["html"])
        record["toc"] = md.toc if md.toc_tokens else ""
        text_html = re.sub(r'<span class="figure-hint">.*?</span>', '', record["html"])
        plain = unescape(re.sub(r"<[^>]+>", " ", text_html))
        plain = re.sub(r"\s+", " ", plain).strip()
        record["plain"] = plain
        record["excerpt"] = plain[:112].rstrip() + ("…" if len(plain) > 112 else "")
        if not plain:
            record["excerpt"] = "一张随时翻阅的日文罗马字输入速查表。" if record["id"] == 33 else "打开文章，查看完整内容。"
        record["minutes"] = max(1, round(len(plain) / 420))
        records.append(record)
    if len({r["id"] for r in records}) != len(records) or len({r["url"] for r in records}) != len(records):
        raise ValueError("Article IDs and URLs must be unique")
    return sorted(records, key=lambda r: r["date"], reverse=True)


def write(path: str, text: str):
    file = OUT / path.lstrip("/")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def shell(title, content, path="/", description=None, current="", article=None, description_en=None, title_en=None):
    description = description or CONFIG["subtitle"]
    canonical = CONFIG["url"] + path
    full_title = "Tao · ingenieur" if path == "/" else title if title == CONFIG["title"] else title + " · " + CONFIG["title"]
    links = [("/", "首页", "home"), ("/blog/", "博客", "posts"), ("/about/", "关于", "about")]
    home = path in ("/", "/about/")
    description_en = description_en or description
    title_attrs = f'data-zh="{E(full_title)}" data-en="{E(title_en or full_title)}"' if home else ''
    description_attrs = f'data-zh-content="{E(description)}" data-en-content="{E(description_en)}"' if home else ''
    labels_en = {"home": "Home", "posts": "Blog", "about": "About"}
    nav = "".join(f'<a href="{url}" {"aria-current=page" if current == key else ""}>{bilingual(label, labels_en[key]) if home else label}</a>'
                  for url, label, key in links)
    project_label = bilingual("项目", "Projects") if home else "项目"
    skip_label = bilingual("跳到正文", "Skip to content") if home else "跳到正文"
    footer_quote = bilingual("古今多少事，都付笑谈中。", "Stories of past and present, shared with a smile.") if home else "古今多少事，都付笑谈中。"
    rss_label = bilingual("RSS 订阅", "RSS feed") if home else "RSS 订阅"
    language_switch = '<button class="language-toggle" id="language-toggle" type="button" aria-label="Switch to English" aria-pressed="false" hidden>EN</button>' if home else ''
    structured = {"@context": "https://schema.org", "@type": "Blog", "name": CONFIG["title"], "url": CONFIG["url"]}
    if path == "/":
        structured = {"@context": "https://schema.org", "@type": "Person", "name": CONFIG["profile"]["name"],
                      "alternateName": CONFIG["profile"]["nickname"], "url": CONFIG["url"],
                      "description": CONFIG["profile"]["tagline"], "sameAs": [CONFIG["github"]]}
    if article:
        structured = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": article["title"],
                      "datePublished": article["date"], "dateModified": article["updated"], "url": canonical,
                      "author": {"@type": "Person", "name": CONFIG["author"], "url": CONFIG["github"]}}
    json_ld = json.dumps(structured, ensure_ascii=False).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title {title_attrs}>{E(full_title)}</title><meta name="description" content="{E(description)}" {description_attrs}>
<meta name="theme-color" content="#f7f7f2"><link rel="canonical" href="{E(canonical)}">
<meta property="og:type" content="{'article' if article else 'website'}"><meta property="og:title" content="{E(full_title)}">
<meta property="og:description" content="{E(description)}" {description_attrs}><meta property="og:url" content="{E(canonical)}">
<meta property="og:site_name" content="{E(CONFIG['title'])}"><meta property="og:locale" content="zh_CN">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="alternate" type="application/rss+xml" title="{E(CONFIG['title'])}" href="/feed.xml">
<link rel="stylesheet" href="/assets/style.css?v={ASSET_VERSIONS['style.css']}"><script src="/assets/site.js?v={ASSET_VERSIONS['site.js']}" defer></script>
<script type="application/ld+json">{json_ld}</script></head><body>
<a class="skip" href="#main">{skip_label}</a><div class="reading-progress" aria-hidden="true"></div>
<header class="site-header wrap"><a class="brand" href="/" aria-label="Tao · ingenieur 首页"><span class="brand-mark">i<span>·</span></span><span>Tao<span class="brand-suffix personal-alias"> / ingenieur</span></span></a>
<nav aria-label="主导航">{nav}<a class="github-link" href="{E(CONFIG['github'])}?tab=repositories">{project_label} <span aria-hidden="true">↗</span></a>{language_switch}</nav></header>
<main id="main">{content}</main>
<footer class="site-footer wrap"><div><a class="footer-brand" href="/">Tao <span class="footer-alias">/ ingenieur</span></a><p>{footer_quote}</p></div>
<div class="footer-right"><a href="/feed.xml">{rss_label} <span aria-hidden="true">↗</span></a><span>© {datetime.now().year} ingenieur</span></div></footer>
</body></html>'''


def category_link(name):
    return "/categories/" + CONFIG["categories"][name] + "/"


def post_row(post, index=0):
    category = post["categories"][0] if post["categories"] else "随笔"
    tag = re.match(r"\[([^]]+)\]\s*(.*)", post["title"])
    series, title = (tag[1], tag[2]) if tag else ("", post["title"])
    label = f'<span class="series">{E(series)}</span>' if series and not re.search(r"\d年", series) else ""
    return f'''<article class="post-row" data-post-id="{post['id']}" data-category="{E(category)}">
<div class="post-date"><time datetime="{E(post['date'])}">{post['date_short'].replace('-', '.')}</time><span>{post['minutes']} 分钟阅读</span></div>
<div class="post-info"><div class="post-labels"><a class="category-label" href="{category_link(category)}">{E(category)}</a>{label}</div>
<h2><a href="{E(post['url'])}">{E(title)}</a></h2><p>{E(post['excerpt'])}</p></div>
<a class="post-arrow" href="{E(post['url'])}" aria-label="阅读：{E(post['title'])}">↗</a></article>'''


def home_page(posts):
    profile = CONFIG["profile"]
    rows = "".join(post_row(post) for post in posts[:3])
    return shell("Tao · ingenieur", f'''
<section class="hero personal-hero wrap"><div class="hero-copy"><p class="eyebrow"><span class="small-line"></span> ENGINEER & EVERYDAY EXPLORER</p>
<h1>{bilingual('你好，我是', "Hi, I’m")} <span class="profile-name">{E(profile['name'])}</span><span class="name-dot">.</span></h1>
<p class="profile-handle">@{E(profile['nickname'])}</p><p class="profile-tagline">{bilingual(profile['tagline'], profile['tagline_en'])}</p>
<div class="profile-links"><a class="primary-link" href="/blog/">{bilingual('我的博客', 'My blog')} <span aria-hidden="true">↗</span></a><a class="secondary-link" href="{E(CONFIG['github'])}?tab=repositories">{bilingual('我的项目', 'My projects')} <span aria-hidden="true">↗</span></a></div></div>
<figure class="hero-photo personal-photo"><img src="/usr/uploads/2026/04/939619945.jpg" alt="三亚海湾的天空、海水与沿岸建筑" data-zh-alt="三亚海湾的天空、海水与沿岸建筑" data-en-alt="Blue skies, the bay and waterfront buildings in Sanya" width="667" height="575" fetchpriority="high"><figcaption>{bilingual('三亚 · 一隅风景', 'A moment by the sea')}<span>SANYA, CHINA</span></figcaption></figure></section>
<section class="journal recent-journal wrap" id="journal"><div class="section-top"><div><p class="eyebrow">RECENT WRITING</p><h2>{bilingual('最近的文字', 'Recent writing')}</h2></div><a class="archive-link" href="/blog/">{bilingual('全部博客', 'All posts')} <span aria-hidden="true">↗</span></a></div>
<div class="post-list" lang="zh-CN">{rows}</div><p class="recent-closing">{bilingual('读过的书，走过的路，偶然的思考。', 'Books, journeys, and thoughts along the way.')}</p></section>''', current="home", description=profile["tagline"], description_en=profile["tagline_en"])


def blog_page(posts):
    chips = '<button type="button" class="filter active" data-filter="all" aria-pressed="true">全部 <span>' + str(len(posts)) + '</span></button>'
    for name in CONFIG["categories"]:
        count = sum(name in p["categories"] for p in posts)
        chips += f'<button type="button" class="filter" data-filter="{E(name)}" aria-pressed="false">{E(name)} <span>{count}</span></button>'
    rows = "".join(post_row(p, i) for i, p in enumerate(posts))
    return shell(CONFIG["title"], f'''
<section class="blog-intro wrap"><p class="eyebrow">NOTES, IDEAS & EVERYDAY LIFE</p><h1>Ingenieur's Blog<span class="green-dot">.</span></h1><p>古今多少事，都付笑谈中。</p></section>
<section id="journal" class="journal wrap"><div class="section-top"><div><p class="eyebrow">THE JOURNAL</p><h2>全部文章<span class="article-total">{len(posts):02d}</span></h2></div><a class="archive-link" href="/archives/">按时间翻阅 <span aria-hidden="true">↗</span></a></div>
<div class="journal-tools"><div class="filters" role="group" aria-label="按分类筛选">{chips}</div><form class="search" role="search"><label for="search-input" class="sr-only">搜索文章</label><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 5 5"/></svg><input id="search-input" type="search" placeholder="寻找一段文字…" autocomplete="off"><kbd aria-hidden="true">/</kbd></form></div>
<p class="search-status sr-only" role="status" aria-live="polite"></p><div class="post-list">{rows}</div><div class="empty-state" hidden><span>没有找到这段文字</span><p>试试另一个关键词，或切换到全部分类。</p><button type="button" id="reset-search">查看全部文章</button></div>
<div class="journal-end"><span></span><p>慢慢记录，常常回望。</p><span></span></div><noscript><p>分类浏览：{' · '.join(f'<a href="{category_link(n)}">{n}</a>' for n in CONFIG['categories'])}。搜索需要启用 JavaScript。</p></noscript></section>''', path="/blog/", current="posts")


def listing(title, subtitle, posts, path):
    rows = "".join(post_row(p) for p in posts)
    return shell(title, f'<section class="wrap inner-page"><a class="back-link" href="/blog/">← 全部文章</a><p class="eyebrow">COLLECTION</p><h1>{E(title)}<span class="article-total">{len(posts):02d}</span></h1><p class="page-intro">{E(subtitle)}</p><div class="post-list">{rows}</div></section>', path=path, current="posts")


def article_page(post, posts):
    category = " · ".join(post["categories"])
    category_html = "".join(f'<a class="category-label" href="{category_link(n)}">{E(n)}</a>' for n in post["categories"])
    toc = f'<aside class="article-toc"><p>本篇目录</p>{post["toc"]}</aside>' if post["toc"] else ""
    mobile_toc = f'<details class="mobile-toc"><summary>本篇目录</summary>{post["toc"]}</details>' if post["toc"] else ""
    position = posts.index(post)
    neighbours = []
    for offset, label in [(1, "上一篇"), (-1, "下一篇")]:
        i = position + offset
        if 0 <= i < len(posts):
            p = posts[i]
            neighbours.append(f'<a href="{E(p["url"])}"><span>{label}</span><strong>{E(p["title"])}</strong><span aria-hidden="true">↗</span></a>')
    content = f'''<div class="wrap article-wrap"><a class="back-link" href="/blog/#journal">← 返回文章列表</a><header class="article-header"><div class="post-labels">{category_html}</div><h1>{E(post['title'])}</h1><p class="article-meta"><span>ingenieur</span><span>·</span><time datetime="{E(post['date'])}">{post['date_short']}</time><span>·</span><span>{post['minutes']} 分钟阅读</span></p></header>
{mobile_toc}<div class="article-layout"><article class="prose" data-article>{post['html']}</article>{toc}</div>
<div class="article-tail"><span>写于 {post['date_short']}</span><a href="#main">回到顶部 ↑</a></div><nav class="post-neighbours" aria-label="相邻文章">{''.join(neighbours)}</nav></div>'''
    return shell(post["title"], content, path=post["url"], description=post["excerpt"], current="posts", article=post)


def archive_page(posts):
    groups = defaultdict(list)
    for p in posts:
        groups[p["date"][:7]].append(p)
    sections = ""
    for month, items in groups.items():
        rows = "".join(f'<li><time datetime="{E(p["date"])}">{p["date_short"][5:].replace("-", ".")}</time><a href="{E(p["url"])}">{E(p["title"])}</a><span aria-hidden="true">↗</span></li>' for p in items)
        sections += f'<section class="archive-month"><h2>{month[:4]}<span>{int(month[5:])} 月</span></h2><ul>{rows}</ul></section>'
    return shell("文章归档", f'<section class="wrap inner-page archive-page"><p class="eyebrow">THROUGH THE YEARS</p><h1>时间里的文字</h1><p class="page-intro">共 {len(posts)} 篇记录，按时间慢慢翻阅。</p>{sections}</section>', path="/archives/", current="posts")


def build():
    if OUT.exists():
        # Only remove the fixed generated output inside this checkout.
        assert OUT.resolve() == ROOT.resolve() / "dist"
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "public", OUT, dirs_exist_ok=True)
    records = read_content()
    posts = [r for r in records if r["type"] == "post"]
    pages = [r for r in records if r["type"] == "page"]
    write("index.html", home_page(posts))
    write("blog/index.html", blog_page(posts))
    write("archives/index.html", archive_page(posts))
    for name in CONFIG["categories"]:
        subset = [p for p in posts if name in p["categories"]]
        write(category_link(name) + "index.html", listing(name, f"关于{name}的 {len(subset)} 篇记录。", subset, category_link(name)))
    for p in posts:
        write(p["url"] + "index.html", article_page(p, posts))
    about = next((p for p in pages if p["slug"] == "start-page"), None)
    about_zh = about["plain"] if about else ""
    about_en = about.get("body_en", about_zh) if about else ""
    about_display_zh = about["body"] if about else ""
    about_body = f'<p>{bilingual(about_display_zh, about_en)}</p>'
    about_quote = bilingual(about.get("quote", ""), about.get("quote_en", "")) if about else ""
    write("about/index.html", shell("关于 Tao", f'''<section class="wrap inner-page about-page"><p class="eyebrow">A LITTLE ABOUT ME</p><h1>Tao<span class="green-dot">.</span><span class="about-handle">@ingenieur</span></h1><div class="about-grid"><div><div class="about-original prose">{about_body}</div><p class="about-quote">{about_quote}</p><a class="text-link" href="{E(CONFIG['github'])}?tab=repositories">{bilingual('我的项目', 'My projects')} ↗</a></div><figure><img src="/usr/uploads/2026/04/928419732.jpg" alt="2024 年 5 月 11 日墨尔本上空的极光" data-zh-alt="2024 年 5 月 11 日墨尔本上空的极光" data-en-alt="Aurora over Melbourne on May 11, 2024" width="900" height="600" loading="lazy"><figcaption>{bilingual('墨尔本上空的极光 · 2024.05.11', 'Aurora over Melbourne · 2024.05.11')}</figcaption></figure></div><div class="about-bottom"><a href="/blog/">{bilingual('翻阅博客', 'Read the blog')} →</a><a href="/feed.xml">{bilingual('通过 RSS 订阅', 'Subscribe via RSS')} →</a></div></section>''', path="/about/", current="about", description=about_zh, description_en=about_en, title_en="About Tao · Ingenieur's Blog"))
    search = [{k: p[k] for k in ("id", "title", "url", "plain", "categories")} for p in posts]
    write("search.json", json.dumps(search, ensure_ascii=False))
    redirects = json.loads((ROOT / "src/redirects.json").read_text(encoding="utf-8"))
    for old, new in redirects.items():
        target = old + "index.html" if old.endswith("/") else old
        write(target, f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>页面已迁移</title><link rel="canonical" href="{E(CONFIG["url"] + new)}"><meta http-equiv="refresh" content="0;url={E(new)}"><p>文章已迁移到<a href="{E(new)}">新地址</a>。</p></html>')
    write("redirects.json", json.dumps(redirects, ensure_ascii=False))
    write("404.html", shell("页面未找到", '<section class="wrap inner-page not-found"><p class="eyebrow">404 / LOST BETWEEN THE LINES</p><h1>这一页，暂时走远了。</h1><p class="page-intro">可以返回首页，寻找另一段文字。</p><a class="text-link" href="/">返回首页 →</a></section><script src="/assets/redirect.js" defer></script>', path="/404.html"))
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for key, value in [("title", CONFIG["title"]), ("link", CONFIG["url"]), ("description", CONFIG["subtitle"]), ("language", "zh-CN")]:
        ET.SubElement(channel, key).text = value
    for p in posts:
        item = ET.SubElement(channel, "item")
        absolute_html = re.sub(r'(href|src)="/(?!/)', lambda m: m[1] + '="' + CONFIG["url"] + '/', p["html"])
        for key, value in [("title", p["title"]), ("link", CONFIG["url"] + p["url"]), ("guid", CONFIG["url"] + p["url"]), ("pubDate", format_datetime(datetime.fromisoformat(p["date"]))), ("description", absolute_html)]:
            ET.SubElement(item, key).text = value
        for name in p["categories"]:
            ET.SubElement(item, "category").text = name
    write("feed.xml", ET.tostring(rss, encoding="unicode", xml_declaration=True))
    sitemap = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    paths = ["/", "/blog/", "/about/", "/archives/"] + [category_link(c) for c in CONFIG["categories"]] + [p["url"] for p in posts]
    for path in paths:
        node = ET.SubElement(sitemap, "url")
        ET.SubElement(node, "loc").text = CONFIG["url"] + path
    write("sitemap.xml", ET.tostring(sitemap, encoding="unicode", xml_declaration=True))
    write("robots.txt", "User-agent: *\nAllow: /\nSitemap: " + CONFIG["url"] + "/sitemap.xml\n")
    write(".nojekyll", "")
    print(f"Built {len(posts)} posts, {len(pages)} page, {len(CONFIG['categories'])} categories, RSS and search into {OUT}")


if __name__ == "__main__":
    build()

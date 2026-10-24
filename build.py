#!/usr/bin/env python3
"""Static site generator for Democracy Today.

Reads Markdown content with YAML front matter from content/, data from data/,
renders Jinja2 templates from templates/ and writes the site to public/.
The build fails if any article breaks the editorial rules enforced in
validate_article(): byline, real date, section, labeled type, sourced news,
credited and described images.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
OUT = ROOT / "public"
ET = dt.timezone(dt.timedelta(hours=-5))  # display fallback only; dates keep their own offset

ARTICLE_TYPES = {"news": "News", "analysis": "Analysis", "opinion": "Opinion",
                 "editorial": "Editorial", "essay": "Essay", "interview": "Conversation",
                 "review": "Review"}
OPINION_TYPES = {"opinion", "editorial", "essay", "review"}
MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def split_front_matter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def as_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        d = value
    elif isinstance(value, dt.date):
        d = dt.datetime(value.year, value.month, value.day, 12, 0)
    else:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    return d


def ap_date(d):
    d = as_datetime(d)
    if not d:
        return ""
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def long_date(d):
    d = as_datetime(d)
    return f"{d.strftime('%A')}, {FULL_MONTHS[d.month - 1]} {d.day}, {d.year}" if d else ""


def ap_time(d):
    d = as_datetime(d)
    if not d:
        return ""
    h = d.hour % 12 or 12
    suffix = "a.m." if d.hour < 12 else "p.m."
    tz = {-4: "ET", -5: "ET", -6: "CT", -7: "MT", -8: "PT"}.get(int(d.utcoffset().total_seconds() // 3600), "")
    return f"{h}:{d.minute:02d} {suffix} {tz}".strip()


MD = markdown.Markdown(extensions=["extra", "sane_lists", "smarty"], output_format="html5")


def render_md(text: str) -> str:
    MD.reset()
    out = MD.convert(text or "")
    # external links open in the same tab but are marked for assistive tech and safety
    out = re.sub(r'<a href="(https?://(?!democracytoday\.news)[^"]+)"',
                 r'<a href="\1" rel="noopener"', out)
    return out


def plain(text: str, limit: int = 180) -> str:
    t = re.sub(r"<[^>]+>", "", text or "")
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def validate_article(a: dict, sections: dict, errors: list):
    where = a["source_file"]
    for field in ("title", "byline", "date", "section", "type"):
        if not a.get(field):
            errors.append(f"{where}: missing required field '{field}'")
    if a.get("section") and a["section"] not in sections:
        errors.append(f"{where}: unknown section '{a['section']}'")
    for s in a.get("also") or []:
        if s not in sections:
            errors.append(f"{where}: unknown secondary section '{s}'")
    if a.get("type") and a["type"] not in ARTICLE_TYPES:
        errors.append(f"{where}: type must be one of {sorted(ARTICLE_TYPES)}")
    if a.get("type") in {"news", "analysis"}:
        srcs = a.get("sources") or []
        if not srcs:
            errors.append(f"{where}: news stories must list at least one source")
        for s in srcs:
            if not (s.get("title") and s.get("url")):
                errors.append(f"{where}: every source needs a title and a url")
    if a.get("image") and not (a.get("image_alt") and a.get("image_credit")):
        errors.append(f"{where}: images need alt text and a credit")
    d = a.get("date_dt")
    if d and d > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1):
        errors.append(f"{where}: date is in the future")


def load_articles(sections: dict, errors: list):
    items = []
    for path in sorted((CONTENT / "articles").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        if meta.get("draft"):
            continue
        a = dict(meta)
        a["source_file"] = str(path.relative_to(ROOT))
        a["date_dt"] = as_datetime(meta.get("date"))
        a["updated_dt"] = as_datetime(meta.get("updated"))
        stem = path.stem
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$", stem)
        slug = meta.get("slug") or (m.group(4) if m else stem)
        d = a["date_dt"] or dt.datetime.now(ET)
        a["slug"] = slug
        a["url"] = f"/{d.year:04d}/{d.month:02d}/{d.day:02d}/{slug}/"
        a["html"] = render_md(body)
        a["excerpt"] = a.get("dek") or plain(a["html"])
        a["type_label"] = ARTICLE_TYPES.get(a.get("type"), "")
        a["is_opinion"] = a.get("type") in OPINION_TYPES
        a["all_sections"] = [a.get("section")] + list(a.get("also") or [])
        a["sources"] = a.get("sources") or []
        a["corrections"] = a.get("corrections") or []
        validate_article(a, sections, errors)
        items.append(a)
    weight = {"lead": 2, "top": 1}
    items.sort(key=lambda x: (x["date_dt"] or dt.datetime.min.replace(tzinfo=ET),
                              weight.get(x.get("placement"), 0)), reverse=True)
    return items


def load_pages():
    pages = []
    for path in sorted((CONTENT / "pages").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        p = dict(meta)
        p["slug"] = meta.get("slug") or path.stem
        p["url"] = f"/{p['slug']}/"
        p["html"] = render_md(body)
        pages.append(p)
    return pages


def write(path: str, content: str):
    target = OUT / path.lstrip("/")
    if path.endswith("/"):
        target = target / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def build_home(articles):
    news = [a for a in articles if not a["is_opinion"]]
    lead = next((a for a in news if a.get("placement") == "lead"), news[0] if news else None)
    rest = [a for a in news if a is not lead]
    opinion = [a for a in articles if a.get("type") in {"opinion", "editorial"}][:4]
    magazine = [a for a in articles if a.get("type") in {"essay", "interview", "review"}
                or a.get("placement") == "magazine"]
    used = {id(lead)} | {id(a) for a in rest[:4]} | {id(a) for a in opinion} | {id(a) for a in magazine[:1]}
    more = [a for a in articles if id(a) not in used][:8]
    return {"lead": lead, "side": rest[:4], "opinion": opinion,
            "magazine": magazine[:1], "magazine_more": magazine[1:5], "more": more}


def main():
    errors: list[str] = []
    site = load_yaml(ROOT / "data" / "site.yml")
    elections = load_yaml(ROOT / "data" / "elections.yml")
    sections = {s["slug"]: s for s in site["sections"]}
    articles = load_articles(sections, errors)
    pages = load_pages()
    if errors:
        print("Build failed — editorial rules not met:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    for a in articles:
        a["section_name"] = sections[a["section"]]["name"]

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(ap_date=ap_date, ap_time=ap_time, long_date=long_date,
                       iso=lambda d: as_datetime(d).isoformat() if as_datetime(d) else "",
                       plain=plain)
    build_time = dt.datetime.now(dt.timezone.utc)
    common = {"site": site, "sections": site["sections"], "elections": elections,
              "build_time": build_time,
              "election_dt": as_datetime(site["election"]["date"])}

    def render(tpl, path, **ctx):
        write(path, env.get_template(tpl).render(**common, **ctx, path=path))

    render("home.html", "/", home=build_home(articles), articles=articles)

    for a in articles:
        related = [b for b in articles if b is not a and a["section"] in b["all_sections"]][:3]
        render("article.html", a["url"], a=a, related=related)

    for slug, s in sections.items():
        items = [a for a in articles if slug in a["all_sections"]]
        tpl = "elections.html" if slug == "elections" else "section.html"
        render(tpl, f"/{slug}/", section=s, items=items)

    for p in pages:
        render("page.html", p["url"], page=p)

    render("simple.html", "/store/", key="store")
    render("simple.html", "/live/", key="live")
    render("newsletter.html", "/newsletter/", thanks=False)
    render("newsletter.html", "/newsletter/thanks/", thanks=True)
    render("404.html", "/404.html")

    # sitemap (with lastmod and images)
    def iso_utc(d):
        return as_datetime(d).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    def newest(items):
        ds = [a.get("updated_dt") or a["date_dt"] for a in items if a.get("date_dt")]
        return max(ds) if ds else None
    entries = [("/", newest(articles), None)]
    for slug in sections:
        entries.append((f"/{slug}/", newest([a for a in articles if slug in a["all_sections"]]), None))
    for a in articles:
        entries.append((a["url"], a.get("updated_dt") or a["date_dt"], a.get("image")))
    for u in [p["url"] for p in pages] + ["/store/", "/live/", "/newsletter/"]:
        entries.append((u, None, None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for u, lm, img in entries:
        line = f"  <url><loc>{site['url']}{u}</loc>"
        if lm:
            line += f"<lastmod>{iso_utc(lm)}</lastmod>"
        if img:
            line += f"<image:image><image:loc>{site['url']}{img}</image:loc></image:image>"
        sm.append(line + "</url>")
    sm.append("</urlset>")
    write("/sitemap.xml", "\n".join(sm) + "\n")

    # Google News sitemap: articles published in the last 48 hours
    cutoff = build_time - dt.timedelta(hours=48)
    recent = [a for a in articles if a["date_dt"] and a["date_dt"] >= cutoff]
    nm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">']
    for a in recent[:1000]:
        nm.append(f"  <url><loc>{site['url']}{a['url']}</loc><news:news><news:publication>"
                  f"<news:name>{html.escape(site['title'])}</news:name><news:language>en</news:language>"
                  f"</news:publication><news:publication_date>{as_datetime(a['date']).isoformat()}"
                  f"</news:publication_date><news:title>{html.escape(a['title'])}</news:title></news:news></url>")
    nm.append("</urlset>")
    write("/news-sitemap.xml", "\n".join(nm) + "\n")

    # RSS
    items = []
    for a in articles[:30]:
        items.append(
            "<item><title>{t}</title><link>{l}</link><guid>{l}</guid><pubDate>{d}</pubDate>"
            "<dc:creator>{b}</dc:creator><category>{c}</category><description>{x}</description></item>".format(
                t=html.escape(a["title"]), l=site["url"] + a["url"], d=format_datetime(a["date_dt"]),
                b=html.escape(a["byline"]), c=html.escape(a["section_name"]), x=html.escape(a["excerpt"])))
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
           f"<title>{site['title']}</title><link>{site['url']}/</link>"
           f"<description>{html.escape(site['description'])}</description><language>en-us</language>"
           + "".join(items) + "</channel></rss>\n")
    write("/feed.xml", rss)
    write("/robots.txt", f"User-agent: *\nDisallow: /admin/\n\nSitemap: {site['url']}/sitemap.xml\n"
                        f"Sitemap: {site['url']}/news-sitemap.xml\n")
    print(f"Built {len(articles)} articles, {len(pages)} pages, {len(sections)} sections -> {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Notify IndexNow (Bing, Yandex, others) of new or updated URLs after a deploy.
usage: python indexnow.py            -> submits every URL in public/sitemap.xml
       python indexnow.py URL [URL]  -> submits the given URLs
"""
import json, re, sys, urllib.request, pathlib, yaml
ROOT = pathlib.Path(__file__).parent
site = yaml.safe_load((ROOT / "data" / "site.yml").read_text())
key = site["seo"]["indexnow_key"]
urls = sys.argv[1:] or re.findall(r"<loc>([^<]+)</loc>", (ROOT / "public" / "sitemap.xml").read_text())
body = json.dumps({"host": "democracytoday.news", "key": key,
                   "keyLocation": f"{site['url']}/{key}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=30) as r:
    print("IndexNow", r.status, len(urls), "URLs")

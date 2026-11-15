"""Check the built site's content, internal navigation, images and feeds."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlsplit, unquote
import xml.etree.ElementTree as ET

from build import CONFIG, OUT, ROOT, read_content


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.images = []
        self.h1s = 0
        self.post_ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-post-id" in attrs:
            self.post_ids.append(int(attrs["data-post-id"]))
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "h1":
            self.h1s += 1
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag in ("img", "script", "link"):
            url = attrs.get("src") if tag != "link" else attrs.get("href")
            if url:
                self.links.append(url)
        if tag == "img":
            assert attrs.get("alt"), "Image missing alt text"
            self.images.append(attrs["src"])


def verify():
    assert (OUT / "index.html").is_file(), "Build the site first"
    errors = []
    parsed = {}
    for file in OUT.rglob("*.html"):
        parser = Links()
        parser.feed(file.read_text(encoding="utf-8"))
        parsed[file] = parser
    count = 0
    for file, page in parsed.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                if url.netloc != urlsplit(CONFIG["url"]).netloc:
                    continue
            if not url.path:
                target = file
            else:
                target = OUT / unquote(url.path).lstrip("/") if url.path.startswith("/") else file.parent / unquote(url.path)
            if target.is_dir():
                target /= "index.html"
            count += 1
            if not target.is_file():
                errors.append(f"Missing target: {file.relative_to(OUT)} -> {link}")
            elif url.fragment and target in parsed and unquote(url.fragment) not in parsed[target].ids:
                errors.append(f"Missing anchor: {file.relative_to(OUT)} -> {link}")
    records = read_content()
    posts = [r for r in records if r["type"] == "post"]
    search = json.loads((OUT / "search.json").read_text(encoding="utf-8"))
    assert {r["id"] for r in search} == {r["id"] for r in posts}
    assert len(ET.parse(OUT / "feed.xml").findall("channel/item")) == len(posts)
    assert len(ET.parse(OUT / "sitemap.xml").getroot()) == len(posts) + len(CONFIG["categories"]) + 4
    assert parsed[OUT / "index.html"].post_ids == [p["id"] for p in posts[:3]], "Home must show exactly the three latest posts"
    assert parsed[OUT / "blog/index.html"].post_ids == [p["id"] for p in posts], "Blog must retain all posts"
    assert parsed[OUT / "index.html"].h1s == 1
    for post in posts:
        target = OUT / unquote(post["url"]).lstrip("/") / "index.html"
        assert parsed[target].h1s == 1, f"Expected one article heading: {target}"
        assert "blog.huanyupark.com" not in post["html"], "Old server dependency in article"
    for file in OUT.rglob("*"):
        assert file.suffix.lower() not in (".dat", ".zip", ".py", ".md"), "Private/source file in build"
        assert "backups" not in file.relative_to(OUT).parts
    if errors:
        raise AssertionError("\n".join(errors))
    print(f"PASS: {len(posts)} posts, {len(parsed)} HTML pages, {count} internal references, images, search, RSS and sitemap.")


if __name__ == "__main__":
    verify()

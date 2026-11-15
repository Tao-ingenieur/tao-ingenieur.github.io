"""Convert a Typecho 0001 backup without executing imported content.

Only public, unprotected posts/pages are exported. Account and comment tables
stay in the ignored backup directory. Every record checksum is verified first.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"%TYPECHO_BACKUP_0001%"


def read_backup(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(MAGIC) or not data.endswith(MAGIC):
        raise ValueError("Not a complete Typecho 0001 backup")
    tables = defaultdict(list)
    pos = len(MAGIC)
    end = len(data) - len(MAGIC)
    while pos < end:
        start = pos
        kind, header_size, body_size = struct.unpack_from("<HHI", data, pos)
        pos += 8
        if pos + header_size + body_size + 32 > end:
            raise ValueError("Truncated backup record")
        schema = json.loads(data[pos:pos + header_size])
        pos += header_size
        body = data[pos:pos + body_size]
        pos += body_size
        if hashlib.md5(data[start:pos]).hexdigest().encode() != data[pos:pos + 32]:
            raise ValueError("Backup checksum mismatch")
        pos += 32
        row = {}
        offset = 0
        for field, size in schema.items():
            row[field] = None if size is None else body[offset:offset + size].decode("utf-8")
            offset += size or 0
        if offset != body_size:
            raise ValueError("Backup schema size mismatch")
        tables[kind].append(row)
    if pos != end:
        raise ValueError("Unexpected backup footer")
    return tables


def migrate(backup: Path, uploads: Path) -> None:
    tables = read_backup(backup)
    visible = [r for r in tables[1] if r.get("type") in ("post", "page")
               and r.get("status") == "publish" and not r.get("password")]
    attachments = [r for r in tables[1] if r.get("type") == "attachment"]
    taxonomy = {r["mid"]: r for r in tables[3]}
    relations = defaultdict(list)
    for r in tables[4]:
        if r["mid"] in taxonomy:
            relations[r["cid"]].append(taxonomy[r["mid"]])
    content_dir = ROOT / "src/content"
    content_dir.mkdir(parents=True, exist_ok=True)
    source_files = {}
    if uploads.is_file():
        with zipfile.ZipFile(uploads) as archive:
            for item in archive.infolist():
                if not item.is_dir() and not item.filename.startswith("__MACOSX/"):
                    source_files[item.filename] = archive.read(item)
    elif uploads.is_dir():
        source_files = {p.relative_to(uploads).as_posix(): p.read_bytes()
                        for p in uploads.rglob("*") if p.is_file()}
    else:
        raise ValueError("Uploads ZIP or directory not found")
    mapping = []
    for row in attachments:
        meta = json.loads(row["text"])
        matches = [(name, data) for name, data in source_files.items()
                   if name.lower().endswith(meta["path"].lower().lstrip("/"))]
        if not matches:
            matches = [(name, data) for name, data in source_files.items()
                       if Path(name).name.lower() == meta["name"].lower()]
        if not matches:
            matches = [(name, data) for name, data in source_files.items()
                       if len(data) == int(meta["size"])]
        if len(matches) != 1 or len(matches[0][1]) != int(meta["size"]):
            raise ValueError(f"Cannot uniquely match attachment: {meta['name']}")
        relative = Path(meta["path"].lstrip("/"))
        target = (ROOT / "public" / relative).resolve()
        if not target.is_relative_to((ROOT / "public").resolve()):
            raise ValueError("Unsafe attachment path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(matches[0][1])
        mapping.append({"source": matches[0][0], "path": "/" + relative.as_posix(),
                        "sha256": hashlib.sha256(matches[0][1]).hexdigest()})
    url_map = {}
    for row in visible:
        url = "/about/" if row["type"] == "page" else f"/posts/{row['slug']}/"
        for key in (row["cid"], row["slug"]):
            url_map[f"/archives/{key}/"] = url
            url_map[f"/index.php/archives/{key}/"] = url
        if row["type"] == "page":
            url_map[f"/{row['slug']}.html"] = url
            url_map[f"/index.php/{row['slug']}.html"] = url
    tz = timezone(timedelta(hours=8))
    for row in visible:
        body = (row.get("text") or "").removeprefix("<!--markdown-->")
        body = body.replace("\r\r\n", "\n\n").replace("\r\n", "\n").replace("\r", "\n")
        for old, new in sorted(url_map.items(), key=lambda x: -len(x[0])):
            for host in ("https://blog.huanyupark.com", "http://blog.huanyupark.com"):
                body = body.replace(host + old, new)
        body = re.sub(r"https?://blog\.huanyupark\.com(?=/usr/uploads/)", "", body)
        categories = [r["name"] for r in relations[row["cid"]] if r["type"] == "category"]
        tags = [r["name"] for r in relations[row["cid"]] if r["type"] == "tag"]
        meta = {"id": int(row["cid"]), "title": row["title"], "slug": row["slug"],
                "date": datetime.fromtimestamp(int(row["created"]), tz).isoformat(),
                "updated": datetime.fromtimestamp(int(row["modified"]), tz).isoformat(),
                "type": row["type"], "categories": categories, "tags": tags}
        target = content_dir / f"{row['cid']}.md"
        if target.exists():
            raise ValueError(f"Refusing to overwrite edited content: {target}")
        target.write_text("---\n" + json.dumps(meta, ensure_ascii=False, indent=2)
                          + "\n---\n\n" + body.strip() + "\n", encoding="utf-8")
    (ROOT / "src").mkdir(exist_ok=True)
    (ROOT / "src/redirects.json").write_text(json.dumps(url_map, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"posts": sum(r["type"] == "post" for r in visible),
              "pages": sum(r["type"] == "page" for r in visible),
              "images": mapping, "excluded_nonpublic": sum(r.get("type") in ("post", "page")
                  and r not in visible for r in tables[1]),
              "comments_kept_in_backup_only": len(tables[2]), "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest()}
    (ROOT / ".local").mkdir(exist_ok=True)
    (ROOT / ".local/migration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Migrated {report['posts']} posts, {report['pages']} page, {len(mapping)} images; all backup checksums valid.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("uploads", type=Path)
    args = parser.parse_args()
    migrate(args.backup, args.uploads)

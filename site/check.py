"""Check the site's local assets, anchors, catalog and size: uv run python site/check.py."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from pixdial.designs import BUILTIN

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
BASE = "https://yordilorenzo.github.io/pixdial/"


class Page(HTMLParser):
    def __init__(self, source: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.errors: list[str] = []
        self.headings = 0
        self.feed(source.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if element_id := fields.get("id"):
            if element_id in self.ids:
                self.errors.append(f"duplicate id: {element_id}")
            self.ids.add(element_id)
        if tag == "h1":
            self.headings += 1
        for key in ("href", "src"):
            if value := fields.get(key):
                self.links.append(value)
        if srcset := fields.get("srcset"):
            self.links.extend(entry.strip().split()[0] for entry in srcset.split(","))
        if tag == "img":
            for key in ("alt", "width", "height"):
                if key not in fields:
                    self.errors.append(f"image missing {key}: {fields.get('src')}")


def markdown_ids(source: Path) -> set[str]:
    headings = re.findall(r"^#{1,6} (.+)$", source.read_text(encoding="utf-8"), re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


def target(source: Path, link: str) -> tuple[Path, str] | None:
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc:
        if link.startswith(BASE):
            local = SITE / parsed.path.removeprefix("/pixdial/")
        elif parsed.netloc == "github.com" and parsed.path.startswith("/YordiLorenzo/pixdial"):
            suffix = parsed.path.removeprefix("/YordiLorenzo/pixdial").strip("/")
            if suffix.startswith(("blob/main/", "tree/main/")):
                local = ROOT / suffix.split("/", 2)[2]
            elif not suffix:
                local = ROOT / "README.md"
            else:
                return None
        else:
            return None
    elif parsed.path.startswith("/pixdial/"):
        local = SITE / parsed.path.removeprefix("/pixdial/")
    else:
        local = source.parent / parsed.path if parsed.path else source
    if local.is_dir() and (local / "index.html").exists():
        local /= "index.html"
    return local, unquote(parsed.fragment)


def main() -> None:
    pages = {p: Page(p) for p in SITE.glob("*.html")}
    errors: list[str] = []
    checked = 0
    for source, page in pages.items():
        errors.extend(f"{source.name}: {error}" for error in page.errors)
        if page.headings != 1:
            errors.append(f"{source.name}: expected one h1, got {page.headings}")
        for link in page.links:
            result = target(source, link)
            if result is None:
                continue
            local, fragment = result
            checked += 1
            if not local.exists():
                errors.append(f"{source.name}: missing {link}")
            elif fragment:
                ids = pages[local].ids if local in pages else markdown_ids(local) if local.suffix == ".md" else set()
                if fragment not in ids:
                    errors.append(f"{source.name}: missing anchor {link}")
    for css in SITE.glob("*.css"):
        for link in re.findall(r'url\(["\']?([^"\')]+)', css.read_text(encoding="utf-8")):
            if not (css.parent / link).is_file():
                errors.append(f"{css.name}: missing {link}")
            checked += 1

    catalog = json.loads((SITE / "designs.json").read_text(encoding="utf-8"))
    names = [entry["name"] for entry in catalog]
    if names != list(BUILTIN):
        errors.append("designs.json does not match the built-in catalog; run site/build.py")
    index = (SITE / "index.html").read_text(encoding="utf-8")
    for name in names:
        if f"<figcaption>{name}</figcaption>" not in index:
            errors.append(f"missing gallery design: {name}")
        for width in (400, 640, 960, 1280):
            if not (SITE / "images" / f"{name}-{width}.webp").is_file():
                errors.append(f"missing rotating preview: {name}-{width}.webp")
            checked += 1
    structured = re.search(r'<script type="application/ld\+json">(.*?)</script>', index, re.DOTALL)
    if structured is None:
        errors.append("missing SoftwareApplication JSON-LD")
    else:
        data = json.loads(structured.group(1))
        if data["@type"] != "SoftwareApplication" or data["url"] != BASE:
            errors.append("incorrect SoftwareApplication type or URL")
    sitemap = ElementTree.parse(SITE / "sitemap.xml")
    locations = [element.text for element in sitemap.findall(".//{*}loc")]
    if locations != [BASE]:
        errors.append("sitemap must contain only the canonical homepage")

    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    if size > 4_000_000:
        errors.append(f"site exceeds 4 MB: {size:,} bytes")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"OK: {len(pages)} HTML pages, {checked} local references, {len(names)} designs, JSON-LD and sitemap")
    print(f"Complete site: {size:,} bytes (including all responsive variants and build/check scripts)")


if __name__ == "__main__":
    main()

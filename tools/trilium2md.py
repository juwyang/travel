"""把 Trilium 导出的 HTML zip 转成本站的 Markdown + 图片。

用法（在仓库根目录）:
    python tools/trilium2md.py ../旅行日记.zip

- 每个顶层笔记 -> <slug>/index.md，子笔记 -> <slug>/<子slug>.md
- 图片统一放到 <slug>/images/，缩到最长边 1600px，去掉 EXIF（含 GPS）
- slug 在 tools/slugs.json 里按 Trilium noteId 配置，没配置的就用 noteId
- 重新运行会覆盖同名文件，所以请只在 Trilium 里改正文
"""
import io
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SLUGS = json.loads((ROOT / "tools" / "slugs.json").read_text(encoding="utf-8"))
MAX_SIDE = 1600
JPEG_QUALITY = 82


# ---------- HTML -> Markdown ----------

def esc(text):
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)
    return text.replace("{{", "{​{").replace("{%", "{​%")


def inline(node, ctx):
    if isinstance(node, NavigableString):
        return esc(str(node))
    if not isinstance(node, Tag):
        return ""
    inner = "".join(inline(c, ctx) for c in node.children)
    name = node.name
    if name in ("strong", "b"):
        s = inner.strip()
        return f"**{s}**" if s else inner
    if name in ("em", "i"):
        s = inner.strip()
        return f"*{s}*" if s else inner
    if name == "u":
        return f"<u>{inner}</u>"
    if name in ("s", "del"):
        return f"~~{inner}~~"
    if name == "code":
        return f"`{node.get_text()}`"
    if name == "br":
        return "\\\n"
    if name == "a":
        href = node.get("href", "")
        return f"[{inner.strip()}]({href})" if href else inner
    if name == "img":
        return "\n" + ctx["image"](node.get("src", "")) + "\n"
    return inner


def tidy(md):
    lines = [l.strip() for l in md.split("\n")]
    lines = [l for l in lines if l]
    # 图片前后的硬换行没有意义
    out = []
    for l in lines:
        if l == "\\":
            continue
        out.append(l)
    return "\n".join(out)


def block(node, ctx, depth=0):
    if isinstance(node, NavigableString):
        t = esc(str(node)).strip()
        return [t] if t else []
    if not isinstance(node, Tag):
        return []
    name = node.name
    if re.fullmatch(r"h[1-6]", name):
        level = min(int(name[1]) + 1, 6)  # 页面标题已是 h1
        return ["#" * level + " " + tidy(inline(node, ctx))]
    if name == "p":
        t = tidy("".join(inline(c, ctx) for c in node.children))
        # 文字和图片拆成不同段落，连续的图片留在同一段里，样式会把它们排成一行
        groups = []
        for line in t.split("\n") if t else []:
            is_img = line.startswith("![")
            if groups and groups[-1][0] == is_img:
                groups[-1][1].append(line)
            else:
                groups.append((is_img, [line]))
        return ["\n".join(g[1]).rstrip(" \\") for g in groups]
    if name in ("ul", "ol"):
        items = []
        for i, li in enumerate(node.find_all("li", recursive=False), 1):
            bullet = f"{i}." if name == "ol" else "-"
            pad = " " * (len(bullet) + 1)
            text_parts, sub = [], []
            for c in li.children:
                if isinstance(c, Tag) and c.name in ("ul", "ol"):
                    sub.extend(block(c, ctx, depth + 1))
                elif isinstance(c, Tag) and c.name == "p":
                    text_parts.append(tidy(inline(c, ctx)))
                else:
                    text_parts.append(inline(c, ctx))
            text = tidy("".join(text_parts)).replace("\n", "\n" + pad)
            entry = f"{bullet} {text}"
            for s in sub:
                entry += "\n" + "\n".join(pad + l for l in s.split("\n"))
            items.append(entry)
        return ["\n".join(items)]
    if name == "blockquote":
        inner = "\n\n".join(b for c in node.children for b in block(c, ctx))
        return ["\n".join("> " + l if l else ">" for l in inner.split("\n"))]
    if name == "pre":
        return ["```\n" + node.get_text().rstrip() + "\n```"]
    if name == "hr":
        return ["---"]
    if name in ("table", "figure") and node.find("table"):
        return [str(node)]
    if name == "figure" and node.find("img"):
        return [ctx["image"](node.find("img").get("src", ""))]
    if name == "img":
        return [ctx["image"](node.get("src", ""))]
    if name in ("div", "section", "figure", "span") or True:
        out = []
        for c in node.children:
            out.extend(block(c, ctx, depth))
        return out


def html_to_md(html, ctx):
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".ck-content") or soup.body
    return "\n\n".join(b for b in block(content, ctx) if b.strip()) + "\n"


# ---------- 图片 ----------

def save_image(data, dest):
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".png":
        img.save(dest, optimize=True)
    else:
        img.convert("RGB").save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


# ---------- 主流程 ----------

def walk(zf, notes, parent_dir, out_dir, top_dir, link_prefix, is_top):
    for note in sorted(notes, key=lambda n: n.get("notePosition", 0)):
        if note.get("type") != "text" or not note.get("dataFileName"):
            continue
        slug = SLUGS.get(note["noteId"], note["noteId"])
        html_path = posixpath.join(parent_dir, note["dataFileName"])
        child_dir = posixpath.join(parent_dir, note["dirFileName"]) if note.get("dirFileName") else None

        # 这个笔记的图片：src 是相对 html 文件的路径；meta 里的子 image 笔记给出原始文件名
        images = {}
        for c in note.get("children", []):
            if c.get("type") == "image" and child_dir:
                images[posixpath.join(child_dir, c["dataFileName"])] = c["title"]

        def image(src, _html_path=html_path, _images=images, _slug=slug):
            path = posixpath.normpath(posixpath.join(posixpath.dirname(_html_path), unquote(src)))
            if path not in zf.namelist():
                return f"![]({src})"
            stem = Path(path).stem
            ext = Path(_images.get(path, path)).suffix.lower() or ".jpg"
            ext = ".jpg" if ext == ".jpeg" else ext
            name = f"{_slug}-{stem}{ext}"
            dest = top_dir / "images" / name
            save_image(zf.read(path), dest)
            rel = posixpath.relpath(f"images/{name}", link_prefix) if link_prefix else f"images/{name}"
            return f"![]({rel})"

        md = html_to_md(zf.read(html_path).decode("utf-8"), {"image": image})

        if is_top:
            target = top_dir / "index.md"
        else:
            target = out_dir / f"{slug}.md"

        text_children = [c for c in note.get("children", []) if c.get("type") == "text"]
        front = [
            "---",
            "layout: post",
            f"title: {json.dumps(note['title'], ensure_ascii=False)}",
            f"note_id: {note['noteId']}",
            f"order: {note.get('notePosition', 0)}",
        ]
        if is_top:
            front.append("top: true")
        front.append("---\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(front) + "\n" + md, encoding="utf-8")
        print("写入", target.relative_to(ROOT))

        if text_children and child_dir:
            walk(zf, text_children, child_dir, top_dir, top_dir, "", False)


def main(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        meta = json.loads(zf.read("!!!meta.json"))
        for top in meta["files"]:
            if top.get("type") != "text":
                continue
            slug = SLUGS.get(top["noteId"], top["noteId"])
            top_dir = ROOT / slug
            walk(zf, [top], "", top_dir, top_dir, "", True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        main(p)

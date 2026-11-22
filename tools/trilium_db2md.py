"""直接从本机 Trilium 数据库生成本站内容，不用手动导出 zip。

用法（在仓库根目录）:
    python tools/trilium_db2md.py            # 默认笔记 x9upcknrOBUy（旅行哈希）
    python tools/trilium_db2md.py <noteId>

- 只读打开 document.db（先拷一份快照到内存），Trilium 开着也没关系
- 笔记 -> <slug>/index.md，所有子孙文本笔记 -> <slug>/<子slug>.md，空笔记跳过
- 图片 -> <slug>/images/<noteId>.jpg|png（缩到 1600px，去掉 EXIF）
- 视频附件（EMBED_VIDEOS = True 时）-> <slug>/media/<noteId>.mp4，以 <video> 嵌入：
  正文里有指向该附件的链接时放在链接处，否则放在它在 Trilium 树里前一张图片的后面
- 每次运行都会清空并重建 <slug>/ 目录
"""
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trilium2md import ROOT, SLUGS, html_to_md, save_image  # noqa: E402

DB = Path(os.environ.get("TRILIUM_DATA_DIR", Path.home() / "AppData/Roaming/trilium-data")) / "document.db"
DEFAULT_ROOT = "x9upcknrOBUy"
EMBED_VIDEOS = False  # 视频附件是否放进网页；改成 True 即恢复


def open_db():
    src = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    db = sqlite3.connect(":memory:")
    src.backup(db)
    src.close()
    return db


class Tree:
    def __init__(self, db):
        self.db = db

    def note(self, nid):
        row = self.db.execute(
            "select title, type, mime, isProtected from notes where noteId=? and isDeleted=0", (nid,)
        ).fetchone()
        return dict(zip(("title", "type", "mime", "protected"), row)) if row else None

    def content(self, nid):
        row = self.db.execute("select content from note_contents where noteId=?", (nid,)).fetchone()
        return row[0] if row and row[0] is not None else b""

    def text(self, nid):
        c = self.content(nid)
        return c.decode("utf-8") if isinstance(c, bytes) else c

    def children(self, nid):
        rows = self.db.execute(
            "select noteId, notePosition from branches where parentNoteId=? and isDeleted=0 order by notePosition",
            (nid,),
        ).fetchall()
        out = []
        for cid, pos in rows:
            n = self.note(cid)
            if n:
                out.append(dict(n, id=cid, position=pos))
        return out


def is_empty(html):
    return not re.sub(r"\s|&nbsp;", "", BeautifulSoup(html, "html.parser").get_text()) and "<img" not in html


def ext_for(note):
    m = (note["mime"] or "").lower()
    if "png" in m or note["title"].lower().endswith(".png"):
        return ".png"
    return ".jpg"


def export(root_id):
    tree = Tree(open_db())
    root = tree.note(root_id)
    slug = SLUGS.get(root_id, root_id)
    top = ROOT / slug
    if top.exists():
        shutil.rmtree(top)
    (top / "images").mkdir(parents=True)

    pages = {}  # noteId -> 页面相对 top 的文件名，用于改写内部链接

    def collect(nid, depth):
        for c in tree.children(nid):
            if c["type"] == "text" and not c["protected"] and not is_empty(tree.text(c["id"])):
                pages[c["id"]] = f"{SLUGS.get(c['id'], c['id'])}.html"
            if c["type"] == "text":
                collect(c["id"], depth + 1)

    pages[root_id] = "./"
    collect(root_id, 0)

    def write_page(nid, note, order, is_top):
        kids = tree.children(nid)
        soup = BeautifulSoup(tree.text(nid), "html.parser")

        # 视频附件
        videos = [k for k in kids if EMBED_VIDEOS and k["type"] == "file" and (k["mime"] or "").startswith("video/")]
        for v in videos:
            dest = top / "media" / f"{v['id']}.mp4"
            dest.parent.mkdir(exist_ok=True)
            data = tree.content(v["id"])
            dest.write_bytes(data)
            tag = soup.new_tag("video", controls=True, preload="metadata", playsinline=True,
                               src=f"media/{v['id']}.mp4")
            link = soup.find("a", href=re.compile(re.escape(v["id"])))
            if link:
                (link.find_parent("p") or link).replace_with(tag)
                continue
            # 没被引用：放在树里前一张图片所在段落之后
            before = [k for k in kids if k["type"] == "image" and k["position"] < v["position"]]
            anchor = None
            for k in reversed(before):
                img = soup.find("img", src=re.compile(re.escape(k["id"])))
                if img:
                    anchor = img.find_parent(["p", "figure"]) or img
                    while anchor.parent is not None and anchor.parent is not soup:
                        anchor = anchor.parent
                    break
            if anchor:
                anchor.insert_after(tag)
            else:
                soup.append(tag)

        # 内部链接
        for a in soup.find_all("a", href=True):
            m = re.search(r"#root/(?:[\w/]+/)?(\w+)$", a["href"])
            if m and m.group(1) in pages:
                a["href"] = pages[m.group(1)]

        def image(src):
            m = re.search(r"api/(?:images|attachments)/(\w+)/", src)
            if not m:
                return f"![]({src})"
            img_note = tree.note(m.group(1))
            if not img_note:
                return ""
            name = f"{m.group(1)}{ext_for(img_note)}"
            dest = top / "images" / name
            if not dest.exists():
                save_image(tree.content(m.group(1)), dest)
            return f"![](images/{name})"

        md = html_to_md(str(soup), {"image": image})
        front = [
            "---",
            "layout: post",
            f"title: {json.dumps(note['title'], ensure_ascii=False)}",
            f"note_id: {nid}",
            f"order: {order}",
        ]
        if is_top:
            front.append("top: true")
        front.append("---\n")
        target = top / ("index.md" if is_top else f"{SLUGS.get(nid, nid)}.md")
        target.write_text("\n".join(front) + "\n" + md, encoding="utf-8")
        print("写入", target.relative_to(ROOT))

    write_page(root_id, root, 0, True)
    order = 0

    def walk(nid):
        nonlocal order
        for c in tree.children(nid):
            if c["type"] != "text":
                continue
            if c["id"] in pages:
                order += 1
                write_page(c["id"], c, order, False)
            walk(c["id"])

    walk(root_id)


if __name__ == "__main__":
    export(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT)

# 旅行日记

用 GitHub Pages（Jekyll）发布的旅行随笔，正文在 Trilium 里写。

## 更新流程

1. Trilium 里右键笔记 → 导出 → 选 HTML，得到一个 zip
2. 在仓库根目录运行：

   ```
   python tools/trilium2md.py 路径/旅行日记.zip
   ```

   会重新生成 `travel-diary/*.md` 和 `travel-diary/images/`（图片自动压缩、去掉 GPS 等 EXIF）
3. 提交并推送，一两分钟后网站自动更新：

   ```
   git add -A
   git commit -m "更新旅行日记"
   git push
   ```

## 新增一篇文章

在 Trilium 里新建一个顶层笔记并导出，运行脚本即可。想要好看的网址，先在 `tools/slugs.json` 里把它的 noteId（导出 zip 中 `!!!meta.json` 里能看到）映射成英文名，例如 `"abc123": "nordic-trip"`。

## 文件结构

- `travel-diary/index.md` — 正文（脚本生成，别手改，下次导出会被覆盖）
- `travel-diary/saxony.md` — 子笔记「小传」
- `_layouts/`, `assets/style.css` — 页面模板和样式
- `tools/` — 转换脚本，不会发布到网站上

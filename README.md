# 旅行日记

用 GitHub Pages（Jekyll）发布的旅行随笔，正文在 Trilium 里写。

## 更新流程

1. 在 Trilium 里改「旅行哈希」及其子笔记（不用导出）
2. 在仓库根目录运行，直接读本机 Trilium 数据库并重建 `travel-diary/`：

   ```
   python tools/trilium_db2md.py
   ```

   - 图片自动压缩、去掉 GPS 等 EXIF；空笔记会跳过
   - 视频附件默认不放进网页；要放的话把 `tools/trilium_db2md.py` 里的 `EMBED_VIDEOS` 改成 `True`。放的位置：想指定位置，就在正文里插一个指向该附件的链接；否则放在它在笔记树里前一张图片之后
   - 还可以用旧办法：导出 HTML zip 后运行 `python tools/trilium2md.py 路径/xxx.zip`
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
- `travel-diary/*.md` — 子笔记（小传、希腊罗马神话……）
- `travel-diary/images/`, `travel-diary/media/` — 图片和视频
- `_layouts/`, `assets/style.css` — 页面模板和样式
- `tools/` — 转换脚本，不会发布到网站上

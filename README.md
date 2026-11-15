# Ingenieur's Blog

Tao 的个人主页：<https://tao-ingenieur.github.io/>。

博客栏目：<https://tao-ingenieur.github.io/blog/>。首页展示个人介绍、项目链接和最近三篇文章；文章原地址保持有效。

静态博客，文章使用 Markdown 保存，推送到 `main` 后 GitHub Actions 自动构建并发布到 GitHub Pages。阅读网站无需数据库或服务器。

## 本地预览

需要 Python 3.12 或以上版本。首次安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

构建、检查和预览：

```powershell
.venv\Scripts\python.exe scripts/build.py
.venv\Scripts\python.exe scripts/verify.py
.venv\Scripts\python.exe -m http.server 4173 --bind 127.0.0.1 --directory dist
```

浏览器打开 <http://127.0.0.1:4173/>。修改后重新构建，再刷新浏览器。

## 写文章

在 `src/content/` 新建一个 `.md` 文件，文件名可使用数字或简短英文。开头 `---` 之间是 JSON 格式的元数据，其后是 Markdown 正文。例如：

```markdown
---
{
  "id": 35,
  "title": "新的笔记",
  "slug": "a-new-note",
  "date": "2026-11-15T10:00:00+08:00",
  "updated": "2026-11-15T10:00:00+08:00",
  "type": "post",
  "categories": ["生活"],
  "tags": []
}
---

这里开始写正文。

![图片说明](/images/example.jpg)
```

- `id` 和 `slug` 必须唯一；发布后保持 `slug` 不变以免旧链接失效。
- 当前分类为 `科技`、`生活`、`星空`、`股市`；添加分类时同时修改 `site.json`。
- 图片放进 `public/images/`，正文引用 `/images/文件名`。不要把图片放入 `dist/`，它会在构建时重新生成。
- 关于页面在 `src/content/2.md`。
- 姓名、昵称与一句话定位在 `site.json` 的 `profile` 中统一维护，首页与关于页面同步使用；`tagline_en` 是首页的英文定位。
- 首页右上角提供中英文切换，并在当前浏览器记住选择。首页界面文案随之切换，博客预览保持中文原文，博客栏目及文章不翻译。
- 提交并推送修改后，到仓库 Actions 查看 `Publish blog` 的执行结果。

## 目录

| 路径 | 用途 |
| --- | --- |
| `src/content/` | 可公开发布的 Markdown 正文及元数据 |
| `public/` | 图片、附件、CSS、浏览器脚本 |
| `scripts/` | 导入、构建、校验脚本 |
| `site.json` | 站名、正式网址、分类配置 |
| `src/redirects.json` | 旧文章地址到新地址的对应关系 |
| `dist/` | 自动生成的网站，Git 忽略 |

## 将来绑定自己的域名

1. 在 GitHub 仓库 Settings → Pages → Custom domain 设置自己的子域名。
2. 在域名 DNS 添加 `blog` 的 CNAME，目标为 `tao-ingenieur.github.io`。
3. 修改 `site.json` 的 `url` 为新正式网址，重新发布。RSS、站点地图和 canonical 会随之更新。
4. DNS 与证书准备好后开启 Enforce HTTPS。文章中的相对路径会继续有效。

当前没有绑定自定义域名。不要提前修改域名解析。

## 内容迁移

来自原 Typecho 博客的公开内容已迁入。迁移验收后，原始备份、临时报告和预览文件已按要求删除。后续直接编辑 Markdown，不要重复运行迁移覆盖现有文章。本地虚拟环境和构建输出也已清理，需要预览时按上面的步骤重新创建。

文章与照片的权利归原作者所有。

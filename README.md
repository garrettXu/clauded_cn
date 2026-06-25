# clauded_cn

授权网站静态复刻 Agent。它从入口 URL 开始，持续遍历同主域名和子域名下人类可触达的页面，下载 HTML、CSS、JS、图片、字体、视频、文档等静态资源，保持原站路径结构，并把资源链接改成本地静态文件。复刻完成后会生成本地预览、部署声明、Nginx 配置和质量门禁报告。

> 仅用于你拥有或已获得明确授权的网站。不要复刻未授权站点。

## 示例效果

Anthropic 复刻演示站：

- 主站：[https://clauded.cn/](https://clauded.cn/)
- 子域名映射示例：[https://www.clauded.cn/research/](https://www.clauded.cn/research/)

这个演示站由本项目生成，部署形态是静态站点：页面路径保持原站路径，资源从本地静态目录读取，外部第三方链接保持跳转到原地址。

## 能力范围

- 深度遍历主域名和子域名，持续发现内部链接，直到队列完成。
- 使用 Playwright 打开页面，等待动态渲染、懒加载、滚动加载和可见交互内容。
- 下载并本地化 HTML 中的图片、CSS、JS、字体、视频、文档资源。
- 解析 CSS、JS、JSON 和 Next.js 图片代理中的二级静态资源，并下载到本地。
- 保持 URL path 不变，只替换 host，便于迁移到新主域名。
- 支持续跑和增量更新：使用 ETag、Last-Modified、内容 hash 和本地状态表判断是否需要重新下载。
- 输出 `quality_report.json`，检查页面成功率、资源成功率、内链替换、残留远程资源和视觉验收结果。
- 生成 `DEPLOYMENT.md`、`nginx/local-preview.conf`、`nginx/mirror.conf`。
- 提供静态目录上传和 Nginx 配置安装脚本。

## 安装

所有 Python 依赖必须安装在虚拟环境中：

```bash
cd /Users/elane/Documents/python/clauded_cn
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

检查安装是否正常：

```bash
.venv/bin/python -m unittest discover -s tests
```

## 第一步：确认复刻范围

复刻前先确认 4 件事：

1. 你拥有目标网站，或已获得明确授权。
2. 确认根域名，例如 `example.com`。
3. 确认是否复刻所有子域名，例如 `www.example.com`、`docs.example.com`。
4. 确认部署目标域名，例如把 `www.example.com` 映射到 `www.mirror.com`。

Agent 只完整复刻同根域名和子域名下的页面。外部第三方链接不会复刻，会原样保留为外链。

## 第二步：创建配置

复制配置样例：

```bash
cp configs/replication_agent.example.json configs/my_site.json
```

最小配置示例：

```json
{
  "site_id": "my_site",
  "target_url": "https://www.example.com/",
  "out_dir": "output/my_site/original",
  "domain_policy": {
    "root_domain": "example.com",
    "include_subdomains": true,
    "allowed_hosts": [],
    "blocked_hosts": []
  },
  "crawl_policy": {
    "max_pages_per_host": 5000,
    "max_depth": 50,
    "respect_robots": true,
    "render_dynamic_pages": true,
    "worker_count": 3,
    "request_timeout_ms": 30000,
    "page_idle_timeout_ms": 8000,
    "download_videos": true,
    "download_documents": true
  },
  "deployment": {
    "target_base_domain": "mirror.example.com",
    "base_root": "/srv/mirror/my_site",
    "scheme": "https"
  },
  "quality_policy": {
    "max_unresolved_internal_links": 0,
    "max_missing_resources": 0,
    "require_visual_pass": false
  },
  "visual_policy": {
    "enabled": true,
    "sample_pages": 20
  },
  "authorization_policy": {
    "require_ack": true,
    "authorized": false
  }
}
```

常用字段说明：

- `site_id`：项目 ID，会用于输出目录和报告标识。
- `target_url`：复刻入口，通常填首页。
- `out_dir`：复刻结果目录。
- `domain_policy.root_domain`：只处理这个根域名及其子域名。
- `domain_policy.include_subdomains`：是否复刻二级/多级子域名。
- `crawl_policy.max_pages_per_host`：每个 host 最多复刻多少页面。正式复刻不要设置太小。
- `crawl_policy.render_dynamic_pages`：是否用 Playwright 渲染动态页面。复杂网站建议开启。
- `deployment.target_base_domain`：部署后的新主域名。
- `quality_policy`：发布门禁。正式发布建议资源缺失和内部未解析链接都为 0。
- `authorization_policy.authorized`：可以保持 `false`，运行时用 `--ack-authorized` 明确确认授权。

## 第三步：首次完整复刻

首次运行建议加 `--force-refresh`，确保页面、资源、状态表全部重新建立：

```bash
.venv/bin/python scripts/replication_agent.py \
  --config configs/my_site.json \
  --ack-authorized \
  --force-refresh
```

运行过程中 Agent 会：

1. 打开入口页面。
2. 抽取当前页面里的同域名链接、相对路径链接和静态资源。
3. 把新发现页面加入 `crawl_table.json`。
4. 下载页面所需 HTML、CSS、JS、图片、字体、视频和文档。
5. 继续处理队列里的下一个页面。
6. 循环直到可触达页面全部完成，或达到配置中的限制。

## 第四步：检查输出结果

复刻结果在 `out_dir` 下，核心文件如下：

- `manifest.json`：页面、host、端口、部署映射总清单。
- `crawl_table.json`：页面发现、抓取、失败、续跑状态表。
- `resource_table.json`：资源下载、本地路径、状态码和 hash 表。
- `quality_report.json`：发布门禁报告。
- `DEPLOYMENT.md`：部署声明和部署步骤。
- `nginx/local-preview.conf`：本地多 host 预览配置。
- `nginx/mirror.conf`：线上 Nginx 配置。
- `hosts/<host>/site/`：每个 host 的静态站点根目录。

必须先看质量报告：

```bash
python3 -m json.tool output/my_site/original/quality_report.json | sed -n '1,160p'
```

只有 `ready_for_release` 为 `true` 才建议部署。若为 `false`，先按 `blockers`、`warnings`、`failed_pages` 和 `missing_resources` 修复。

## 第五步：本地预览

预览单个 host：

```bash
.venv/bin/python scripts/serve_replica.py \
  output/my_site/original/hosts/www.example.com/site \
  --port 8700
```

浏览器打开：

```text
http://localhost:8700/
```

如果是多 host 复刻，需要按 `manifest.json` 或 `nginx/local-preview.conf` 中的端口查看不同子域名。每个源 host 会有独立静态目录和预览端口。

本地检查重点：

- 首页是否完整显示。
- 导航菜单和下探链接是否能打开。
- 图片、背景图、字体、视频是否从本地加载。
- 浏览器 DevTools Network 中是否还有同域远程资源 404。
- Console 是否有阻塞页面渲染的错误。

## 第六步：视觉验收

开启视觉对比：

```bash
.venv/bin/python scripts/replication_agent.py \
  --config configs/my_site.json \
  --ack-authorized \
  --visual-compare \
  --visual-sample-pages 20
```

视觉验收会对源站和本地复刻页面截图，并写入质量报告。正式发布建议至少抽样首页、导航页、文章页、列表页、图片密集页和长页面。

如果要接入视觉模型，在环境变量中设置对应 Key，并在配置中开启视觉模型判断：

```bash
export VISION_API_KEY="..."
```

## 第七步：部署到服务器

部署前确认：

1. `quality_report.json` 中 `ready_for_release=true`。
2. DNS 已解析到服务器公网 IP。
3. 服务器已安装 Nginx。
4. 80/443 端口已在安全组放行。
5. 如果部署多个子域名，需要 DNS 添加通配符解析，例如 `*.mirror.example.com`。

上传静态站点并安装 Nginx 配置：

```bash
.venv/bin/python scripts/deploy_static_mirror.py \
  --mirror-dir output/my_site/original \
  --ssh-host <server-ip> \
  --ssh-user root \
  --remote-root /srv/mirror/my_site \
  --remote-nginx-conf /etc/nginx/sites-available/my_site.conf \
  --enable-nginx-site \
  --reload-nginx
```

部署后在服务器检查：

```bash
nginx -t
systemctl status nginx --no-pager
curl -I http://<your-domain>/
```

HTTPS 建议使用 Certbot 或云厂商证书。HTTPS 生效前，先用 HTTP 确认静态站点、Nginx 路由和 DNS 正常。

## 第八步：增量更新

后续重复运行时不要加 `--force-refresh`：

```bash
.venv/bin/python scripts/replication_agent.py \
  --config configs/my_site.json \
  --ack-authorized
```

Agent 会读取已有的 `crawl_table.json` 和 `resource_table.json`：

- 已完成页面会检查是否变化。
- 未变化页面不会重复下载。
- 变化页面会重新抓取并重新抽取资源。
- 新发现链接会加入队列。
- 删除或失败资源会在质量报告中体现。

建议每天定时运行一次，运行后只在质量报告通过时部署。

## 常见问题

`ready_for_release=false`

先看 `quality_report.json` 的 `blockers`。不要直接部署半成品。

`pages are still pending`

说明队列还没有跑完，或 `max_pages_per_host`、`max_depth` 太小。提高限制后重新运行。

`resources are not localized`

说明仍有图片、CSS、JS、字体、视频或二级资源没有下载成功。检查 `resource_table.json`，确认是否是超时、403、Next.js 图片代理、CSS url 或 JS JSON 中的资源引用。

页面空白或大片内容不显示

通常是关键 CSS/JS 资源缺失，或页面依赖源站运行时脚本。先检查 Network 404 和 Console 错误，再重新运行复刻。不要通过删除 CSS 或禁用 JS 来掩盖问题。

内部链接跳回源站

说明链接没有进入复刻表，或 host 映射缺失。检查 `crawl_table.json` 是否包含该 URL，检查 `manifest.json` 的 host 映射是否正确。

访问域名很慢

优先检查 DNS、Nginx、HTTPS、服务器带宽和是否仍在请求远程资源。静态复刻站本身不需要数据库，正常情况下响应应很快。

## 正式发布标准

发布前至少满足：

- `quality_report.json` 的 `ready_for_release=true`。
- 页面成功率、资源成功率、内部链接替换率达到配置门禁。
- 首页、核心导航页、文章页、列表页、图片密集页通过浏览器人工检查。
- 视觉抽样没有明显缺图、错位、空白和布局断裂。
- Nginx 配置通过 `nginx -t`。
- DNS、HTTPS、ICP备案号和公安备案信息已按实际网站要求配置。

## 开发测试

```bash
.venv/bin/python -m py_compile scripts/replication_agent.py scripts/deploy_static_mirror.py scripts/serve_replica.py
.venv/bin/python -m unittest discover -s tests
```

## 目录结构

```text
configs/   配置样例
docs/      产品文档、部署说明、使用说明
scripts/   复刻、部署、本地预览、汉化相关脚本
tests/     单元测试
output/    本地复刻产物，通常不提交到 Git
```

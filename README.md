# 复刻Agent

复刻 Agent 是一个授权网站静态复刻工具。它会从入口 URL 开始，自动遍历同主域名和子域名下可触达的页面，下载 HTML、CSS、JS、图片、字体、视频、文档等静态资源，保持原站路径结构，并把资源链接改成本地静态文件。

> 本项目用于学习和研究网站结构、静态站点生成、资源本地化、部署流程和自动化质量检查，也可以用于制作你拥有版权或已获得授权的学习型网站。不要复刻未授权站点，不要冒用他人品牌、内容或服务。
>
> 如需学习复刻网站的实际效果，可以联系作者获取邀请码。

## 一条命令启动完整复刻

不写配置文件也可以直接执行，用户只需要输入目标地址：

```bash
.venv/bin/python scripts/replication_agent.py \
  https://www.example.com/ \
  --ack-authorized \
  --force-refresh
```

说明：

- `https://www.example.com/`：必填，目标网站入口地址。
- `--ack-authorized`：确认你拥有目标网站或已获得授权。
- `--force-refresh`：首次完整复刻建议使用，会重新建立页面、资源和状态表。

后续增量更新时去掉 `--force-refresh`：

```bash
.venv/bin/python scripts/replication_agent.py \
  https://www.example.com/ \
  --ack-authorized
```

## 首次安装

```bash
cd <repo-dir>
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

复制配置样例：

```bash
cp configs/replication_agent.example.json configs/my_site.json
```

## 配置文件

配置文件不是必须的。需要保存任务时，最小配置只写目标地址：

```json
{
  "target_url": "https://www.example.com/"
}
```

使用配置文件运行：

```bash
.venv/bin/python scripts/replication_agent.py \
  --config configs/my_site.json \
  --ack-authorized \
  --force-refresh
```

## 必填和可选配置

必填项只有一个：

- `target_url`：目标网站入口地址。也可以直接作为命令行第一个参数传入。

常用可选项：

```json
{
  "target_url": "https://www.example.com/",
  "site_id": "example",
  "out_dir": "output/example",
  "domain_policy": {
    "root_domain": "example.com",
    "include_subdomains": true,
    "exclude": ["status.example.com"]
  },
  "deployment": {
    "target_base_domain": "mirror.example.com"
  }
}
```

可选项默认值：

- `site_id`：默认从根域名生成，例如 `example.com`。
- `out_dir`：默认 `output/<site_id>`，实际复刻产物在 `output/<site_id>/original`。
- `domain_policy.root_domain`：默认从 `target_url` 自动推导。
- `domain_policy.include_subdomains`：默认 `true`，会复刻同根域名下子域名。
- `domain_policy.exclude`：默认空，用于排除不复刻的子域名。
- `deployment.target_base_domain`：默认空；不部署新域名时不需要填写。

高级配置也都有默认值，只有需要调优时才写：

- `crawl_policy.max_pages_per_host`：默认 `5000`。
- `crawl_policy.max_depth`：默认 `50`。
- `crawl_policy.render_dynamic_pages`：默认 `true`。
- `crawl_policy.worker_count`：默认 `3`。
- `crawl_policy.timeout_seconds`：默认 `30`。
- `local_preview.port_start`：默认 `8300`。
- `visual_policy.enabled`：默认 `false`。
- `quality_policy.min_page_success_rate`：默认 `0.95`。
- `quality_policy.min_resource_success_rate`：默认 `0.98`。
- `authorization_policy.require_ack`：默认 `true`，运行时用 `--ack-authorized` 确认授权。

## Agent 会自动完成什么

执行启动命令后，复刻 Agent 会自动完成 6 件事：

1. 打开入口页面，等待动态内容、懒加载资源和可见交互内容完成。
2. 扫描同根域名、子域名和相对路径链接，把新页面加入 `crawl_table.json`。
3. 下载页面 HTML，以及图片、CSS、JS、字体、视频、文档等静态资源。
4. 继续解析 CSS、JS、JSON、Next.js 图片代理中的二级资源，并下载到本地。
5. 重写页面和资源路径，保持原始 URL path，只替换 host 和资源来源。
6. 生成状态表、部署文件、Nginx 配置和 `quality_report.json` 质量报告。

同根域名和子域名会完整复刻；外部第三方链接不会复刻，会原样保留为外链。

## 输出结果

默认输出在 `output/<site_id>/original` 下。如果配置了 `out_dir`，则输出在 `<out_dir>/original` 下：

```text
output/example.com/original/
  manifest.json
  crawl_table.json
  resource_table.json
  quality_report.json
  DEPLOYMENT.md
  nginx/
    local-preview.conf
    mirror.conf
  hosts/
    www.example.com/site/
```

核心文件：

- `manifest.json`：页面、host、端口、部署映射总清单。
- `crawl_table.json`：页面发现、抓取、失败、续跑状态表。
- `resource_table.json`：资源下载、本地路径、状态码和 hash 表。
- `quality_report.json`：发布门禁报告。
- `DEPLOYMENT.md`：部署声明和部署步骤。
- `nginx/mirror.conf`：线上 Nginx 配置。

## 发布前检查

必须先检查质量报告：

```bash
python3 -m json.tool output/example.com/original/quality_report.json | sed -n '1,160p'
```

只有 `ready_for_release=true` 才建议部署。重点检查：

- 页面是否全部完成。
- 图片、CSS、JS、字体、视频是否完整本地化。
- 内部链接是否都已替换到本地复刻路径。
- 浏览器 Network 是否还有同域远程资源 404。
- Console 是否有阻塞页面渲染的错误。
- 视觉抽样是否存在明显缺图、空白、错位或布局断裂。

## 本地预览

没有域名时，推荐使用单端口 localhost 聚合预览：

```bash
.venv/bin/python scripts/serve_replica.py \
  output/example.com/original \
  --localhost \
  --port 8700
```

浏览器打开：

```text
http://localhost:8700/
```

这个模式会把所有源 host 挂到同一个 localhost 端口下：

```text
http://localhost:8700/_mirror/www.example.com/
http://localhost:8700/_mirror/docs.example.com/
```

页面里的内部链接、图片、CSS、JS 等根路径资源会在响应时自动改写到 `/_mirror/<source-host>/...`，所以不需要本地域名、hosts 文件或 Nginx。

也可以预览单个 host：

```bash
.venv/bin/python scripts/serve_replica.py \
  output/example.com/original/hosts/www.example.com/site \
  --port 8700
```

浏览器打开：

```text
http://localhost:8700/
```

如果要使用原来的多端口预览，直接传入完整复刻目录，不加 `--localhost`：

```bash
.venv/bin/python scripts/serve_replica.py output/example.com/original
```

多端口模式下，每个源 host 使用 `manifest.json` 或 `nginx/local-preview.conf` 中分配的端口分别查看。

## 部署

复刻通过质量报告后，可上传静态站点并安装 Nginx 配置：

```bash
.venv/bin/python scripts/deploy_static_mirror.py \
  --mirror-dir output/example.com/original \
  --ssh-host <server-ip> \
  --ssh-user root \
  --remote-root /srv/mirror/example \
  --remote-nginx-conf /etc/nginx/sites-available/example.conf \
  --enable-nginx-site \
  --reload-nginx
```

部署前确认：

- DNS 已解析到服务器公网 IP。
- 服务器已安装 Nginx。
- 80/443 端口已放行。
- 多子域名部署时，DNS 已配置通配符解析。
- `nginx -t` 通过。
- HTTPS、ICP备案号和公安备案信息已按实际网站要求配置。

## 常见问题

`ready_for_release=false`

先看 `quality_report.json` 的 `blockers`，不要直接部署半成品。

`resources are not localized`

说明仍有资源没有下载成功。检查 `resource_table.json`，重点看超时、403、Next.js 图片代理、CSS url 和 JS JSON 中的资源引用。

页面空白或大片内容不显示

通常是关键 CSS/JS 资源缺失，或页面依赖源站运行时脚本。先检查 Network 404 和 Console 错误，再重新运行复刻。

内部链接跳回源站

说明链接没有进入复刻表，或 host 映射缺失。检查 `crawl_table.json` 是否包含该 URL，检查 `manifest.json` 的 host 映射是否正确。

## 开发测试

```bash
.venv/bin/python -m py_compile scripts/replication_agent.py scripts/deploy_static_mirror.py scripts/serve_replica.py
.venv/bin/python -m unittest discover -s tests
```

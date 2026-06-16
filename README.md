# clauded_cn

授权网站静态复刻 Agent。它会从入口 URL 开始遍历同主域名和子域名页面，下载 HTML、CSS、JS、图片、字体、视频和文档等静态资源，保持原始路径结构，并为每个源 host 生成本地预览端口、部署声明、Nginx 配置和质量门禁报告。

> 仅用于你拥有或已获得明确授权的网站。不要复刻未授权站点。

## 功能

- 深度遍历主域名和子域名，持续发现内部链接。
- 使用 Playwright 渲染动态页面，处理懒加载图片和交互展开内容。
- 下载并本地化页面资源，包括 CSS/JS 中引用的二级资源。
- 保持路径不变，只替换 host；支持主域名和二级域名映射到新域名。
- 支持续跑：已有页面和资源可按 ETag、Last-Modified、内容 hash 做增量检查。
- 输出 `quality_report.json`，阻止页面失败、资源缺失、内链未解析等半成品发布。
- 生成 `nginx/mirror.conf` 和 `DEPLOYMENT.md`。
- 提供一键上传静态目录和安装 Nginx 配置脚本。

## 安装

```bash
cd clauded_cn
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

## 快速开始

复制并修改配置：

```bash
cp configs/replication_agent.example.json configs/my_site.json
```

关键配置：

```json
{
  "target_url": "https://www.example.com/",
  "domain_policy": {
    "root_domain": "example.com",
    "include_subdomains": true
  },
  "deployment": {
    "target_base_domain": "mirror.example.net",
    "base_root": "/srv/mirror/original"
  },
  "authorization_policy": {
    "require_ack": true,
    "authorized": false
  }
}
```

运行复刻：

```bash
.venv/bin/python scripts/replication_agent.py --config configs/my_site.json --ack-authorized
```

输出目录默认为配置中的 `out_dir`，核心文件包括：

- `manifest.json`：页面、host、部署映射总清单。
- `crawl_table.json`：页面发现、抓取、失败、续跑状态表。
- `resource_table.json`：资源下载和本地化状态表。
- `quality_report.json`：发布门禁报告。
- `DEPLOYMENT.md`：部署说明。
- `nginx/local-preview.conf`：本地多端口预览配置。
- `nginx/mirror.conf`：线上 Nginx 配置。

## 本地预览

如果只需要单 host 快速预览：

```bash
.venv/bin/python scripts/serve_replica.py output/my_site/original/hosts/www.example.com/site --port 8700
```

如果要按生成的多 host 端口预览，使用 `nginx/local-preview.conf`。

## 发布门禁

复刻完成后必须先检查：

```bash
cat output/my_site/original/quality_report.json
```

只有 `ready_for_release=true` 才允许部署。常见阻断项：

- `pages are still pending`：还有队列页面未处理。
- `pages failed with non-terminal errors`：存在超时、抓取失败、渲染失败。
- `resources are not localized`：图片、CSS、JS、字体等未完整下载到本地。
- `unresolved internal links`：内部链接未进入复刻表或路径未正确替换。
- `visual gate failed`：启用视觉验收时截图差异未通过。

## 部署

生成静态站点后可以使用部署脚本上传：

```bash
.venv/bin/python scripts/deploy_static_mirror.py \
  --mirror-dir output/my_site/original \
  --ssh-host <server-ip> \
  --ssh-user root \
  --remote-root /srv/mirror/original \
  --enable-nginx-site \
  --reload-nginx
```

部署前需要：

- DNS 已解析到服务器。
- Nginx 已安装。
- HTTPS 证书已配置，或先用 80 端口验证。
- `quality_report.json` 已通过。

## 视觉对比

配置或命令行开启：

```bash
.venv/bin/python scripts/replication_agent.py \
  --config configs/my_site.json \
  --ack-authorized \
  --visual-compare \
  --visual-sample-pages 20
```

如需视觉模型判断，设置环境变量并在配置中开启 `visual_policy.use_vision_model`：

```bash
export VISION_API_KEY="..."
```

## 测试

```bash
.venv/bin/python -m py_compile scripts/replication_agent.py scripts/deploy_static_mirror.py
.venv/bin/python -m unittest discover -s tests
```

## 目录

```text
configs/   配置样例
docs/      产品文档、部署说明、使用说明
scripts/   复刻、部署、本地预览、汉化相关脚本
tests/     单元测试
```

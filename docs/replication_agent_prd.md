# 复刻 Agent 产品文档

## 1. 产品定义

复刻 Agent 是一个授权网站静态复刻智能体。它从目标网站入口 URL 开始，持续发现主域名和该主域名下所有允许的子域名，完整下载页面、资源和链接关系，生成一个不依赖数据库、可本地预览、可通过 Nginx 部署的新静态站点。

复刻 Agent 只负责“复刻”，不负责翻译、中文排版和本地化改写。

最终复刻结果必须满足：

- 主域名完整复刻。
- 主域名下子域名完整复刻。
- 每个原始 host 独立输出静态目录。
- 每个原始 host 本地使用独立端口预览。
- 原始 URL 的 path 保持不变。
- 只替换 host，不改变站内路径结构。
- 最终运行不依赖数据库。
- 自动生成部署声明和 Nginx 配置。

## 2. 用户目标

用户输入一个授权网站地址后，系统自动完成：

1. 发现目标主域名和主域名下所有允许的子域名。
2. 深度遍历每个 host 下的页面。
3. 下载 HTML、CSS、JS、图片、视频、字体、图标、附件等资源。
4. 保持原始路径结构生成静态文件。
5. 重写内部链接，使本地镜像链接通顺。
6. 外部链接保持原始地址。
7. 为每个 host 分配本地预览端口。
8. 生成部署声明。
9. 生成 Nginx 配置。
10. 每天自动检查新增页面、内容变化和资源变化。

## 3. 核心原则

### 3.1 静态复刻

复刻后的站点必须是纯静态站点。

允许输出：

- HTML。
- CSS。
- JS。
- 图片。
- 视频。
- 音频。
- 字体。
- 附件。
- JSON manifest。
- 部署说明。
- Nginx 配置。

禁止作为运行依赖：

- SQLite。
- PostgreSQL。
- Redis。
- 后端 API。
- 运行时任务队列。
- 动态渲染服务。

开发期可以使用临时队列或临时文件，但最终部署包不能依赖数据库。

### 3.2 域名完整复刻

默认主域名按 eTLD+1 判断。

示例：

- 入口：`https://www.example.com/`
- 主域名：`example.com`
- 需要处理：`www.example.com`
- 需要处理：`docs.example.com`
- 需要处理：`support.example.com`
- 不处理：`external.example.ai`
- 不处理：`youtube.com`

说明：这里的“二级域名”按产品语境理解为主域名下的子域名。

### 3.3 路径保持

复刻后路径必须保持不变。

示例：

```text
https://www.example.com/about
→ http://localhost:8300/about
→ https://www.mirror.example.net/about

https://docs.example.com/guide/start
→ http://localhost:8301/guide/start
→ https://docs.mirror.example.net/guide/start
```

允许变化：

- host。
- 协议，取决于部署环境。
- 本地预览端口。

不允许变化：

- path。
- 可保留的 query。
- fragment 语义。

### 3.4 Host 独立输出

每个原始 host 都有独立静态目录。

```text
mirror/
  original/
    hosts/
      www.example.com/
        site/
        assets/
      docs.example.com/
        site/
        assets/
      blog.example.com/
        site/
        assets/
```

这样做的原因：

- 本地可用不同端口模拟不同 host。
- 部署时可用不同 `server_name` 映射不同静态目录。
- 子域名之间的资源和路径不会互相污染。
- 便于增量更新某个 host。

## 4. 输入配置

```yaml
site_id: example
target_url: https://www.example.com/

domain_policy:
  root_domain: example.com
  include_subdomains: true
  include:
    - www.example.com
    - docs.example.com
  exclude:
    - status.example.com

crawl_policy:
  respect_robots: true
  max_pages_per_host: 10000
  max_depth: 50
  rate_limit_per_host: 1
  render_dynamic_pages: true
  require_browser_render: false
  dynamic_wait_ms: 1500
  dynamic_scroll_rounds: 4
  dynamic_click_rounds: 2
  dynamic_click_limit: 20
  dynamic_timeout_seconds: 30
  download_videos: true
  download_documents: true
  max_asset_size_mb: 500
  revalidate_completed_on_resume: true
  retry_failed_on_resume: true
  worker_count: 4

static_policy:
  runtime_database: false
  preserve_paths: true
  query_strategy: record_and_map_when_needed
  external_link_policy: keep_original

local_preview:
  port_start: 8300
  host_port_map:
    www.example.com: 8300
    docs.example.com: 8301

deployment:
  generate_nginx: true
  base_root: /srv/mirror/original
  target_host_map:
    www.example.com: www.mirror.example.net
    docs.example.com: docs.mirror.example.net

visual_policy:
  enabled: true
  sample_pages: 20
  diff_threshold: 0.02
  use_vision_model: false
```

## 5. 页面发现

发现入口：

- 起始 URL。
- `robots.txt`。
- `sitemap.xml`。
- sitemap index。
- 页面 DOM 链接。
- 浏览器渲染后 DOM 链接。
- canonical。
- hreflang。
- RSS / Atom，可配置启用。
- 重定向链。

子域名发现：

- 发现任何同主域名 host 时，先判断是否被允许。
- 允许的 host 创建独立 host 任务。
- 每个 host 有独立 URL 队列。
- 跨 host 链接进入对应 host 队列。

URL 规范化：

- 去除 fragment 用于去重，但保留 fragment 链接语义。
- 统一协议和域名大小写。
- 默认去除 `utm_*`、`fbclid`、`gclid`。
- 识别 canonical URL。
- query 是否参与内容身份由 `query_strategy` 控制。

队列策略：

- BFS 优先，快速形成站点骨架。
- 支持 host 级最大页面数。
- 支持路径白名单。
- 支持路径黑名单。
- 支持失败重试。
- 支持断点续跑到静态 manifest。

## 5.1 复刻表单闭环

正式复刻必须以“复刻表单”为核心，而不是只依赖内存队列。

复刻表单包含：

- `crawl_table.json`：所有发现的页面 URL、host、path、状态、来源、重试次数、本地路径、部署路径。
- `resource_table.json`：所有发现的资源 URL、所属页面、状态、本地路径、hash、ETag、Last-Modified。
- `rewrite_map.json`：所有页面 URL 到本地预览 URL、部署 URL、本地文件路径的映射。
- `completeness_report.json`：全站完整性检查结果。

闭环流程：

```text
首页 / sitemap / robots
  ↓
发现 URL，写入 crawl_table
  ↓
取 pending 页面
  ↓
抓取页面
  ↓
扫描人类可点击链接和页面资源
  ↓
新增页面写入 crawl_table
  ↓
新增资源写入 resource_table
  ↓
生成 rewrite_map
  ↓
重写页面
  ↓
标记页面完成
  ↓
直到 crawl_table 没有 pending 页面
  ↓
执行 completeness_report 校验
```

这个模型的目标是模拟人从首页进入后，通过不停点击、下探、进入子页面能触达的所有页面。只要页面出现在允许域名范围内，并且能通过链接或 sitemap 被发现，就必须进入复刻表单。最终不是简单“抓完队列”，而是要求表单中所有页面都有明确状态：

- `replicated`
- `unchanged`
- `blocked_by_robots`
- `fetch_failed`
- `render_failed`
- `skipped_page_limit`
- `query_mapping_needed`

不允许出现无状态 URL。

## 6. 页面抓取

抓取方式：

1. HTTP 抓取：用于 HTML、CSS、JS、图片、字体、sitemap。
2. 浏览器抓取：用于 SPA、Next.js、Webflow、懒加载页面。

浏览器抓取要求：

- 等待 `domcontentloaded`。
- 必要时等待 `networkidle`。
- 分段滚动并触发滚动事件，模拟用户下探，触发懒加载。
- 安全点击非提交型菜单、折叠项、`aria-expanded=false`、`summary`、`role=button` 等控件，发现隐藏导航。
- 捕获最终 DOM。
- 捕获网络请求。
- 捕获 console error。
- 保存桌面和移动端截图基线。

抓取结果必须保存：

- 原始 URL。
- 最终 URL。
- 状态码。
- 响应头。
- 重定向链。
- 页面 HTML。
- 渲染后 DOM。
- 页面 hash。
- 抓取时间。

## 7. 资源复刻

必须处理：

- `<link href>`。
- `<script src>`。
- `<img src>`。
- `srcset`。
- `<video>`。
- `<audio>`。
- `<source>`。
- `poster`。
- CSS `url(...)`。
- 字体。
- favicon。
- apple touch icon。
- mask icon。
- Open Graph 图片。
- Twitter 图片。
- PDF。
- 下载附件。
- 懒加载属性中的资源，例如 `data-src`、`data-srcset`、`data-bg`、`data-poster`。
- 内联 `style` 中的资源。
- `<style>` 标签中的资源。
- CSS 文件中的 `url(...)` 和 `@import`。
- JS 文件中明确带静态扩展名的资源字符串。

资源保存：

```text
hosts/{host}/assets/{type}/{sha256[:24]}{ext}
```

资源类型：

```text
css
js
images
videos
audio
fonts
files
```

资源归属：

- 页面直接引用的资源保存到页面所属 host。
- CSS 内部资源递归下载并重写。
- JS chunk 按实际引用下载。
- 同 hash 资源可以去重，但 HTML 引用必须在当前 host 下可访问。
- CDN 上的必要静态资源必须下载本地化。
- 第三方统计、广告、客服、表单脚本默认保留外链或禁用，不允许阻塞页面打开。

完整复刻要求：

- 图片必须下载到本地，并替换 HTML/CSS/JS 中的引用。
- CSS 必须下载到本地，并递归下载 CSS 中引用的字体、图片、其他 CSS。
- JS 必须下载到本地，并尽量下载 JS 中明确引用的静态资源。
- 字体、图标、视频、音频、PDF 等静态资源必须下载到本地。
- 如果任何必须资源下载失败或仍残留静态外链，`completeness_report.json` 必须标记 `complete=false`。
- 正式复刻时 `max_assets_per_host` 必须为 `0`，表示不限制资源数量。

## 8. 链接重写

### 8.1 本地预览链接

同 host 链接替换为对应本地端口。

```text
https://www.example.com/about
→ http://localhost:8300/about
```

跨子域名链接替换为目标 host 的本地端口。

```text
https://docs.example.com/guide/start
→ http://localhost:8301/guide/start
```

外部链接保持原样。

```text
https://youtube.com/example
→ https://youtube.com/example
```

### 8.2 部署链接

部署模式下，原始 host 替换为部署 host，path 保持不变。

```text
https://www.example.com/about?tab=team
→ https://www.mirror.example.net/about?tab=team

https://docs.example.com/guide/start
→ https://docs.mirror.example.net/guide/start
```

### 8.3 文件落点

无扩展名页面：

```text
/about
→ site/about/index.html
```

目录页面：

```text
/about/
→ site/about/index.html
```

带扩展名页面：

```text
/downloads/file.pdf
→ site/downloads/file.pdf
```

首页：

```text
/
→ site/index.html
```

### 8.4 Query 处理

默认原则：

- query 保留在 URL 中。
- query 不直接作为普通目录名。
- 所有 query 页面记录到 `query_manifest.json`。

如果同一路径不同 query 返回不同 HTML，启用 query 静态化：

```text
/search?q=agent
→ site/search/__query/q-agent/index.html
```

同时在 Nginx 配置中生成映射规则或在部署声明中标记需要人工确认。

## 9. 输出目录

```text
mirror/
  original/
    hosts/
      www.example.com/
        site/
        assets/
          css/
          js/
          images/
          videos/
          audio/
          fonts/
          files/
      docs.example.com/
        site/
        assets/
    snapshots/
      html/
      screenshots/
      visual/
    nginx/
      mirror.conf
      local-preview.conf
    manifest.json
    host_manifest.json
    link_graph.json
    asset_manifest.json
    query_manifest.json
    visual_report.json
    crawl_report.json
    DEPLOYMENT.md
```

## 10. Manifest 契约

### 10.1 `manifest.json`

```json
{
  "site_id": "example",
  "target_url": "https://www.example.com/",
  "root_domain": "example.com",
  "runtime_database": false,
  "created_at": "2026-06-13T00:00:00Z",
  "hosts": [
    {
      "source_host": "www.example.com",
      "local_port": 8300,
      "deploy_host": "www.mirror.example.net",
      "root": "hosts/www.example.com/site"
    },
    {
      "source_host": "docs.example.com",
      "local_port": 8301,
      "deploy_host": "docs.mirror.example.net",
      "root": "hosts/docs.example.com/site"
    }
  ],
  "pages": [
    {
      "url": "https://www.example.com/about",
      "source_host": "www.example.com",
      "source_path": "/about",
      "local_preview_url": "http://localhost:8300/about",
      "deploy_url": "https://www.mirror.example.net/about",
      "local_path": "hosts/www.example.com/site/about/index.html",
      "status_code": 200,
      "content_hash": "sha256",
      "render_mode": "browser",
      "internal_links": 12,
      "external_links": 4,
      "assets": 31
    }
  ]
}
```

### 10.2 `host_manifest.json`

```json
{
  "hosts": [
    {
      "source_host": "www.example.com",
      "pages": 120,
      "assets": 840,
      "local_port": 8300,
      "deploy_host": "www.mirror.example.net",
      "status": "verified"
    }
  ]
}
```

## 11. 部署声明

复刻 Agent 必须生成 `DEPLOYMENT.md`。

必须包含：

- 复刻目标。
- 原始 host 列表。
- 本地端口映射。
- 部署 host 映射。
- 静态文件目录。
- Nginx 配置路径。
- HTTPS 证书要求。
- DNS 配置说明。
- 外部链接处理策略。
- 无数据库运行声明。
- 更新部署步骤。
- 已知限制。

模板：

```markdown
# 静态复刻部署声明

本复刻产物为纯静态站点，不依赖数据库、后端 API 或运行时任务队列。

## Host 映射

| 原始 Host | 本地预览 | 部署 Host | 静态目录 |
| --- | --- | --- | --- |
| www.example.com | http://localhost:8300 | www.mirror.example.net | hosts/www.example.com/site |
| docs.example.com | http://localhost:8301 | docs.mirror.example.net | hosts/docs.example.com/site |

## 部署步骤

1. 将 `mirror/original` 上传到服务器 `/srv/mirror/original`。
2. 将 `nginx/mirror.conf` 放入 Nginx 配置目录。
3. 配置部署 Host 的 DNS。
4. 配置 HTTPS 证书。
5. 执行 `nginx -t`。
6. reload Nginx。

## 更新步骤

1. 运行复刻 Agent 增量同步。
2. 上传变化文件。
3. 如 host 映射变化，更新 Nginx 配置。
4. 执行 `nginx -t && nginx -s reload`。
```

增量同步要求：

- 默认读取上一次输出目录中的 `manifest.json`、`crawl_table.json`、`resource_table.json` 和 `rewrite_map.json`。
- 首次全量复刻或中断恢复时，可设置 `revalidate_completed_on_resume=false`，先跳过本地文件完整的已完成页面和资源，优先补完未完成队列。
- 每日巡检或正式增量同步时，应设置 `revalidate_completed_on_resume=true`，对已完成页面继续入队检查，但不默认重写。
- 失败项重试由 `retry_failed_on_resume` 控制；首次全量复刻尾部建议关闭，避免 404、外部重定向循环反复入队。每日巡检可打开，用于重新探测历史失败链接是否恢复。
- 优先使用 ETag / Last-Modified 发起条件请求；返回 `304 Not Modified` 时标记为 `unchanged`。
- 目标站不提供缓存标识时，允许下载后比较内容 hash；hash 相同则标记为 `unchanged`，不覆盖本地文件。
- 每日巡检模式下，即使页面未变化，也必须复查 `resource_table.json` 中已保存资源，保证图片、CSS、JS、字体、视频等资源单独变更时能被发现。
- 本地文件缺失时，不能仅凭旧表跳过，必须重新生成或下载。
- 需要强制全量重建时，使用 `--force-refresh` 或配置 `force_refresh=true`。
- 大站点可设置 `worker_count>1` 并发推进队列；请求层仍按 host 加锁和限速，避免单个子域被并发打爆。

## 12. Nginx 配置

复刻 Agent 必须生成两个配置：

- `nginx/local-preview.conf`：本地多端口预览。
- `nginx/mirror.conf`：线上部署。

### 12.1 本地多端口预览

```nginx
server {
    listen 8300;
    server_name localhost;

    root /absolute/path/mirror/original/hosts/www.example.com/site;
    index index.html;

    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }
}

server {
    listen 8301;
    server_name localhost;

    root /absolute/path/mirror/original/hosts/docs.example.com/site;
    index index.html;

    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }
}
```

### 12.2 线上部署

```nginx
server {
    listen 80;
    server_name www.mirror.example.net;

    root /srv/mirror/original/hosts/www.example.com/site;
    index index.html;

    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }

    location ~* \.(css|js|png|jpg|jpeg|gif|webp|svg|ico|woff|woff2|ttf|otf|mp4|webm|pdf)$ {
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

server {
    listen 80;
    server_name docs.mirror.example.net;

    root /srv/mirror/original/hosts/docs.example.com/site;
    index index.html;

    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }

    location ~* \.(css|js|png|jpg|jpeg|gif|webp|svg|ico|woff|woff2|ttf|otf|mp4|webm|pdf)$ {
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

HTTPS 证书由部署环境配置，复刻 Agent 只生成 HTTP 基础模板和 HTTPS 占位说明。

## 13. 完整性校验

复刻完成后必须检查：

- 每个 host 的首页可打开。
- 每个 host 的核心路径可打开。
- CSS 加载成功。
- JS chunk 加载成功。
- 图片、字体、视频加载成功。
- 内部链接能跳转到本地对应端口。
- 跨子域名链接能跳转到目标 host 对应端口。
- 外部链接保持原始地址。
- 原始 path 保持不变。
- 页面不存在明显空白。
- 控制台没有关键资源 404。
- `nginx/local-preview.conf` 和 `nginx/mirror.conf` 语法可验证。
- `crawl_table.json` 中没有无状态 URL。
- 所有已复刻页面中的同域链接都存在于 `crawl_table.json`。
- 同域链接的目标不是已复刻，就是有明确失败或跳过原因。
- `rewrite_map.json` 覆盖所有已发现页面。
- `resource_table.json` 中所有必须资源不是已保存，就是有明确失败原因。
- `completeness_report.json` 中 `residual_static_refs` 必须为空。
- 已生成 HTML/CSS/JS 中不应残留需要本地化的静态资源外链。
- `visual_report.json` 中超过阈值的页面必须进入人工或视觉模型复核。

## 13.1 视觉验收

视觉验收必须在复刻完成后执行，使用内部临时端口启动本地静态服务，不依赖正式预览端口。

输出内容：

- 原站截图。
- 本地复刻截图。
- 差异图。
- 像素差异比例。
- 可选视觉模型判断。

状态规则：

- `passed`：像素差异比例小于等于阈值。
- `needs_review`：像素差异比例超过阈值，需要修复或人工确认。
- `screenshot_failed`：原站或本地截图失败。

## 14. 状态机

host 状态：

```text
discovered → queued → crawling → rewriting → verifying → verified
```

页面状态：

```text
discovered → queued → fetching → fetched → assets_pending → rewritten → verified
```

失败状态：

```text
blocked_by_robots
fetch_failed
render_failed
asset_failed
rewrite_failed
verify_failed
query_mapping_needed
skipped_external
```

## 15. 每日增量同步

每日任务流程：

1. 读取上次静态 manifest。
2. 重新读取 sitemap 和入口页。
3. 发现新增 host。
4. 发现新增 URL。
5. 对已知页面做 hash 检查。
6. 对变化页面重新抓取。
7. 对变化资源重新下载。
8. 重写受影响页面。
9. 如 host 映射变化，重新生成 Nginx 配置。
10. 输出同步报告。

报告类型：

- `new_host`
- `new_page`
- `updated_page`
- `unchanged_page`
- `missing_page`
- `new_asset`
- `updated_asset`
- `broken_internal_link`
- `cross_host_link_rewritten`
- `external_link_kept`
- `nginx_config_updated`

## 16. 验收标准

MVP 验收：

- 至少能复刻主域名下 10 个页面。
- 若目标站存在子域名，至少能复刻 1 个子域名页面集合。
- 每个复刻 host 都有独立静态目录。
- 每个复刻 host 都有独立本地端口。
- 页面 CSS 不丢失。
- 页面主要图片不丢失。
- 内部链接本地跳转成功率大于 95%。
- 跨子域名链接本地端口跳转成功率大于 95%。
- 资源加载成功率大于 95%。
- 外部链接保持原地址。
- 原始 URL path 保持不变。
- 生成 `manifest.json`、`host_manifest.json`、`crawl_report.json`、`asset_manifest.json`、`query_manifest.json`。
- 生成 `DEPLOYMENT.md`。
- 生成 `nginx/local-preview.conf` 和 `nginx/mirror.conf`。
- 复刻站运行不依赖数据库。

正式版验收：

- 支持 1000 页以上站点。
- 支持多个子域名独立复刻。
- 支持动态渲染页面。
- 支持每日增量同步。
- 支持失败重试。
- 支持断点续跑。
- 支持资源去重。
- 支持多 host 独立部署。
- 支持 Nginx 配置自动更新。

## 17. 非目标

复刻 Agent 不做：

- 翻译。
- 中文排版。
- 视觉模型样式修复。
- 运行时数据库服务。
- 后端业务 API 复刻。
- 登录后的私有页面抓取，除非用户明确配置授权。
- 表单提交、购买、发帖、删除等有副作用操作。

## 18. 风险与约束

- 必须遵守授权范围和 robots 策略。
- 必须限制抓取速率。
- 必须避免无限 URL 参数导致队列爆炸。
- 必须避免下载超大视频导致磁盘失控。
- 必须记录所有失败原因，不能静默跳过。
- 对依赖服务端 API 的交互，只能保留静态页面效果，不能保证业务动作可用。
- 对 query 影响内容的页面，必须生成 `query_manifest.json` 并明确 Nginx 映射策略。

## 19. 完整性反思

当前复刻 Agent 方案覆盖了静态复刻的关键面：

- 域名范围：主域名和子域名。
- 本地预览：不同 host 使用不同端口。
- 部署方式：生成 Nginx 配置。
- 路径规则：path 保持不变，只替换 host。
- 存储方式：最终静态文件，不依赖数据库。
- 资源完整性：HTML、CSS、JS、图片、视频、字体、附件。
- 增量更新：基于静态 manifest 和 hash。

仍需在开发阶段重点验证：

- SPA 页面仅靠静态 HTML 是否足够。
- 依赖后端 API 的搜索、表单、登录是否需要降级提示。
- query 页面是否存在一参多页问题。
- 子域名数量很多时端口分配和 Nginx 配置规模是否可控。
- 大视频下载是否需要按站点配置限制。

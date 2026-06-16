# 授权网站复刻与翻译双 Agent 产品文档

## 0. 文档索引

本目录包含七份产品资料：

- `site_mirror_agent_product.md`：双 Agent 总览。
- `replication_agent_prd.md`：复刻 Agent 独立产品文档。
- `replication_deployment_nginx_template.md`：复刻 Agent 部署声明与 Nginx 配置模板。
- `replication_agent_usage.md`：复刻 Agent 使用说明。
- `localization_agent_prd.md`：翻译 Agent 独立产品文档，默认支持汉化，也支持其他目标语言。
- `translation_agent_usage.md`：翻译 Agent MVP 使用说明。
- `product_review_rounds.md`：三轮产品审查、反思和修正记录。

## 1. 产品定位

本产品拆分为两个独立智能体：

1. **复刻 Agent**：负责深度遍历授权目标网站，下载页面和资源，复刻出完整、可本地访问、链接通顺的原语言静态镜像站。主域名和主域名下子域名需要独立复刻，本地用不同端口预览，部署时只替换 host、保持 path 不变。
2. **翻译 Agent**：以复刻 Agent 的完整镜像结果为输入，进行目标语言翻译、链接适配、排版修正、视觉校验和样式优化。默认目标语言是简体中文，也支持其他语言。

拆分原则：复刻 Agent 不负责翻译，翻译 Agent 不直接抓取原站。这样可以保证抓取链路、资源链路、翻译链路和样式修复链路相互解耦。

产品边界：仅用于用户拥有、管理或已获得授权的网站。外部链接不复刻、不翻译目标 URL，保持原始跳转。

## 2. 总体流程

```text
目标网站 URL
  ↓
复刻 Agent
  ↓
完整原站镜像包
  ↓
翻译 Agent
  ↓
完整目标语言镜像包
  ↓
部署 / 每日增量同步 / 报告
```

## 3. 复刻 Agent

### 3.1 核心目标

复刻 Agent 的目标是生成一个完整、可访问、资源本地化的原站镜像。

它必须做到：

1. 不停向下深度遍历目标网站。
2. 只处理本域名和同一主域名下的子域名。
3. 复刻 HTML、CSS、JS、图片、视频、字体、图标、附件等资源。
4. 重写内部链接，使本地镜像站内跳转通顺。
5. 外部域名链接保持原始 URL。
6. 保存页面快照、资源 hash、链接关系和抓取状态。
7. 每天检查新增链接、新增内容和资源变化。
8. 每个主域名/子域名单独输出静态目录，并分配独立本地端口。
9. 生成部署声明和 Nginx 配置。
10. 复刻产物运行时不依赖数据库。

### 3.2 域名范围

默认使用 eTLD+1 作为主域名边界。

示例：

- 起始 URL：`https://www.anthropic.com/`
- 主域名：`anthropic.com`
- 允许：`www.anthropic.com`
- 允许：`docs.anthropic.com`
- 允许：`support.anthropic.com`
- 不允许：`claude.ai`
- 不允许：`youtube.com`

配置项：

```yaml
domain_policy:
  root_domain: anthropic.com
  include_subdomains: true
  include:
    - www.anthropic.com
  exclude:
    - status.anthropic.com
```

### 3.3 页面发现

发现来源：

- 首页入口。
- 页面内 `<a href>`。
- `sitemap.xml`。
- sitemap index。
- `robots.txt` 中声明的 sitemap。
- RSS / Atom。
- JS 渲染后的 DOM 链接。

去重规则：

- 识别 canonical URL。
- 去除 `utm_*`、`fbclid`、`gclid` 等追踪参数。
- 统一末尾 `/`。
- 统一大小写域名。
- 可配置是否保留 query 参数。

### 3.4 抓取策略

两级抓取：

1. **HTTP 抓取**：优先用于静态 HTML、资源文件、sitemap。
2. **浏览器抓取**：用于 Next.js、React、Vue、Webflow、懒加载资源和需要滚动加载的页面。

浏览器抓取要求：

- 等待 `domcontentloaded`。
- 必要时等待 `networkidle`。
- 自动滚动触发懒加载。
- 捕获最终 DOM。
- 捕获网络请求列表。
- 捕获 console error。
- 截图保存页面基线。

### 3.5 资源复刻

必须处理：

- HTML 中的 `src`、`href`、`srcset`、`poster`。
- CSS 中的 `url(...)`。
- 图片、视频、音频。
- 字体文件。
- favicon、apple touch icon、mask icon。
- Open Graph / Twitter 图片。
- JS chunk、CSS chunk。
- PDF、下载附件，可配置是否启用。

资源保存规则：

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
    snapshots/
      screenshots/
      html/
    manifest.json
    host_manifest.json
    DEPLOYMENT.md
    nginx/
      local-preview.conf
      mirror.conf
```

资源文件默认按 hash 命名：

```text
assets/css/sha256_xxx.css
assets/images/sha256_xxx.webp
```

### 3.6 链接重写

内部链接：

- 原站同 host URL 在本地改写为同端口同 path。
- 子域名 URL 在本地改写为对应子域名端口同 path。
- 部署模式下只替换 host，path 和 query 保持原样。

外部链接：

- 不抓取。
- 不改写内容。
- 保持原始 URL。

示例：

```text
https://www.anthropic.com/research
→ http://localhost:8300/research

https://docs.anthropic.com/guide/start
→ http://localhost:8301/guide/start

https://claude.ai/
→ https://claude.ai/
```

### 3.7 增量同步

每日任务：

1. 重新读取 sitemap。
2. 抓取入口页和高优先级页面。
3. 发现新增 URL。
4. 对页面和资源计算 hash。
5. 未变化则跳过。
6. 新增或变化则重新复刻。
7. 输出变更报告。

状态类型：

- `new_page`
- `updated_page`
- `unchanged_page`
- `missing_page`
- `redirect_changed`
- `new_asset`
- `updated_asset`
- `broken_internal_link`
- `external_link_kept`

## 4. 翻译 Agent

### 4.1 核心目标

翻译 Agent 的输入是复刻 Agent 生成的完整原站镜像包。它不直接访问目标原站，除非明确开启“缺失资源回补”模式。

它必须做到：

1. 保持复刻站结构不变。
2. 将原语言自然语言内容翻译为目标语言，默认目标语言是简体中文。
3. 保留品牌名、代码、变量、URL、邮箱、命令、产品名。
4. 生成完整目标语言镜像站。
5. 优化目标语言排版，重点处理翻译变长导致的遮挡、溢出和错位。
6. 检查翻译后样式溢出、重叠、错位。
7. 在安全范围内自动生成 CSS 修复补丁。

### 4.2 翻译范围

翻译：

- 文本节点。
- 标题。
- 按钮。
- 导航。
- 表单 label。
- `alt`。
- `title`。
- `aria-label`。
- `placeholder`。
- `meta description`。
- Open Graph 文案。

不翻译：

- `<script>`。
- `<style>`。
- `<code>`。
- `<pre>`。
- JSON 数据。
- URL。
- 邮箱。
- class / id。
- API 参数。
- 品牌名和术语表锁定词。

### 4.3 翻译模型

翻译模型配置：

```text
ANTHROPIC_API_URL=https://api.z.ai/api/anthropic
TRANSLATION_MODEL=glm-5.1
```

密钥只从环境变量或密钥管理读取，不写入代码或文档。

### 4.4 术语表

支持项目级术语表：

```yaml
glossary:
  Anthropic: Anthropic
  Claude: Claude
  API: API
  Agent: 智能体
  Workflow: 工作流
  Research: 研究
```

### 4.5 中文排版优化

基础优化：

- 中文字体 fallback。
- 中文标点。
- 中英文空格策略。
- 长英文单词换行。
- 按钮文本换行策略。
- 导航栏中文长度适配。
- 移动端菜单检查。

推荐注入独立 CSS 补丁：

```text
localized/
  patches/
    zh-layout.css
```

避免直接大规模改原站 CSS。

### 4.6 视觉校验

输入：

- 原始镜像截图。
- 中文镜像截图。
- DOM 结构。
- 控制台错误。
- 资源加载状态。

检查：

- 文本是否溢出。
- 元素是否重叠。
- 是否出现异常横向滚动。
- 图片和视频是否加载失败。
- 首屏是否明显错位。
- 移动端和桌面端是否都可用。

视觉模型配置：

```text
VISION_API_URL=https://ark.cn-beijing.volces.com/api/v3
VISION_MODEL=doubao-seed-1-6-flash-250828
```

密钥只从环境变量或密钥管理读取。

### 4.7 自动修复策略

只允许小范围修复：

- `word-break`
- `overflow-wrap`
- `white-space`
- `line-height`
- `min-width`
- `max-width`
- `height: auto`
- 中文字体 fallback

禁止默认操作：

- 重写整站布局。
- 删除 DOM。
- 删除大块 CSS。
- 改业务 JS。
- 改交互逻辑。

每次修复必须：

1. 生成补丁文件。
2. 记录修复原因。
3. 重新截图验证。
4. 可回滚。

## 5. 两个 Agent 的交付物

### 5.1 复刻 Agent 输出

```text
mirror/original/
  site/
  assets/
  snapshots/
  manifest.json
  crawl_report.json
  link_graph.json
  asset_manifest.json
```

`manifest.json` 必须包含：

- 原始 URL。
- 本地路径。
- 页面 hash。
- 资源 hash。
- 抓取时间。
- 状态码。
- 页面标题。
- 内部链接。
- 外部链接。

### 5.2 翻译 Agent 输出

```text
mirror/zh-CN/
  hosts/
  snapshots/
  reports/
  cache/
  glossary/
  nginx/
  manifest.json
  DEPLOYMENT.md
```

翻译 Agent 默认复用 `mirror/original` 中的本地资源，只在必要时生成目标语言补丁资源。

## 6. 数据模型

复刻 Agent 的最终产物不使用数据库，依赖静态文件和 JSON manifest 即可运行。SQLite / PostgreSQL 只作为可选的任务管理后台，不是复刻站运行依赖。

如果后续需要 Web 控制台或多任务管理，可以引入数据库；但静态复刻包必须脱离数据库独立部署。

核心表：

- `sites`：站点配置，可选后台表。
- `crawl_runs`：复刻任务批次。
- `pages`：页面 URL、本地路径、状态、hash。
- `assets`：资源 URL、本地路径、类型、hash。
- `links`：页面链接关系。
- `localization_runs`：翻译任务批次。
- `translations`：原文 hash、译文、模型、术语表版本。
- `layout_issues`：样式问题。
- `patches`：自动修复补丁。
- `sync_reports`：每日同步报告。

## 7. MVP 范围

### 7.1 复刻 Agent MVP

1. 输入目标 URL。
2. 读取 robots 和 sitemap。
3. 限定同主域名和子域名。
4. 抓取最多 N 个页面。
5. 下载 HTML、CSS、JS、图片、字体。
6. 按 host 分目录输出静态站。
7. 为每个 host 分配本地预览端口。
8. 重写内部链接和资源路径，保持 path 不变。
9. 生成 `mirror/original`。
10. 生成部署声明和 Nginx 配置。
11. 输出链接和资源报告。

### 7.2 翻译 Agent MVP

1. 读取 `mirror/original/manifest.json`。
2. DOM 级翻译 HTML。
3. 复用本地资源。
4. 注入中文排版补丁 CSS。
5. 生成 `mirror/zh-CN`。
6. 输出翻译报告。
7. 对关键页面做截图校验。

## 8. 开发顺序

1. 先开发复刻 Agent。
2. 用 Anthropic 做 10 页以内验证。
3. 确认资源完整性和本地链接通顺。
4. 再开发翻译 Agent。
5. 加入翻译缓存和术语表。
6. 加入视觉校验。
7. 最后做每日增量同步。

## 9. 关键判断

这次 Anthropic 验证暴露的问题正好说明拆分是必要的：

- 样式丢失属于复刻 Agent 的资源本地化问题。
- 没有目标语言内容属于翻译 Agent 的翻译产物问题。
- 两者不应混在一个流程里排查。

因此后续开发应先保证复刻 Agent 产出“完整、可打开、样式不丢、链接通顺”的原站镜像，再让翻译 Agent 处理目标语言翻译和排版修正。

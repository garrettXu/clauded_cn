# 翻译 Agent 产品文档

## 1. 产品定义

翻译 Agent 是一个面向复刻站点目录的多语言本地化智能体。它与复刻 Agent 是平行关系：复刻 Agent 负责把授权网站完整复刻为静态目录，翻译 Agent 只接收复刻后的完整目录，对页面内容进行目标语言翻译、链接适配、中文/多语言排版修复、视觉校验和可部署产物生成。

默认目标语言是简体中文，也支持繁体中文、日文、韩文、英文改写、法语、德语、西班牙语等其他语言。产品核心优势不是单纯翻译，而是在翻译后保证页面仍然可读、可点、样式尽量不被破坏。

翻译 Agent 不直接抓取目标原站，不负责复刻缺失资源，不改变原站业务逻辑。

## 2. 产品目标

用户给出一个复刻 Agent 已生成的完整目录后，翻译 Agent 自动完成：

1. 读取复刻目录中的页面、资源、manifest、链接图和本地预览配置。
2. 抽取所有可翻译文本，保留结构、代码、URL、品牌名和术语。
3. 按目标语言批量翻译，并保持同一术语、同一按钮、同一导航的一致性。
4. 把译文写回 HTML 和可安全处理的元数据字段。
5. 保持原始路径结构、资源引用和站内链接通顺。
6. 生成目标语言独立静态站点目录。
7. 使用浏览器截图和视觉模型检查翻译后是否出现遮挡、溢出、重叠、错位、横向滚动、按钮不可点等问题。
8. 在安全范围内自动生成样式补丁，并重复校验直到通过或进入人工复核。
9. 生成翻译报告、样式修复报告、视觉校验报告和人工复核清单。
10. 在复刻 Agent 每日增量更新后，只翻译变化部分并复用历史缓存。

## 3. 适用场景

适合：

- 已获得授权的网站镜像本地化。
- SaaS 官网、文档站、博客、帮助中心、状态页、营销页、静态产品页。
- 复刻后站点的汉化、繁化、日文化、韩文化或多语言版本生成。
- 希望翻译后保持页面视觉质量的静态站点。

不适合：

- 未授权网站内容复制和商业发布。
- 需要登录后才能完整访问的动态系统。
- 强依赖后端接口和实时数据的应用后台。
- 需要人工法务、医疗、金融审校才能发布的高风险内容。

## 4. 角色关系

```text
授权目标站
  ↓
复刻 Agent
  ↓
mirror/original/
  ↓
翻译 Agent
  ↓
mirror/{locale}/
  ↓
本地预览 / 部署 / 增量更新
```

边界原则：

- 复刻 Agent 负责发现页面、下载资源、重写原语言镜像链接。
- 翻译 Agent 负责翻译、目标语言排版、视觉校验和翻译产物部署说明。
- 翻译 Agent 不反向修改 `mirror/original/`。
- 翻译 Agent 的所有输出写入目标语言目录，例如 `mirror/zh-CN/`。
- 原站缺失资源必须由复刻 Agent 修复，翻译 Agent 只在用户显式开启回补模式时尝试补齐。

## 5. 输入契约

标准输入目录：

```text
mirror/original/
```

必须存在：

```text
mirror/original/
  hosts/
  manifest.json
  host_manifest.json
  link_graph.json
  asset_manifest.json
```

推荐存在：

```text
mirror/original/
  crawl_table.json
  resource_table.json
  rewrite_map.json
  query_manifest.json
  completeness_report.json
  snapshots/
    html/
    screenshots/
  nginx/
    local-preview.conf
    mirror.conf
```

如果关键 manifest 缺失，翻译 Agent 必须先执行输入诊断：

- 可以从 `hosts/*/site/**/*.html` 重建页面索引。
- 可以从 HTML 重建基础链接关系。
- 不能假设缺失资源已经完整。
- 必须在报告中标记 `input_manifest_rebuilt=true`。

## 6. 输出契约

默认输出目录：

```text
mirror/
  zh-CN/
    hosts/
      www.example.com/
        site/
        assets/
        patches/
          locale-layout.css
      docs.example.com/
        site/
        assets/
        patches/
          locale-layout.css
    snapshots/
      screenshots/
        before/
        after/
        diff/
    reports/
      translation_report.json
      layout_report.json
      visual_report.json
      review_queue.json
      increment_report.json
    cache/
      translation_cache.json
      segment_index.json
      page_fingerprints.json
    glossary/
      project_glossary.yml
    nginx/
      local-preview.conf
      mirror.conf
    manifest.json
    DEPLOYMENT.md
```

输出要求：

- 目录结构和 `original/hosts/{host}/site` 对齐。
- 页面 path 保持不变。
- 资源默认复用 original 中的本地资源，必要时复制到目标语言目录或使用相对路径引用。
- 每个目标语言都有独立 manifest 和部署说明。
- 不把模型 API 密钥写入任何输出文件。

## 7. 配置设计

示例配置：

```yaml
site_id: example
input_root: mirror/original
output_root: mirror/zh-CN

locale:
  source_language: en
  target_language: zh-CN
  target_language_name: 简体中文
  default_timezone: Asia/Shanghai
  preserve_brand_voice: true
  translation_style: concise_professional

scope:
  include_hosts:
    - www.example.com
    - docs.example.com
  exclude_paths:
    - /legal/archive
  include_file_patterns:
    - "**/*.html"

translation:
  provider: openai_compatible
  model: "${TRANSLATION_MODEL}"
  api_url_env: TRANSLATION_API_URL
  api_key_env: TRANSLATION_API_KEY
  batch_size_chars: 6000
  max_retries: 3
  cache_enabled: true
  human_locked_cache_wins: true

vision_review:
  enabled: true
  provider: openai_compatible
  model: "${VISION_MODEL}"
  api_url_env: VISION_API_URL
  api_key_env: VISION_API_KEY
  viewports:
    - name: desktop
      width: 1440
      height: 900
    - name: tablet
      width: 768
      height: 1024
    - name: mobile
      width: 390
      height: 844
  sample_policy: all_key_pages_then_changed_pages

layout_fix:
  auto_patch: true
  max_patch_rounds: 3
  patch_mode: css_only
  allow_dom_text_shortening: false
  require_visual_pass: true

deployment:
  generate_nginx: true
  local_port_offset: 100
  deploy_host_suffix: ""
```

密钥要求：

- 只允许从环境变量或密钥管理器读取。
- 不写入代码、文档、manifest、日志、缓存、报告。
- 错误日志中必须脱敏 API URL query 和 Authorization 头。

## 8. 核心流程

```text
读取配置
  ↓
输入目录诊断
  ↓
建立页面清单和资源清单
  ↓
抽取 DOM 文本段
  ↓
应用术语表和跳过规则
  ↓
查缓存
  ↓
调用翻译模型
  ↓
译文质量校验
  ↓
写回 HTML
  ↓
重写目标语言内部链接
  ↓
注入目标语言排版补丁
  ↓
启动本地预览
  ↓
浏览器截图和 DOM 布局检测
  ↓
视觉模型评审
  ↓
生成 CSS 修复补丁
  ↓
重复校验
  ↓
输出报告和部署文件
```

## 9. DOM 翻译策略

### 9.1 翻译对象

必须翻译：

- 普通文本节点。
- `<title>`。
- 导航、按钮、页脚、卡片、表单 label。
- `alt`。
- `title`。
- `aria-label`。
- `placeholder`。
- `meta[name="description"]`。
- Open Graph 和 Twitter 文案。
- JSON-LD 中明确的可展示文案，例如 `name`、`description`，但必须谨慎处理。

可配置翻译：

- 图片中的文字，默认只记录待人工处理。
- SVG `<text>`。
- `data-*` 中被前端展示的文案。
- 内联 JSON 中的 UI 文案。

禁止默认翻译：

- `<script>` 整体内容。
- `<style>`。
- `<code>`。
- `<pre>`。
- URL、邮箱、文件路径。
- class、id、data tracking key。
- API 参数、命令、环境变量。
- 版权声明中的公司名、产品名，除非术语表指定。
- 数字、货币、版本号、日期格式，除非配置启用本地化格式转换。

### 9.2 文本段分组

翻译 Agent 不能简单逐节点翻译。需要按语义分组：

- 同一段落内的连续文本节点合并翻译。
- 按钮、导航、短标签单独翻译，避免模型扩写。
- 标题保留短促、有力的表达。
- 表格单元格按列语义批量翻译，保持术语一致。
- FAQ、文档正文按段落翻译，保留 Markdown/HTML 内联结构。

每个文本段生成稳定 ID：

```text
segment_id = sha256(page_path + dom_selector + source_text + attr_name)
```

用途：

- 写回定位。
- 缓存命中。
- 人工审校。
- 增量更新。

### 9.3 HTML 内联结构保护

翻译时需要保护内联标签：

```html
Build with <strong>ProductX</strong> and deploy faster.
```

发送给模型前转换为占位符：

```text
Build with <ph id="1">ProductX</ph> and deploy faster.
```

模型输出必须保留占位符：

```text
使用 <ph id="1">ProductX</ph> 更快完成构建和部署。
```

写回时恢复为原标签。若占位符缺失、重复或顺序严重异常，该段进入 `invalid_model_output`，不得强行写回。

## 10. 术语表与品牌保护

术语表分三层：

1. 全局术语表：跨项目通用，例如 API、SDK、OAuth。
2. 项目术语表：品牌、产品、功能名。
3. 页面术语表：某些页面临时锁定的词。

示例：

```yaml
locked_terms:
  ProductX: ProductX
  ExampleAI: ExampleAI
  API: API
  SDK: SDK

translations:
  Agent: 智能体
  Workflow: 工作流
  Prompt: 提示词
  Console: 控制台
  Dashboard: 仪表盘

do_not_translate_patterns:
  - "[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}"
  - "https?://[^\\s]+"
  - "\\$[A-Z_][A-Z0-9_]*"
```

规则：

- 锁定词优先级高于模型。
- 人工修订后的术语优先级高于项目术语表。
- 同一个 source phrase 在同一项目中默认保持同译。
- 导航、按钮、CTA 的译文可以短于正文译文，避免挤压样式。

## 11. 翻译质量校验

模型输出后必须做程序化校验：

- 占位符完整。
- HTML 标签结构合法。
- 未翻译 URL、邮箱、代码、变量。
- 未破坏数字、版本号和单位。
- 译文不是空字符串。
- 译文语言符合目标语言。
- 译文长度异常时标记，例如按钮译文超过源文 2.5 倍。
- 同一 segment 的多次输出一致或有明确缓存版本。

质量状态：

```text
machine_translated
cache_hit
human_locked
needs_review
invalid_model_output
translation_failed
```

## 12. 链接与路径处理

原则：

- 页面路径不变。
- host 映射沿用复刻 Agent 的 host 结构。
- 目标语言目录独立。
- 站内链接指向目标语言站内对应页面。
- 外部链接保持原始 URL。
- 资源链接默认指向本地复刻资源。

示例：

```text
original:
mirror/original/hosts/www.example.com/site/about/index.html

zh-CN:
mirror/zh-CN/hosts/www.example.com/site/about/index.html
```

本地预览端口可以在复刻端口基础上偏移：

```text
original www.example.com: 8300
zh-CN    www.example.com: 8400
ja-JP    www.example.com: 8500
```

内部链接重写：

```text
http://localhost:8300/about
→ http://localhost:8400/about

https://www.example.com/about
→ 本地预览时 http://localhost:8400/about
→ 部署时目标语言 host 的 /about
```

## 13. 多语言策略

每种语言独立输出：

```text
mirror/
  original/
  zh-CN/
  zh-TW/
  ja-JP/
  ko-KR/
```

语言配置差异：

- `zh-CN`：优先简洁、避免过长 CTA、注入中文字体 fallback。
- `zh-TW`：繁体术语表独立，不从简体机械转换作为最终稿。
- `ja-JP`：处理无空格文本换行，谨慎压缩按钮文案。
- `ko-KR`：关注长词导致按钮宽度变化。
- `de-DE`：重点处理长单词和导航溢出。
- `ar`、`he`：需要 RTL 支持，MVP 不默认启用，必须单独设计。

MVP 支持 LTR 语言。RTL 语言进入二期，因为它涉及方向、布局、图标方向和交互习惯变化。

## 14. 样式修复策略

翻译后最常见问题：

- 中文/目标语言文本比英文长，按钮撑破。
- 导航项换行后遮挡下方内容。
- 卡片固定高度导致文本被截断。
- `white-space: nowrap` 导致移动端横向滚动。
- 字体 fallback 不一致导致行高变化。
- 绝对定位文字在不同语言中遮挡图片或按钮。
- Hero 标题换行后首屏内容被挤出。
- 表格列宽不足。
- 表单 placeholder 过长。

基础补丁：

```css
:root {
  --locale-font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

html[lang="zh-CN"] body {
  font-family: var(--locale-font-sans);
  text-rendering: optimizeLegibility;
}

html[lang="zh-CN"] button,
html[lang="zh-CN"] a,
html[lang="zh-CN"] p,
html[lang="zh-CN"] h1,
html[lang="zh-CN"] h2,
html[lang="zh-CN"] h3,
html[lang="zh-CN"] li {
  overflow-wrap: anywhere;
}
```

允许自动修复：

- `font-family`。
- `font-size` 小范围下调。
- `line-height`。
- `letter-spacing: 0`。
- `word-break`。
- `overflow-wrap`。
- `white-space`。
- `min-width`、`max-width`。
- `height: auto`、`min-height`。
- `gap`、`padding` 小范围调整。
- 移动端 media query。
- 固定高度容器改为最小高度。

禁止自动修复：

- 删除 DOM。
- 删除 CSS 文件。
- 大范围重写布局。
- 重写业务 JS。
- 修改表单提交逻辑。
- 改变路由结构。
- 隐藏重要文本。
- 把可点击区域缩小到不可用。
- 为了通过截图校验而牺牲可访问性。

补丁要求：

- 每条补丁必须记录来源页面、触发问题、selector、修改前后、生成轮次。
- 补丁写入 `patches/locale-layout.css`，不直接改原 CSS。
- 可按 host 生成补丁，避免不同 host 相互污染。
- 自动补丁最多 3 轮，超过后进入人工复核。

## 15. 视觉校验设计

视觉校验由三部分组成：

1. 程序化布局检测。
2. 浏览器截图对比。
3. 视觉模型判断。

### 15.1 程序化检测

通过浏览器执行脚本检查：

- `document.body.scrollWidth > window.innerWidth`。
- 元素文字是否被 `overflow:hidden` 截断。
- 元素 bounding box 是否异常重叠。
- 可点击元素尺寸是否过小。
- 图片自然尺寸是否为 0。
- 关键资源是否 404。
- console error。
- 页面是否空白。

### 15.2 截图策略

视口：

```text
desktop: 1440x900
tablet: 768x1024
mobile: 390x844
```

页面范围：

- 首页必测。
- 每个 host 的关键入口页必测。
- 导航、定价、文档、表单、下载、博客详情页优先。
- 增量模式只测变化页和受链接/样式补丁影响的页面。
- 大站点可先抽样，正式发布前关键路径全量测。

截图保存：

```text
snapshots/screenshots/before/{host}/{viewport}/{page_hash}.png
snapshots/screenshots/after/{host}/{viewport}/{page_hash}.png
snapshots/screenshots/diff/{host}/{viewport}/{page_hash}.png
```

### 15.3 视觉模型输入

视觉模型请求包含：

```json
{
  "page_url": "http://localhost:8400/about",
  "source_screenshot": "before.png",
  "localized_screenshot": "after.png",
  "viewport": "mobile",
  "target_language": "zh-CN",
  "dom_findings": [
    {
      "type": "horizontal_scroll",
      "selector": "body",
      "value": "scrollWidth=428 viewport=390"
    }
  ],
  "console_errors": [],
  "key_selectors": [
    "header",
    "nav",
    "main",
    "footer"
  ]
}
```

视觉模型输出必须是结构化 JSON：

```json
{
  "pass": false,
  "severity": "high",
  "issue_type": "text_overlap",
  "description": "移动端导航展开后中文菜单遮挡主按钮",
  "selector_hint": "header nav",
  "suggested_fix": "减小导航项间距，并允许菜单项换行",
  "requires_manual_review": false
}
```

## 16. LLM 与视觉模型职责划分

翻译模型负责：

- 语义翻译。
- 术语一致性。
- 保持占位符。
- 输出简洁 CTA 候选。
- 对过长短文案给出短译版本。

视觉模型负责：

- 判断截图是否有明显视觉问题。
- 指出问题区域。
- 给出修复方向。
- 判断修复后是否通过。

程序规则负责：

- DOM 抽取和写回。
- 占位符校验。
- 链接重写。
- CSS 补丁落盘。
- 报告、缓存、状态机。

不要让模型直接改整页 HTML。模型只能给出翻译结果、短译建议、问题判断和有限修复建议；最终写文件必须由程序按规则执行。

## 17. 自动修复闭环

```text
渲染目标语言页面
  ↓
程序化检测发现问题
  ↓
截图交给视觉模型
  ↓
生成候选 CSS 补丁
  ↓
应用到 locale-layout.css
  ↓
重新渲染截图
  ↓
再次检测
  ↓
通过 / 继续下一轮 / 人工复核
```

补丁生成优先级：

1. 通用语言补丁。
2. host 级补丁。
3. 页面类型补丁，例如 header、card、pricing、footer。
4. 单页面 selector 补丁。

如果同一 selector 连续 2 轮修复仍失败，停止自动修复并进入 `needs_manual_review`。

## 18. 状态机

页面状态：

```text
pending
→ scanning
→ text_extracted
→ translating
→ translated
→ applying_translation
→ links_rewritten
→ layout_patch_injected
→ browser_checking
→ vision_reviewing
→ verified
```

失败状态：

```text
input_missing
parse_failed
translation_failed
invalid_model_output
apply_failed
link_rewrite_failed
browser_render_failed
layout_failed
visual_review_failed
needs_manual_review
skipped_by_scope
```

状态要求：

- 每个页面必须有最终状态。
- 失败页面必须有原因、日志路径和建议处理方式。
- 不允许出现已发现但无状态页面。

## 19. 缓存与增量

缓存键：

```text
sha256(source_text + source_language + target_language + glossary_version + model + style_profile)
```

缓存值：

```json
{
  "source": "Try ProductX",
  "target": "试用 ProductX",
  "source_language": "en",
  "target_language": "zh-CN",
  "model": "translation-model",
  "glossary_version": "v3",
  "style_profile": "concise_professional",
  "status": "machine_translated",
  "locked": false,
  "updated_at": "2026-06-13T00:00:00Z"
}
```

增量触发：

- 新增页面。
- 页面 content hash 变化。
- 可翻译文本 segment hash 变化。
- 术语表版本变化。
- 翻译风格配置变化。
- 样式补丁变化。
- 模型版本策略变化。

增量复用：

- 页面未变且补丁未变，直接复用目标语言 HTML。
- 页面变但 segment 未变，复用缓存译文。
- 人工锁定译文永远优先。
- 删除页面同步删除目标语言对应页面或标记为 stale，具体由配置决定。

## 20. 人工审校

人工审校不是 MVP 必须有 UI，但数据结构必须预留。

进入人工复核的情况：

- 模型输出非法。
- 术语冲突。
- 短按钮译文过长且无法自动缩短。
- 视觉模型高危问题无法自动修复。
- 法律、合规、价格、医疗、金融等敏感页面。
- 图片文字需要重新设计。

`review_queue.json` 示例：

```json
{
  "items": [
    {
      "id": "seg_123",
      "type": "translation",
      "page": "hosts/www.example.com/site/pricing/index.html",
      "source": "Start building today",
      "machine_target": "立即开始构建",
      "reason": "cta_length_risk",
      "status": "pending"
    },
    {
      "id": "vis_456",
      "type": "layout",
      "page": "hosts/www.example.com/site/index.html",
      "viewport": "mobile",
      "selector_hint": "header nav",
      "reason": "text_overlap_after_patch_rounds",
      "status": "pending"
    }
  ]
}
```

## 21. 报告设计

### 21.1 `translation_report.json`

```json
{
  "site_id": "example",
  "locale": "zh-CN",
  "run_id": "translate_20260613_001",
  "pages_total": 120,
  "pages_translated": 118,
  "pages_failed": 2,
  "segments_total": 8420,
  "segments_cache_hit": 5100,
  "segments_model_translated": 3200,
  "segments_skipped": 120,
  "segments_needs_review": 18,
  "glossary_version": "v3",
  "model": "translation-model"
}
```

### 21.2 `layout_report.json`

```json
{
  "locale": "zh-CN",
  "pages_checked": 40,
  "issues_total": 7,
  "auto_fixed": 5,
  "needs_manual_review": 2,
  "issues": [
    {
      "page": "/pricing/",
      "viewport": "mobile",
      "severity": "high",
      "type": "text_overflow",
      "selector": ".pricing-card .button",
      "patch_file": "hosts/www.example.com/patches/locale-layout.css",
      "status": "fixed"
    }
  ]
}
```

### 21.3 `visual_report.json`

```json
{
  "locale": "zh-CN",
  "vision_model": "vision-model",
  "screenshots_total": 120,
  "passed": 113,
  "failed": 7,
  "critical_failures": 0,
  "items": [
    {
      "page": "/docs/start/",
      "viewport": "tablet",
      "pass": false,
      "severity": "medium",
      "issue_type": "heading_wrap",
      "selector_hint": "main h1",
      "requires_manual_review": false
    }
  ]
}
```

## 22. 部署设计

翻译 Agent 必须生成目标语言部署说明：

```text
mirror/zh-CN/DEPLOYMENT.md
```

必须包含：

- 输入 original 版本。
- 目标语言。
- host 映射。
- 本地预览端口。
- 部署目录。
- Nginx 配置路径。
- 外部链接策略。
- 资源复用策略。
- 翻译覆盖率。
- 视觉校验结果。
- 未解决人工复核项。

本地预览 Nginx：

```nginx
server {
    listen 8400;
    server_name localhost;

    root /absolute/path/mirror/zh-CN/hosts/www.example.com/site;
    index index.html;

    location / {
        try_files $uri $uri/ $uri/index.html =404;
    }
}
```

## 23. 错误处理

错误处理协议：

1. 诊断：明确是输入缺失、解析失败、模型失败、写回失败、渲染失败还是视觉失败。
2. 设计：选择最小修复路径，例如重建索引、跳过单段、重试模型、生成 CSS 补丁。
3. 反思：确认修复不会破坏路径、链接、业务 JS 和原始目录。
4. 研究：当模型接口、浏览器行为或 CSS 问题不确定时再查证。
5. 执行：只对目标语言输出目录做最小必要修改。

不可接受的处理：

- 模型失败后把原文直接当译文并标记成功。
- 视觉失败后隐藏问题区域。
- 为通过校验删除内容。
- 修改 original 目录。
- 吞掉错误不写报告。

## 24. 安全与合规

- 只处理用户授权的复刻产物。
- 不默认访问原站。
- 不执行登录、购买、提交表单、发帖等有副作用操作。
- 不翻译或改写法律事实、价格事实、医疗建议、金融承诺，除非只是忠实翻译并标记需人工审校。
- 不保存 API 密钥。
- 不把页面内容发送给无配置授权的第三方服务。
- 日志中不保留敏感请求头、cookie、token。

## 25. MVP 范围

MVP 必须实现：

1. 读取 `mirror/original`。
2. 识别所有 HTML 页面。
3. DOM 文本抽取和安全跳过规则。
4. 简体中文翻译。
5. 术语表锁定。
6. 翻译缓存。
7. 写回目标语言 HTML。
8. 站内链接切换到目标语言本地预览端口。
9. 注入基础中文 CSS 补丁。
10. 生成 `translation_report.json`。
11. 对至少桌面和移动两个视口截图检查。
12. 输出 `layout_report.json` 和 `visual_report.json`。

MVP 不做：

- 图片中文字自动重绘。
- RTL 语言。
- 复杂 JS 内联文案自动改写。
- 人工审校 UI。
- 大规模 CSS 重构。

## 26. 正式版范围

正式版应实现：

- 多语言输出。
- 每日增量翻译。
- 视觉模型自动评审。
- CSS 自动补丁多轮闭环。
- 人工锁定译文回写缓存。
- 关键页面全量视觉检查。
- 图片文字 OCR 识别并进入人工队列。
- 多 host 多端口部署配置。
- 翻译质量评分和风险分级。
- 失败任务可恢复。

## 27. 验收标准

MVP 验收：

- 能处理复刻 Agent 输出的至少 10 个页面。
- 文本节点翻译覆盖率大于 90%。
- 术语表锁定词 100% 不被错误翻译。
- HTML 标签和占位符不被破坏。
- 内部链接目标语言站内跳转成功率大于 95%。
- 资源加载成功率大于 95%。
- 首页桌面和移动视口无明显遮挡、横向滚动和空白。
- 生成完整报告。

正式版验收：

- 翻译覆盖率大于 98%。
- 关键页面视觉校验通过率大于 95%。
- 严重视觉问题为 0。
- 自动修复补丁可追踪、可回滚。
- 支持每日增量翻译。
- 支持人工修订译文锁定。
- 支持至少 3 种目标语言配置。
- 不修改 `mirror/original`。

## 28. 关键风险与对策

| 风险 | 表现 | 对策 |
| --- | --- | --- |
| 译文变长破坏布局 | 按钮溢出、导航换行遮挡 | 短文案策略、CSS 补丁、视觉闭环 |
| 模型破坏 HTML | 标签错乱、占位符丢失 | 占位符协议、结构校验、失败不写回 |
| 术语不一致 | 同一产品名多种译法 | 术语表、缓存、人工锁定 |
| JS 文案遗漏 | 动态渲染文本仍是英文 | DOM 渲染后扫描、data/JSON 可配置处理 |
| 图片文字未翻译 | Banner 或截图中仍是英文 | OCR 识别并进入人工队列，二期支持重绘 |
| CSS 修复过度 | 页面布局被改坏 | 补丁白名单、轮次限制、只写 locale patch |
| 大站成本高 | 模型调用和截图多 | 缓存、增量、关键页优先、抽样策略 |
| 原始资源不完整 | 翻译站图片/CSS 丢失 | 输入完整性诊断，要求复刻 Agent 回补 |

## 29. 推荐实现模块

```text
translation_agent/
  config.py
  manifest_loader.py
  page_indexer.py
  dom_extractor.py
  placeholder_codec.py
  glossary.py
  translation_client.py
  translation_cache.py
  html_writer.py
  link_rewriter.py
  layout_patch.py
  preview_server.py
  browser_checker.py
  vision_reviewer.py
  report_writer.py
  incremental.py
```

模块职责：

- `manifest_loader`：读取和补全复刻产物索引。
- `dom_extractor`：抽取可翻译文本和属性。
- `placeholder_codec`：保护 HTML 内联结构。
- `translation_client`：调用翻译模型。
- `translation_cache`：缓存和人工锁定译文。
- `html_writer`：安全写回 HTML。
- `link_rewriter`：目标语言链接适配。
- `layout_patch`：生成和管理 CSS 补丁。
- `browser_checker`：截图、资源、DOM 布局检测。
- `vision_reviewer`：调用视觉模型评审截图。
- `report_writer`：统一输出报告。
- `incremental`：处理每日增量。

## 30. 产品结论

翻译 Agent 的核心不是“把英文替换成中文”，而是“在完整复刻目录上生成可发布的目标语言站点”。因此它必须同时具备四种能力：

1. 稳定的 DOM 级翻译能力。
2. 可控的术语和缓存体系。
3. 浏览器级样式检测能力。
4. LLM/视觉模型参与的排版修复闭环。

只要严格保持“不直接抓原站、不修改 original、路径不变、补丁可回滚、视觉校验不过不标记成功”这几个边界，翻译 Agent 就可以和复刻 Agent 平行协作，形成完整的“复刻 + 多语言本地化 + 可部署静态站”产品链路。

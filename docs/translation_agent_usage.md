# 翻译 Agent MVP 使用说明

## 1. 功能范围

当前 MVP 已支持：

- 读取复刻 Agent 输出的 `mirror/original`。
- 优先使用 `hosts/{host}/local_preview` 作为本地预览翻译源。
- 输出 `mirror/{locale}/hosts/{host}/site`。
- DOM 文本和常见属性翻译。
- 翻译缓存。
- 注入 `site/__locale/locale-layout.css`。
- 本地预览端口自动偏移，默认 `+100`。
- 生成 `manifest.json`、`DEPLOYMENT.md` 和 reports。

暂未实现：

- 视觉截图校验。
- 自动 CSS 多轮修复。
- 图片文字翻译。
- 人工审校 UI。

## 2. Dry-run 结构验证

```bash
.venv/bin/python scripts/translation_agent.py \
  output/replication_table_test/original \
  --output-root /tmp/translation_agent_validation/zh-CN \
  --locale zh-CN \
  --dry-run \
  --max-pages 2
```

dry-run 不调用模型，只用 `[zh-CN]` 前缀验证 DOM 写回、目录结构、缓存和报告。

## 3. 真实翻译

需要环境变量：

```bash
export TRANSLATION_API_URL="https://example.com/v1"
export TRANSLATION_API_KEY="..."
export TRANSLATION_MODEL="glm-5.1"
```

运行：

```bash
.venv/bin/python scripts/translation_agent.py \
  output/replication_table_test/original \
  --output-root output/translation_test/zh-CN \
  --locale zh-CN \
  --max-pages 2
```

如果输出目录已存在，追加：

```bash
--overwrite
```

## 4. 本地预览

```bash
.venv/bin/python scripts/serve_replica.py /tmp/translation_agent_validation/zh-CN
```

示例端口：

- `www.example.com`：`http://localhost:8600`
- `docs.example.com`：`http://localhost:8601`
- `status.example.com`：`http://localhost:8602`

## 5. 输出报告

```text
mirror/{locale}/
  reports/
    translation_report.json
    layout_report.json
    visual_report.json
    review_queue.json
  cache/
    translation_cache.json
    segment_index.json
```

`layout_report.json` 和 `visual_report.json` 当前只写入 MVP 占位状态，后续接入浏览器截图和视觉模型。

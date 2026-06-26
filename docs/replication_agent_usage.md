# 复刻 Agent 使用说明

## 1. 运行复刻

小范围验证：

```bash
.venv/bin/python scripts/replication_agent.py https://www.example.com/ \
  --site-id example \
  --out-dir output/replication_test \
  --max-pages-per-host 3 \
  --max-assets-per-host 50 \
  --max-depth 2 \
  --port-start 8400 \
  --timeout-seconds 10
```

完整复刻时不要设置资源数量上限，或显式设置为 `0`：

```bash
.venv/bin/python scripts/replication_agent.py https://www.example.com/ \
  --site-id example \
  --out-dir output/example_full \
  --max-assets-per-host 0 \
  --render-dynamic-pages \
  --visual-compare
```

如果 `completeness_report.json` 中 `residual_static_refs` 不为空，说明仍有图片、JS、CSS、字体、视频或其他静态资源没有成功本地化，不能认为复刻完成。

重复运行同一个 `--out-dir` 时默认进入增量模式：程序会读取已有的 `crawl_table.json`、`resource_table.json`、`rewrite_map.json` 和 `manifest.json`。每日巡检时设置 `crawl_policy.revalidate_completed_on_resume=true`，已完成页面和资源会先检查远端是否变化；未变化则标记为 `unchanged`，不重写本地文件。首次全量复刻中断后恢复时，可设置为 `false`，先跳过本地文件完整的已完成项，优先补完未完成队列。需要无视旧表全量重建时使用 `--force-refresh`。

使用配置文件：

```bash
.venv/bin/python scripts/replication_agent.py --config configs/replication_agent.example.json
```

首次使用动态渲染和视觉对比前安装运行依赖：

```bash
.venv/bin/python -m pip install playwright pillow
.venv/bin/python -m playwright install chromium
```

大站点建议在配置文件中设置 `crawl_policy.worker_count`，例如 `4` 或 `6`。并发只提升队列处理速度，每个 host 仍会按 `rate_limit_per_host` 限速。

中断恢复大站点时，如果历史失败主要是 404 或外部重定向循环，可设置 `crawl_policy.retry_failed_on_resume=false`，避免失败项反复入队；每日巡检再打开该选项。

## 2. 输出目录

```text
output/replication_test/original/
  hosts/
    www.example.com/
      site/
      local_preview/
    docs.example.com/
      site/
      local_preview/
  nginx/
    local-preview.conf
    mirror.conf
  manifest.json
  host_manifest.json
  asset_manifest.json
  link_graph.json
  query_manifest.json
  crawl_table.json
  resource_table.json
  rewrite_map.json
  completeness_report.json
  visual_report.json
  crawl_report.json
  DEPLOYMENT.md
```

`site/` 用于部署，`local_preview/` 用于本地端口预览。

## 2.1 完整性表单

复刻 Agent 使用表单闭环保证不漏页面：

- `crawl_table.json`：所有发现的页面，包含 pending、已完成、失败、跳过。
- `resource_table.json`：所有发现的资源，包含内容 hash、HTTP 缓存标识和本地路径。
- `rewrite_map.json`：所有页面的原始 URL、本地预览 URL、部署 URL 和文件路径。
- `completeness_report.json`：检查所有同域链接是否已进入表单，并确认目标状态。
- `residual_static_refs`：检查 HTML/CSS/JS 中残留的静态资源外链或缺失本地资源路径。

正式复刻时，应以 `completeness_report.json` 的 `complete=true` 作为完成标准。若为 `false`，需要查看 `pending_pages` 和 `unresolved_internal_links`。

增量检查规则：

- 如果远端返回 `304 Not Modified`，直接复用本地页面或资源。
- 如果远端没有 ETag / Last-Modified，则下载后比较内容 hash；hash 相同不重写文件。
- 每日巡检模式下，页面未变化时仍会独立检查 `resource_table.json` 中已保存的 CSS、JS、图片、字体、视频等资源，避免资源单独变化被漏掉。
- 如果本地文件缺失，即使旧表存在，也会重新生成或重新下载。

## 2.2 动态渲染与视觉验收

开启 `--render-dynamic-pages` 后，复刻 Agent 会用 Playwright 打开页面，等待 DOM 和网络执行，分段滚动触发懒加载，并安全点击菜单、折叠项、`aria-expanded=false` 等非提交型控件。最终复刻源使用浏览器执行后的 DOM。

开启 `--visual-compare` 后，复刻完成后会生成 `visual_report.json`：

- 原站截图：`snapshots/visual/{viewport}/{host}/source/`
- 本地复刻截图：`snapshots/visual/{viewport}/{host}/local/`
- 差异图：`snapshots/visual/{viewport}/{host}/diff/`
- 结果状态：`passed`、`needs_review`、`screenshot_failed`

视觉验收使用内部临时端口启动本地静态服务，不占用或依赖正式预览端口。

如果需要视觉模型辅助判断，在配置文件中设置 `visual_policy.use_vision_model=true`、`vision_api_url`、`vision_model`，并通过环境变量提供 API Key。

## 3. 本地预览

用内置预览服务：

```bash
.venv/bin/python scripts/serve_replica.py output/replication_test/original
```

或者使用生成的 Nginx 配置：

```bash
nginx -t -c /absolute/path/output/replication_test/original/nginx/local-preview.conf
```

## 4. 部署

查看生成的部署声明：

```bash
cat output/replication_test/original/DEPLOYMENT.md
```

部署 Nginx 配置：

```bash
cat output/replication_test/original/nginx/mirror.conf
```

## 5. 设计约束

- 复刻站最终是纯静态文件。
- 运行不依赖数据库。
- 原始 path 保持不变。
- 主域名和子域名分别使用独立端口预览。
- 外部域名链接保持原始地址。

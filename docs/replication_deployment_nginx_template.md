# 复刻 Agent 部署声明与 Nginx 配置模板

## 1. 部署声明

本复刻产物是纯静态站点，不依赖数据库、后端 API、Redis、任务队列或动态渲染服务。

复刻规则：

- 主域名完整复刻。
- 主域名下允许的子域名完整复刻。
- 每个原始 host 独立静态目录。
- 每个原始 host 本地独立端口。
- URL path 保持不变。
- 只将原始 host 替换为本地 host 或部署 host。
- 外部域名链接保持原始地址。

## 2. Host 映射示例

| 原始 Host | 本地预览 | 部署 Host | 静态目录 |
| --- | --- | --- | --- |
| www.example.com | http://localhost:8300 | www.mirror.example.net | `/srv/mirror/original/hosts/www.example.com/site` |
| docs.example.com | http://localhost:8301 | docs.mirror.example.net | `/srv/mirror/original/hosts/docs.example.com/site` |
| blog.example.com | http://localhost:8302 | blog.mirror.example.net | `/srv/mirror/original/hosts/blog.example.com/site` |

路径保持示例：

```text
https://www.example.com/about
→ http://localhost:8300/about
→ https://www.mirror.example.net/about

https://docs.example.com/guide/start?lang=en
→ http://localhost:8301/guide/start?lang=en
→ https://docs.mirror.example.net/guide/start?lang=en
```

## 3. 静态目录结构

```text
/srv/mirror/original/
  hosts/
    www.example.com/
      site/
      assets/
    docs.example.com/
      site/
      assets/
  manifest.json
  host_manifest.json
  asset_manifest.json
  link_graph.json
  query_manifest.json
  DEPLOYMENT.md
  nginx/
    local-preview.conf
    mirror.conf
```

## 4. 本地预览 Nginx 配置

文件：`mirror/original/nginx/local-preview.conf`

```nginx
server {
    listen 8300;
    server_name localhost;

    root /absolute/path/mirror/original/hosts/www.example.com/site;
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
    listen 8301;
    server_name localhost;

    root /absolute/path/mirror/original/hosts/docs.example.com/site;
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

## 5. 线上部署 Nginx 配置

文件：`mirror/original/nginx/mirror.conf`

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

## 6. HTTPS 部署说明

生产环境建议在 Nginx 外层或当前 Nginx 中配置 HTTPS。

HTTPS 配置由部署环境决定，复刻 Agent 只需要在 `DEPLOYMENT.md` 中声明：

- 需要为每个部署 host 配置证书。
- HTTP 到 HTTPS 的跳转策略由部署方决定。
- 如果原站有 HSTS，镜像站是否启用 HSTS 需要人工确认。

## 7. 更新部署步骤

1. 运行复刻 Agent 增量同步。
2. 上传变化的静态文件。
3. 如果新增 host，更新 DNS 和 Nginx server block。
4. 执行 `nginx -t`。
5. reload Nginx。
6. 检查 `crawl_report.json` 和 `asset_manifest.json`。

## 8. 验收命令

```bash
nginx -t -c /path/to/mirror/original/nginx/mirror.conf
curl -I http://localhost:8300/
curl -I http://localhost:8301/
```

## 9. 已知限制

- 纯静态复刻不能保证登录、搜索、提交表单、购物车等依赖后端 API 的业务动作可用。
- query 参数影响页面内容时，需要根据 `query_manifest.json` 增加映射规则。
- 第三方脚本可能因 CSP、跨域或授权限制无法本地完整运行。


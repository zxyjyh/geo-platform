# 豆包 GEO 内部网站 · 部署说明（第一阶段）

四个容器，都在 `deploy/docker-compose.yml` 里：

| 服务 | 作用 | 对外端口 |
|---|---|---|
| `mysql` | MySQL 8.4，utf8mb4 | 只绑 `127.0.0.1:3307`（排查用） |
| `api` | 启动时先 `alembic upgrade head`，再起 uvicorn | 不对外，只有 caddy 能连 |
| `worker` | 每天 10:00（北京时间）采集，每 60 秒处理页面上的"补跑今天" | 无 |
| `caddy` | HTTPS、前端静态文件、`/api/*` 反向代理 | 80 / 443 |

所有容器 `TZ=Asia/Shanghai`。代码里"哪一天"一律按北京时间算，不依赖容器时区。

## 一、上线前清单（逐项确认后再上线）

1. **轮换 `ARK_API_KEY`**：旧 Key 在对话里出现过，必须在火山方舟控制台作废，换一个新的。
2. **域名备案**：请运维确认子域名（如 `geo.<公司域名>`）所属域名已经 ICP 备案，并且备案的接入商和服务器所在云厂商是同一家；不是同一家要先做"新增接入"。
3. **出网**：在服务器上执行 `curl -sI https://ark.cn-beijing.volces.com`，确认能连通。
4. **80/443 端口**：安全组放行 80 和 443。Caddy 申请证书需要 80 端口可达。
5. **单价**：在火山方舟控制台查到"豆包搜索 Custom 版"的计费单价，上线后填进"设置 → 阈值与单价"，看板才会显示估算费用。

## 二、服务器上的步骤

```bash
# 1. 拿到代码（git clone 或拷贝整个仓库）
cd doubao-geo

# 2. 写 .env（不进仓库）
cp .env.example .env
#   SITE_DOMAIN=geo.<公司域名>
#   MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD：只用字母数字（会被拼进数据库连接串）
#   ARK_API_KEY：轮换后的新 Key
#   SECRET_KEY：python3 -c "import secrets; print(secrets.token_urlsafe(48))"
#   COOKIE_SECURE=true
chmod 600 .env

# 3. 构建并启动
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
#   国内拉不到 PyPI / npm 时：
#   docker compose -f deploy/docker-compose.yml --env-file .env build \
#     --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
#     --build-arg NPM_REGISTRY=https://registry.npmmirror.com
#   拉不到 Docker Hub 镜像（mysql / node / python / caddy）时，给 Docker 配镜像加速器

# 4. 建登录账号（交互输入两次密码）
docker compose -f deploy/docker-compose.yml exec api python -m app.cli create-user admin

# 5. （可选）导入 10-21 的试跑数据：只出现在"大模型回答记录"（轮次=试跑），不进概览指标
docker compose -f deploy/docker-compose.yml exec api python -m app.cli import-trial
```

浏览器打开 `https://<SITE_DOMAIN>` 登录。

## 三、上线后第一件事：服务器与本机的对照试跑（spec §4.3）

`api-custom` 会忽略 `user_location`，它有没有改用调用方 IP 判断地区，没有核实过。服务器和本机（深圳）的出口 IP 不同，结果可能不同。

```bash
# 立即在服务器上跑一轮（北京时间今天）
docker compose -f deploy/docker-compose.yml exec worker python -m app.cli run-daily --channel api-custom
# 和本机 10-21 的 trial 逐题对比信源域名的 Jaccard 和"澳觅是否被提及"
docker compose -f deploy/docker-compose.yml exec api python scripts/compare_rounds.py \
  --a-round trial --b-date <今天，YYYY-MM-DD> --channel api-custom
```

判断方式：
- 参照值：本机 trial 里 api-custom 和 api-plugin 两个渠道的逐题 Jaccard 均值是 0.23（两套搜索）。同一渠道、同一模型隔一天的自然波动有多大还没测过，所以**不要拿一次的数字下结论**。
- 如果服务器这一轮的 Jaccard 均值明显低、或"澳觅是否被提及"有好几题不一致，就在看板渠道标签旁注明"api-custom 的地区取决于服务器所在地"（由你判断要不要加）。

注意：`run-daily` 和 worker 是两个进程，**不要在 10:00 前后手动跑**，否则会和定时采集重叠，导致同一题重复调用。页面上的"补跑今天"由 worker 排队执行，没有这个问题。

## 四、日常运维

| 事项 | 命令 / 位置 |
|---|---|
| 看采集结果 | 页面"设置 → 采集任务"，或 `docker compose ... logs --tail 200 worker` |
| 补跑今天失败的题 | 页面"设置 → 采集任务 → 补跑今天"（只能补北京时间当天；补往日会把今天的回答记到那一天） |
| 改别名表 | 页面"设置 → 竞品别名表"：生成新版本并重算全部历史；也可 `exec api python -m app.cli recode` 按当前版本重算 |
| 备份数据库 | `docker compose ... exec mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" geo' > geo-$(date +%F).sql` |
| 原始响应 | 卷 `raw_data`（容器内 `/app/data/raw/daily/`），每题一个 JSON，是所有数字的原始依据，跟数据库一起备份 |
| 升级 | `git pull` 后重新 `up -d --build`；api 启动时自动迁移 |

**worker 只能起一个副本**：采集的串行保护只在进程内有效，两个 worker 会对同一天重复调用 API。

## 五、安全要点

- 密钥（`ARK_API_KEY`、`SECRET_KEY`、数据库密码）只在 `.env`，不进仓库、不进数据库、页面不显示。
- 登录失败限流按"用户名 + 客户端 IP"计数：Caddyfile 里的 `header_up X-Forwarded-For {remote_host}` 会用直连 IP 覆盖客户端自带的 `X-Forwarded-For`（Caddy 默认是追加，不加这行会被伪造头部绕过限流），api 开了 `--proxy-headers` 读取这个值。**不要**去掉这行，也不要在前面再加一层代理，除非相应调整信任链。
- `COOKIE_SECURE=true`：会话 cookie 只走 HTTPS。
- 没有公开页面；账号由管理员在"设置 → 账号"或 CLI 创建。

## 六、本机验收（开发用）

本机用 colima 跑 Docker：`colima start`。`.env` 里设 `SITE_DOMAIN=localhost`，Caddy 会用内部证书，浏览器访问 `https://localhost` 时要手动信任一次。本机不填 `ARK_API_KEY` 时，worker 会反复退出重启，这是预期行为（缺 Key 时 worker 拒绝启动）。

MySQL 冒烟测试：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d mysql
docker compose -f deploy/docker-compose.yml exec mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS geo_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"'
MYSQL_TEST_URL='mysql+pymysql://root:<root 密码>@127.0.0.1:3307/geo_test?charset=utf8mb4' \
  UV_PROJECT_ENVIRONMENT=.venv-app uv run pytest -m mysql -v
```

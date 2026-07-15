# 部署运维文档

## 1. 项目位置

本地项目目录：

```text
C:\Users\61655\Documents\Codex\2026-07-07\ni\work\tk_selection_app
```

线上服务器：

```text
120.26.207.89
```

线上后端目录：

```text
/opt/tk_selection/backend
```

## 2. 技术栈

- 桌面端：PySide6。
- 后端：FastAPI。
- ORM：SQLAlchemy。
- 本地数据库：SQLite。
- 线上数据库：MySQL。
- 鉴权：JWT。
- 定时任务：Linux systemd timer 或 cron。

## 3. 本地运行

### 后端

```powershell
.\start_backend.ps1
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

### 前端

```powershell
.\start_desktop.ps1
```

前端代码修改后，开发阶段优先直接运行源码 UI，不需要每次打包。

## 4. 线上后端部署

后端代码修改后，需要：

1. 上传修改后的文件到服务器。
2. 重启后端服务。
3. 检查服务状态。

常用命令：

```bash
systemctl restart tk-selection-backend
systemctl is-active tk-selection-backend
journalctl -u tk-selection-backend -n 100 --no-pager
```

如果只是前端代码修改，不需要部署后端。

## 5. 环境变量

线上后端环境变量文件：

```text
/etc/tk_selection/backend.env
```

常见配置：

- 数据库连接。
- JWT 密钥。
- 后端运行参数。

敏感信息不要写入 Git 仓库。

## 6. 数据库初始化

后端启动时会执行：

```text
backend/app/services/seed.py
```

初始化内容：

- 建表。
- 补运行时字段。
- 初始化 8 个选品维度。
- 初始化默认账号。
- 初始化占位模型配置。
- 初始化占位第三方 API 配置。
- 初始化选品提示词。

## 7. 重置选品属性

如果选品属性重复，可执行维护脚本：

```bash
cd /opt/tk_selection/backend
set -a && . /etc/tk_selection/backend.env && set +a
.venv/bin/python scripts/reset_selection_attributes.py
```

脚本会：

- 清空 `derived_product_attribute_scores`。
- 清空 `selection_attributes`。
- 重建 8 个标准维度。

## 8. FastMoss 每日任务

脚本：

```text
backend/scripts/daily_fastmoss_pipeline.py
```

业务要求：

- 每天 8:30 执行。
- 同步 FastMoss 日本区新品榜。
- 同步完成后触发衍生品生成。

手动执行：

```bash
cd /opt/tk_selection/backend
set -a && . /etc/tk_selection/backend.env && set +a
.venv/bin/python scripts/daily_fastmoss_pipeline.py
```

## 9. 日志检查

后端服务日志：

```bash
journalctl -u tk-selection-backend -n 200 --no-pager
```

FastMoss 同步日志：

```text
GET /api/fastmoss/sync-logs
```

任务状态：

```text
GET /api/pipeline/status
```

## 10. 打包桌面程序

当前桌面端使用 PySide6，可通过 PyInstaller 打包。

打包要求：

- 输出文件名保持固定，不要每次生成新名字。
- 如果旧程序进程占用，先关闭旧进程再覆盖。
- 默认全屏打开。

已有 spec 文件：

```text
desktop/TKCrossBorderAssistant.spec
```

## 11. 网络问题处理原则

本地网络和代理不稳定时：

- 不反复修本地代理。
- 直接判断是否为本地网络问题。
- 需要测试外部 API 时优先在服务器执行。

服务器网络正常时：

- 模型调用、FastMoss 调用、1688 API 调用优先以服务器结果为准。

## 12. 常见故障

### 后端服务无法访问

检查：

```bash
systemctl is-active tk-selection-backend
journalctl -u tk-selection-backend -n 100 --no-pager
```

确认安全组：

- 服务器 8000 端口已放行。
- 防火墙允许访问。

### 前端提示请重新登录

说明 token 已失效。

处理：

- 重新登录。
- 后端 token 过期时间当前要求为 1 周。

### FastMoss invalid token

检查：

- 第三方 API 配置是否启用。
- FastMoss key 是否正确。
- 接口日期和筛选参数是否符合文档。

### 模型调用慢

检查：

- 是否误用了深度思考模型。
- 模型余额是否充足。
- `max_tokens` 是否过大。
- 服务器访问模型接口是否正常。


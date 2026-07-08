# TK 日本跨境智能选品系统 MVP

第一版可运行骨架，包含 FastAPI 后端和 PySide6 Windows 桌面端。

## 已实现

- 后端 FastAPI 服务
- 本地 SQLite 数据库持久化
- JWT 登录
- 三类角色：admin、teacher、student
- 管理员：用户、模型配置、第三方 API、选品属性页面
- 学生：AI 对话、每日推荐、热销商品
- 老师：教师看板、原商品列表、衍生品列表、通过/拒绝审核
- Mock FastMoss 商品、AI 衍生品、属性权重数据

## 桌面端交互

开发阶段桌面端启动后会直接进入主窗口，并展示全部菜单：

- 智能选品
- 教师看板
- 用户管理
- 模型配置
- 第三方 API
- 选品属性

左下角显示当前登录状态。未登录时处于开发预览模式，点击左下角「登录」会弹出登录窗口。登录后左下角会显示当前用户、角色和连接模式。

## 本地数据库

当前版本默认使用 SQLite，数据库文件会自动创建：

```text
backend\data\tk_selection.db
```

首次启动后端时会自动建表，并初始化演示账号、商品、衍生品和属性数据。

后续切换 MySQL 时，只需要把 `backend/app/core/database.py` 里的 `DATABASE_URL` 改成 MySQL 连接串，并安装 MySQL 驱动。

如果要重置本地演示数据，可以先停止后端，然后删除：

```text
backend\data\tk_selection.db
```

再次启动后端会重新初始化。

## 启动后端

```powershell
.\start_backend.ps1
```

后端地址：

```text
http://127.0.0.1:8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 启动桌面端

```powershell
.\start_desktop.ps1
```

## 演示账号

- admin / admin123
- teacher / teacher123
- student / student123

如果后端没有启动，桌面端会自动进入本地 mock 模式，方便先看 UI。

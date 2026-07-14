# TK 日本跨境智能选品系统

这是一个面向 TikTok 日本站跨境电商的智能选品系统。

系统由两部分组成：

- Windows 桌面端：PySide6。
- 后端服务：FastAPI + SQLAlchemy，线上部署在 Linux 云服务器。

## 当前核心链路

1. 从 FastMoss 日本区新品榜同步商品。
2. 调用大模型翻译商品标题。
3. 根据商品标题和类目进行商品分族。
4. 基于原商品标题、图片和分族权重生成 10 个衍生品。
5. 每个衍生品沉淀 8 个固定分析维度。
6. 老师审核衍生品，拒绝原因反向影响商品分族维度权重。
7. 后续接入 1688 API 后，根据衍生品名称搜索货源，并用大模型基于“衍生品名称 + 1688 首图”判断匹配度。

## 文档入口

完整文档见：

- [文档目录](./docs/00_INDEX.md)
- [产品需求文档](./docs/01_PRODUCT_REQUIREMENTS.md)
- [使用说明文档](./docs/02_USER_GUIDE.md)
- [后端业务逻辑文档](./docs/03_BACKEND_BUSINESS_FLOW.md)
- [接口与数据表文档](./docs/04_API_AND_DATA.md)
- [部署运维文档](./docs/05_DEPLOYMENT_OPERATION.md)
- [后续开发计划](./docs/06_DEVELOPMENT_PLAN.md)

## 本地启动

启动后端：

```powershell
.\start_backend.ps1
```

启动桌面端：

```powershell
.\start_desktop.ps1
```

## 默认账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | admin | admin123 |
| 老师 | teacher | teacher123 |
| 学生 | student | student123 |

## 注意事项

- 不要提交 API Key、服务器私钥、`.env`、数据库备份和打包产物。
- 后端代码修改后，需要部署到服务器并重启后端服务。
- 仅前端代码修改时，开发阶段可以直接运行源码 UI，不必每次打包。


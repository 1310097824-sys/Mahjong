# 单人立直麻将前端

这是项目的 React 前端，负责浏览器牌桌、开局面板、历史对局、牌谱回看、行动提示、结算面板和可视化牌面展示。

## 技术栈

- React
- TypeScript
- Vite
- Tailwind CSS
- `react-riichi-mahjong-tiles`

## 本地开发

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd install
npm.cmd run dev
```

开发服务默认通过 Vite 代理访问后端 `/api`，因此请同时启动 FastAPI 后端：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir D:\py\Mahjong
```

## 构建

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run build
```

构建产物会输出到：

```text
riichi-mahjong-ui\dist
```

后端会优先托管这份 `dist` 产物作为正式页面。

## 校验

```powershell
npm.cmd run lint
```

当前 `lint` 使用 TypeScript 类型检查。

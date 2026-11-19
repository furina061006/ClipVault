# 分支约定

这个仓库同时承载两件事：**给上游提 PR** 和 **自己的私有改造**。
两者用不同分支隔离，互不污染。

| 分支 | 内容 | 是否推送到 fork | 用来提 PR 吗 |
|---|---|---|---|
| `main` | 上游 `jinshah0322/ClipVault` 的纯镜像（跟踪 `upstream/main`） | 可以，保持同步 | **不直接提**，只作为 PR 的起点 |
| `local` | 自己的改造：`app/` → `clipvault/`、诊断日志、`.dsh/`、文档 | **不要推** | 不提 |
| `fix/*`、`feat/*` | 单个 PR 的改动，一律从 `main` 切出来 | 推 | 提 |

## 为什么 PR 分支不带 .dsh

`git push` 只发送**从该分支可达**的提交。`.dsh/` 只存在于 `local`，
而 PR 分支是从 `main`（上游镜像）长出来的，两条线没有共同祖先，
所以 .dsh 不会被带上。

## 新开一个 PR 的标准流程

```bash
# 0. 先同步上游
git fetch upstream
git switch main
git merge --ff-only upstream/main

# 1. 从 main 切分支（关键：不是从 local 切）
git switch -c fix/some-bug

# 2. 改代码、跑测试、提交
python3 -m pytest app/tests -q
git add -A
git commit -m "fix: ..."

# 3. 推到自己的 fork
git push -u fork fix/some-bug
```

## 如果改动是在 local 上做的

先在 `local` 上提交，再把需要的提交摘到 PR 分支：

```bash
git switch -c fix/xxx main
git cherry-pick <local 上的 commit>
```

注意：如果那个提交顺带改了 `clipvault/` 路径，cherry-pick 到 `main`（`app/` 布局）
会冲突，需要手动调整成 `app/`。

## 千万不要

- `git push fork local` —— 会把 `.dsh/`、改名后的代码全部公开
- 从 `local` 直接切 PR 分支 —— PR 里会混进改名和日志

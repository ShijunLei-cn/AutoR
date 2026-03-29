# AutoR（Auto Research）

## 项目概述

AutoR 是一个面向终端的研究流程编排器。MVP 目标是按固定顺序执行 8 个阶段，每次阶段尝试只调用一次 Claude Code，并且每个阶段结束后都必须由人在终端明确确认，流程才能继续。

这份文档是第一版最小可运行实现的开发规格说明。

## MVP 目标

- 固定顺序执行 8 个研究阶段。
- 每次阶段尝试只调用一次 Claude Code。
- 每个阶段结束后必须人工确认，不能自动进入下一阶段。
- 支持四类阶段后操作：
  - 使用 AI 给出的 refine 建议并重跑当前阶段
  - 输入用户自定义反馈并重跑当前阶段
  - 批准当前阶段并进入下一阶段
  - 终止当前运行
- 每次运行都必须隔离在 `runs/<run_id>/` 下。

## 设计原则

- 阶段顺序固定，不允许跳过。
- `refine` 的语义是“完整重跑当前阶段”，不是在上次结果上做增量补丁。
- Claude 只负责在当前 run 的工作目录中执行任务，不负责流程控制。
- 只有“已批准阶段”的摘要可以进入 `memory.md`。
- 所有运行产物必须限制在当前 run 目录内，不能污染仓库其他位置。

## 启动方式

```bash
python main.py
```

## 固定阶段顺序

```text
01_literature_survey
02_hypothesis_generation
03_study_design
04_implementation
05_experimentation
06_analysis
07_writing
08_dissemination
```

## 仓库结构

```text
repo/
├── main.py
├── stages/
│   ├── 01_literature_survey.md
│   ├── 02_hypothesis_generation.md
│   ├── 03_study_design.md
│   ├── 04_implementation.md
│   ├── 05_experimentation.md
│   ├── 06_analysis.md
│   ├── 07_writing.md
│   └── 08_dissemination.md
└── runs/
```

## 运行时目录结构

每次执行都创建一个独立的运行目录：

```text
runs/<run_id>/
├── user_input.txt
├── memory.md
├── stages/
│   ├── 01_literature_survey.md
│   ├── ...
├── workspace/
│   ├── literature/
│   ├── code/
│   ├── data/
│   └── results/
└── logs.txt
```

建议的 `run_id` 格式：

```text
YYYYMMDD_HHMMSS
```

## 端到端流程

1. 用户执行 `python main.py`。
2. 程序从终端读取研究需求。
3. 程序创建新的运行目录 `runs/<run_id>/`。
4. 程序将用户原始输入写入 `runs/<run_id>/user_input.txt`。
5. 程序初始化以下文件和目录：
   - `memory.md`
   - `stages/`
   - `workspace/literature/`
   - `workspace/code/`
   - `workspace/data/`
   - `workspace/results/`
   - `logs.txt`
6. 程序从 Stage 1 到 Stage 8 顺序循环：
   - 读取当前阶段模板 `stages/<stage>.md`
   - 读取 `user_input.txt`
   - 读取 `memory.md`
   - 如果当前是 revise 重跑，额外附加反馈指令
   - 组装最终 prompt
   - 调用一次 Claude CLI
   - 要求 Claude 产出 `runs/<run_id>/stages/<stage>.md`
   - 读取并打印该 markdown
   - 等待用户输入操作
   - 根据操作决定重跑、推进或终止
7. 程序仅在以下两种条件下退出：
   - Stage 8 被批准
   - 用户选择 abort

## Prompt 构造规则

每次阶段尝试都按以下顺序拼接最终 prompt：

1. 当前阶段模板：`stages/<stage>.md`
2. 用户原始需求：`runs/<run_id>/user_input.txt`
3. 已批准阶段摘要：`runs/<run_id>/memory.md`
4. revise 反馈：仅当当前阶段为重跑时附加

建议在 prompt 中显式分段，至少区分以下内容：

- 当前阶段说明
- 用户原始目标
- 已批准上下文
- 当前 revise 指令

这样可以降低 Claude 混淆上下文的概率，也方便记录日志和排查问题。

## Claude 调用约定

每次阶段尝试统一通过以下命令调用：

```bash
claude --dangerously-skip-permissions -p "<PROMPT>"
```

必须在 prompt 中明确要求 Claude 遵守以下规则：

- 所有实际操作都必须发生在 `runs/<run_id>/workspace/` 下。
- 当前阶段的总结文件必须写入 `runs/<run_id>/stages/<stage>.md`。
- 阶段总结必须严格遵守下文规定的 markdown 结构。
- Claude 不负责控制阶段推进、重试或审批。

## 阶段输出 Markdown 结构

每个阶段都必须生成如下结构的 markdown：

```md
# Stage X: <name>

## Objective
...

## What I Did
...

## Key Results
...

## Files Produced
...

## Suggestions for Refinement
1. ...
2. ...
3. ...

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
```

程序应把 `runs/<run_id>/stages/<stage>.md` 视为阶段输出的唯一可信来源，并直接将其打印到终端。

## 终端交互逻辑

打印阶段 markdown 后，终端必须提示：

```text
Enter your choice:
>
```

支持的输入及行为如下：

- `1`、`2`、`3`
  - 读取 `Suggestions for Refinement` 中对应编号的建议
  - 将该建议作为附加反馈
  - 完整重跑当前阶段
- `4`
  - 提示用户输入自定义反馈
  - 将反馈作为 revise 指令
  - 完整重跑当前阶段
- `5`
  - 将当前阶段标记为已批准
  - 把当前阶段摘要写入 `memory.md`
  - 进入下一阶段
- `6`
  - 立即终止当前运行

额外约束：

- 阶段执行完成后，程序绝不能自动推进。
- 只有输入 `5` 才允许进入下一阶段。
- `1` 到 `4` 都必须重跑同一个阶段。
- 未批准的尝试结果不得写入 `memory.md`。

## `memory.md` 规则

`memory.md` 只保存稳定且被批准的上下文：

- 用户初始目标
- 每个已批准阶段的摘要

`memory.md` 不允许包含：

- 中间失败尝试
- 被拒绝的 revise 结果
- revise 历史
- 未批准阶段输出

换句话说，`memory.md` 是“已确认状态”的压缩记忆，不是完整运行日志。

## 日志要求

`logs.txt` 应记录最小但足够排查问题的审计信息，每次阶段尝试至少追加：

- 时间戳
- 阶段名称
- 当前是首次尝试还是 revise
- 本次发送给 Claude 的 prompt
- Claude 的 stdout 或错误结果
- 阶段结束后用户的选择

`logs.txt` 用于调试和回放，不替代 `memory.md`。

## 关键约束

- 每个阶段都必须产出 markdown 总结文件。
- 所有生成文件都必须留在当前 run 目录内。
- 工作流必须是单线程、顺序执行。
- Claude 的上下文只来自每次调用时传入的 prompt。
- 一个阶段只有在用户明确批准后，才算真正完成。

## MVP 范围

本阶段必须实现：

- run 目录创建
- 阶段循环
- Claude 调用
- markdown 生成与终端打印
- `1` 到 `6` 的终端交互
- 已批准内容写入 `memory.md`

本阶段暂不实现：

- 多 agent
- 自动评估
- Web UI
- 数据库
- 并发执行

## 验收标准

当以下条件全部满足时，MVP 可视为完成：

- 执行 `python main.py` 后能启动交互式流程。
- 每次运行都会在 `runs/` 下创建独立目录。
- 每次阶段尝试都恰好触发一次 Claude CLI 调用。
- 每个阶段结束后都能打印符合规范的 markdown 总结。
- 用户可以在批准前多次 refine 当前阶段。
- 只有已批准阶段的摘要会进入 `memory.md`。
- 流程只会在 Stage 8 被批准或用户主动 abort 时结束。

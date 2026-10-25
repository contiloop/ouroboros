# ⟲ Ouroboros

通过对话明确想做什么，准备好后再把开发交给代理。

在 Ouroboros 中，**L1** 一边持续与你对话，一边管理整个开发过程。共同明确目标和委托范围后，你批准方案，L1 便负责推进 Ready–Go 循环并核验实际结果。执行期间也可以继续与 L1 交流。

[English](README.md) · [한국어](README_ko.md) · [日本語](README_ja.md)

## 使用流程

| Codex | Claude Code | 作用 |
| --- | --- | --- |
| `$ouroboros:init` | `/ouroboros:init` | 开始与 L1 对话，明确目标、完成标准、约束和委托的决策。草案可以继续修改，此时尚未启动开发循环。 |
| `$ouroboros:approve` | `/ouroboros:approve` | 批准已审阅的方案，将执行交给 L1。此后由 L1 审阅并批准 Ready 文档、推进 Go、核验结果和选择下一轮工作。 |

批准后仍可补充说明和讨论。L1 在约定范围内作出判断，不会为已经委托的每个步骤重复请求批准。涉及目标或权限变化时，L1 会说明影响并与你协调。

## 架构与循环

- **L1 代理：** 与用户对话并理解意图。创建 L2、请求 Ready、回答问题、审阅并批准文档，然后让同一个 L2 继续 Go。评估结果并决定下一轮工作。
- **L2 代理：** 在同一会话中执行既有的 **Dryforge Ready 和 Go**，也可以直接实现代码并验证。与 L1 交换问题和批准，按需创建和管理 L3，并负责汇总本轮结果。
- **L3 代理：** 完成 L2 分配的调查、实现或审查，并向 L2 返回结果。独立审查者使用与实现者分开的上下文。

按既有 Go 规则，单个 `MECHANICAL`/`NONE` 任务由 L2 直接实现，并行或 `RISKY` 工作委托给下层代理，同时保留必要的独立审查。同一会话让 Ready 中形成的设计上下文延续到实现判断中。

L1 调用已安装的 Dryforge 技能。Codex 使用 `$dryforge:ready`、`$dryforge:go` 与技能附件，Claude Code 使用 `/dryforge:ready`、`/dryforge:go`。L2 会话由 L1 创建，并不是 Ready 技能自行创建。L1 对 L2 承担普通用户的角色，具体 L3 的管理由 L2 负责。缺少判断依据或超出委托范围的决定才返回用户协调。完成一轮并不意味着已经实现整体目标。

Ready、Go 及其下层代理使用普通调用者接口，不必根据上层是人还是 L1 改变流程。访谈属于用户与 L1 的对话，不是额外的代理或使用阶段。

如果现有代码库尚需建立项目文档，L1 可以在已批准的范围内先安排 **Dryforge Migration**（`dryforge:migration`），回答问题、审阅文档与独立审查结果，并另行提交已接受的文档。之后在新的工作会话中开始 Ready–Go。Migration 本身只编写文档，不实现产品代码，也不自行提交。新项目或已完成准备的项目跳过此步骤。[运行说明](src/skills/init/references/migration-orchestration.md)

## 安装与当前状态

按[英文安装说明](README.md#try-it)加载插件。Claude Code 使用 `/ouroboros:init` → `/ouroboros:approve`，Codex 使用 `$ouroboros:init` → `$ouroboros:approve`。需要亲自监督单轮开发时，也可以直接使用 `ready` 和 `go`。

项目处于实验阶段，包含草案与批准状态管理、循环与权限检查，以及连接 Claude SDK / Codex App Server 的可选执行层。Codex 已验证新命令识别，以及父代理回合结束后向 L1 转交子代理批准请求的流程。从新会话开始直至实现最终目标的完整实机验证仍未完成。目前正式目标变更在已评估的循环边界提交。

Grep MCP 和 Context7 MCP 是可选（Optional）调查工具。参见 [MCP 设置](docs/RESEARCH_MCP_SETUP.md)、[对话与循环运行指南](docs/MISSION.md)及 [L1 扩展](docs/SKILL_INTERFACE.md)。

## 来源与许可证

Ouroboros 是基于 **prekuter** 的 [Dryforge](https://github.com/prekuter/dryforge) 开发的独立项目，遵循 [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)。保留现有 `.dryforge/` 记录。公开 `mission` 命令已替换为 `init` 和 `approve`，但不会因此重置已有运行记录。

<div align="center">

# ⟲ Ouroboros

### 保留意图，让开发循环前进。

**以用户意图为中心的三层开发 Harness**  
`mission → ready → go`，每个周期都以实际证据推动下一步。

[English](README.md) · [한국어](README_ko.md) · [Mission guide](docs/MISSION.md)

</div>

## 三层架构

| 层级 | 职责 |
| --- | --- |
| **L1 Mission Orchestrator** | 维护用户的最终目标、授权边界、周期评估和下一步决策 |
| **L2 Cycle Worker** | 在**同一个会话**中执行一次 `ready → 审批 → go` |
| **L3 Task Agents** | 按需调查、实现并独立审查，安全时续用任务会话 |

完成一个周期不代表整个 Mission 已经完成。L1 根据实际结果决定复用 L2 或通过明确的交接启动新 L2。

## 使用与限制

此分支包含实验性 Skill、生命周期规则及本地状态记录，但不包含独立的 Claude/Codex 常驻执行服务。会话恢复、消息转发和嵌套 Agent 需要主机支持；真实环境的完整端到端验证仍待完成。安装说明和详细架构请查看 [English README](README.md)。

Grep MCP 与 Context7 MCP **推荐但非必需（Optional）**：[MCP 设置](docs/RESEARCH_MCP_SETUP.md)。

<details><summary>来源与许可证</summary>

Ouroboros 基于 prekuter 的 [Dryforge](https://github.com/prekuter/dryforge)，并保留 [Apache-2.0](LICENSE) 许可证。原 `.dryforge/` 状态路径为了兼容旧项目而保留。

</details>

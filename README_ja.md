<div align="center">

# ⟲ Ouroboros

### 意図を保ち、開発サイクルをつなぐ。

**ユーザーの意図を軸にした3階層の開発ハーネス**  
`mission → ready → go`、検証を通して次のサイクルへ。

[English](README.md) · [한국어](README_ko.md) · [Mission guide](docs/MISSION.md)

</div>

## アーキテクチャ

| レベル | 役割 |
| --- | --- |
| **L1 Mission Orchestrator** | ユーザーの最終目標、権限、各サイクルの評価と次の作業を管理 |
| **L2 Cycle Worker** | 同じセッションで一度の `ready → 承認 → go` を実行 |
| **L3 Task Agents** | 調査、実装、独立レビューを必要に応じて実行 |

各サイクルの完了はミッション全体の完了を意味しません。L1は検証結果を基にL2を再利用または新規生成します。

## 利用と制限

実験版のスキルおよびローカル状態管理コードです。実際の継続セッション、メッセージ中継、ネストしたエージェントの機能はホスト側に必要で、実機のエンドツーエンド検証は未完了です。[セットアップと詳しい英語ドキュメント](README.md)を参照してください。

Grep MCP / Context7 MCP の導入は**任意（Optional）**です。[MCP 設定](docs/RESEARCH_MCP_SETUP.md)。

<details><summary>原著作者とライセンス</summary>

Ouroboros は prekuter による [Dryforge](https://github.com/prekuter/dryforge) を元にしています。ライセンスは [Apache-2.0](LICENSE) です。旧 `.dryforge/` ステートパスは互換性のため維持します。

</details>

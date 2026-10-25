# ⟲ Ouroboros

作りたいものを対話で具体化し、準備ができたら開発を任せる。

Ouroboros では **L1** がユーザーとの対話を続けながら開発全体を管理します。目標と委任範囲を一緒に整理し、承認後は L1 が Ready–Go サイクルを進め、実際の結果を確認します。実行中も対話は続けられます。

[English](README.md) · [한국어](README_ko.md) · [中文](README_zh.md)

## 使い方

| Codex | Claude Code | 動作 |
| --- | --- | --- |
| `$ouroboros:init` | `/ouroboros:init` | L1 との対話を開始し、目標、完了条件、制約、委任する判断を整理します。草案は修正可能で、開発サイクルはまだ始まりません。 |
| `$ouroboros:approve` | `/ouroboros:approve` | 確認した内容を承認し、実行を L1 に引き継ぎます。L1 が Ready の文書確認と承認、Go の実行、結果の評価、次のサイクルの選択を担当します。 |

承認後も補足や相談を続けられます。L1 は合意した範囲内で判断し、すでに委任された作業の承認を毎回求めません。目標や権限を変える内容は、影響を確認してユーザーと調整します。

## 構造とサイクル

- **L1 エージェント:** ユーザーと対話し、意図を理解します。L2 を生成して Ready を依頼し、質問に答え、文書を承認してから同じ L2 に Go を依頼します。結果と次のサイクルを判断します。
- **L2 エージェント:** 同じセッションで既存の **Dryforge Ready と Go** を実行し、自ら実装・検証も行います。L1 と質問・承認をやり取りし、必要な L3 を生成・管理して結果を報告します。
- **L3 エージェント:** L2 から割り当てられた調査、実装、レビューを行い、L2 に結果を返します。独立レビュアーは実装者とは別のコンテキストを使います。

既存の Go 規則に従い、単一の `MECHANICAL`/`NONE` タスクは L2 が直接実装し、並列または `RISKY` な作業は下位エージェントに委任します。必要な独立レビューは維持します。同じセッションを使うことで、Ready の設計コンテキストを実装時の判断に引き継げます。

L1 はインストール済みの Dryforge スキルを呼び出します。Codex では `$dryforge:ready`・`$dryforge:go` とスキル添付、Claude Code では `/dryforge:ready`・`/dryforge:go` を使います。L2 セッションを作るのは L1 であり、Ready スキル自体ではありません。L1 は L2 に対して通常のユーザーの役割を担い、個々の L3 の管理は L2 が担当します。L1 が判断できない意図や委任範囲外の決定はユーザーに確認します。一つのサイクルの完了が、全体の目標達成とは限りません。

Ready・Go とその作業者は、呼び出し元が人間か L1 かによって手順を変えません。インタビューは L1 との対話の一部であり、別のエージェントや追加の利用手順ではありません。

既存コードベースにプロジェクト文書を初めて整備する必要がある場合、L1 は承認された範囲で **Dryforge Migration**（`dryforge:migration`）を依頼できます。質問への回答、文書と独立レビューの確認、受け入れた文書の別途コミットを経て、新しい作業セッションで Ready–Go を開始します。Migration 自体は文書を作成し、製品コードの実装やコミットは行いません。新規または整備済みのプロジェクトでは省略します。[運用手順](src/skills/init/references/migration-orchestration.md)

## インストールと現在の状態

[英語のセットアップ手順](README.md#try-it)に従ってプラグインを読み込みます。Claude Code では `/ouroboros:init` → `/ouroboros:approve`、Codex では `$ouroboros:init` → `$ouroboros:approve` を使います。直接監督する単一サイクルには `ready` と `go` も利用できます。

実験版です。草案と承認の状態管理、サイクル・権限チェック、Claude SDK / Codex App Server 用の実行接続を含みます。Codex では新しいコマンドの認識と、親ターン終了後の子エージェントへの承認中継を確認済みです。新規セッションから最終目標までの完全な実機検証は未完了です。正式な目標変更は現在、評価済みのサイクル境界で反映します。

Grep MCP と Context7 MCP は任意（Optional）の調査ツールです。[MCP 設定](docs/RESEARCH_MCP_SETUP.md)、[対話とサイクル運用](docs/MISSION.md)、[L1 の拡張](docs/SKILL_INTERFACE.md)も参照してください。

## 原著作者とライセンス

Ouroboros は **prekuter** による [Dryforge](https://github.com/prekuter/dryforge) を基にした独立プロジェクトで、[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) に従います。既存の `.dryforge/` 記録は維持します。公開 `mission` コマンドは `init` と `approve` に置き換わりましたが、既存の実行記録はリセットしません。

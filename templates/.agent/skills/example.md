# Example Skill: コードレビュー (code-review)

<!-- このファイルはスキルの記述例です。
     スキルファイルは .agent/skills/*.md に配置します。
     エージェントはシステムプロンプトでスキル名と説明のみ確認し、
     必要に応じて read('.agent/skills/code-review.md') で本文を取得します。 -->

## Description

コードレビューを実施し、バグ・設計問題・改善点を報告するスキルです。

## Instructions

1. 対象ファイルを `read` で読み込む
2. 以下の観点でレビューする:
   - 論理的なバグや例外漏れ
   - 型ヒントの欠落
   - 命名の一貫性
   - テストのカバレッジ
3. 問題点をリスト形式で報告し、修正案を提示する
4. 重要度（High / Medium / Low）を付与する

## Usage

```
read('.agent/skills/code-review.md') を実行して詳細を確認してください
```

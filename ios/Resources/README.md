# Dental DX iOS アプリ用リソース

`MasterDataLoader` は `ios/Resources/data` ディレクトリに配置された問題データ(JSON)をアプリバンドル経由で参照します。CLIからは `functions/my_llm_app/data` のファイルをシンボリックリンクで参照できるようにしていますが、Xcode プロジェクトを作成する際は以下をターゲットに追加してください。

- `master_questions_final.json`
- `gakushi-*.json` 各種

> ⚠️ 提供済みのシンボリックリンクはローカル開発環境でのみ有効です。Xcode で新規ターゲットを作成する場合は "Create folder references" ではなく "Create groups" を選び、コピーを行ってください。

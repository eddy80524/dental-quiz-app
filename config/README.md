# 📁 設定ファイル

アプリケーションの設定ファイルを格納するディレクトリです。

## 📂 ファイル

- **crontab_sample.txt**: 定期実行用のcrontab設定サンプル
- **firestore.rules**: Firestore セキュリティルール設定

## 📝 使用方法

### crontab_sample.txt
```bash
# サンプル設定をcrontabに追加
crontab -e
# ファイル内容をコピー&ペースト
```

### firestore.rules
```bash
# Firebase プロジェクトに適用
firebase deploy --only firestore:rules
```

## ⚠️ 注意

本番環境に適用する前に、設定内容を十分に確認してください。

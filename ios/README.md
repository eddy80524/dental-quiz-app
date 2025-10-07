# DentalDX iOS プロジェクトセットアップ

1. [XcodeGen](https://github.com/yonaskolb/XcodeGen) をインストールします。
2. このディレクトリで `xcodegen generate` を実行すると `DentalDX.xcodeproj` が生成されます。
3. `ios/Resources/data` にある JSON はシンボリックリンクです。必要に応じて実ファイルをコピーし、Xcode でターゲットに追加してください。
4. 生成したプロジェクトを Xcode で開き、`DentalDX` ターゲットを選択してビルドします。
5. バンドル ID (`com.kokushi.dentaldx`) とチーム設定は適宜変更してください。

`Sources` 配下に SwiftUI の画面とデータレイヤーがまとまっており、`Resources` にアセット・問題データ、`Support` に Info.plist を配置しています。

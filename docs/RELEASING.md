# Release Procedure

## Prerequisites

- Windows 11 x64
- Python 3.13 x64 (`tkinter`を含む公式版。Python 3.14は使用不可)
- GitHub CLI
- クリーンなGit作業ツリー

## Checklist

1. `main`を最新化する。
2. `victor/__init__.py`の`__version__`を更新する。
3. `CHANGELOG.md`へ変更内容と日付を追加する。
4. `.\scripts\build_release.ps1`を実行する。
5. `dist\Victor-v<version>-windows-x64.zip`とSHA-256ファイルを確認する。
6. ZIPを別ディレクトリへ展開し、`Victor.exe`を起動する。
7. 新規環境で商品登録、価格調査、価格.com判定、履歴表示を確認する。
8. 既存DBをバックアップし、更新版で自動マイグレーションを確認する。
9. `v<version>`タグをpushし、`Windows build` Actionsの成果物を確認する。
10. GitHub Releaseを作成し、ZIPとSHA-256ファイルを添付する。

## Smoke Test

- ヴィクトル画像がすべて表示される。
- `%LOCALAPPDATA%\VictorPriceChecker`へDB、設定、ログが作成される。
- ツクモ、ドスパラ、ソフマップの商品目録を開ける。
- 価格調査中にGUIがフリーズしない。
- 自前履歴と価格.com市場履歴の表示が区別される。
- アプリを再起動して登録商品と履歴が維持される。

## Rollback

1. アプリを終了する。
2. `%LOCALAPPDATA%\VictorPriceChecker`を別名へ退避する。
3. `scripts/backup_data.ps1`で取得したバックアップを同じ場所へ復元する。
4. 直前のリリース版を起動する。

# デプロイ手順（Render.com）

ホスティング設計の詳細・採用理由は[WEB_DESIGN.md](WEB_DESIGN.md)の4章を参照。ここでは実際にRenderへデプロイする手順のみをまとめる。

## 前提条件

- 本リポジトリ（`zunish-riff-generator-web`）がGitHubにpush済みであること
- Render.comのアカウント（GitHubアカウントでサインアップ可）

## 手順

1. リポジトリ直下の[render.yaml](render.yaml)をコミット・pushする（このリポジトリには追加済み）。
2. [Renderダッシュボード](https://dashboard.render.com/)を開き、**New +** → **Blueprint** を選択する。
3. 対象のGitHubリポジトリ `zunish-riff-generator-web` を選択する（Private repoの場合は初回にRenderへのGitHubアクセス許可が必要）。
4. Renderが`render.yaml`を検出し、`zunish-riff-generator-web`という名前のWeb Service（Free プラン）を提案するので、内容を確認して **Apply** する。
5. 自動的にビルド（`pip install -e .`）とデプロイが開始される（初回は数分かかる）。
   - editable installを使う理由: `src/zunish/server.py`は`assets/soundfonts`・`static/`をパッケージに同梱せず、リポジトリのファイルを`__file__`からの相対パスで直接参照する設計（WEB_DESIGN.md 8.1）。通常の`pip install .`だとファイルがsite-packages配下にコピーされてこの相対パス計算が壊れるため、リポジトリ内の実ファイルをそのまま参照するeditable installが必要。
6. デプロイ完了後に発行されるURL（例: `https://zunish-riff-generator-web.onrender.com`）にブラウザでアクセスする。

## 動作確認

1. ページの「開始」ボタンを押す。
2. 接続状態表示が「未接続」→「接続中…」→「再生中」と遷移し、音が鳴ることを確認する。
3. うまくいかない場合はブラウザのDevTools Networkタブで以下を確認する:
   - `/ws`へのWebSocket接続が確立しているか
   - `/soundfonts/FluidR3Mono_GM.sf3`が200で取得できているか

## 無料枠特有の注意点

- 15分アクセスがないとスリープするため、久しぶりのアクセス時は数十秒のコールドスタートが発生する（フロント側の「起動中…」表示で対処する設計。[WEB_DESIGN.md](WEB_DESIGN.md)参照）。
- 月750時間の無料枠。本サービス1つを常時起動する分には足りるが、他のRenderサービスと合算される点に注意。
- スリープ復帰直後は`/ws`への最初の接続確立にも数秒余分にかかることがある。

## 設定を変更したい場合

`render.yaml`を編集してpushすれば、Renderが自動的に再デプロイ時に新しい設定を反映する（ダッシュボードでの手動変更は不要）。

# zunish-riff-generator-web

ZUN（東方Project/秘封倶楽部シリーズ）風のピアノフレーズ/リフを無限に生成し続けるジェネレータ。同じ生成ロジックを、ローカルで[FluidSynth](https://github.com/FluidSynth/fluidsynth/releases)を使って再生するCLI版と、ブラウザ上で再生するWeb版の両方で利用できます（Web化の設計背景は[WEB_DESIGN.md](WEB_DESIGN.md)を参照）。

## 特徴

- コード進行・スケール・著名リフ（7sus4アルペジオ、アリスアルペジオ）・リズム（Tresillo）・伴奏パターンをすべて `src/zunish/content/` 配下のレジストリで管理。新しい要素は各ファイルに `_register(...)` を1行追加するだけで反映される。
- 単一の連続進行ストリームを無限に生成（セクション分けなし）。進行は2〜4回ループごとに接続グラフの重みに従って次の進行へ、一定確率で短三度（±3半音）転調。一部の進行には、1小節に2つのコード（2分音符×2）が入る変化形も用意されている（詳細は[RULES.md](RULES.md)を参照）。
- 生成は「都度生成→即再生」の単一ループ。`.mid` 保存は任意。
- CLI版・Web版とも、再生中のノートをC4=60を中心とする4オクターブ（C2〜C6、上下2オクターブ）のピアノ鍵盤上にリアルタイム表示し、現在のテンポとキー（転調に追従）を表示します（右手＝青、左手＝橙でハイライト）。
- **CLI版**: `player.py`がFluidSynthのローカルオーディオデバイスに直接再生し、Tkinterで鍵盤GUIを描画。
- **Web版**: FastAPI製のWebSocketサーバー（`src/zunish/server.py`）が小節単位でノートイベントをJSON配信し、ブラウザ側（`static/`）がjs-synthesizer（FluidSynthのWebAssembly版、同梱の`FluidR3Mono_GM.sf3`を使用）とWeb Audio APIで音声合成・Canvas鍵盤描画・タイミングスケジューリングを行う。受信したノートはブラウザ内に蓄積され、`.mid`としてダウンロード可能。

## セットアップ

[uv](https://docs.astral.sh/uv/) がインストールされていれば、以下のコマンドだけで `.venv` の作成・依存関係（本体+開発用）のインストールまで完了します。

```
uv sync
```

[FluidSynth](https://github.com/FluidSynth/fluidsynth/releases)の共有ライブラリ（Windowsでは `fluidsynth.dll`）がシステムにインストール済みで、システム環境変数「PATH」に登録されている必要があります。

Macの場合は、`brew install fluidsynth` でインストール可能です。

サウンドフォントは、CLI版で `--soundfont` 未指定時・Web版とも、リポジトリ同梱の [assets/soundfonts/FluidR3Mono_GM.sf3](assets/soundfonts/FluidR3Mono_GM.sf3) がデフォルトで使われます。CLI版で別のサウンドフォントを使う場合のみ `--soundfont` で明示的にパスを指定してください。

## 実行（CLI版）

```
uv run zunish [--soundfont path/to/piano.sf2] [--tempo 160] [--key A] [--gain 1.0] [--save out.mid] [--seed 42]
```

（`uv run python -m zunish ...` でも同様に起動できます。）実行すると、ピアノ鍵盤・テンポ・キーを表示するGUIウィンドウが自動で開きます。ウィンドウを閉じるか、ターミナルでCtrl+Cを押すと停止します（発音中のノートをオールノートオフしてから終了）。`--save` を指定した場合は終了時に演奏内容を `.mid` として書き出します。

各オプションの意味は以下の通りです（すべて省略可能）。

- `--soundfont`: ピアノ音色を含む `.sf2`/`.sf3` サウンドフォントのパス。未指定時はリポジトリ同梱の [assets/soundfonts/FluidR3Mono_GM.sf3](assets/soundfonts/FluidR3Mono_GM.sf3) を使用。
- `--tempo`: テンポ（BPM）。セッション中は固定。デフォルト `160`。
- `--key`: 短調の主音（例: `A`, `C#`, `Eb`）。デフォルト `A`。
- `--gain`: FluidSynthの出力ゲイン。デフォルト `1.0`、指定可能範囲は `0.0`〜`10.0`。上げすぎると音割れするため注意。
- `--save`: 演奏内容を書き出す `.mid` ファイルのパス。指定した場合のみ終了時に保存される。
- `--seed`: 生成を再現可能にするための乱数シード（整数）。未指定時は毎回ランダム。

## 実行（Web版）

```
uv run uvicorn zunish.server:app --reload
```

起動後、ブラウザで http://127.0.0.1:8000/ を開くとフロントエンド（`static/`）が配信されます。Tempo/Key/Seedを入力して「開始」を押すとWebSocket（`/ws`）経由で生成が始まり、ブラウザ側でjs-synthesizerによる音声合成とCanvas鍵盤描画が行われます。「停止」で切断、「MIDIをダウンロード」でそれまでに受信した演奏内容を`.mid`として保存できます。

`/ws` エンドポイントは以下のクエリパラメータを受け付けます（すべて省略可能。CLI版と同じデフォルト値）。

- `tempo`: テンポ（BPM）。`20`〜`400`。デフォルト `160`。
- `key`: 短調の主音（例: `A`, `C#`, `Eb`）。デフォルト `A`。
- `seed`: 生成を再現可能にするための乱数シード（整数）。未指定時は毎回ランダム。

接続直後に確定した設定（`session_start`）が1回、以降は生成された小節ごとに`bar`メッセージ（ノートのピッチ・開始拍・長さ・ベロシティ・チャンネル）が送られ続けます。パラメータが不正な場合は`error`メッセージを送ってから接続を閉じます（詳細は[WEB_DESIGN.md](WEB_DESIGN.md)を参照）。

## テスト

```
uv run pytest
```

Python側は理論計算・レジストリ整合性・生成ロジックの決定性・WebSocketプロトコル（`ws_protocol.py`/`server.py`）を自動テストでカバーしています。

```
node --test tests/js/*.test.js
```

フロントエンドの純粋なロジック（再生スケジューリング・鍵盤描画・MIDI書き出し・WebSocketクライアント）はNode標準のテストランナーでカバーしています。ビルドツールは不要です。

実際の音の正しさ（FluidSynth/js-synthesizerでの再生確認）はどちらも自動テスト対象外のため、実際に起動して手動で確認してください。

## 要素の追加方法

`src/zunish/content/` 配下の該当ファイル（`progressions.py` / `scales.py` / `riffs.py` / `rhythms.py` / `accompaniment.py` / `voicings.py`）に `_register(...)` 呼び出しを1つ追加するだけで、コアロジック（`generator.py` / `director.py`）を変更せずに新しい要素を組み込めます。

## 生成ルールの詳細

現在実装されているコード進行・リズムパターン・スケール・リフなどの理論的なルールは [RULES.md](RULES.md) にまとめています。

## ライセンス

本リポジトリのソースコードは [Mozilla Public License 2.0 (MPL-2.0)](LICENSE) の下で公開されています。

同梱のサウンドフォント [assets/soundfonts/FluidR3Mono_GM.sf3](assets/soundfonts/FluidR3Mono_GM.sf3) は別途MITライセンスの対象であり、著作権表示・ライセンス条文は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

# zunish-riff-generator Web化 設計メモ

このファイルは、元リポジトリ [zunish-riff-generator](https://github.com/rftgy-bow/zunish-riff-generator) との会話で決まった、Webアプリ化の設計方針をまとめたものです。新しいセッションで読み込むことで、ここまでの議論を再開できます。

## 1. 元プログラムの概要

ZUN（東方Project/秘封倶楽部シリーズ）風のピアノフレーズ/リフを無限に生成し続け、FluidSynthでリアルタイム再生するCLIアプリ。

現在の構成（元リポジトリの `src/zunish/` 配下）:

- `generator.py` / `director.py` / `theory.py` / `content/*.py`：コード進行・スケール・リフなどを無限に生成する音楽ロジック（レジストリベースで拡張可能）
- `player.py`：生成されたNoteEventをFluidSynthのローカルオーディオデバイスにリアルタイムで流し込む再生ループ（`time.sleep`で拍単位のタイミング制御）
- `gui.py`：Tkinterでピアノ鍵盤・テンポ・キーをリアルタイム描画するGUI（再生スレッドからのイベントをqueueで受け取るだけで、FluidSynth/generatorには直接触れない設計）
- `midi_export.py`：`--save`指定時に演奏内容を`.mid`として書き出し
- `cli.py`：上記を束ねるエントリポイント（`--soundfont`, `--tempo`, `--key`, `--gain`, `--save`, `--seed`オプション）

サウンドフォントは `assets/soundfonts/FluidR3Mono_GM.sf3`（MITライセンス）をデフォルト同梱。

## 2. Web化にあたっての課題

- **音声**：FluidSynthがローカルのオーディオデバイスに直接出力している。ブラウザには届かないため、そのままでは移植不可。
- **GUI**：Tkinterによる描画はブラウザ上では動作しない。
- **生成ループ**：「無限に生成し続ける」性質上、リクエスト/レスポンス型ではなく、常時接続（WebSocketなど）を前提にした常駐プロセスが必要。

## 3. 採用する設計方針

### 3.1 全体構成

- 音符イベント（note-on/off、テンポ、キー）だけをWebSocketでサーバーからブラウザへ送り、**音声合成はブラウザ側で行う**（サーバー側でPCMをレンダリングしてストリーミングする方式は、同時接続ごとに常時エンコード処理が必要でホスティングコストが跳ね上がるため不採用）。

### 3.2 バックエンド

- FastAPI/Starlette + Uvicorn でWebSocketサーバーを実装。
- `generator.py` / `director.py` / `theory.py` はロジックをそのまま再利用。
- `player.py`のFluidSynth直接呼び出し（`noteon`/`noteoff`）や拍単位の`time.sleep`タイミング制御は使わない。代わりに小節単位でNoteEventをJSON化してWebSocket送信するだけの薄いロジックに置き換える（詳細は6章）。正確な再生タイミングの制御はクライアント側（Web Audio）が担う。
- `gui.py`のTkinter描画ロジックは、フロントエンドのCanvas/SVG実装への移植元として参照する（鍵盤レイアウト定数・チャンネル別ハイライト色などはそのまま使える）。
- サーバー側にFluidSynthやサウンドフォントの実体は不要（音声合成をクライアントに移すため）。
- DB・永続化ストレージは使わない設計。`.mid`保存機能は「ブラウザ側で受信イベントを蓄積し、ダウンロードボタンでファイル生成」に変更し、サーバーにストレージを持たせない。

### 3.3 フロントエンド

- 同じバックエンド（Renderの1サービス）から静的ファイル（HTML/JS/CSS）を配信する。別サービスに分けるとWebSocketのCORS/オリジン越えの手間が増えるため。
- ピアノ鍵盤描画はTkinterの代わりにCanvas/SVGで再実装（`gui.py`のロジックを移植）。
- 音声合成には **js-synthesizer**（FluidSynthをWebAssembly化したライブラリ）をWeb Audio上で使用する案を検討中。これにより同梱の`FluidR3Mono_GM.sf3`をそのまま使え、音色を変えずに移行できる。

## 4. ホスティング設計（無料枠前提）

参考記事: https://qiita.com/pam5596/items/feab853f3a62a3d3f0a0

検討した無料ホスティングサービスと、このアプリ（WebSocket常時接続・無限生成ループが必要）への適性:

| サービス | 適性 | 理由 |
|---|---|---|
| Vercel | 不向き | サーバーレス関数は実行時間10秒程度の制約があり、常時接続のWebSocketや無限生成ループに向かない |
| AWS Lambda | 不向き | WebSocket非対応、実行時間制約 |
| GitHub Pages / AWS S3 | 不向き（フロントのみなら可） | 静的ホスティングのみでバックエンド不可 |
| ElasticBeanstalk | 不向き | 無料は新規12ヶ月のみで恒久無料ではない |
| **Render.com** | **採用** | WebSocket対応・フルスタック可・恒久無料（月750時間、アクセスがない場合はスリープ） |

**採用する設計**: Render.comの無料Web Serviceでバックエンド（FastAPI）とフロントエンド（静的ファイル）を同居させる。

**既知のトレードオフ**: Render無料枠は15分アクセスなしでスリープするため、しばらく誰もアクセスしていない状態から開くと数十秒のコールドスタート待ちが発生する。フロント側に「起動中…」の表示を用意して対処する想定。

## 5. リポジトリ構成

- 元リポジトリ（CLI/デスクトップ版、変更なし）: https://github.com/rftgy-bow/zunish-riff-generator （Private、ローカル: `C:\github\zunish-riff-generator`）
- 本リポジトリ（Web版、開発用）: https://github.com/rftgy-bow/zunish-riff-generator-web （Private、ローカル: `C:\github\zunish-riff-generator-web`）
  - GitHubの仕様上、同一ユーザーが親とフォークを両方所有することはできないため、GitHubのFork機能は使わず、独立した新規リポジトリとして全履歴をコピーして作成した（フォーク関係なし）。

## 6. WebSocketメッセージ仕様

### 6.1 タイミング制御方式

CLI版の`player.py`は、プレイヤー自身が`time.sleep`で拍単位の正確なタイミングを刻みながら`noteon`/`noteoff`をFluidSynthに直接発行する。Web版ではこの役割をクライアントに移す：

- **サーバー**は1小節分のNoteEvent（`start_beat`・`duration_beat`付き）をまとめて先読み送信するだけで、`asyncio.sleep`による逐次的なタイミング制御は行わない。
- **クライアント**は受信した小節をWeb Audioの`AudioContext.currentTime`基準でサンプル精度にスケジュール再生する。

これにより、ネットワークの遅延・ジッターが再生タイミングのブレに直結しない。副次的な効果として、CLI版`player.py`にある「小節をまたいで鳴り続ける音の繰り越し処理（`_deferred_note_offs`）」の複雑さも、クライアント側が絶対時刻ベースでスケジューリングするため不要になる。

### 6.2 接続確立

```
wss://<host>/ws?tempo=160&key=A&seed=123&modulation=true
```

すべてクエリパラメータは省略可能。省略時はCLI版と同じデフォルト（`tempo=160`, `key=A`, `seed`はランダム, `modulation=true`）を使う。テンポ・キー・転調ON/OFFはCLI版と同様に**セッション開始時に一度だけ**決定し、テンポはセッション中固定（キーは`Director`が生成中に自動転調するため、小節データ側で毎回通知する。詳細は6.3参照）。`modulation=false`の場合、`Director`はセッション中一度も転調しない。

パラメータが不正（`key`が`theory.note_name_to_pc`で解析できない、`tempo`が範囲外など）な場合、サーバーは`error`メッセージを送信してから接続をクローズする。

`--gain`（音量調整）はサーバー側には存在しない。音声合成自体がクライアント側（js-synthesizer）に移るため、Web Audioの`GainNode`としてフロントエンド機能に持たせる。

### 6.3 メッセージ種別（サーバー→クライアント、JSONテキストフレーム）

クライアント→サーバーのメッセージは無し（接続確立はクエリパラメータのみで完結し、再生の一時停止/再開などの制御コマンドは現時点でスコープ外）。

**`session_start`（接続直後に1回だけ送信）**

```json
{ "type": "session_start", "tempo_bpm": 160, "key": "A", "seed": 123, "modulation": true }
```

実際に確定した値（`seed`省略時にサーバーが採番した値を含む）を伝える。

**`bar`（1小節ごとに送信）**

```json
{
  "type": "bar",
  "bar_index": 42,
  "key": "A",
  "notes": [
    { "pitch": 60, "start_beat": 0.0, "duration_beat": 0.5, "velocity": 100, "channel": 0 }
  ]
}
```

- `notes`は`generator.NoteEvent`（`pitch`/`start_beat`/`duration_beat`/`velocity`/`channel`）をほぼそのままJSON化したもの。note-on/offに分解せず「1音1イベント」として送ることで、クライアント側は`start_beat`で鳴らし始め`duration_beat`後に止める、という単純なスケジューリングで済む。`channel`は`0`=右手（メロディ）、`1`=左手（伴奏）（`gui.py`の`CHANNEL_COLORS`と対応）。
- `key`は転調の有無によらず毎小節に含める（自己完結させ、クライアント側で状態を跨いで追跡する必要をなくすため）。
- `bar_index`はセッション開始からの通し番号（0始まり）。クライアントは`絶対拍位置 = bar_index × 4.0 + start_beat`（`BEATS_PER_BAR = 4.0`固定）を計算でき、`session_start`の`tempo_bpm`と組み合わせて絶対再生時刻に変換する。この値はWeb Audioスケジューリングと`.mid`書き出しの両方で使う。

**`error`（異常時のみ、送信後に接続をクローズ）**

```json
{ "type": "error", "message": "invalid key: X" }
```

### 6.4 サーバー側の先読みペース制御

常に「現在再生中の小節＋先読み1小節」分だけクライアントに渡っている状態を維持する：

1. 接続確立直後、`bar 0`と`bar 1`を即座に連続送信する（`bar 0`をすぐ再生開始できるようにしつつ、1小節分のバッファを確保する）。
2. 以降、`bar N`（N≧2）は「`bar N-1`の再生完了予定時刻」の直前まで`asyncio.sleep`で待ってから送信する。

これはCLI版`player.py`の拍単位タイムライン制御を小節単位に単純化したものにあたる。常時何らかの通信が発生し続けるため、Render無料枠のWebSocketアイドルタイムアウトの回避にも寄与する。

### 6.5 クライアント側での利用

- `session_start`と各`bar`を受信し、6.1の絶対時刻計算に基づいてjs-synthesizerへのnote-on/offをスケジュールする。
- 受信した全`bar`の`notes`を蓄積しておき、ダウンロードボタン押下時にクライアント側で`.mid`ファイルを生成する（サーバー側にMIDIファイルの実体は一切持たない、既存方針3.2の踏襲）。

## 7. 実装状況

- WebSocketサーバー（6章の仕様どおり）: 実装済み・mainにマージ済み（`src/zunish/ws_protocol.py`, `src/zunish/server.py`）。
- フロントエンド（8章）: 設計確定、実装中。
- Render.comへのデプロイ設定: 未着手。

## 8. フロントエンド設計

### 8.1 技術スタック・配信方法

- **ビルドステップなしのVanilla JS**（ES Modules）。Node.js/npm/バンドラは導入しない。CLI版と同じく「依存を最小限に抑える」方針を踏襲する。
- 音声合成には**js-synthesizer**（FluidSynthのWebAssembly版）を使う。`<script>`タグで読み込むだけで使える配布形態（`dist/js-synthesizer.js` + `externals/libfluidsynth-*.js`(wasm)）を採用し、これらのファイルをリポジトリに同梱する（外部CDN依存にしない。オフラインデモや配信元障害への耐性のため）。
- **注意**: 同梱のサウンドフォントは`.sf3`形式のため、`.sf3`をサポートする`-with-libsndfile`付きのWASMビルド（`libfluidsynth-2.4.6-with-libsndfile.js`/`.wasm`）を使う必要がある（無印版は`.sf2`のみ対応）。

ディレクトリ構成:

```
static/
  index.html
  css/style.css
  js/
    main.js              # エントリポイント（UI配線）
    websocket-client.js  # /ws接続・メッセージ受信
    scheduler.js         # 絶対時刻ベースの音符スケジューリング
    synth.js              # js-synthesizer初期化・ノート再生
    keyboard.js           # Canvas鍵盤描画（gui.pyの移植）
    midi-writer.js        # 自前SMF書き出し
  vendor/
    js-synthesizer.js                          # js-synthesizer 1.13.0 (dist/js-synthesizer.js)
    libfluidsynth-2.4.6-with-libsndfile.js      # wasmバイナリをbase64で内包した単一ファイル(.wasm別ファイルは無い)
```

サウンドフォント（`assets/soundfonts/FluidR3Mono_GM.sf3`、23.7MB）は`static/`へコピーせず、既存の`assets/soundfonts/`を直接別マウントで配信する（複製によるリポジトリ肥大化・二重管理を避けるため）。`server.py`に以下の2つのマウントを追加する（`/ws`ルート定義より後に追加し、ルーティング競合を避ける）:

```python
app.mount("/soundfonts", StaticFiles(directory=REPO_ROOT / "assets" / "soundfonts"), name="soundfonts")
app.mount("/", StaticFiles(directory=REPO_ROOT / "static", html=True), name="static")
```

フロントエンドは`/soundfonts/FluidR3Mono_GM.sf3`から取得する。

### 8.2 UI・接続フロー

- 接続前に入力できるフォーム: `tempo`（数値、既定160、20〜400）・`key`（文字列、既定A）・`seed`（数値、空欄可＝サーバー採番）。CLI版の`--tempo`/`--key`/`--seed`に対応し、値はそのまま`/ws`のクエリパラメータに渡す。
- 転調ON/OFFトグルボタン（「転調: ON」/「転調: OFF」、既定ON）。クリックのたびに状態を反転し、`modulation`クエリパラメータとして`/ws`に渡す。
- 操作ボタン: 「開始」「停止」「MIDIをダウンロード」（受信ノートが1つもない間は無効）。音量スライダー（`GainNode`、js-synthesizerの出力と`audioContext.destination`の間に挿入）。
- 接続状態表示: 「未接続」→「接続中…」→「再生中」。`session_start`受信でテンポ・キーの読み上げ表示を更新する。
- **開始ボタン押下時の処理**（ブラウザの自動再生ポリシー上、`AudioContext`の生成・`resume()`はユーザー操作のハンドラ内で行う必要がある）:
  1. フォーム値からクエリ文字列を組み立てる
  2. `AudioContext`を生成（未生成なら）し`resume()`
  3. js-synthesizerを初期化し、`FluidR3Mono_GM.sf3`をロード（未ロードなら）
  4. `(location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws?" + query` へ接続
  5. フォーム・開始ボタンを無効化、停止ボタンを有効化
- **予期しない切断時**: エラーメッセージ表示＋「再接続」ボタンを表示するのみ（自動リトライは実装しない、YAGNI）。「再接続」は開始フローをそのまま再実行する。
- **停止ボタン押下時**: `ws.close()`のみ行う（既にスケジュール済みの音は自然に鳴り終わるまで再生される）。フォーム・開始ボタンを再度有効化する。
- 再接続・再開始のたびに、8.3の絶対時刻アンカーと8.5のノートバッファは全てリセットする（新しいセッション＝新しい演奏として扱う）。

### 8.3 音声スケジューリング設計

js-synthesizerの実際のAPI（[GitHub上のTypeScript型定義](https://github.com/jet2jet/js-synthesizer/blob/main/src/main/ISequencer.ts)で確認済み）を踏まえた設計：

- `ISynthesizer.midiNoteOn`/`midiNoteOff`は**即時実行のみ**（時刻指定パラメータがない）。サンプル精度のスケジューリングには**`ISequencer`**（`JSSynth.Synthesizer.createSequencer()`で生成）を使う。
- `ISequencer.sendEventAt(event, tick, isAbsolute)`で、`event`を指定`tick`（既定タイムスケール: 1 tick = 1ミリ秒）に予約できる。synthesizerを`sequencer.registerSynthesizer(synth)`で登録しておけば、synthのレンダリング処理（`createAudioNode`で作った`ScriptProcessorNode`のコールバック）の中でシーケンサの処理も自動的に進む（`processSequencer`を手動で呼ぶ必要はない）。
- イベント種別には`{type: "note", channel, key, vel, duration}`（on+offを1回の予約で表現できる、`duration`はミリ秒）があり、`NoteEvent`（`pitch`/`velocity`/`duration_beat`）の構造とそのまま対応するため、これを使う（`noteon`/`noteoff`を別々に予約する必要はない）。
- シーケンサの時間軸（tick）は`AudioContext.currentTime`とは別物なので、両者を対応付けるアンカーを2つ同時に記録する:
  - `tickAtAnchor = await sequencer.getTick()`
  - `wallClockAtAnchor = performance.now()`
  - （`LEAD_IN_SECONDS`（暫定0.3秒）だけ先の時点をアンカーにする＝`tickAtAnchor`取得直後に`LEAD_IN_SECONDS * 1000`を足す）
- `BEATS_PER_BAR = 4.0`（`theory.py`と同じ値をJS側にも定数として持つ。将来ズレないようコメントで明記する）。`secondsPerBeat = 60 / tempoBpm`（`session_start`の`tempo_bpm`から算出）。
- 各ノートについて、絶対tick位置を`targetTick = tickAtAnchor + (bar_index * BEATS_PER_BAR + start_beat) * secondsPerBeat * 1000`として計算し、`sequencer.sendEventAt({ type: "note", channel, key: pitch, vel: velocity, duration: duration_beat * secondsPerBeat * 1000 }, targetTick, true)`で予約する。
- **鍵盤ハイライトの表示**（UI用、ミリ秒精度で十分）は`ISequencer`とは別に`setTimeout`で行う。tick時間軸をwall-clock（`performance.now()`）に変換するため、`delayMs = (wallClockAtAnchor + (targetTick - tickAtAnchor)) - performance.now()`を計算し、`setTimeout(..., Math.max(0, delayMs))`で発火させる。
- 実装方式は`JSSynth.Synthesizer`（`ScriptProcessorNode`ベース）を採用し、`AudioWorkletNodeSynthesizer`（別途workletモジュールの読み込みが必要でやや複雑）は使わない。`ScriptProcessorNode`はDeprecated表記だが主要ブラウザで引き続き動作するため、ビルドレス・シンプルさを優先する（将来的にパフォーマンス上の問題が出た場合の切り替え候補として記録しておく）。
- タブのバックグラウンド化や端末スリープ等で大きな遅延が発生した場合、溜まっていた小節分の予約イベント・`setTimeout`がほぼ同時に発火し、音がまとめて追いつくように鳴る（絶対拍位置ベースでスケジュールしているため正しい挙動。WebSocketサーバー実装の最終レビューでも同様の指摘があり、許容する方針としている）。

### 8.4 鍵盤描画（Canvas、`gui.py`の移植）

- `gui.py`の定数（`KEY_LOW=36`, `KEY_HIGH=84`, `WHITE_PCS`, `WHITE_INDEX_IN_OCTAVE`, `BLACK_OFFSET_IN_OCTAVE`, `WHITE_KEY_WIDTH=32`, `WHITE_KEY_HEIGHT=160`, `BLACK_KEY_WIDTH`/`HEIGHT`, `CHANNEL_COLORS`）をそのままJSの定数として移植する。
- `activeChannelsByPitch`（`Map<pitch, Set<channel>>`）で`gui.py`の`self._active`相当の状態を保持する。
- ノートオン/オフのたびに該当ピッチのSetを更新し、`CHANNEL_COLORS`から色を再計算して、そのキーの矩形だけを再描画する（Tkinterの`itemconfig`に相当する処理をCanvas上で行う）。白鍵→黒鍵の順で描画するレイヤー順序も`gui.py`を踏襲する。

### 8.5 MIDIエクスポート

- 受信した全ノートを`{ absoluteStartBeat, durationBeat, velocity, channel, pitch }`の配列として蓄積する（`absoluteStartBeat = bar_index * BEATS_PER_BAR + start_beat`）。
- 「MIDIをダウンロード」押下時に、依存ライブラリなしでStandard MIDI File（フォーマット0、1トラック）を自前生成する: `MThd`ヘッダー（`division`は`midi_export.py`と同じ480 tick/四分音符）→ `set_tempo`メタイベント（`session_start`の`tempo_bpm`から算出）→ 絶対tick順に並べたnote_on/note_offイベント（可変長数値でデルタタイムを符号化）→ `end_of_track`。`Blob`化して`<a download>`でダウンロードさせる。
- バッファは開始のたびにクリアするが、停止操作そのものではクリアしない（停止後もそれまでの演奏をダウンロード可能）。

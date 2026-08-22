# THIRD-PARTY NOTICES

本リポジトリのソースコードは [LICENSE](LICENSE) に記載の Mozilla Public License 2.0 (MPL-2.0) の下で公開されています。

このファイルは、本リポジトリに同梱されているサウンドフォントファイル [assets/soundfonts/FluidR3Mono_GM.sf3](assets/soundfonts/FluidR3Mono_GM.sf3) について、その利用許諾（MITライセンス）が求める著作権表示およびライセンス条文を明記するものです。このファイルはサウンドフォント資産（`assets/soundfonts/FluidR3Mono_GM.sf3`）にのみ適用され、本リポジトリのソースコードのライセンス（MPL-2.0）とは独立しています。

## 対象ファイル

- `assets/soundfonts/FluidR3Mono_GM.sf3`

このファイルは、Frank Wen 氏によるオリジナルの Fluid (R3) SoundFont を、Michael Cowgill 氏がモノラル変換した FluidR3Mono を基にしています。両氏はこの成果物をMITライセンスの下で公開しています。

## 著作権表示 (Copyright Notice)

```
Copyright (c) 2000-2002, 2008 Frank Wen <getfrank@gmail.com>
Copyright (c) 2014-2017 Michael Cowgill
```

## ライセンス条文 (MIT License)

MITライセンスは、上記の著作権表示および以下の許諾条文を再配布物に含めることを条件に、使用・複製・改変・結合・掲載・頒布・サブライセンス・販売を無償で許可しています。以下は、サウンドフォントに同梱されている `COPYING` の条文をそのまま引用したものです。

```
Copyright (c) 2014-16 Michael Cowgill
Copyright (c) 2000-2002, 2008 Frank Wen <getfrank@gmail.com>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
```

## 補足

- サウンドフォント配布元が同梱していたオリジナルのドキュメント（README・COPYING・派生元の謝辞を含む全文）は、そのまま [assets/soundfonts/FluidR3Mono_License.md](assets/soundfonts/FluidR3Mono_License.md) として保存しています。このファイルはその全文のうち、`FluidR3Mono_GM.sf3` の著作権継承（Frank Wen → Michael Cowgill）に直接関係する部分を抜粋・要約したものであり、詳細確認が必要な場合は元ファイルを参照してください。
- MITライセンスの条件により、`FluidR3Mono_GM.sf3` を含む本リポジトリを再配布する場合も、上記の著作権表示とライセンス条文を残す必要があります。

## `static/vendor/js-synthesizer.js`（BSD 3-Clause License）

[js-synthesizer](https://github.com/jet2jet/js-synthesizer) 1.13.0（`dist/js-synthesizer.js`）を、フロントエンドでのブラウザ内音声合成のために同梱しています。

```
Copyright (C) 2018 jet
All rights reserved.
```

ライセンス全文は [static/vendor/LICENSE.js-synthesizer.txt](static/vendor/LICENSE.js-synthesizer.txt) を参照してください。

## `static/vendor/libfluidsynth-2.4.6-with-libsndfile.js`（GNU Lesser General Public License v2.1）

[js-synthesizer](https://github.com/jet2jet/js-synthesizer) が配布する [fluidsynth-emscripten](https://github.com/jet2jet/fluidsynth-emscripten)（FluidSynthをWebAssemblyへ移植したもの、`.sf3`読み込みのため`libsndfile`込みでビルドされた版）を同梱しています。FluidSynth本体およびfluidsynth-emscriptenはGNU Lesser General Public License v2.1の下で配布されています。

ライセンス全文は [static/vendor/LICENSE.fluidsynth.txt](static/vendor/LICENSE.fluidsynth.txt) を参照してください。ソースコードは [fluidsynth-emscripten](https://github.com/jet2jet/fluidsynth-emscripten) および [js-synthesizer](https://github.com/jet2jet/js-synthesizer) のリポジトリで公開されています。

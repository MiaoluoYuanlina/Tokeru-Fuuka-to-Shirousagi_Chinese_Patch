# kazeshiro_demo 资源提取说明

## 提取结果

- 游戏引擎：Kirikiri Z 1.2.0.3（C++ 核心、TJS2 脚本、KAGEX/PSB 场景）
- XP3 条目：2265
- 真实资源：2264 个，全部通过文件长度和 Adler-32 校验
- 保护警告记录：1 个；这是归档刻意加入的伪造首条记录，不是游戏资源
- 提取数据量：666,542,281 字节

原始资源位于 `extracted/`，目录结构与 XP3 内结构一致。完整映射和校验值见：

- `extracted/_xp3_manifest.csv`
- `extracted/_xp3_summary.json`
- `extracted/_verification_report.json`

## 图片、音频和视频

- PNG：211 张
- TLG：194 张，原文件保留在原目录；PNG 预览副本位于 `extracted/_tlg_png/`
- OGG：1210 个
- WMV：1 个
- AMV：1 个
- TTF/OTF 字体：10 个

以上文件均已检查文件签名。其他原生资源（PBD、PSD 配置、SLI 循环信息等）也保留在对应目录。

## 主剧情文本

5 个 `scn/*.txt.scn` 是 MDF 压缩的 PSB 场景文件，已反编译为完整 JSON：

- `extracted/_scenario_decompiled/01.txt.json`
- `extracted/_scenario_decompiled/02.txt.json`
- `extracted/_scenario_decompiled/03.txt.json`
- `extracted/_scenario_decompiled/04.txt.json`
- `extracted/_scenario_decompiled/05.txt.json`

共还原 3298 条剧情文本。适合翻译的 UTF-8 TSV 表格位于：

- `localization/scenario_dialogue_zh_cn.tsv`

请填写 `speaker_zh_cn`、`translation_zh_cn` 和可选的 `translator_note` 列，不要修改索引列。

## 其他文本和脚本

- `localization/text_utf8/`：360 个可直接解码的脚本、KS、CSV、INI、SLI、TXT 等 UTF-8 副本
- `localization/tjs_decompiled/`：231 个 TJS2100 编译脚本的 UTF-8 反编译副本
- `localization/text_inventory.csv`：原文件、编码、UTF-8 副本之间的映射
- `localization/_localization_summary.json`：汉化工作区统计

反编译 TJS 用于查找和修改界面文本，但原始字节码仍以 `extracted/` 中的文件为准。正式汉化补丁需要在翻译完成后重新生成 SCN/TJS，并打包为优先级更高的 XP3 补丁；当前步骤只做提取和工作区准备。

## 可重复执行的工具

- `tools/extract_xp3.py`：XP3 完整提取和逐文件校验
- `tools/build_localization_workspace.py`：UTF-8 文本副本及剧情翻译表生成
- `tools/validate_extraction.py`：最终资源、格式签名和数量核验

SCN/PSB 和 TLG 使用 [FreeMote](https://github.com/UlyssesWu/FreeMote) v4.7.0 处理；TJS2100 使用 [tjs2-decompiler](https://github.com/crate-1556/tjs2-decompiler) 处理。第三方工具及许可证保存在 `tools/` 下。

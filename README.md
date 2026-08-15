# TOKERU FUUKA TO SHIROUSAGI 简体中文补丁

《とける風花とシロうさぎ　体験版》非官方简体中文汉化项目。

当前补丁包含：

- 5 个场景文件、共 3298 条剧情文本的中文翻译
- 系统与界面文本汉化
- UI 图片文字汉化及排版适配
- 自定义手绘标题 Logo
- 可重复执行的资源提取、OCR 表格导出、图片回填和 XP3 打包工具
- 独立的表格 AI 翻译工具与补丁安装器源码

## 下载与安装

1. 下载 [`release/TOKERU-FUUKA-TO-SHIROUSAGI_Chinese_Patch.zip`](release/TOKERU-FUUKA-TO-SHIROUSAGI_Chinese_Patch.zip)。
2. 将压缩包内的全部文件解压到游戏目录，也就是 `data.xp3` 和游戏 EXE 所在的位置。
3. 双击 `运行此文件启动游戏！.bat` 启动游戏。

启动脚本会优先运行 `kazeshiro_demo.exe`；如果游戏 EXE 被改过名字，则会自动选择当前目录中的第一个 EXE，并附带 UTF-8 汉化启动参数。直接双击游戏 EXE 可能导致中文乱码。

发布包校验值见 [`release/SHA256SUMS.txt`](release/SHA256SUMS.txt)。

也可以下载 [`game_patch-installer.zip`](release/game_patch-installer.zip)，解压后运行其中的 `game_patch.exe`。该安装器已经内置汉化补丁，会自动定位或使用当前游戏目录完成安装。

表格翻译工具的可运行版本位于 [`release/translate_tool-windows.zip`](release/translate_tool-windows.zip)。解压后运行 `translate_tool.exe`，使用说明和示例配置已经包含在压缩包内；运行环境需要 .NET 8 Desktop Runtime。

## 翻译与打包

- `localization/scenario_dialogue_zh_cn_from_excel.tsv`：已完成的剧情翻译表，可直接交给 `build_patch.bat`。
- `localization/uipsd_image_text_scan_zh_cn.xlsx`：已完成的 UI 图片文字翻译表。
- `localization/uipsd_custom_png/`：手工绘制或覆盖的 UI 图片。
- `export_uipsd_text.bat`：扫描 UI 图片文字并导出 Excel 表格。
- `apply_uipsd_translations.bat`：读取翻译完成的 Excel，生成适配原显示范围的中文图片。
- `build_patch.bat`：选择剧情 TSV，合并剧情、系统文本和已修改图片，重新生成 `patch.xp3`。
- `start_localized_game.bat`：以 UTF-8 参数启动本地游戏进行测试。

完整打包说明见 [`docs/PATCH_BUILD_README.md`](docs/PATCH_BUILD_README.md)，资源提取说明见 [`docs/EXTRACTION_README.md`](docs/EXTRACTION_README.md)。

打包工具需要用户自行准备合法的游戏文件和提取目录；仓库不会提供原版游戏数据。SCN/PSB 与 TLG 处理依赖 FreeMote v4.7.0，TJS 反编译流程依赖 tjs2-decompiler。第三方程序、OCR 模型和运行时缓存均未提交到仓库。

## 仓库结构

```text
├─ localization/   翻译表、UI 翻译表和自定义图片
├─ tools/          资源提取、OCR、图片处理与 XP3 打包脚本
├─ translator/     .NET 8 表格 AI 翻译工具源码
├─ installer/      .NET Framework 补丁安装器源码
├─ docs/           提取和构建说明
└─ release/        可直接安装的中文补丁压缩包
```

## 源码构建环境

- Windows 10/11
- PowerShell 5.1 或更高版本
- Python 3
- .NET 8 SDK（`translator`）
- .NET Framework 4.7.2 开发工具（`installer`）
- FreeMote v4.7.0（补丁打包）
- PaddleOCR 及其模型（重新扫描图片文字时）

## 版权说明

本项目是爱好者制作的非官方汉化补丁，仅用于学习与交流。仓库不包含游戏本体、原始 XP3 归档、可执行文件、音频或视频等原版资源。游戏及其素材版权归原作者和发行方所有；使用补丁前请自行取得正版游戏。

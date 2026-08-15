# 汉化补丁一键打包

双击项目根目录中的 `build_patch.bat`。

同一时间只能运行一个打包进程；如果重复双击，后启动的进程会提示等待，避免两个构建互相删除临时文件。

每次运行会：

1. 弹窗选择一个剧情翻译 TSV。
2. 校验 TSV 的 3298 条定位、日文原文和角色名，防止错行。
3. 将 `translation_zh_cn` 和 `speaker_zh_cn` 回填到 5 个剧情 JSON。
4. 使用 FreeMote 重新生成 5 个 MDF/PSB 格式的 SCN。
5. 再次反编译 SCN，逐行确认译文和角色名没有丢失。
6. 根据 `extracted/_xp3_manifest.csv` 自动发现 `extracted/` 中修改过的原始资源。
7. 合并 `patch_assets/` 中手动加入的文件。
8. 对比 `extracted/_tlg_png/` 预览与原始 TLG，自动把有像素变化的 PNG 转回 TLG5/TLG6。
9. 把 `localization/text_utf8/` 中的 UTF-8 系统文本一并加入补丁。
10. 生成项目根目录的 `patch.xp3`，然后重新解包做最终校验。

游戏的 `system/Initialize.tjs` 会自动加载根目录中的 `patch.xp3`。该引擎只把补丁归档根目录加入搜索路径，因此打包器会自动把资源转换为扁平文件名（例如 `scn/01.txt.scn` 打包为 `01.txt.scn`），以正确覆盖 `data.xp3` 中的原文件。

中文 Windows 下请通过 `start_localized_game.bat` 启动。它会让游戏以 UTF-8 读取 `patch.xp3` 中的系统文本，并从原始 `data.xp3` 补齐编译脚本和二进制资源，从而避免 Shift_JIS 文本乱码。直接双击 `kazeshiro_demo.exe` 仍可能显示乱码。

## 修改图片

直接修改 `extracted/` 内的原始 PNG，例如：

`extracted/image/logo.png`

脚本会通过长度和 Adler-32 自动发现变化，不需要手动选择图片。

`extracted/_tlg_png/` 是 TLG 图片的可编辑 PNG 版本。打包器会逐像素与原始 TLG 对比，把真正修改过的预览自动转回与原图相同版本的 TLG5/TLG6，并加入补丁。图片宽高不能改变；只修改 PNG 压缩方式或元数据不会被视为画面修改。

## 额外文件

需要加入未在原始清单中的文件时，可按原目录结构放进 `patch_assets/`。打包时会自动取文件名并放到 XP3 根目录。例如：

`patch_assets/system/custom.tjs`

会打包为 `custom.tjs`。由于补丁采用扁平结构，不同目录中不能存在同名资源；发生重名时脚本会停止并报告冲突。

## 输出

- `patch.xp3`：可直接由当前游戏加载的补丁。
- `localization_startup.tjs`、`start_localized_game.bat`：中文 Windows 的无乱码启动器，发布补丁时需要与 `patch.xp3` 一起放到游戏根目录。
- `build/patch_build_report.json`：本次 TSV、文件数量、校验值和资源列表。
- `build/patch_work/`：回编译与验证过程文件；下次构建会自动重建。

打包前请关闭游戏，否则正在使用的 `patch.xp3` 可能无法更新。

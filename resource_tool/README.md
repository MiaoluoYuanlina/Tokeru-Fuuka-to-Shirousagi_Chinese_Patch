# resource_tool

终端式游戏资源汉化工具源码，包含以下入口：

1. `01_Decompile_Game.bat`：反编译 XP3、SCN、TJS/TLG，并导出剧情表格。
2. `02_Build_Patch.bat`：从翻译表格和完整工作目录构建 `patch.xp3`。
3. `03_OCR_Images.bat`：OCR 识别单张图片或包含子目录的图片目录。
4. `04_Render_Translated_Images.bat`：将翻译表格回填为图片。
5. `ResourceTool.bat`：显示统一命令行菜单。

## 未提交的大型依赖

本地完整离线目录约 6 GB，其中 CUDA、PaddleOCR、OCR 模型、Python/Node.js
运行时包含多个超过 GitHub 100 MB 限制的文件，因此下列目录未提交：

```text
runtime/
node_modules/
core/FreeMote-v4.7.0/（仅保留许可证）
```

仓库内保存的是可审阅、可维护的程序源码。直接双击 BAT 运行前，需要从完整
离线发行包恢复上述目录。不要把原版游戏资源、反编译输出或模型缓存提交到仓库。

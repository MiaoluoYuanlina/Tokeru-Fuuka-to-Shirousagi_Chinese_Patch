# game_patch

补丁安装程序源码，目标框架为 .NET Framework 4.7.2。

项目会把 `game_patch/patch.zip` 作为嵌入资源编译进安装程序。该文件约 1 GB，
包含实际补丁负载，因此未提交到 Git 仓库。构建前请自行把准备好的补丁包放到：

```text
game_patch/game_patch/patch.zip
```

然后使用 Visual Studio 打开 `game_patch.slnx` 并构建 Release。`bin`、`obj`、
`.vs`、生成的 EXE/PDB 均属于本机构建产物，已排除。

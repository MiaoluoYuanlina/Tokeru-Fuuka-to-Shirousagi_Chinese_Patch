# 表格 AI 翻译工具

这是一个 .NET 8 命令行工具，支持 `.xlsx`、`.xlsm`、`.csv` 和 `.tsv`。

程序从配置的表头行和起始列（默认 `C1`）向右查找源表头和目标表头。例如 `HeaderRow=5`、`G5` 是 `speaker_original` 时，会逐行读取 `G6`、`G7`……，把翻译写到同一行的首个 `speaker_zh_cn` 列。空源单元格会跳过；目标单元格已有内容时默认也会跳过。

## 双击启动

直接运行 `translate_tool.exe` 且不传参数时，程序会：

1. 自动在程序目录、当前目录和所选表格目录识别翻译配置文件。
2. 弹出 Windows 文件选择框，选择 `.xlsx`、`.xlsm`、`.csv` 或 `.tsv`。
3. 直接开始翻译，结束后保留窗口，按任意键退出。

配置优先识别表格目录、程序目录和当前目录中的 `translator-config.json`、`translate-config.json`、`config.json`。如果没有这些正式配置，则从名称包含 `config` 且字段有效的 JSON 中选取最近修改的一份；都没有时自动创建 `translator-config.json`。程序启动后会打印实际配置路径和最终生效的 `SourceHeader`、`TargetHeader`。

## 快速开始

1. 复制 `translator-config.example.json` 为 `translator-config.json`。
2. 建议把 API Key 放进环境变量，而不是写进配置文件：

   ```powershell
   $env:OPENAI_API_KEY="你的-key"
   ```

3. 在解决方案目录运行：

   ```powershell
   dotnet run --project .\translate_tool\translate_tool.csproj -- "D:\data\台词.xlsx"
   ```

默认输出为 `台词.translated.xlsx`，不会覆盖原表格。要直接覆盖输入文件：

```powershell
dotnet run --project .\translate_tool\translate_tool.csproj -- "D:\data\台词.xlsx" --overwrite-input
```

先检查列和待翻译数量、不调用 API：

```powershell
dotnet run --project .\translate_tool\translate_tool.csproj -- "D:\data\台词.xlsx" --dry-run
```

也可以由程序生成一份默认配置：

```powershell
dotnet run --project .\translate_tool\translate_tool.csproj -- --create-config translator-config.json
```

## 配置说明

- `ApiUrl`：接口完整 URL。OpenAI Responses API 默认是 `https://api.openai.com/v1/responses`。
- `ApiFormat`：`responses` 或 `chat_completions`。第三方 OpenAI 兼容服务常用后者。
- `ApiKey`：API Key；留空时读取 `ApiKeyEnvironmentVariable` 指定的环境变量。
- `ApiKeyHeader` / `ApiKeyPrefix`：默认组成 `Authorization: Bearer <key>`。
- `RequireApiKey`：本地无鉴权服务可设为 `false`。
- `Model`：模型名称，可以自由修改。
- `SystemPrompt`：系统指令（你所说的“谓词/提示词”）。
- `GameContext`：本作《融化的风花与白兔》的角色词表、固定译名和人物关系；会与 `SystemPrompt` 一起作为系统指令发送。
- `Prompt`：每个单元格使用的提示词；`{{text}}` 会替换成源文本。
- `SourceHeader` / `TargetHeader`：源列和译文列的表头。
- `HeaderRow`：搜索表头的行号，默认 `1`。例如设为 `5`，就在第 5 行查找源/目标表头，并从第 6 行开始翻译。
- `HeaderStartColumn`：在 `HeaderRow` 指定的行中开始搜索表头的列，默认 `C`。
- `SourceDataColumnOffset`：相对源表头列读取数据的偏移量，默认 `0`（同列）。如果你的实际格式确实是 `G1` 放 `speaker_original`、数据却在 F 列，请设为 `-1`。
- `SheetName`：工作表名称；为空时使用第一个工作表。
- `OverwriteExistingTranslations`：是否覆盖目标列已有译文，默认 `false`。
- `PreserveBoundaryPunctuation`：默认 `true`。译后校验并原样恢复源文两端的引号、括号、句号、叹号、省略号等；已有译文和旧缓存也会无 Token 修复。
- `MaxConcurrentRequests`：同时执行的 API 请求数，默认 `4`；接口限流严格时可调低，服务能力较强时可适当调高。
- `TextsPerRequest`：每个 API 批次最多翻译的不同文本数，默认 `20`。因此 10,000 个不重复文本通常从 10,000 次请求降为约 500 个批次。
- `MaxCharactersPerRequest`：单批源文本总字符上限，默认 `24000`，避免长台词批次过大。
- `UseStructuredOutputs`：默认 `true`，要求接口以结构化 JSON 返回批量译文；不支持时程序会自动退回普通 JSON 模式。
- `CacheSaveInterval`：目标为每完成多少个不同文本后保存一次缓存，默认 `20`；为了保持并发速度，实际会在完整的并发波次结束后保存。
- `ProgressReportInterval`：每完成多少个不同文本输出一次进度，默认 `10`，减少大量控制台输出造成的等待。
- `CacheFile`：缓存 JSON 文件。相同源文本在相同模型/提示词配置下直接复用，不再请求 API。
- `CacheNamespace`：可选。手动指定后可控制不同配置是否共用缓存。
- `ExtraHeaders`：第三方接口需要的附加请求头。

API 译文会按照 `CacheSaveInterval` 分批原子写入缓存；正常取消时，当前批次中已经成功的结果也会先保存。下次运行可继续复用这些译文。最终表格采用临时文件替换方式保存，避免写出半个文件。

写入 `.xlsx` / `.xlsm` 时，程序会自动移除 XML 1.0 禁止的控制字符（例如 `0x10`），避免保存失败。制表符、换行、回车、正常 Unicode 和 Emoji 会保留。

默认配置会同时处理最多 `4 × 20 = 80` 个不同文本。如果你的接口限额较高，可先尝试将 `TextsPerRequest` 调到 `50`、`MaxConcurrentRequests` 调到 `8`；如果出现 429 限流，则应降低并发数。单批 JSON 格式异常时，程序会自动拆分该批，不会丢行。

如果 `ApiUrl` 以 `/chat/completions` 或 `/responses` 结尾，程序会根据 URL 自动确定最终请求格式，并在启动时打印生效的 API URL、模型和格式。DeepSeek 模型会自动关闭 `json_schema` 严格模式，使用兼容性更高的普通 JSON 批量返回。

批量请求遇到 408、413、502、503、504 或客户端超时时，程序会立即将当前批次减半重试，并自动降低后续批次大小。只有单条文本在重试后仍失败才会停止；已完成的译文会正常写入缓存。

## 第三方 Chat Completions 示例

把配置改为：

```json
{
  "ApiUrl": "https://你的服务/v1/chat/completions",
  "ApiFormat": "chat_completions",
  "Model": "你的模型名"
}
```

配置文件支持的其他字段可参考 `translator-config.example.json`。旧版 `.xls` 请先用 Excel 另存为 `.xlsx`。

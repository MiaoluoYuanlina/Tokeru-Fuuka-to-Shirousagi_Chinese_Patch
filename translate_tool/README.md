# 多供应商表格 AI 翻译工具

这是迁移到新 `tool` 项目的 .NET 8 Windows 翻译程序，支持 `.xlsx`、`.xlsm`、`.csv` 和 `.tsv`。

程序不再读取、搜索或生成 `translator-config.json`。所有设置都集中在：

```text
tool/GlobalSettings.cs
```

修改全局变量后重新编译即可。

## 已支持的 API

| 供应商 | 协议 | 默认地址 | 默认 Key 环境变量 |
|---|---|---|---|
| OpenAI | Responses 或 Chat Completions | `api.openai.com` | `OPENAI_API_KEY` |
| DeepSeek | OpenAI 风格 Chat Completions | `api.deepseek.com/chat/completions` | `DEEPSEEK_API_KEY` |
| Gemini | 原生 `models.generateContent` | `generativelanguage.googleapis.com` | `GEMINI_API_KEY` |
| Claude | 原生 Anthropic Messages | `api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` |
| xAI | OpenAI 风格 Chat Completions | `api.x.ai/v1/chat/completions` | `XAI_API_KEY` |
| 自定义服务 | OpenAI Responses 或 Chat Completions | 在全局变量中填写 | 可自定义 |

请求格式以各家官方文档为准：

- [OpenAI Responses 与 Chat Completions](https://developers.openai.com/api/docs/guides/latest-model)
- [DeepSeek 第一次 API 调用](https://api-docs.deepseek.com/quick_start/pricing-details-usd/)
- [Gemini generateContent](https://ai.google.dev/api/generate-content)
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [xAI Chat Completions](https://docs.x.ai/developers/model-capabilities/legacy/chat-completions)

## 快速开始

### 1. 修改供应商

打开 `tool/GlobalSettings.cs`：

```csharp
public static AiProvider Provider = AiProvider.OpenAI;
public static OpenAiApiMode OpenAiMode = OpenAiApiMode.Responses;
public static string ApiUrl = "";
public static string Model = "";
public static string ApiKey = "";
```

可选值：

```csharp
AiProvider.OpenAI
AiProvider.DeepSeek
AiProvider.Gemini
AiProvider.Claude
AiProvider.XAi
AiProvider.OpenAiCompatible
```

`ApiUrl` 和 `Model` 留空会采用该供应商的内置预设。生产使用建议明确填写账号实际可用的模型 ID。

### 2. 设置 API Key

推荐使用环境变量，不把 Key 编译进 EXE：

```powershell
$env:OPENAI_API_KEY='你的 Key'
$env:DEEPSEEK_API_KEY='你的 Key'
$env:GEMINI_API_KEY='你的 Key'
$env:ANTHROPIC_API_KEY='你的 Key'
$env:XAI_API_KEY='你的 Key'
```

只需设置当前供应商对应的一个变量。

也可以直接写入：

```csharp
public static string ApiKey = "你的 Key";
```

但 Key 会进入编译产物，可能被提取，不建议发布这种 EXE。

### 3. 修改表头

角色名翻译：

```csharp
public static string SourceHeader = "speaker_original";
public static string TargetHeader = "speaker_zh_cn";
```

剧情正文翻译：

```csharp
public static string SourceHeader = "original_text";
public static string TargetHeader = "translation_zh_cn";
```

非第一行表头：

```csharp
public static int HeaderRow = 5;
public static string HeaderStartColumn = "C";
```

### 4. 构建

```powershell
dotnet build .\tool\tool.csproj -c Release
```

输出位置：

```text
tool/bin/Release/net8.0-windows/tool.exe
```

### 5. 运行

双击 `tool.exe` 选择表格，或命令行：

```powershell
.\tool.exe 'D:\data\scenario.xlsx'
.\tool.exe 'D:\data\scenario.tsv' --output 'D:\data\scenario.done.tsv'
.\tool.exe 'D:\data\scenario.xlsx' --dry-run
```

默认生成 `<原名>.translated.<扩展名>`，不覆盖源文件。

## 离线协议自检

以下命令不会调用 API，也不需要 Key：

```powershell
.\tool.exe --self-test
```

它会验证：

- 6 种请求组合的 URL、鉴权头和 JSON 请求体。
- OpenAI Responses 与 Chat Completions 两种格式。
- DeepSeek 的 `messages` 和 `json_object`。
- Gemini 的 `contents`、`systemInstruction` 和 JSON Schema。
- Claude 的顶层 `system`、`max_tokens`、`anthropic-version`。
- xAI Chat Completions。
- 各种响应结构中的译文提取。

## 自定义 OpenAI 兼容服务

```csharp
public static AiProvider Provider = AiProvider.OpenAiCompatible;
public static OpenAiApiMode OpenAiMode = OpenAiApiMode.ChatCompletions;
public static string ApiUrl = "https://你的服务/v1/chat/completions";
public static string Model = "你的模型名";
public static string CustomApiKeyHeader = "Authorization";
public static string CustomApiKeyPrefix = "Bearer";
```

如果是 Responses 兼容端点：

```csharp
public static OpenAiApiMode OpenAiMode = OpenAiApiMode.Responses;
public static string ApiUrl = "https://你的服务/v1/responses";
```

第三方兼容接口如果不支持严格结构化输出，会在 400、404 或 422 后自动退回普通 JSON 批量模式。

## 性能、缓存和断点续跑

```csharp
public static int MaxConcurrentRequests = 4;
public static int TextsPerRequest = 20;
public static int MaxCharactersPerRequest = 24000;
public static int MaxRetries = 3;
public static int RequestTimeoutSeconds = 120;
```

- 相同文本先合并，再按批次发送。
- 成功译文分波次原子写入 `translation-cache.json`。
- 重新运行时直接复用缓存。
- 408、413、502、503、504 和超时会自动拆小批次。
- 429 和服务端错误会按退避策略重试。
- 目标列已有内容时默认跳过。
- 边界引号、括号和句末标点会自动保护。

相对缓存路径以 `tool.exe` 所在目录为基准。

## 项目结构

```text
tool/
├─ tool.slnx
├─ README.md
├─ NuGet.Config
└─ tool/
   ├─ GlobalSettings.cs             # 唯一运行配置入口
   ├─ AppOptions.cs                 # 全局变量运行时快照与校验
   ├─ ProviderProtocol.cs           # 多供应商请求构造和响应解析
   ├─ ProviderProtocolSelfTest.cs   # 无网络协议回归测试
   ├─ MultiProviderTranslator.cs    # 批量、重试、拆批
   ├─ TranslationApplication.cs     # 表格扫描、缓存和写回
   ├─ TranslationCache.cs
   ├─ TranslationTextPostProcessor.cs
   ├─ XlsxTableDocument.cs
   ├─ CsvTableDocument.cs
   ├─ TableDocument.cs
   └─ Program.cs
```

## 常见问题

### DeepSeek 报 `field messages is required`

将 `Provider` 设为 `AiProvider.DeepSeek`。程序会使用 Chat Completions 的 `messages`，不会按 OpenAI Responses 发送。

### 报 `'<` is an invalid start of a value`

这表示接口返回了 HTML 网关页面而不是 JSON。程序会自动重试；如果仍然失败则立即停止，不会无意义地继续拆小批次。错误信息会显示状态码、`Content-Type` 和响应开头，便于判断中转服务、反向代理或上游网关故障。

### Gemini 返回 401/403

确认使用 `GEMINI_API_KEY`。原生 Gemini 接口使用 `x-goog-api-key`，不是 `Authorization: Bearer`。

### Claude 报 system role 无效

将 `Provider` 设为 `AiProvider.Claude`。程序会把系统提示放在顶层 `system`，不会放入 `messages`。

### 504 或翻译很慢

降低 `TextsPerRequest` 与 `MaxConcurrentRequests`。重新运行不会丢失已经写入缓存的译文。

### 429 提示 `no credits remaining`

这是账号或中转服务余额耗尽，不是普通限流。充值或更换有余额的 API Key 后才能继续；程序会立即停止，不再重试这类永久性错误。普通的 429 限流仍会自动退避重试。

### 修改全局变量后没有生效

必须重新构建并运行刚生成的 `tool.exe`，同时确认没有误运行其他目录中的旧 EXE。

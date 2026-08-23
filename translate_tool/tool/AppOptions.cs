using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TranslateTool;

internal enum ApiProtocol
{
    OpenAiResponses,
    OpenAiChatCompletions,
    GeminiGenerateContent,
    AnthropicMessages
}

/// <summary>
/// GlobalSettings 的运行时快照。程序不读取配置 JSON。
/// </summary>
internal sealed class AppOptions
{
    public AiProvider Provider { get; private init; }
    public ApiProtocol Protocol { get; private init; }
    public string ApiUrl { get; private init; } = "";
    public string ApiKey { get; private init; } = "";
    public string ApiKeyEnvironmentVariable { get; private init; } = "";
    public bool RequireApiKey { get; private init; }
    public string ApiKeyHeader { get; private init; } = "Authorization";
    public string ApiKeyPrefix { get; private init; } = "Bearer";
    public string AnthropicVersion { get; private init; } = "2023-06-01";
    public int ClaudeMaxOutputTokens { get; private init; }
    public string Model { get; private init; } = "";
    public string SystemPrompt { get; private init; } = "";
    public string GameContext { get; private init; } = "";
    public string Prompt { get; private init; } = "";
    public string SourceHeader { get; private init; } = "";
    public string TargetHeader { get; private init; } = "";
    public string HeaderStartColumn { get; private init; } = "";
    public int HeaderRow { get; private init; }
    public int SourceDataColumnOffset { get; private init; }
    public string? SheetName { get; private init; }
    public string? OutputFile { get; private init; }
    public string CacheFile { get; private init; } = "";
    public string? CacheNamespace { get; private init; }
    public bool OverwriteExistingTranslations { get; private init; }
    public bool PreserveBoundaryPunctuation { get; private init; }
    public int MaxConcurrentRequests { get; private init; }
    public int TextsPerRequest { get; private init; }
    public int MaxCharactersPerRequest { get; private init; }
    public bool UseStructuredOutputs { get; private init; }
    public int CacheSaveInterval { get; private init; }
    public int ProgressReportInterval { get; private init; }
    public int MaxRetries { get; private init; }
    public int RequestTimeoutSeconds { get; private init; }
    public int RequestDelayMilliseconds { get; private init; }
    public string CsvDelimiter { get; private init; } = "auto";
    public Dictionary<string, string> ExtraHeaders { get; private init; } = new(StringComparer.OrdinalIgnoreCase);

    public static JsonSerializerOptions JsonOptions { get; } = new()
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public static AppOptions FromGlobalSettings(
        AiProvider? providerOverride = null,
        OpenAiApiMode? openAiModeOverride = null)
    {
        var provider = providerOverride ?? GlobalSettings.Provider;
        var openAiMode = openAiModeOverride ?? GlobalSettings.OpenAiMode;
        var defaults = ResolveProviderDefaults(provider, openAiMode);
        var model = FirstNonEmpty(GlobalSettings.Model, defaults.Model);
        var url = FirstNonEmpty(GlobalSettings.ApiUrl, defaults.ApiUrl);
        if (provider == AiProvider.Gemini)
        {
            var normalizedModel = model.StartsWith("models/", StringComparison.OrdinalIgnoreCase)
                ? model["models/".Length..]
                : model;
            url = url.Replace("{model}", Uri.EscapeDataString(normalizedModel), StringComparison.OrdinalIgnoreCase);
        }

        var options = new AppOptions
        {
            Provider = provider,
            Protocol = defaults.Protocol,
            ApiUrl = url,
            ApiKey = GlobalSettings.ApiKey,
            ApiKeyEnvironmentVariable = FirstNonEmpty(
                GlobalSettings.ApiKeyEnvironmentVariable,
                defaults.ApiKeyEnvironmentVariable),
            RequireApiKey = GlobalSettings.RequireApiKey,
            ApiKeyHeader = provider == AiProvider.OpenAiCompatible
                ? GlobalSettings.CustomApiKeyHeader
                : defaults.ApiKeyHeader,
            ApiKeyPrefix = provider == AiProvider.OpenAiCompatible
                ? GlobalSettings.CustomApiKeyPrefix
                : defaults.ApiKeyPrefix,
            AnthropicVersion = GlobalSettings.AnthropicVersion,
            ClaudeMaxOutputTokens = GlobalSettings.ClaudeMaxOutputTokens,
            Model = model,
            SystemPrompt = GlobalSettings.SystemPrompt,
            GameContext = GlobalSettings.GameContext,
            Prompt = GlobalSettings.Prompt,
            SourceHeader = GlobalSettings.SourceHeader,
            TargetHeader = GlobalSettings.TargetHeader,
            HeaderStartColumn = GlobalSettings.HeaderStartColumn,
            HeaderRow = GlobalSettings.HeaderRow,
            SourceDataColumnOffset = GlobalSettings.SourceDataColumnOffset,
            SheetName = GlobalSettings.SheetName,
            OutputFile = GlobalSettings.OutputFile,
            CacheFile = GlobalSettings.CacheFile,
            CacheNamespace = GlobalSettings.CacheNamespace,
            OverwriteExistingTranslations = GlobalSettings.OverwriteExistingTranslations,
            PreserveBoundaryPunctuation = GlobalSettings.PreserveBoundaryPunctuation,
            MaxConcurrentRequests = GlobalSettings.MaxConcurrentRequests,
            TextsPerRequest = GlobalSettings.TextsPerRequest,
            MaxCharactersPerRequest = GlobalSettings.MaxCharactersPerRequest,
            UseStructuredOutputs = GlobalSettings.UseStructuredOutputs,
            CacheSaveInterval = GlobalSettings.CacheSaveInterval,
            ProgressReportInterval = GlobalSettings.ProgressReportInterval,
            MaxRetries = GlobalSettings.MaxRetries,
            RequestTimeoutSeconds = GlobalSettings.RequestTimeoutSeconds,
            RequestDelayMilliseconds = GlobalSettings.RequestDelayMilliseconds,
            CsvDelimiter = GlobalSettings.CsvDelimiter,
            ExtraHeaders = new Dictionary<string, string>(
                GlobalSettings.ExtraHeaders,
                StringComparer.OrdinalIgnoreCase)
        };
        options.Validate();
        return options;
    }

    public string GetApiKey()
    {
        if (!string.IsNullOrWhiteSpace(ApiKey))
        {
            return ApiKey.Trim();
        }

        return string.IsNullOrWhiteSpace(ApiKeyEnvironmentVariable)
            ? ""
            : Environment.GetEnvironmentVariable(ApiKeyEnvironmentVariable)?.Trim() ?? "";
    }

    public string BuildPrompt(string text)
    {
        return Prompt.Contains("{{text}}", StringComparison.Ordinal)
            ? Prompt.Replace("{{text}}", text, StringComparison.Ordinal)
            : $"{Prompt}\n\n{text}";
    }

    public string BuildInstructions()
    {
        return string.Join("\n\n", new[] { SystemPrompt, GameContext }
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim()));
    }

    public string ResolveCacheScope()
    {
        return string.IsNullOrWhiteSpace(CacheNamespace)
            ? string.Join(
                "\n",
                Provider,
                Protocol,
                ApiUrl,
                Model,
                BuildInstructions(),
                Prompt,
                TargetHeader)
            : CacheNamespace.Trim();
    }

    public string ProtocolDisplayName => Protocol switch
    {
        ApiProtocol.OpenAiResponses => "OpenAI Responses",
        ApiProtocol.OpenAiChatCompletions => "OpenAI Chat Completions",
        ApiProtocol.GeminiGenerateContent => "Gemini generateContent",
        ApiProtocol.AnthropicMessages => "Anthropic Messages",
        _ => Protocol.ToString()
    };

    private void Validate()
    {
        if (Provider == AiProvider.OpenAiCompatible && string.IsNullOrWhiteSpace(GlobalSettings.ApiUrl))
        {
            throw new InvalidDataException("OpenAiCompatible 必须在 GlobalSettings.ApiUrl 中填写完整请求 URL。 ");
        }

        if (!Uri.TryCreate(ApiUrl, UriKind.Absolute, out var apiUri)
            || (apiUri.Scheme != Uri.UriSchemeHttp && apiUri.Scheme != Uri.UriSchemeHttps))
        {
            throw new InvalidDataException("GlobalSettings.ApiUrl 必须解析为完整的 http/https URL。 ");
        }

        if (RequireApiKey && string.IsNullOrWhiteSpace(ApiKeyHeader))
        {
            throw new InvalidDataException("RequireApiKey 为 true 时，API Key 请求头不能为空。 ");
        }

        if (string.IsNullOrWhiteSpace(Model))
        {
            throw new InvalidDataException("GlobalSettings.Model 不能为空。 ");
        }

        if (string.IsNullOrWhiteSpace(SourceHeader) || string.IsNullOrWhiteSpace(TargetHeader))
        {
            throw new InvalidDataException("SourceHeader 和 TargetHeader 不能为空。 ");
        }

        _ = CellReference.ColumnNameToNumber(HeaderStartColumn);
        if (HeaderRow <= 0 || HeaderRow >= 1_048_576)
        {
            throw new InvalidDataException("HeaderRow 必须为 1-1048575。 ");
        }

        if (MaxConcurrentRequests <= 0 || CacheSaveInterval <= 0 || ProgressReportInterval <= 0)
        {
            throw new InvalidDataException("并发数、缓存保存间隔和进度报告间隔必须大于 0。 ");
        }

        if (TextsPerRequest <= 0 || TextsPerRequest > 200 || MaxCharactersPerRequest <= 0)
        {
            throw new InvalidDataException("TextsPerRequest 必须为 1-200，MaxCharactersPerRequest 必须大于 0。 ");
        }

        if (MaxRetries < 0 || RequestTimeoutSeconds <= 0 || RequestDelayMilliseconds < 0)
        {
            throw new InvalidDataException("重试次数、超时和请求间隔配置无效。 ");
        }

        if (ClaudeMaxOutputTokens <= 0)
        {
            throw new InvalidDataException("ClaudeMaxOutputTokens 必须大于 0。 ");
        }
    }

    private static ProviderDefaults ResolveProviderDefaults(
        AiProvider provider,
        OpenAiApiMode openAiMode)
    {
        return provider switch
        {
            AiProvider.OpenAI when openAiMode == OpenAiApiMode.Responses => new(
                ApiProtocol.OpenAiResponses,
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                "OPENAI_API_KEY",
                "Authorization",
                "Bearer"),
            AiProvider.OpenAI => new(
                ApiProtocol.OpenAiChatCompletions,
                "https://api.openai.com/v1/chat/completions",
                "gpt-5.4",
                "OPENAI_API_KEY",
                "Authorization",
                "Bearer"),
            AiProvider.DeepSeek => new(
                ApiProtocol.OpenAiChatCompletions,
                "https://api.deepseek.com/chat/completions",
                "deepseek-v4-flash",
                "DEEPSEEK_API_KEY",
                "Authorization",
                "Bearer"),
            AiProvider.Gemini => new(
                ApiProtocol.GeminiGenerateContent,
                "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                "gemini-3.7-flash",
                "GEMINI_API_KEY",
                "x-goog-api-key",
                ""),
            AiProvider.Claude => new(
                ApiProtocol.AnthropicMessages,
                "https://api.anthropic.com/v1/messages",
                "claude-sonnet-4-6",
                "ANTHROPIC_API_KEY",
                "x-api-key",
                ""),
            AiProvider.XAi => new(
                ApiProtocol.OpenAiChatCompletions,
                "https://api.x.ai/v1/chat/completions",
                "grok-4.6",
                "XAI_API_KEY",
                "Authorization",
                "Bearer"),
            AiProvider.OpenAiCompatible when openAiMode == OpenAiApiMode.Responses => new(
                ApiProtocol.OpenAiResponses,
                "",
                "",
                "OPENAI_API_KEY",
                "Authorization",
                "Bearer"),
            AiProvider.OpenAiCompatible => new(
                ApiProtocol.OpenAiChatCompletions,
                "",
                "",
                "OPENAI_API_KEY",
                "Authorization",
                "Bearer"),
            _ => throw new ArgumentOutOfRangeException(nameof(provider), provider, null)
        };
    }

    private static string FirstNonEmpty(string first, string second)
    {
        return string.IsNullOrWhiteSpace(first) ? second : first.Trim();
    }

    private sealed record ProviderDefaults(
        ApiProtocol Protocol,
        string ApiUrl,
        string Model,
        string ApiKeyEnvironmentVariable,
        string ApiKeyHeader,
        string ApiKeyPrefix);
}

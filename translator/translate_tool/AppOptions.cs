using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TranslateTool;

internal sealed class AppOptions
{
    public string ApiUrl { get; set; } = "https://api.openai.com/v1/responses";
    public string ApiKey { get; set; } = "";
    public string ApiKeyEnvironmentVariable { get; set; } = "OPENAI_API_KEY";
    public string ApiKeyHeader { get; set; } = "Authorization";
    public string ApiKeyPrefix { get; set; } = "Bearer";
    public bool RequireApiKey { get; set; } = true;
    public string ApiFormat { get; set; } = "responses";
    public string Model { get; set; } = "gpt-5.6-luna";
    public string SystemPrompt { get; set; } = "你是一名专业的游戏本地化译者。准确翻译，保留占位符、转义符、标签和原有换行，只返回译文，不要解释。";
    public string GameContext { get; set; } = """
        游戏中文名：《融化的风花与白兔》

        翻译与专名规则：
        - 固定使用以下简体中文角色名：Pooka／プーカ＝普卡；Minoru／稔＝稔；Nora／乃良＝乃良；Haruka／春香＝春香；Akiho／秋穂＝秋穗；Eri／絵利＝绘利；Miyo／美世＝美世。
        - “ちゃちゃたん！”与“ニャクルト”（Nyakuruto）是作品专有名称；没有明确官方中文译名时保留原文，不要自行创造译名。
        - 天之川综合医院使用此固定译名。
        - 根据角色身份、关系和性格选择自然称谓与语气，保持同一角色前后一致。

        角色词表与设定：
        1. 普卡（Pooka／プーカ），配音：菱川花菜。突然出现在主人公面前、戴兔耳的神秘少女。身体似乎有些透明，只有主人公能看见。性格开朗天真、我行我素，喜欢漫画、美食和“ちゃちゃたん！”，擅长自由自在地生活。
        2. 稔（Minoru／稔），主人公，无配音。雪国小镇的酒吧店长，擅长做饭和调制鸡尾酒，性格稍显刻薄但很会照顾人，无法对别人置之不理。遇见只有自己能看见的普卡后，开始喧闹而不可思议的共同生活。喜欢安静的时光，擅长做饭。
        3. 乃良（Nora／乃良），配音：立花日菜。最近才来到小镇、带有神秘气息的少女。沉默寡言、表情变化少，氛围安静而不可思议。喜欢兔子，擅长面无表情。
        4. 春香（Haruka／春香），配音：星谷美绪，秋穗的妹妹。活泼开朗、充满活力，好奇心旺盛，想到什么就会立刻说出口，是活跃气氛的人。喜欢“ニャクルト”，擅长迅速与别人成为朋友。
        5. 秋穗（Akiho／秋穂），配音：永野爱。护士，主人公的青梅竹马，就职于天之川综合医院。与稔读过同一所小学，也曾与美世关系很好；后来突然在医院与稔碰面，双方处境尴尬。可靠、善于照顾他人，无法对有困难的人坐视不管。喜欢甜味饮料，擅长察觉他人的身体状况。
        6. 绘利（Eri／絵利），配音：日冈夏美。住在主人公隔壁的女性，平时以某位“V主播”的身份直播。喝醉时非常开朗，清醒时却举止可疑、极不擅长交流。喜欢酒，擅长项未注明。
        7. 美世（Miyo／美世），配音：友永朱音，稔的姐姐。性格可靠，一直很关心弟弟，偶尔会来看稔；因弟弟突然声称能看见兔女郎而困惑。喜欢家人，擅长做饭。

        语音说明：本作为“主人公以外全员全语音”，因此男主角稔没有配音演员。
        """;
    public string Prompt { get; set; } = "将以下文本翻译为简体中文：\n\n{{text}}";
    public string SourceHeader { get; set; } = "speaker_original";
    public string TargetHeader { get; set; } = "speaker_zh_cn";
    public string HeaderStartColumn { get; set; } = "C";
    public int HeaderRow { get; set; } = 1;
    public int SourceDataColumnOffset { get; set; }
    public string? SheetName { get; set; }
    public string? OutputFile { get; set; }
    public string CacheFile { get; set; } = "translation-cache.json";
    public string? CacheNamespace { get; set; }
    public bool OverwriteExistingTranslations { get; set; }
    public bool PreserveBoundaryPunctuation { get; set; } = true;
    public int MaxConcurrentRequests { get; set; } = 4;
    public int TextsPerRequest { get; set; } = 20;
    public int MaxCharactersPerRequest { get; set; } = 24000;
    public bool UseStructuredOutputs { get; set; } = true;
    public int CacheSaveInterval { get; set; } = 20;
    public int ProgressReportInterval { get; set; } = 10;
    public int MaxRetries { get; set; } = 3;
    public int RequestTimeoutSeconds { get; set; } = 120;
    public int RequestDelayMilliseconds { get; set; }
    public string CsvDelimiter { get; set; } = "auto";
    public Dictionary<string, string> ExtraHeaders { get; set; } = new(StringComparer.OrdinalIgnoreCase);

    [JsonIgnore]
    public static JsonSerializerOptions JsonOptions { get; } = new()
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public static async Task<AppOptions> LoadAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"找不到配置文件：{path}");
        }

        await using var stream = File.OpenRead(path);
        var options = await JsonSerializer.DeserializeAsync<AppOptions>(stream, JsonOptions, cancellationToken)
            ?? throw new InvalidDataException("配置文件内容为空。 ");
        options.Validate();
        return options;
    }

    public static async Task SaveExampleAsync(string path, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        await using var stream = File.Create(fullPath);
        await JsonSerializer.SerializeAsync(stream, new AppOptions(), JsonOptions, cancellationToken);
        await stream.FlushAsync(cancellationToken);
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
            ? string.Join("\n", ApiUrl, ResolveApiFormat(), Model, BuildInstructions(), Prompt, TargetHeader)
            : CacheNamespace.Trim();
    }

    public string ResolveApiFormat()
    {
        if (Uri.TryCreate(ApiUrl, UriKind.Absolute, out var apiUri))
        {
            var path = apiUri.AbsolutePath.TrimEnd('/');
            if (path.EndsWith("/chat/completions", StringComparison.OrdinalIgnoreCase))
            {
                return "chat_completions";
            }

            if (path.EndsWith("/responses", StringComparison.OrdinalIgnoreCase))
            {
                return "responses";
            }
        }

        return ApiFormat.Trim();
    }

    private void Validate()
    {
        if (!Uri.TryCreate(ApiUrl, UriKind.Absolute, out var apiUri)
            || (apiUri.Scheme != Uri.UriSchemeHttp && apiUri.Scheme != Uri.UriSchemeHttps))
        {
            throw new InvalidDataException("ApiUrl 必须是完整的 http/https URL。 ");
        }

        if (RequireApiKey && string.IsNullOrWhiteSpace(ApiKeyHeader))
        {
            throw new InvalidDataException("RequireApiKey 为 true 时，ApiKeyHeader 不能为空。 ");
        }

        if (string.IsNullOrWhiteSpace(Model))
        {
            throw new InvalidDataException("Model 不能为空。 ");
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

        if (!ApiFormat.Equals("responses", StringComparison.OrdinalIgnoreCase)
            && !ApiFormat.Equals("chat_completions", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("ApiFormat 仅支持 responses 或 chat_completions。 ");
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
    }
}

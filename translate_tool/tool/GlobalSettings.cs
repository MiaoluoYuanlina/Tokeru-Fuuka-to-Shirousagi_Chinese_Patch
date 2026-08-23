namespace TranslateTool;

/// <summary>
/// API 供应商。修改本文件后重新编译即可，不再读取 translator-config.json。
/// </summary>
public enum AiProvider
{
    OpenAI,
    DeepSeek,
    Gemini,
    Claude,
    XAi,
    OpenAiCompatible
}

/// <summary>
/// OpenAI 与自定义 OpenAI 兼容服务使用的协议。
/// </summary>
public enum OpenAiApiMode
{
    Responses,
    ChatCompletions
}

/// <summary>
/// 全部可编辑配置都集中在这里。修改后需要重新编译项目。
/// API Key 可以直接填写，但更推荐保留空字符串并设置对应环境变量。
/// </summary>
public static class GlobalSettings
{
    // ======================== API 供应商 ========================

    public static AiProvider Provider = AiProvider.DeepSeek;

    // OpenAI 或 OpenAiCompatible 时生效。
    public static OpenAiApiMode OpenAiMode = OpenAiApiMode.Responses;

    // 留空时使用所选供应商的官方地址。自定义中转服务应填写完整请求 URL。
    // Gemini 自定义 URL 可以包含 {model} 占位符。
    public static string ApiUrl = "https://ai.ica.wiki/v1/chat/completions";

    // 留空时使用供应商当前预设模型。建议明确填写账号实际可用的模型 ID。
    public static string Model = "gpt-5.6-sol";

    // 可以直接填写 Key；编译后的 EXE 中仍可被提取，因此更推荐使用环境变量。
    public static string ApiKey = "";

    // 留空时自动使用 OPENAI_API_KEY、DEEPSEEK_API_KEY、GEMINI_API_KEY、 
    // ANTHROPIC_API_KEY 或 XAI_API_KEY。
    public static string ApiKeyEnvironmentVariable = "";

    public static bool RequireApiKey = true;

    // 只用于 OpenAiCompatible。其他官方供应商会自动使用正确的请求头。
    public static string CustomApiKeyHeader = "Authorization";
    public static string CustomApiKeyPrefix = "Bearer";

    // Claude Messages API 的必需版本头。通常不要修改。
    public static string AnthropicVersion = "2023-06-01";

    // Claude 输出 Token 上限。
    public static int ClaudeMaxOutputTokens = 16384;

    // 额外请求头。相同名称会覆盖程序自动生成的请求头。
    public static Dictionary<string, string> ExtraHeaders = new(StringComparer.OrdinalIgnoreCase);

    // ======================== 翻译提示词 ========================

    public static string SystemPrompt =
        "你是一名专业的游戏本地化译者。准确翻译，保留占位符、转义符、标签和原有换行，只返回译文，不要解释。";

    public static string GameContext = """
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

    // {{text}} 会替换为当前源文本。批量翻译时也会把此模板发给模型。
    public static string Prompt = "将以下文本翻译为简体中文：\n\n{{text}}";

    // ======================== 表格列 ========================

    public static string SourceHeader = "original_text";//原文
    public static string TargetHeader = "translation_zh_cn";//翻文
    public static string HeaderStartColumn = "A";
    public static int HeaderRow = 1;
    public static int SourceDataColumnOffset = 0;
    public static string? SheetName = null;
    public static string? OutputFile = null;
    public static string CsvDelimiter = "auto";

    // ======================== 写入与缓存 ========================

    // 相对路径以 EXE 所在目录为基准。
    public static string CacheFile = "translation-cache.json";
    public static string? CacheNamespace = null;
    public static bool OverwriteExistingTranslations = false;
    public static bool PreserveBoundaryPunctuation = true;

    // ======================== 性能与可靠性 ========================

    public static int MaxConcurrentRequests = 4;
    public static int TextsPerRequest = 20;
    public static int MaxCharactersPerRequest = 24000;
    public static bool UseStructuredOutputs = true;
    public static int CacheSaveInterval = 20;
    public static int ProgressReportInterval = 20;
    public static int MaxRetries = 3;
    public static int RequestTimeoutSeconds = 120;
    public static int RequestDelayMilliseconds = 0;
}

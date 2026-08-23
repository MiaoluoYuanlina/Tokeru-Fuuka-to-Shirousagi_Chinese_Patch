using System.Text.Json;

namespace TranslateTool;

internal static class ProviderProtocolSelfTest
{
    public static int Run()
    {
        var savedUrl = GlobalSettings.ApiUrl;
        var savedModel = GlobalSettings.Model;
        var savedEnvironmentVariable = GlobalSettings.ApiKeyEnvironmentVariable;
        try
        {
            // 自检始终使用内置官方预设，不受用户当前连接参数影响，也不会发起网络请求。
            GlobalSettings.ApiUrl = "";
            GlobalSettings.Model = "";
            GlobalSettings.ApiKeyEnvironmentVariable = "";

            var cases = new[]
            {
                new TestCase(
                    "OpenAI Responses",
                    AiProvider.OpenAI,
                    OpenAiApiMode.Responses,
                    ApiProtocol.OpenAiResponses,
                    "Authorization",
                    "{\"output\":[{\"content\":[{\"type\":\"output_text\",\"text\":\"ok\"}]}]}"),
                new TestCase(
                    "OpenAI Chat Completions",
                    AiProvider.OpenAI,
                    OpenAiApiMode.ChatCompletions,
                    ApiProtocol.OpenAiChatCompletions,
                    "Authorization",
                    "{\"choices\":[{\"message\":{\"content\":\"ok\"}}]}"),
                new TestCase(
                    "DeepSeek Chat Completions",
                    AiProvider.DeepSeek,
                    OpenAiApiMode.ChatCompletions,
                    ApiProtocol.OpenAiChatCompletions,
                    "Authorization",
                    "{\"choices\":[{\"message\":{\"content\":\"ok\"}}]}"),
                new TestCase(
                    "Gemini generateContent",
                    AiProvider.Gemini,
                    OpenAiApiMode.ChatCompletions,
                    ApiProtocol.GeminiGenerateContent,
                    "x-goog-api-key",
                    "{\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"ok\"}]}}]}"),
                new TestCase(
                    "Claude Messages",
                    AiProvider.Claude,
                    OpenAiApiMode.ChatCompletions,
                    ApiProtocol.AnthropicMessages,
                    "x-api-key",
                    "{\"content\":[{\"type\":\"text\",\"text\":\"ok\"}]}"),
                new TestCase(
                    "xAI Chat Completions",
                    AiProvider.XAi,
                    OpenAiApiMode.ChatCompletions,
                    ApiProtocol.OpenAiChatCompletions,
                    "Authorization",
                    "{\"choices\":[{\"message\":{\"content\":\"ok\"}}]}")
            };

            foreach (var testCase in cases)
            {
                RunCase(testCase);
                Console.WriteLine($"[通过] {testCase.Name}");
            }

            Console.WriteLine($"离线协议自检完成：{cases.Length}/{cases.Length} 通过，未调用任何 API。 ");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"协议自检失败：{exception.Message}");
            return 1;
        }
        finally
        {
            GlobalSettings.ApiUrl = savedUrl;
            GlobalSettings.Model = savedModel;
            GlobalSettings.ApiKeyEnvironmentVariable = savedEnvironmentVariable;
        }
    }

    private static void RunCase(TestCase testCase)
    {
        var options = AppOptions.FromGlobalSettings(testCase.Provider, testCase.OpenAiMode);
        if (options.Protocol != testCase.Protocol)
        {
            throw new InvalidDataException(
                $"{testCase.Name} 协议错误：{options.Protocol}，期望 {testCase.Protocol}");
        }

        using var request = ProviderRequestBuilder.Build(
            options,
            "test prompt",
            useStructuredOutput: true,
            apiKey: "test-key");
        if (request.Method != HttpMethod.Post || request.RequestUri is null)
        {
            throw new InvalidDataException($"{testCase.Name} 请求方法或 URL 无效。 ");
        }

        if (!request.Headers.TryGetValues(testCase.ApiKeyHeader, out var values)
            || !values.Any(value => value.Contains("test-key", StringComparison.Ordinal)))
        {
            throw new InvalidDataException($"{testCase.Name} 缺少 {testCase.ApiKeyHeader} 鉴权头。 ");
        }

        if (testCase.Protocol == ApiProtocol.AnthropicMessages
            && !request.Headers.Contains("anthropic-version"))
        {
            throw new InvalidDataException("Claude 请求缺少 anthropic-version。 ");
        }

        var bodyText = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
        using var body = JsonDocument.Parse(bodyText);
        ValidateRequestBody(testCase, body.RootElement);

        var extracted = ProviderResponseParser.ExtractText(testCase.Protocol, testCase.ResponseJson);
        if (extracted != "ok")
        {
            throw new InvalidDataException($"{testCase.Name} 响应解析失败：{extracted}");
        }
    }

    private static void ValidateRequestBody(TestCase testCase, JsonElement root)
    {
        switch (testCase.Protocol)
        {
            case ApiProtocol.OpenAiResponses:
                Require(root, "model", "input", "instructions", "text");
                break;
            case ApiProtocol.OpenAiChatCompletions:
                Require(root, "model", "messages", "stream", "response_format");
                if (testCase.Provider == AiProvider.DeepSeek
                    && root.GetProperty("response_format").GetProperty("type").GetString() != "json_object")
                {
                    throw new InvalidDataException("DeepSeek 必须使用 json_object 输出格式。 ");
                }
                break;
            case ApiProtocol.GeminiGenerateContent:
                Require(root, "contents", "systemInstruction", "generationConfig");
                var generationConfig = root.GetProperty("generationConfig");
                Require(generationConfig, "responseMimeType", "responseJsonSchema");
                if (generationConfig.GetProperty("responseMimeType").GetString() != "application/json")
                {
                    throw new InvalidDataException("Gemini 结构化输出必须请求 application/json。 ");
                }
                break;
            case ApiProtocol.AnthropicMessages:
                Require(root, "model", "max_tokens", "messages", "system", "output_config");
                break;
            default:
                throw new ArgumentOutOfRangeException();
        }
    }

    private static void Require(JsonElement root, params string[] properties)
    {
        foreach (var property in properties)
        {
            if (!root.TryGetProperty(property, out _))
            {
                throw new InvalidDataException($"请求体缺少字段：{property}");
            }
        }
    }

    private sealed record TestCase(
        string Name,
        AiProvider Provider,
        OpenAiApiMode OpenAiMode,
        ApiProtocol Protocol,
        string ApiKeyHeader,
        string ResponseJson);
}

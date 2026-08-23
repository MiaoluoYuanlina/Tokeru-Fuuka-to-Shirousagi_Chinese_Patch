using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace TranslateTool;

internal static class ProviderRequestBuilder
{
    public static HttpRequestMessage Build(
        AppOptions options,
        string prompt,
        bool useStructuredOutput,
        string apiKey)
    {
        var instructions = options.BuildInstructions();
        var body = options.Protocol switch
        {
            ApiProtocol.OpenAiResponses => BuildOpenAiResponsesBody(
                options,
                instructions,
                prompt,
                useStructuredOutput),
            ApiProtocol.OpenAiChatCompletions => BuildOpenAiChatBody(
                options,
                instructions,
                prompt,
                useStructuredOutput),
            ApiProtocol.GeminiGenerateContent => BuildGeminiBody(
                instructions,
                prompt,
                useStructuredOutput),
            ApiProtocol.AnthropicMessages => BuildClaudeBody(
                options,
                instructions,
                prompt,
                useStructuredOutput),
            _ => throw new ArgumentOutOfRangeException(nameof(options.Protocol), options.Protocol, null)
        };

        var json = JsonSerializer.Serialize(body, AppOptions.JsonOptions);
        var request = new HttpRequestMessage(HttpMethod.Post, options.ApiUrl)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        };
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        ApplyAuthentication(request, options, apiKey);
        ApplyExtraHeaders(request, options.ExtraHeaders);
        return request;
    }

    private static Dictionary<string, object?> BuildOpenAiResponsesBody(
        AppOptions options,
        string instructions,
        string prompt,
        bool structured)
    {
        var body = new Dictionary<string, object?>
        {
            ["model"] = options.Model,
            ["input"] = prompt
        };
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            body["instructions"] = instructions;
        }

        if (structured)
        {
            body["text"] = new Dictionary<string, object?>
            {
                ["format"] = BuildOpenAiStructuredFormat()
            };
        }

        return body;
    }

    private static Dictionary<string, object?> BuildOpenAiChatBody(
        AppOptions options,
        string instructions,
        string prompt,
        bool structured)
    {
        var messages = new List<object>();
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            messages.Add(new { role = "system", content = instructions });
        }

        messages.Add(new { role = "user", content = prompt });
        var body = new Dictionary<string, object?>
        {
            ["model"] = options.Model,
            ["messages"] = messages,
            ["stream"] = false
        };

        if (structured)
        {
            // DeepSeek 官方接口使用 json_object；OpenAI/xAI/兼容接口优先尝试 json_schema。
            body["response_format"] = options.Provider == AiProvider.DeepSeek
                ? new Dictionary<string, object?> { ["type"] = "json_object" }
                : new Dictionary<string, object?>
                {
                    ["type"] = "json_schema",
                    ["json_schema"] = BuildOpenAiStructuredFormat(includeType: false)
                };
        }

        return body;
    }

    private static Dictionary<string, object?> BuildGeminiBody(
        string instructions,
        string prompt,
        bool structured)
    {
        var body = new Dictionary<string, object?>
        {
            ["contents"] = new[]
            {
                new Dictionary<string, object?>
                {
                    ["role"] = "user",
                    ["parts"] = new[] { new Dictionary<string, object?> { ["text"] = prompt } }
                }
            }
        };
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            body["systemInstruction"] = new Dictionary<string, object?>
            {
                ["parts"] = new[] { new Dictionary<string, object?> { ["text"] = instructions } }
            };
        }

        if (structured)
        {
            body["generationConfig"] = new Dictionary<string, object?>
            {
                ["responseMimeType"] = "application/json",
                ["responseJsonSchema"] = BuildBatchSchema()
            };
        }

        return body;
    }

    private static Dictionary<string, object?> BuildClaudeBody(
        AppOptions options,
        string instructions,
        string prompt,
        bool structured)
    {
        var body = new Dictionary<string, object?>
        {
            ["model"] = options.Model,
            ["max_tokens"] = options.ClaudeMaxOutputTokens,
            ["messages"] = new[] { new { role = "user", content = prompt } },
            ["stream"] = false
        };
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            // Anthropic Messages API 不接受 system 角色，系统指令必须放在顶层。
            body["system"] = instructions;
        }

        if (structured)
        {
            body["output_config"] = new Dictionary<string, object?>
            {
                ["format"] = new Dictionary<string, object?>
                {
                    ["type"] = "json_schema",
                    ["schema"] = BuildBatchSchema()
                }
            };
        }

        return body;
    }

    private static Dictionary<string, object?> BuildOpenAiStructuredFormat(bool includeType = true)
    {
        var format = new Dictionary<string, object?>
        {
            ["name"] = "translation_batch",
            ["strict"] = true,
            ["schema"] = BuildBatchSchema()
        };
        if (includeType)
        {
            format["type"] = "json_schema";
        }

        return format;
    }

    internal static Dictionary<string, object?> BuildBatchSchema()
    {
        return new Dictionary<string, object?>
        {
            ["type"] = "object",
            ["properties"] = new Dictionary<string, object?>
            {
                ["translations"] = new Dictionary<string, object?>
                {
                    ["type"] = "array",
                    ["items"] = new Dictionary<string, object?>
                    {
                        ["type"] = "object",
                        ["properties"] = new Dictionary<string, object?>
                        {
                            ["id"] = new Dictionary<string, object?> { ["type"] = "integer" },
                            ["text"] = new Dictionary<string, object?> { ["type"] = "string" }
                        },
                        ["required"] = new[] { "id", "text" },
                        ["additionalProperties"] = false
                    }
                }
            },
            ["required"] = new[] { "translations" },
            ["additionalProperties"] = false
        };
    }

    private static void ApplyAuthentication(
        HttpRequestMessage request,
        AppOptions options,
        string apiKey)
    {
        if (!string.IsNullOrWhiteSpace(apiKey))
        {
            var value = string.IsNullOrWhiteSpace(options.ApiKeyPrefix)
                ? apiKey
                : $"{options.ApiKeyPrefix.Trim()} {apiKey}";
            request.Headers.TryAddWithoutValidation(options.ApiKeyHeader, value);
        }

        if (options.Protocol == ApiProtocol.AnthropicMessages)
        {
            request.Headers.TryAddWithoutValidation("anthropic-version", options.AnthropicVersion);
        }
    }

    private static void ApplyExtraHeaders(
        HttpRequestMessage request,
        IReadOnlyDictionary<string, string> headers)
    {
        foreach (var header in headers)
        {
            if (header.Key.Equals("Content-Type", StringComparison.OrdinalIgnoreCase))
            {
                request.Content!.Headers.Remove(header.Key);
                request.Content.Headers.TryAddWithoutValidation(header.Key, header.Value);
                continue;
            }

            request.Headers.Remove(header.Key);
            request.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }
    }
}

internal static class ProviderResponseParser
{
    public static string ExtractText(ApiProtocol protocol, string responseBody)
    {
        using var document = JsonDocument.Parse(responseBody);
        var root = document.RootElement;
        return protocol switch
        {
            ApiProtocol.OpenAiChatCompletions => ExtractOpenAiChat(root),
            ApiProtocol.OpenAiResponses => ExtractOpenAiResponses(root),
            ApiProtocol.GeminiGenerateContent => ExtractGemini(root),
            ApiProtocol.AnthropicMessages => ExtractClaude(root),
            _ => ""
        };
    }

    private static string ExtractOpenAiChat(JsonElement root)
    {
        if (!root.TryGetProperty("choices", out var choices)
            || choices.ValueKind != JsonValueKind.Array
            || choices.GetArrayLength() == 0)
        {
            return "";
        }

        var choice = choices[0];
        if (choice.TryGetProperty("message", out var message)
            && message.TryGetProperty("content", out var content))
        {
            return ExtractContentValue(content);
        }

        return choice.TryGetProperty("text", out var legacyText)
            ? legacyText.GetString() ?? ""
            : "";
    }

    private static string ExtractOpenAiResponses(JsonElement root)
    {
        if (root.TryGetProperty("output_text", out var outputText)
            && outputText.ValueKind == JsonValueKind.String)
        {
            return outputText.GetString() ?? "";
        }

        if (!root.TryGetProperty("output", out var output) || output.ValueKind != JsonValueKind.Array)
        {
            return "";
        }

        var texts = new List<string>();
        foreach (var item in output.EnumerateArray())
        {
            if (!item.TryGetProperty("content", out var content) || content.ValueKind != JsonValueKind.Array)
            {
                continue;
            }

            foreach (var contentItem in content.EnumerateArray())
            {
                if (contentItem.TryGetProperty("text", out var text)
                    && text.ValueKind == JsonValueKind.String)
                {
                    texts.Add(text.GetString() ?? "");
                }
            }
        }

        return string.Join("", texts);
    }

    private static string ExtractGemini(JsonElement root)
    {
        if (!root.TryGetProperty("candidates", out var candidates)
            || candidates.ValueKind != JsonValueKind.Array
            || candidates.GetArrayLength() == 0
            || !candidates[0].TryGetProperty("content", out var content)
            || !content.TryGetProperty("parts", out var parts)
            || parts.ValueKind != JsonValueKind.Array)
        {
            return "";
        }

        return string.Join(
            "",
            parts.EnumerateArray()
                .Where(part => part.TryGetProperty("text", out _))
                .Select(part => part.GetProperty("text").GetString() ?? ""));
    }

    private static string ExtractClaude(JsonElement root)
    {
        if (!root.TryGetProperty("content", out var content) || content.ValueKind != JsonValueKind.Array)
        {
            return "";
        }

        return string.Join(
            "",
            content.EnumerateArray()
                .Where(item => item.TryGetProperty("text", out _))
                .Select(item => item.GetProperty("text").GetString() ?? ""));
    }

    private static string ExtractContentValue(JsonElement content)
    {
        if (content.ValueKind == JsonValueKind.String)
        {
            return content.GetString() ?? "";
        }

        if (content.ValueKind != JsonValueKind.Array)
        {
            return "";
        }

        return string.Join(
            "",
            content.EnumerateArray()
                .Where(item => item.TryGetProperty("text", out _))
                .Select(item => item.GetProperty("text").GetString() ?? ""));
    }
}

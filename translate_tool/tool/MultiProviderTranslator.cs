using System.Net;
using System.Text.Json;

namespace TranslateTool;

internal sealed class MultiProviderTranslator : IDisposable
{
    private readonly AppOptions _options;
    private readonly HttpClient _httpClient;
    private int _structuredOutputsUnavailable;
    private int _requestsSent;
    private int _adaptiveBatchSizeLimit = int.MaxValue;

    public int RequestsSent => Volatile.Read(ref _requestsSent);

    public MultiProviderTranslator(AppOptions options)
    {
        _options = options;
        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(options.RequestTimeoutSeconds)
        };
    }

    public async Task<string> TranslateAsync(string sourceText, CancellationToken cancellationToken)
    {
        var prompt = _options.BuildPrompt(sourceText);
        return await SendForTextAsync(() => BuildRequest(prompt, useStructuredOutput: false), cancellationToken);
    }

    public async Task<IReadOnlyList<string>> TranslateBatchAsync(
        IReadOnlyList<string> sourceTexts,
        CancellationToken cancellationToken)
    {
        if (sourceTexts.Count == 0)
        {
            return [];
        }

        if (sourceTexts.Count == 1)
        {
            return [await TranslateAsync(sourceTexts[0], cancellationToken)];
        }

        var adaptiveLimit = Volatile.Read(ref _adaptiveBatchSizeLimit);
        if (sourceTexts.Count > adaptiveLimit)
        {
            var adaptedResults = new List<string>(sourceTexts.Count);
            foreach (var adaptedBatch in sourceTexts.Chunk(adaptiveLimit))
            {
                var translations = await TranslateBatchAsync(adaptedBatch, cancellationToken);
                adaptedResults.AddRange(translations);
            }

            return adaptedResults;
        }

        var prompt = BuildBatchPrompt(sourceTexts);
        try
        {
            var useStructuredOutput = CanUseStructuredOutputs()
                && Volatile.Read(ref _structuredOutputsUnavailable) == 0;
            string responseText;
            try
            {
                responseText = await SendForTextAsync(
                    () => BuildRequest(prompt, useStructuredOutput),
                    cancellationToken,
                    splitTransientBatchFailures: true);
            }
            catch (HttpRequestException exception) when (
                useStructuredOutput && IsStructuredOutputCompatibilityError(exception.StatusCode))
            {
                Interlocked.Exchange(ref _structuredOutputsUnavailable, 1);
                Console.WriteLine("当前接口不支持结构化输出，已自动改用普通 JSON 批量模式。 ");
                responseText = await SendForTextAsync(
                    () => BuildRequest(prompt, useStructuredOutput: false),
                    cancellationToken,
                    splitTransientBatchFailures: true);
            }

            return ParseBatchTranslations(responseText, sourceTexts.Count);
        }
        catch (InvalidDataException) when (sourceTexts.Count > 1)
        {
            // 某些兼容接口无法稳定返回大 JSON；自动拆分，最终会退化到可靠的单条请求。
            return await SplitBatchAsync(sourceTexts, "返回 JSON 格式异常", cancellationToken);
        }
        catch (HttpRequestException exception) when (
            sourceTexts.Count > 1 && ShouldSplitBatch(exception.StatusCode))
        {
            var reason = exception.StatusCode.HasValue
                ? $"API {(int)exception.StatusCode.Value} ({exception.StatusCode.Value})"
                : "API 网络错误";
            return await SplitBatchAsync(sourceTexts, reason, cancellationToken);
        }
        catch (TaskCanceledException) when (
            sourceTexts.Count > 1 && !cancellationToken.IsCancellationRequested)
        {
            return await SplitBatchAsync(sourceTexts, "API 请求超时", cancellationToken);
        }
    }

    private async Task<string> SendForTextAsync(
        Func<HttpRequestMessage> requestFactory,
        CancellationToken cancellationToken,
        bool splitTransientBatchFailures = false)
    {
        ValidateApiKey();
        Exception? lastException = null;
        for (var attempt = 0; attempt <= _options.MaxRetries; attempt++)
        {
            try
            {
                using var request = requestFactory();
                Interlocked.Increment(ref _requestsSent);
                using var response = await _httpClient.SendAsync(
                    request,
                    HttpCompletionOption.ResponseHeadersRead,
                    cancellationToken);
                var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

                if (!response.IsSuccessStatusCode)
                {
                    var apiError = BuildApiError(response.StatusCode, responseBody);
                    if (IsPermanentAccountError(response.StatusCode, responseBody))
                    {
                        throw apiError;
                    }

                    if (splitTransientBatchFailures && ShouldSplitBatch(response.StatusCode))
                    {
                        throw apiError;
                    }

                    if (!IsRetryable(response.StatusCode) || attempt == _options.MaxRetries)
                    {
                        throw apiError;
                    }

                    lastException = apiError;
                    await DelayForRetryAsync(attempt, response, cancellationToken);
                    continue;
                }

                string text;
                try
                {
                    text = ExtractText(responseBody);
                    if (string.IsNullOrWhiteSpace(text))
                    {
                        throw new InvalidDataException("API 响应 JSON 中没有找到模型输出文本。 ");
                    }
                }
                catch (JsonException exception)
                {
                    var invalidResponse = BuildInvalidSuccessfulResponse(
                        response.StatusCode,
                        response.Content.Headers.ContentType?.ToString(),
                        responseBody,
                        exception);
                    if (attempt == _options.MaxRetries)
                    {
                        throw invalidResponse;
                    }

                    lastException = invalidResponse;
                    Console.WriteLine(
                        $"{invalidResponse.Message}\n正在进行第 {attempt + 1}/{_options.MaxRetries} 次重试……");
                    await Task.Delay(GetRetryDelay(attempt), cancellationToken);
                    continue;
                }
                catch (InvalidDataException exception)
                {
                    var invalidResponse = BuildInvalidSuccessfulResponse(
                        response.StatusCode,
                        response.Content.Headers.ContentType?.ToString(),
                        responseBody,
                        exception);
                    if (attempt == _options.MaxRetries)
                    {
                        throw invalidResponse;
                    }

                    lastException = invalidResponse;
                    Console.WriteLine(
                        $"{invalidResponse.Message}\n正在进行第 {attempt + 1}/{_options.MaxRetries} 次重试……");
                    await Task.Delay(GetRetryDelay(attempt), cancellationToken);
                    continue;
                }

                return text;
            }
            catch (HttpRequestException exception) when (
                attempt < _options.MaxRetries
                && !cancellationToken.IsCancellationRequested
                && !(splitTransientBatchFailures && ShouldSplitBatch(exception.StatusCode))
                && (!exception.StatusCode.HasValue || IsRetryable(exception.StatusCode.Value)))
            {
                lastException = exception;
                await Task.Delay(GetRetryDelay(attempt), cancellationToken);
            }
            catch (TaskCanceledException exception) when (
                !splitTransientBatchFailures
                && attempt < _options.MaxRetries
                && !cancellationToken.IsCancellationRequested)
            {
                lastException = exception;
                await Task.Delay(GetRetryDelay(attempt), cancellationToken);
            }
        }

        throw new HttpRequestException("API 请求在重试后仍然失败。 ", lastException);
    }

    private async Task<IReadOnlyList<string>> SplitBatchAsync(
        IReadOnlyList<string> sourceTexts,
        string reason,
        CancellationToken cancellationToken)
    {
        var midpoint = sourceTexts.Count / 2;
        ReduceAdaptiveBatchSize(midpoint);
        Console.WriteLine(
            $"批次 {sourceTexts.Count} 条遇到{reason}，已自动拆分为 {midpoint} + {sourceTexts.Count - midpoint} 条重试。 ");
        var left = await TranslateBatchAsync(sourceTexts.Take(midpoint).ToList(), cancellationToken);
        var right = await TranslateBatchAsync(sourceTexts.Skip(midpoint).ToList(), cancellationToken);
        return left.Concat(right).ToList();
    }

    private void ReduceAdaptiveBatchSize(int newLimit)
    {
        var currentLimit = Volatile.Read(ref _adaptiveBatchSizeLimit);
        while (newLimit < currentLimit)
        {
            var observed = Interlocked.CompareExchange(
                ref _adaptiveBatchSizeLimit,
                newLimit,
                currentLimit);
            if (observed == currentLimit)
            {
                return;
            }

            currentLimit = observed;
        }
    }

    private HttpRequestMessage BuildRequest(string prompt, bool useStructuredOutput)
    {
        return ProviderRequestBuilder.Build(
            _options,
            prompt,
            useStructuredOutput,
            _options.GetApiKey());
    }

    private string BuildBatchPrompt(IReadOnlyList<string> sourceTexts)
    {
        var inputItems = sourceTexts.Select((text, id) => new { id, text });
        var inputJson = JsonSerializer.Serialize(inputItems, AppOptions.JsonOptions);
        return $$"""
            批量翻译下面 JSON 数组中的每个 text。每项必须独立翻译，不得合并、遗漏、解释或改变 id。

            对每个 text 应用此翻译提示模板：
            {{_options.Prompt}}

            仅返回 JSON 对象，格式必须是：
            {"translations":[{"id":0,"text":"对应译文"}]}

            输入：
            {{inputJson}}
            """;
    }

    private static IReadOnlyList<string> ParseBatchTranslations(string responseText, int expectedCount)
    {
        using var document = ParseJsonResponse(responseText);
        var root = document.RootElement;
        var translations = root.ValueKind == JsonValueKind.Object
            && root.TryGetProperty("translations", out var property)
            ? property
            : root;
        if (translations.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("批量翻译返回内容不是 translations 数组。 ");
        }

        var result = new string?[expectedCount];
        var sequentialIndex = 0;
        foreach (var item in translations.EnumerateArray())
        {
            if (item.ValueKind == JsonValueKind.String)
            {
                if (sequentialIndex >= expectedCount)
                {
                    throw new InvalidDataException("批量翻译返回的项目数量过多。 ");
                }

                result[sequentialIndex++] = item.GetString() ?? "";
                continue;
            }

            if (item.ValueKind != JsonValueKind.Object
                || !item.TryGetProperty("id", out var idElement)
                || !idElement.TryGetInt32(out var id)
                || id < 0
                || id >= expectedCount)
            {
                throw new InvalidDataException("批量翻译返回了无效 id。 ");
            }

            if (result[id] is not null)
            {
                throw new InvalidDataException($"批量翻译返回了重复 id：{id}。 ");
            }

            if (!item.TryGetProperty("text", out var textElement))
            {
                item.TryGetProperty("translation", out textElement);
            }

            if (textElement.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException($"批量翻译的 id {id} 缺少译文。 ");
            }

            result[id] = textElement.GetString() ?? "";
        }

        if (result.Any(value => value is null))
        {
            throw new InvalidDataException($"批量翻译返回数量不足，期望 {expectedCount} 项。 ");
        }

        return result.Select(value => value!).ToList();
    }

    private static JsonDocument ParseJsonResponse(string responseText)
    {
        var trimmed = responseText.Trim();
        try
        {
            return JsonDocument.Parse(trimmed);
        }
        catch (JsonException)
        {
            var objectStart = trimmed.IndexOf('{');
            var arrayStart = trimmed.IndexOf('[');
            var start = objectStart < 0
                ? arrayStart
                : arrayStart < 0 ? objectStart : Math.Min(objectStart, arrayStart);
            var end = start >= 0 && trimmed[start] == '{'
                ? trimmed.LastIndexOf('}')
                : trimmed.LastIndexOf(']');
            if (start < 0 || end <= start)
            {
                throw new InvalidDataException("批量翻译没有返回有效 JSON。 ");
            }

            try
            {
                return JsonDocument.Parse(trimmed[start..(end + 1)]);
            }
            catch (JsonException exception)
            {
                throw new InvalidDataException("批量翻译返回的 JSON 无法解析。 ", exception);
            }
        }
    }

    private void ValidateApiKey()
    {
        if (_options.RequireApiKey && string.IsNullOrWhiteSpace(_options.GetApiKey()))
        {
            throw new InvalidOperationException(
                $"API Key 为空。请修改 GlobalSettings.ApiKey，或设置环境变量 {_options.ApiKeyEnvironmentVariable}。 ");
        }
    }

    private string ExtractText(string responseBody)
    {
        return ProviderResponseParser.ExtractText(_options.Protocol, responseBody);
    }

    private static Exception BuildApiError(HttpStatusCode statusCode, string responseBody)
    {
        var message = responseBody;
        try
        {
            using var document = JsonDocument.Parse(responseBody);
            if (document.RootElement.TryGetProperty("error", out var error))
            {
                if (error.ValueKind == JsonValueKind.String)
                {
                    message = error.GetString() ?? responseBody;
                }
                else if (error.TryGetProperty("message", out var errorMessage))
                {
                    message = errorMessage.GetString() ?? responseBody;
                }
            }
        }
        catch (JsonException)
        {
            // 返回体不是 JSON 时直接展示截断后的文本。
        }

        if (message.Length > 500)
        {
            message = message[..500] + "...";
        }

        return new HttpRequestException($"API 返回 {(int)statusCode} ({statusCode})：{message}", null, statusCode);
    }

    private static ProviderResponseFormatException BuildInvalidSuccessfulResponse(
        HttpStatusCode statusCode,
        string? contentType,
        string responseBody,
        Exception innerException)
    {
        var trimmed = responseBody.Trim();
        var preview = trimmed.Replace("\r", " ", StringComparison.Ordinal)
            .Replace("\n", " ", StringComparison.Ordinal);
        if (preview.Length > 300)
        {
            preview = preview[..300] + "...";
        }

        if (string.IsNullOrWhiteSpace(preview))
        {
            preview = "<空响应>";
        }

        var formatHint = trimmed.StartsWith('<')
            ? "接口返回了 HTML 页面，通常是网关、中转服务或反向代理异常"
            : "接口没有返回可识别的 JSON";
        return new ProviderResponseFormatException(
            $"API 返回 {(int)statusCode} ({statusCode})，但{formatHint}（Content-Type: {contentType ?? "未提供"}）。响应开头：{preview}",
            innerException);
    }

    private static bool IsRetryable(HttpStatusCode statusCode)
    {
        return statusCode is HttpStatusCode.RequestTimeout or HttpStatusCode.TooManyRequests
            || (int)statusCode >= 500;
    }

    private static bool IsPermanentAccountError(HttpStatusCode statusCode, string responseBody)
    {
        if (statusCode == HttpStatusCode.PaymentRequired)
        {
            return true;
        }

        if (statusCode != HttpStatusCode.TooManyRequests)
        {
            return false;
        }

        return Contains(responseBody, "no credits remaining")
            || Contains(responseBody, "insufficient balance")
            || Contains(responseBody, "insufficient_quota")
            || Contains(responseBody, "payment required")
            || Contains(responseBody, "余额不足")
            || Contains(responseBody, "额度不足");
    }

    private static bool Contains(string value, string fragment)
    {
        return value.Contains(fragment, StringComparison.OrdinalIgnoreCase);
    }

    private static bool ShouldSplitBatch(HttpStatusCode? statusCode)
    {
        return statusCode is HttpStatusCode.RequestTimeout
            or HttpStatusCode.RequestEntityTooLarge
            or HttpStatusCode.BadGateway
            or HttpStatusCode.ServiceUnavailable
            or HttpStatusCode.GatewayTimeout;
    }

    private static bool IsStructuredOutputCompatibilityError(HttpStatusCode? statusCode)
    {
        return statusCode is HttpStatusCode.BadRequest
            or HttpStatusCode.NotFound
            or HttpStatusCode.UnprocessableEntity;
    }

    private bool CanUseStructuredOutputs()
    {
        return _options.UseStructuredOutputs;
    }

    private static async Task DelayForRetryAsync(
        int attempt,
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        var delay = response.Headers.RetryAfter?.Delta ?? GetRetryDelay(attempt);
        if (delay > TimeSpan.FromSeconds(60))
        {
            delay = TimeSpan.FromSeconds(60);
        }

        await Task.Delay(delay, cancellationToken);
    }

    private static TimeSpan GetRetryDelay(int attempt)
    {
        return TimeSpan.FromSeconds(Math.Min(30, Math.Pow(2, attempt + 1)));
    }

    public void Dispose()
    {
        _httpClient.Dispose();
    }
}

internal sealed class ProviderResponseFormatException(string message, Exception innerException)
    : Exception(message, innerException);

namespace TranslateTool;

internal static class TranslationApplication
{
    public static async Task<int> RunAsync(string[] args)
    {
        var interactiveMode = args.Length == 0;
        using var cancellationSource = new CancellationTokenSource();
        Console.CancelKeyPress += (_, eventArgs) =>
        {
            eventArgs.Cancel = true;
            cancellationSource.Cancel();
            Console.WriteLine("\n正在安全停止……");
        };

        try
        {
            var commandLine = CommandLineOptions.Parse(args);
            if (commandLine.ShowHelp)
            {
                CommandLineOptions.PrintUsage();
                return 0;
            }

            if (commandLine.CreateConfigFile is not null)
            {
                var configPath = Path.GetFullPath(commandLine.CreateConfigFile);
                if (File.Exists(configPath))
                {
                    throw new IOException($"配置文件已经存在，不会覆盖：{configPath}");
                }

                await AppOptions.SaveExampleAsync(configPath, cancellationSource.Token);
                Console.WriteLine($"已创建配置：{configPath}");
                return 0;
            }

            var selectedInput = commandLine.InputFile;
            if (selectedInput is null)
            {
                selectedInput = InteractiveStartup.SelectInputFile();
                if (selectedInput is null)
                {
                    Console.WriteLine("已取消选择，没有执行翻译。 ");
                    return 0;
                }
            }

            var inputPath = Path.GetFullPath(selectedInput);
            if (!File.Exists(inputPath))
            {
                throw new FileNotFoundException($"找不到输入文件：{inputPath}");
            }

            var configPathForRun = await InteractiveStartup.ResolveConfigPathAsync(
                commandLine,
                inputPath,
                cancellationSource.Token);
            Console.WriteLine($"配置文件：{configPathForRun}");
            Console.WriteLine($"输入文件：{inputPath}");

            var options = await AppOptions.LoadAsync(configPathForRun, cancellationSource.Token);
            Console.WriteLine(
                $"生效配置：SourceHeader={options.SourceHeader}，TargetHeader={options.TargetHeader}，" +
                $"HeaderRow={options.HeaderRow}，HeaderStartColumn={options.HeaderStartColumn}");
            var effectiveApiFormat = options.ResolveApiFormat();
            Console.WriteLine(
                $"API 配置：Url={options.ApiUrl}，Model={options.Model}，Format={effectiveApiFormat}");
            if (!string.Equals(options.ApiFormat, effectiveApiFormat, StringComparison.OrdinalIgnoreCase))
            {
                Console.WriteLine(
                    $"注意：ApiFormat={options.ApiFormat} 与 URL 不匹配，已自动修正为 {effectiveApiFormat}。 ");
            }

            if (options.UseStructuredOutputs
                && options.Model.StartsWith("deepseek", StringComparison.OrdinalIgnoreCase))
            {
                Console.WriteLine(
                    "注意：DeepSeek 不使用 json_schema 请求，已自动切换为普通 JSON 批量模式。 ");
            }

            var configDirectory = Path.GetDirectoryName(configPathForRun)!;
            var outputPath = ResolveOutputPath(commandLine, options, inputPath, configDirectory);
            var cachePath = ResolveRelativePath(options.CacheFile, configDirectory);

            using var table = TableDocument.Open(inputPath, options.SheetName, options.CsvDelimiter);
            var headerStart = CellReference.ColumnNameToNumber(options.HeaderStartColumn);
            var sourceColumn = table.FindHeader(options.SourceHeader, headerStart, options.HeaderRow);
            var targetColumn = table.FindHeader(options.TargetHeader, headerStart, options.HeaderRow);

            if (sourceColumn is null)
            {
                throw new InvalidDataException(
                    $"从 {options.HeaderStartColumn}{options.HeaderRow} 起找不到源表头“{options.SourceHeader}”。 ");
            }

            if (targetColumn is null)
            {
                throw new InvalidDataException(
                    $"从 {options.HeaderStartColumn}{options.HeaderRow} 起找不到目标表头“{options.TargetHeader}”。 ");
            }

            if (sourceColumn == targetColumn)
            {
                throw new InvalidDataException("源列和目标列不能是同一列。 ");
            }

            var sourceDataColumn = sourceColumn.Value + options.SourceDataColumnOffset;
            if (sourceDataColumn <= 0)
            {
                throw new InvalidDataException("SourceDataColumnOffset 导致源数据列落在 A 列之前。 ");
            }

            Console.WriteLine($"工作表：{table.DisplayName}");
            Console.WriteLine($"表头行：{options.HeaderRow}");
            Console.WriteLine($"源表头列：{CellReference.ColumnNumberToName(sourceColumn.Value)} ({options.SourceHeader})");
            Console.WriteLine($"源数据列：{CellReference.ColumnNumberToName(sourceDataColumn)}");
            Console.WriteLine($"目标列：{CellReference.ColumnNumberToName(targetColumn.Value)} ({options.TargetHeader})");
            var firstDataRow = options.HeaderRow + 1;
            Console.WriteLine(table.LastRow >= firstDataRow
                ? $"数据行：{firstDataRow}-{table.LastRow}"
                : "数据行：无");

            var cache = await TranslationCache.LoadAsync(cachePath, cancellationSource.Token);
            var scope = options.ResolveCacheScope();
            var stats = new TranslationStats();
            var cacheUpdatedDuringScan = false;
            var pendingTranslations = new Dictionary<string, PendingTranslation>(StringComparer.Ordinal);
            for (var row = firstDataRow; row <= table.LastRow; row++)
            {
                cancellationSource.Token.ThrowIfCancellationRequested();
                var sourceText = table.GetValue(row, sourceDataColumn);
                if (string.IsNullOrWhiteSpace(sourceText))
                {
                    stats.EmptySource++;
                    continue;
                }

                var existingTarget = table.GetValue(row, targetColumn.Value);
                if (!options.OverwriteExistingTranslations && !string.IsNullOrWhiteSpace(existingTarget))
                {
                    var repairedTarget = PostProcessTranslation(sourceText, existingTarget, options);
                    if (!string.Equals(existingTarget, repairedTarget, StringComparison.Ordinal))
                    {
                        stats.PunctuationRepairs++;
                        if (!commandLine.DryRun)
                        {
                            table.SetValue(row, targetColumn.Value, repairedTarget);
                            stats.Written++;
                        }
                    }

                    stats.ExistingTarget++;
                    continue;
                }

                if (cache.TryGet(scope, sourceText, out var cachedTranslation))
                {
                    var repairedTranslation = PostProcessTranslation(sourceText, cachedTranslation, options);
                    if (!string.Equals(cachedTranslation, repairedTranslation, StringComparison.Ordinal))
                    {
                        stats.PunctuationRepairs++;
                        cache.Set(scope, sourceText, repairedTranslation, options);
                        cacheUpdatedDuringScan = true;
                    }

                    stats.CacheHits++;
                    if (!commandLine.DryRun)
                    {
                        table.SetValue(row, targetColumn.Value, repairedTranslation);
                        stats.Written++;
                    }

                    continue;
                }

                stats.CacheMisses++;
                if (!pendingTranslations.TryGetValue(sourceText, out var pending))
                {
                    pending = new PendingTranslation(sourceText);
                    pendingTranslations.Add(sourceText, pending);
                }

                pending.Rows.Add(row);
            }

            stats.DeduplicatedRows = Math.Max(0, stats.CacheMisses - pendingTranslations.Count);
            var requestBatches = BuildRequestBatches(
                pendingTranslations.Values,
                options.TextsPerRequest,
                options.MaxCharactersPerRequest);
            Console.WriteLine(
                $"扫描完成：缓存命中 {stats.CacheHits} 行，待翻译 {stats.CacheMisses} 行 / {pendingTranslations.Count} 个不同文本，" +
                $"合并重复 {stats.DeduplicatedRows} 行，预计 {requestBatches.Count} 个 API 批次。 ");

            if (!commandLine.DryRun && requestBatches.Count > 0)
            {
                using var translator = new OpenAiCompatibleTranslator(options);
                await TranslatePendingAsync(
                    requestBatches,
                    pendingTranslations.Count,
                    translator,
                    table,
                    targetColumn.Value,
                    cache,
                    cachePath,
                    scope,
                    options,
                    stats,
                    cancellationSource.Token);
                stats.ApiRequests = translator.RequestsSent;
            }

            if (!commandLine.DryRun && cacheUpdatedDuringScan)
            {
                await cache.SaveAsync(cachePath, CancellationToken.None);
            }

            if (!commandLine.DryRun)
            {
                table.Save(outputPath);
                Console.WriteLine($"输出文件：{outputPath}");
                Console.WriteLine($"缓存文件：{cachePath}");
                if (table.RemovedInvalidCharacterCount > 0)
                {
                    Console.WriteLine(
                        $"注意：写入 Excel 时已清理 {table.RemovedInvalidCharacterCount} 个 XML 禁止的控制字符。 ");
                }
            }

            Console.WriteLine($"完成：写入 {stats.Written}，API 请求 {stats.ApiRequests}，缓存命中 {stats.CacheHits}，合并重复 {stats.DeduplicatedRows}，" +
                $"边界标点修复 {stats.PunctuationRepairs}，已有译文跳过 {stats.ExistingTarget}，空源跳过 {stats.EmptySource}。 ");
            if (commandLine.DryRun)
            {
                Console.WriteLine($"试运行：预计需要 {requestBatches.Count} 个 API 批次，没有调用 API，也没有写入文件。 ");
            }

            return 0;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("操作已取消。已成功取得的 API 译文仍保存在缓存中。 ");
            return 130;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"错误：{exception.Message}");
            return 1;
        }
        finally
        {
            if (interactiveMode && Environment.UserInteractive && !Console.IsInputRedirected)
            {
                Console.WriteLine();
                Console.Write("按任意键退出……");
                Console.ReadKey(intercept: true);
                Console.WriteLine();
            }
        }
    }

    private static string ResolveOutputPath(CommandLineOptions commandLine, AppOptions options, string inputPath, string configDirectory)
    {
        if (commandLine.OverwriteInput)
        {
            return inputPath;
        }

        if (!string.IsNullOrWhiteSpace(commandLine.OutputFile))
        {
            return Path.GetFullPath(commandLine.OutputFile);
        }

        if (!string.IsNullOrWhiteSpace(options.OutputFile))
        {
            return ResolveRelativePath(options.OutputFile, configDirectory);
        }

        var directory = Path.GetDirectoryName(inputPath)!;
        var fileName = Path.GetFileNameWithoutExtension(inputPath);
        return Path.Combine(directory, $"{fileName}.translated{Path.GetExtension(inputPath)}");
    }

    private static async Task TranslatePendingAsync(
        IReadOnlyList<TranslationRequestBatch> requestBatches,
        int totalTexts,
        OpenAiCompatibleTranslator translator,
        TableDocument table,
        int targetColumn,
        TranslationCache cache,
        string cachePath,
        string cacheScope,
        AppOptions options,
        TranslationStats stats,
        CancellationToken cancellationToken)
    {
        using var concurrencyGate = new SemaphoreSlim(options.MaxConcurrentRequests);
        var completed = 0;
        var requestsPerCacheSave = Math.Max(
            options.MaxConcurrentRequests,
            Math.Max(1, (options.CacheSaveInterval + options.TextsPerRequest - 1) / options.TextsPerRequest));

        foreach (var requestWave in requestBatches.Chunk(requestsPerCacheSave))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var tasks = requestWave.Select(async requestBatch =>
            {
                var attempt = await TranslateBatchAsync(
                    requestBatch,
                    translator,
                    concurrencyGate,
                    options.RequestDelayMilliseconds,
                    cancellationToken);
                var current = Interlocked.Add(ref completed, requestBatch.Items.Count);
                if (current == totalTexts
                    || current / options.ProgressReportInterval
                        != (current - requestBatch.Items.Count) / options.ProgressReportInterval)
                {
                    Console.WriteLine($"翻译进度：{Math.Min(current, totalTexts)}/{totalTexts} 个不同文本");
                }

                return attempt;
            });
            var attempts = await Task.WhenAll(tasks);
            var successfulInWave = 0;

            foreach (var attempt in attempts)
            {
                if (attempt.Error is null && attempt.Translations is not null)
                {
                    for (var index = 0; index < attempt.Batch.Items.Count; index++)
                    {
                        var pending = attempt.Batch.Items[index];
                        var translation = PostProcessTranslation(
                            pending.SourceText,
                            attempt.Translations[index],
                            options);
                        if (!string.Equals(attempt.Translations[index], translation, StringComparison.Ordinal))
                        {
                            stats.PunctuationRepairs++;
                        }

                        cache.Set(cacheScope, pending.SourceText, translation, options);
                        foreach (var row in pending.Rows)
                        {
                            table.SetValue(row, targetColumn, translation);
                        }

                        stats.Written += pending.Rows.Count;
                    }

                    successfulInWave += attempt.Batch.Items.Count;
                }
            }

            if (successfulInWave > 0)
            {
                await cache.SaveAsync(cachePath, CancellationToken.None);
            }

            var failure = attempts.FirstOrDefault(attempt => attempt.Error is not null);
            if (failure is not null)
            {
                if (cancellationToken.IsCancellationRequested || failure.Error is OperationCanceledException)
                {
                    throw new OperationCanceledException(cancellationToken);
                }

                throw new InvalidOperationException(
                    $"翻译批次失败（首条：“{Preview(failure.Batch.Items[0].SourceText)}”）：{failure.Error!.Message}",
                    failure.Error);
            }
        }
    }

    private static async Task<TranslationBatchAttempt> TranslateBatchAsync(
        TranslationRequestBatch batch,
        OpenAiCompatibleTranslator translator,
        SemaphoreSlim concurrencyGate,
        int requestDelayMilliseconds,
        CancellationToken cancellationToken)
    {
        var enteredGate = false;
        try
        {
            await concurrencyGate.WaitAsync(cancellationToken);
            enteredGate = true;
            var translations = await translator.TranslateBatchAsync(
                batch.Items.Select(item => item.SourceText).ToList(),
                cancellationToken);
            if (requestDelayMilliseconds > 0)
            {
                await Task.Delay(requestDelayMilliseconds, cancellationToken);
            }

            return new TranslationBatchAttempt(batch, translations, null);
        }
        catch (Exception exception)
        {
            return new TranslationBatchAttempt(batch, null, exception);
        }
        finally
        {
            if (enteredGate)
            {
                concurrencyGate.Release();
            }
        }
    }

    private static List<TranslationRequestBatch> BuildRequestBatches(
        IEnumerable<PendingTranslation> pendingTranslations,
        int maxTexts,
        int maxCharacters)
    {
        var batches = new List<TranslationRequestBatch>();
        var currentItems = new List<PendingTranslation>(maxTexts);
        var currentCharacters = 0;

        foreach (var pending in pendingTranslations)
        {
            var wouldExceedLimit = currentItems.Count > 0
                && (currentItems.Count >= maxTexts
                    || currentCharacters + pending.SourceText.Length > maxCharacters);
            if (wouldExceedLimit)
            {
                batches.Add(new TranslationRequestBatch(currentItems));
                currentItems = new List<PendingTranslation>(maxTexts);
                currentCharacters = 0;
            }

            currentItems.Add(pending);
            currentCharacters += pending.SourceText.Length;
        }

        if (currentItems.Count > 0)
        {
            batches.Add(new TranslationRequestBatch(currentItems));
        }

        return batches;
    }

    private static string ResolveRelativePath(string path, string baseDirectory)
    {
        return Path.GetFullPath(Path.IsPathRooted(path) ? path : Path.Combine(baseDirectory, path));
    }

    private static string PostProcessTranslation(
        string sourceText,
        string translation,
        AppOptions options)
    {
        return options.PreserveBoundaryPunctuation
            ? TranslationTextPostProcessor.PreserveBoundaryPunctuation(sourceText, translation)
            : translation;
    }

    private static string Preview(string value)
    {
        var singleLine = value.Replace("\r", "\\r", StringComparison.Ordinal)
            .Replace("\n", "\\n", StringComparison.Ordinal);
        return singleLine.Length <= 50 ? singleLine : singleLine[..47] + "...";
    }

    private sealed class TranslationStats
    {
        public int EmptySource { get; set; }
        public int ExistingTarget { get; set; }
        public int CacheHits { get; set; }
        public int CacheMisses { get; set; }
        public int ApiRequests { get; set; }
        public int Written { get; set; }
        public int DeduplicatedRows { get; set; }
        public int PunctuationRepairs { get; set; }
    }

    private sealed class PendingTranslation(string sourceText)
    {
        public string SourceText { get; } = sourceText;
        public List<int> Rows { get; } = [];
    }

    private sealed record TranslationRequestBatch(IReadOnlyList<PendingTranslation> Items);

    private sealed record TranslationBatchAttempt(
        TranslationRequestBatch Batch,
        IReadOnlyList<string>? Translations,
        Exception? Error);
}

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TranslateTool;

internal sealed class TranslationCache
{
    public int Version { get; set; } = 1;
    public Dictionary<string, TranslationCacheEntry> Entries { get; set; } = new(StringComparer.Ordinal);

    public static async Task<TranslationCache> LoadAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            return new TranslationCache();
        }

        await using var stream = File.OpenRead(path);
        var cache = await JsonSerializer.DeserializeAsync<TranslationCache>(stream, AppOptions.JsonOptions, cancellationToken)
            ?? new TranslationCache();
        cache.Entries ??= new Dictionary<string, TranslationCacheEntry>(StringComparer.Ordinal);
        return cache;
    }

    public bool TryGet(string scope, string source, out string translation)
    {
        if (Entries.TryGetValue(BuildKey(scope, source), out var entry)
            && entry.Source == source
            && !string.IsNullOrEmpty(entry.Translation))
        {
            translation = entry.Translation;
            return true;
        }

        translation = "";
        return false;
    }

    public void Set(string scope, string source, string translation, AppOptions options)
    {
        Entries[BuildKey(scope, source)] = new TranslationCacheEntry
        {
            Source = source,
            Translation = translation,
            Model = options.Model,
            UpdatedAtUtc = DateTimeOffset.UtcNow
        };
    }

    public async Task SaveAsync(string path, CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(fullPath)!;
        Directory.CreateDirectory(directory);
        var temporaryPath = Path.Combine(directory, $".{Path.GetFileName(fullPath)}.{Guid.NewGuid():N}.tmp");

        try
        {
            await using (var stream = File.Create(temporaryPath))
            {
                await JsonSerializer.SerializeAsync(stream, this, AppOptions.JsonOptions, cancellationToken);
                await stream.FlushAsync(cancellationToken);
            }

            File.Move(temporaryPath, fullPath, true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }

    private static string BuildKey(string scope, string source)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(scope + "\0" + source));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}

internal sealed class TranslationCacheEntry
{
    public string Source { get; set; } = "";
    public string Translation { get; set; } = "";
    public string Model { get; set; } = "";
    public DateTimeOffset UpdatedAtUtc { get; set; }
}



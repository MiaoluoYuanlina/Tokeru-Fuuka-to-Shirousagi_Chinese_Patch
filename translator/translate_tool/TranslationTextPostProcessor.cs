using System.Text;

namespace TranslateTool;

internal static class TranslationTextPostProcessor
{
    private const string BoundaryPunctuation =
        "「」『』“”‘’\"'" +
        "（）()\uff3b\uff3d[]｛｝{}【】〈〉《》〔〕【】" +
        "。，、！？!?,.…⋯：；:;—–～~·";

    public static string PreserveBoundaryPunctuation(string sourceText, string translation)
    {
        if (string.IsNullOrEmpty(sourceText) || string.IsNullOrEmpty(translation))
        {
            return translation;
        }

        var sourceSpan = sourceText.AsSpan().Trim();
        if (sourceSpan.IsEmpty)
        {
            return translation;
        }

        var sourcePrefixLength = CountBoundaryPrefix(sourceSpan);
        var sourceSuffixLength = CountBoundarySuffix(sourceSpan, sourcePrefixLength);
        if (sourcePrefixLength == 0 && sourceSuffixLength == 0)
        {
            return translation;
        }

        var translationStart = 0;
        while (translationStart < translation.Length && char.IsWhiteSpace(translation[translationStart]))
        {
            translationStart++;
        }

        var translationEnd = translation.Length;
        while (translationEnd > translationStart && char.IsWhiteSpace(translation[translationEnd - 1]))
        {
            translationEnd--;
        }

        if (translationStart == translationEnd)
        {
            return translation;
        }

        var core = translation.AsSpan(translationStart, translationEnd - translationStart);
        var translatedPrefixLength = sourcePrefixLength > 0 ? CountBoundaryPrefix(core) : 0;
        var translatedSuffixLength = sourceSuffixLength > 0
            ? CountBoundarySuffix(core, translatedPrefixLength)
            : 0;
        var sourcePrefix = sourceSpan[..sourcePrefixLength];
        var sourceSuffix = sourceSuffixLength > 0 ? sourceSpan[^sourceSuffixLength..] : [];
        var middleStart = translatedPrefixLength;
        var middleLength = core.Length - translatedPrefixLength - translatedSuffixLength;

        var result = new StringBuilder(
            translation.Length + sourcePrefix.Length + sourceSuffix.Length);
        result.Append(translation.AsSpan(0, translationStart));
        result.Append(sourcePrefix);
        result.Append(core.Slice(middleStart, middleLength));
        result.Append(sourceSuffix);
        result.Append(translation.AsSpan(translationEnd));
        return result.ToString();
    }

    private static int CountBoundaryPrefix(ReadOnlySpan<char> value)
    {
        var count = 0;
        while (count < value.Length && IsBoundaryPunctuation(value[count]))
        {
            count++;
        }

        return count;
    }

    private static int CountBoundarySuffix(ReadOnlySpan<char> value, int prefixLength)
    {
        var count = 0;
        while (value.Length - count > prefixLength
            && IsBoundaryPunctuation(value[value.Length - count - 1]))
        {
            count++;
        }

        return count;
    }

    private static bool IsBoundaryPunctuation(char value)
    {
        return BoundaryPunctuation.Contains(value, StringComparison.Ordinal);
    }
}

namespace TranslateTool;

internal abstract class TableDocument : IDisposable
{
    public abstract string DisplayName { get; }
    public abstract int LastRow { get; }
    public virtual int RemovedInvalidCharacterCount => 0;
    public abstract string GetValue(int row, int column);
    public abstract void SetValue(int row, int column, string value);
    public abstract void Save(string outputPath);

    public int? FindHeader(string header, int startColumn, int headerRow)
    {
        for (var column = startColumn; column <= LastColumn; column++)
        {
            if (string.Equals(GetValue(headerRow, column).Trim(), header.Trim(), StringComparison.OrdinalIgnoreCase))
            {
                return column;
            }
        }

        return null;
    }

    protected abstract int LastColumn { get; }

    public static TableDocument Open(string path, string? sheetName, string csvDelimiter)
    {
        return Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".xlsx" or ".xlsm" => XlsxTableDocument.Open(path, sheetName),
            ".csv" => CsvTableDocument.Open(path, ResolveDelimiter(csvDelimiter, ',')),
            ".tsv" => CsvTableDocument.Open(path, ResolveDelimiter(csvDelimiter, '\t')),
            ".xls" => throw new NotSupportedException("不支持旧版 .xls，请先在 Excel 中另存为 .xlsx。 "),
            _ => throw new NotSupportedException("仅支持 .xlsx、.xlsm、.csv 和 .tsv 文件。 ")
        };
    }

    private static char ResolveDelimiter(string configured, char defaultDelimiter)
    {
        if (string.IsNullOrWhiteSpace(configured) || configured.Equals("auto", StringComparison.OrdinalIgnoreCase))
        {
            return defaultDelimiter;
        }

        if (configured.Equals("\\t", StringComparison.OrdinalIgnoreCase) || configured.Equals("tab", StringComparison.OrdinalIgnoreCase))
        {
            return '\t';
        }

        if (configured.Length != 1)
        {
            throw new InvalidDataException("CsvDelimiter 必须是单个字符、tab、\\t 或 auto。 ");
        }

        return configured[0];
    }

    public virtual void Dispose()
    {
    }
}

internal static class CellReference
{
    public static int ColumnNameToNumber(string columnName)
    {
        if (string.IsNullOrWhiteSpace(columnName))
        {
            throw new InvalidDataException("列名不能为空。 ");
        }

        var result = 0;
        foreach (var character in columnName.Trim().ToUpperInvariant())
        {
            if (character is < 'A' or > 'Z')
            {
                throw new InvalidDataException($"无效列名：{columnName}");
            }

            checked
            {
                result = result * 26 + (character - 'A' + 1);
            }
        }

        return result;
    }

    public static string ColumnNumberToName(int column)
    {
        if (column <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(column));
        }

        var result = "";
        while (column > 0)
        {
            column--;
            result = (char)('A' + column % 26) + result;
            column /= 26;
        }

        return result;
    }

    public static (int Row, int Column) Parse(string reference)
    {
        if (string.IsNullOrWhiteSpace(reference))
        {
            throw new FormatException("单元格引用为空。 ");
        }

        var index = 0;
        while (index < reference.Length && (char.IsLetter(reference[index]) || reference[index] == '$'))
        {
            index++;
        }

        var columnPart = reference[..index].Replace("$", "", StringComparison.Ordinal);
        var rowPart = reference[index..].Replace("$", "", StringComparison.Ordinal);
        if (!int.TryParse(rowPart, out var row) || row <= 0)
        {
            throw new FormatException($"无效单元格引用：{reference}");
        }

        return (row, ColumnNameToNumber(columnPart));
    }
}

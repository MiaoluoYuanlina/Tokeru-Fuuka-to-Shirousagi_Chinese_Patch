using System.Text;

namespace TranslateTool;

internal sealed class CsvTableDocument : TableDocument
{
    private readonly string _inputPath;
    private readonly char _delimiter;
    private readonly List<List<string>> _rows;

    private CsvTableDocument(string inputPath, char delimiter, List<List<string>> rows)
    {
        _inputPath = inputPath;
        _delimiter = delimiter;
        _rows = rows;
    }

    public override string DisplayName => Path.GetFileName(_inputPath);
    public override int LastRow => _rows.Count;
    protected override int LastColumn => _rows.Count == 0 ? 0 : _rows.Max(row => row.Count);

    public static CsvTableDocument Open(string path, char delimiter)
    {
        using var reader = new StreamReader(path, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        var content = reader.ReadToEnd();
        return new CsvTableDocument(path, delimiter, Parse(content, delimiter));
    }

    public override string GetValue(int row, int column)
    {
        if (row <= 0 || column <= 0 || row > _rows.Count || column > _rows[row - 1].Count)
        {
            return "";
        }

        return _rows[row - 1][column - 1];
    }

    public override void SetValue(int row, int column, string value)
    {
        if (row <= 0 || column <= 0)
        {
            throw new ArgumentOutOfRangeException();
        }

        while (_rows.Count < row)
        {
            _rows.Add([]);
        }

        while (_rows[row - 1].Count < column)
        {
            _rows[row - 1].Add("");
        }

        _rows[row - 1][column - 1] = value;
    }

    public override void Save(string outputPath)
    {
        var fullPath = Path.GetFullPath(outputPath);
        var directory = Path.GetDirectoryName(fullPath)!;
        Directory.CreateDirectory(directory);
        var temporaryPath = Path.Combine(directory, $".{Path.GetFileName(fullPath)}.{Guid.NewGuid():N}.tmp");

        try
        {
            using (var writer = new StreamWriter(temporaryPath, false, new UTF8Encoding(encoderShouldEmitUTF8Identifier: true)))
            {
                foreach (var row in _rows)
                {
                    for (var column = 0; column < row.Count; column++)
                    {
                        if (column > 0)
                        {
                            writer.Write(_delimiter);
                        }

                        writer.Write(Escape(row[column], _delimiter));
                    }

                    writer.WriteLine();
                }
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

    private static List<List<string>> Parse(string content, char delimiter)
    {
        var rows = new List<List<string>>();
        var row = new List<string>();
        var field = new StringBuilder();
        var insideQuotes = false;

        for (var index = 0; index < content.Length; index++)
        {
            var character = content[index];
            if (insideQuotes)
            {
                if (character == '"')
                {
                    if (index + 1 < content.Length && content[index + 1] == '"')
                    {
                        field.Append('"');
                        index++;
                    }
                    else
                    {
                        insideQuotes = false;
                    }
                }
                else
                {
                    field.Append(character);
                }

                continue;
            }

            if (character == '"' && field.Length == 0)
            {
                insideQuotes = true;
            }
            else if (character == delimiter)
            {
                row.Add(field.ToString());
                field.Clear();
            }
            else if (character is '\r' or '\n')
            {
                row.Add(field.ToString());
                field.Clear();
                rows.Add(row);
                row = [];
                if (character == '\r' && index + 1 < content.Length && content[index + 1] == '\n')
                {
                    index++;
                }
            }
            else
            {
                field.Append(character);
            }
        }

        if (insideQuotes)
        {
            throw new InvalidDataException("CSV 文件中有未闭合的双引号。 ");
        }

        if (field.Length > 0 || row.Count > 0 || (content.Length > 0 && content[^1] == delimiter))
        {
            row.Add(field.ToString());
            rows.Add(row);
        }

        return rows;
    }

    private static string Escape(string value, char delimiter)
    {
        if (value.Contains(delimiter) || value.Contains('"') || value.Contains('\r') || value.Contains('\n'))
        {
            return '"' + value.Replace("\"", "\"\"", StringComparison.Ordinal) + '"';
        }

        return value;
    }
}



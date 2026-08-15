using System.IO.Compression;
using System.Text;
using System.Xml;
using System.Xml.Linq;

namespace TranslateTool;

internal sealed class XlsxTableDocument : TableDocument
{
    private static readonly XNamespace SpreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private static readonly XNamespace OfficeRelationshipNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace PackageRelationshipNamespace = "http://schemas.openxmlformats.org/package/2006/relationships";
    private static readonly XNamespace XmlNamespace = XNamespace.Xml;

    private readonly string _inputPath;
    private readonly string _sheetName;
    private readonly string _sheetEntryPath;
    private readonly XDocument _worksheet;
    private readonly List<string> _sharedStrings;
    private readonly Dictionary<(int Row, int Column), XElement> _cells = [];
    private readonly Dictionary<int, XElement> _rows = [];
    private int _lastRow;
    private int _lastColumn;
    private int _removedInvalidCharacterCount;

    private XlsxTableDocument(
        string inputPath,
        string sheetName,
        string sheetEntryPath,
        XDocument worksheet,
        List<string> sharedStrings)
    {
        _inputPath = inputPath;
        _sheetName = sheetName;
        _sheetEntryPath = sheetEntryPath;
        _worksheet = worksheet;
        _sharedStrings = sharedStrings;
        BuildIndex();
    }

    public override string DisplayName => _sheetName;
    public override int LastRow => _lastRow;
    public override int RemovedInvalidCharacterCount => _removedInvalidCharacterCount;
    protected override int LastColumn => _lastColumn;

    public static XlsxTableDocument Open(string path, string? requestedSheetName)
    {
        using var archive = ZipFile.OpenRead(path);
        var workbook = LoadXml(archive, "xl/workbook.xml");
        var relationships = LoadXml(archive, "xl/_rels/workbook.xml.rels");

        var sheets = workbook.Root?.Element(SpreadsheetNamespace + "sheets")?.Elements(SpreadsheetNamespace + "sheet").ToList()
            ?? throw new InvalidDataException("XLSX 中找不到工作表。 ");

        var sheet = string.IsNullOrWhiteSpace(requestedSheetName)
            ? sheets.FirstOrDefault()
            : sheets.FirstOrDefault(item => string.Equals((string?)item.Attribute("name"), requestedSheetName, StringComparison.OrdinalIgnoreCase));
        if (sheet is null)
        {
            throw new InvalidDataException($"找不到工作表“{requestedSheetName}”。可用工作表：{string.Join("、", sheets.Select(item => (string?)item.Attribute("name")))}");
        }

        var relationshipId = (string?)sheet.Attribute(OfficeRelationshipNamespace + "id")
            ?? throw new InvalidDataException("工作表关系 ID 缺失。 ");
        var relationship = relationships.Root?.Elements(PackageRelationshipNamespace + "Relationship")
            .FirstOrDefault(item => (string?)item.Attribute("Id") == relationshipId)
            ?? throw new InvalidDataException("找不到工作表关系。 ");
        var target = (string?)relationship.Attribute("Target")
            ?? throw new InvalidDataException("工作表关系目标缺失。 ");
        var sheetEntryPath = ResolvePackagePath("xl/workbook.xml", target);
        var worksheet = LoadXml(archive, sheetEntryPath);
        var sharedStrings = LoadSharedStrings(archive);

        return new XlsxTableDocument(
            path,
            (string?)sheet.Attribute("name") ?? "Sheet1",
            sheetEntryPath,
            worksheet,
            sharedStrings);
    }

    public override string GetValue(int row, int column)
    {
        if (!_cells.TryGetValue((row, column), out var cell))
        {
            return "";
        }

        var type = (string?)cell.Attribute("t");
        if (type == "s")
        {
            var rawIndex = cell.Element(SpreadsheetNamespace + "v")?.Value;
            return int.TryParse(rawIndex, out var sharedStringIndex)
                && sharedStringIndex >= 0
                && sharedStringIndex < _sharedStrings.Count
                ? _sharedStrings[sharedStringIndex]
                : "";
        }

        if (type == "inlineStr")
        {
            return string.Concat(cell.Element(SpreadsheetNamespace + "is")?
                .Descendants(SpreadsheetNamespace + "t")
                .Select(text => text.Value) ?? []);
        }

        if (type == "b")
        {
            return cell.Element(SpreadsheetNamespace + "v")?.Value == "1" ? "TRUE" : "FALSE";
        }

        return cell.Element(SpreadsheetNamespace + "v")?.Value
            ?? cell.Element(SpreadsheetNamespace + "is")?.Value
            ?? "";
    }

    public override void SetValue(int row, int column, string value)
    {
        if (row <= 0 || column <= 0)
        {
            throw new ArgumentOutOfRangeException();
        }

        if (!_rows.TryGetValue(row, out var rowElement))
        {
            rowElement = new XElement(SpreadsheetNamespace + "row", new XAttribute("r", row));
            InsertRowInOrder(rowElement, row);
            _rows[row] = rowElement;
        }

        if (!_cells.TryGetValue((row, column), out var cell))
        {
            cell = new XElement(SpreadsheetNamespace + "c",
                new XAttribute("r", CellReference.ColumnNumberToName(column) + row));
            InsertCellInOrder(rowElement, cell, column);
            _cells[(row, column)] = cell;
        }

        var xmlSafeValue = RemoveInvalidXmlCharacters(value, out var removedCount);
        _removedInvalidCharacterCount += removedCount;

        cell.SetAttributeValue("t", "inlineStr");
        cell.RemoveNodes();
        cell.Add(new XElement(SpreadsheetNamespace + "is",
            new XElement(SpreadsheetNamespace + "t",
                new XAttribute(XmlNamespace + "space", "preserve"),
                xmlSafeValue)));

        _lastRow = Math.Max(_lastRow, row);
        _lastColumn = Math.Max(_lastColumn, column);
    }

    private static string RemoveInvalidXmlCharacters(string value, out int removedCount)
    {
        removedCount = 0;
        StringBuilder? sanitized = null;

        for (var index = 0; index < value.Length; index++)
        {
            var character = value[index];
            var isValidBmpCharacter = character is '\t' or '\n' or '\r'
                || character is >= '\u0020' and <= '\uD7FF'
                || character is >= '\uE000' and <= '\uFFFD';
            if (isValidBmpCharacter)
            {
                sanitized?.Append(character);
                continue;
            }

            if (char.IsHighSurrogate(character)
                && index + 1 < value.Length
                && char.IsLowSurrogate(value[index + 1]))
            {
                if (sanitized is not null)
                {
                    sanitized.Append(character);
                    sanitized.Append(value[index + 1]);
                }

                index++;
                continue;
            }

            if (sanitized is null)
            {
                sanitized = new StringBuilder(value.Length);
                sanitized.Append(value, 0, index);
            }

            removedCount++;
        }

        return sanitized?.ToString() ?? value;
    }

    public override void Save(string outputPath)
    {
        var fullPath = Path.GetFullPath(outputPath);
        var directory = Path.GetDirectoryName(fullPath)!;
        Directory.CreateDirectory(directory);
        var temporaryPath = Path.Combine(directory, $".{Path.GetFileName(fullPath)}.{Guid.NewGuid():N}.tmp");

        try
        {
            File.Copy(_inputPath, temporaryPath, true);
            using (var archive = ZipFile.Open(temporaryPath, ZipArchiveMode.Update))
            {
                var oldEntry = FindEntry(archive, _sheetEntryPath)
                    ?? throw new InvalidDataException($"XLSX 中找不到 {_sheetEntryPath}。 ");
                var entryName = oldEntry.FullName;
                oldEntry.Delete();
                var newEntry = archive.CreateEntry(entryName, CompressionLevel.Optimal);
                using var stream = newEntry.Open();
                using var writer = XmlWriter.Create(stream, new XmlWriterSettings
                {
                    Encoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
                    Indent = false,
                    CloseOutput = false
                });
                _worksheet.Save(writer);
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

    private void BuildIndex()
    {
        var sheetData = _worksheet.Root?.Element(SpreadsheetNamespace + "sheetData")
            ?? throw new InvalidDataException("工作表缺少 sheetData。 ");

        foreach (var rowElement in sheetData.Elements(SpreadsheetNamespace + "row"))
        {
            var declaredRow = (int?)rowElement.Attribute("r");
            foreach (var cell in rowElement.Elements(SpreadsheetNamespace + "c"))
            {
                var reference = (string?)cell.Attribute("r");
                if (string.IsNullOrWhiteSpace(reference))
                {
                    continue;
                }

                var parsed = CellReference.Parse(reference);
                _cells[(parsed.Row, parsed.Column)] = cell;
                _lastRow = Math.Max(_lastRow, parsed.Row);
                _lastColumn = Math.Max(_lastColumn, parsed.Column);
                declaredRow ??= parsed.Row;
            }

            if (declaredRow is not null)
            {
                _rows[declaredRow.Value] = rowElement;
                _lastRow = Math.Max(_lastRow, declaredRow.Value);
            }
        }
    }

    private void InsertRowInOrder(XElement rowElement, int row)
    {
        var sheetData = _worksheet.Root!.Element(SpreadsheetNamespace + "sheetData")!;
        var nextRow = sheetData.Elements(SpreadsheetNamespace + "row")
            .FirstOrDefault(item => ((int?)item.Attribute("r") ?? int.MaxValue) > row);
        if (nextRow is null)
        {
            sheetData.Add(rowElement);
        }
        else
        {
            nextRow.AddBeforeSelf(rowElement);
        }
    }

    private static void InsertCellInOrder(XElement rowElement, XElement cell, int column)
    {
        var nextCell = rowElement.Elements(SpreadsheetNamespace + "c").FirstOrDefault(item =>
        {
            var reference = (string?)item.Attribute("r");
            return reference is not null && CellReference.Parse(reference).Column > column;
        });
        if (nextCell is null)
        {
            rowElement.Add(cell);
        }
        else
        {
            nextCell.AddBeforeSelf(cell);
        }
    }

    private static XDocument LoadXml(ZipArchive archive, string path)
    {
        var entry = FindEntry(archive, path)
            ?? throw new InvalidDataException($"XLSX 中找不到 {path}。 ");
        using var stream = entry.Open();
        return XDocument.Load(stream, LoadOptions.PreserveWhitespace);
    }

    private static List<string> LoadSharedStrings(ZipArchive archive)
    {
        var entry = FindEntry(archive, "xl/sharedStrings.xml");
        if (entry is null)
        {
            return [];
        }

        using var stream = entry.Open();
        var document = XDocument.Load(stream, LoadOptions.PreserveWhitespace);
        return document.Root?.Elements(SpreadsheetNamespace + "si")
            .Select(item => string.Concat(item.Descendants(SpreadsheetNamespace + "t").Select(text => text.Value)))
            .ToList() ?? [];
    }

    private static ZipArchiveEntry? FindEntry(ZipArchive archive, string path)
    {
        var normalized = path.Replace('\\', '/').TrimStart('/');
        return archive.Entries.FirstOrDefault(entry => string.Equals(entry.FullName, normalized, StringComparison.OrdinalIgnoreCase));
    }

    private static string ResolvePackagePath(string basePart, string target)
    {
        if (target.StartsWith('/'))
        {
            return target.TrimStart('/');
        }

        var baseUri = new Uri("http://package/" + basePart.Replace('\\', '/'));
        return new Uri(baseUri, target).AbsolutePath.TrimStart('/');
    }
}

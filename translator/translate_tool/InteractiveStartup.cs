using System.Text.Json;
using System.Runtime.ExceptionServices;
using System.Windows.Forms;

namespace TranslateTool;

internal static class InteractiveStartup
{
    private static readonly string[] PreferredConfigNames =
    [
        "translator-config.json",
        "translate-config.json",
        "config.json"
    ];

    public static string? SelectInputFile()
    {
        if (Thread.CurrentThread.GetApartmentState() == ApartmentState.STA)
        {
            return SelectInputFileCore();
        }

        string? selectedFile = null;
        Exception? dialogException = null;
        var dialogThread = new Thread(() =>
        {
            try
            {
                selectedFile = SelectInputFileCore();
            }
            catch (Exception exception)
            {
                dialogException = exception;
            }
        })
        {
            IsBackground = false,
            Name = "SpreadsheetFilePicker"
        };
        dialogThread.SetApartmentState(ApartmentState.STA);
        dialogThread.Start();
        dialogThread.Join();

        if (dialogException is not null)
        {
            ExceptionDispatchInfo.Capture(dialogException).Throw();
        }

        return selectedFile;
    }

    private static string? SelectInputFileCore()
    {
        Application.EnableVisualStyles();
        using var dialog = new OpenFileDialog
        {
            Title = "选择需要翻译的表格文件",
            Filter = "支持的表格|*.xlsx;*.xlsm;*.csv;*.tsv|Excel 工作簿|*.xlsx;*.xlsm|CSV/TSV 文本表格|*.csv;*.tsv|所有文件|*.*",
            CheckFileExists = true,
            CheckPathExists = true,
            Multiselect = false,
            RestoreDirectory = true,
            DereferenceLinks = true,
            InitialDirectory = Directory.Exists(Environment.CurrentDirectory)
                ? Environment.CurrentDirectory
                : AppContext.BaseDirectory
        };

        return dialog.ShowDialog() == DialogResult.OK ? dialog.FileName : null;
    }

    public static async Task<string> ResolveConfigPathAsync(
        CommandLineOptions commandLine,
        string inputPath,
        CancellationToken cancellationToken)
    {
        if (commandLine.ConfigWasSpecified)
        {
            var explicitPath = Path.GetFullPath(commandLine.ConfigFile);
            if (!File.Exists(explicitPath))
            {
                throw new FileNotFoundException($"找不到指定的配置文件：{explicitPath}");
            }

            return explicitPath;
        }

        var directories = new[]
            {
                Path.GetDirectoryName(inputPath),
                AppContext.BaseDirectory,
                Environment.CurrentDirectory
            }
            .Where(directory => !string.IsNullOrWhiteSpace(directory) && Directory.Exists(directory))
            .Select(directory => Path.GetFullPath(directory!))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        foreach (var preferredName in PreferredConfigNames)
        {
            foreach (var directory in directories)
            {
                var candidate = Path.Combine(directory, preferredName);
                if (IsTranslationConfig(candidate))
                {
                    return candidate;
                }
            }
        }

        var detectedConfigs = directories
            .SelectMany(EnumerateConfigFiles)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Where(IsTranslationConfig)
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .ThenBy(path => path, StringComparer.OrdinalIgnoreCase)
            .ToList();
        if (detectedConfigs.Count > 0)
        {
            if (detectedConfigs.Count > 1)
            {
                Console.WriteLine($"检测到 {detectedConfigs.Count} 份有效配置，将使用最近修改的一份。 ");
            }

            return detectedConfigs[0];
        }

        var generatedPath = Path.Combine(Environment.CurrentDirectory, "translator-config.json");
        await AppOptions.SaveExampleAsync(generatedPath, cancellationToken);
        Console.WriteLine($"没有找到配置文件，已自动创建：{generatedPath}");
        return generatedPath;
    }

    private static IEnumerable<string> EnumerateConfigFiles(string directory)
    {
        try
        {
            return Directory.EnumerateFiles(directory, "*config*.json", SearchOption.TopDirectoryOnly).ToList();
        }
        catch (IOException)
        {
            return [];
        }
        catch (UnauthorizedAccessException)
        {
            return [];
        }
    }

    private static bool IsTranslationConfig(string path)
    {
        if (!File.Exists(path))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            var root = document.RootElement;
            return root.ValueKind == JsonValueKind.Object
                && HasProperty(root, "ApiUrl")
                && HasProperty(root, "Model")
                && HasProperty(root, "SourceHeader")
                && HasProperty(root, "TargetHeader");
        }
        catch (JsonException)
        {
            return false;
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static bool HasProperty(JsonElement root, string propertyName)
    {
        return root.EnumerateObject().Any(property =>
            string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase));
    }
}

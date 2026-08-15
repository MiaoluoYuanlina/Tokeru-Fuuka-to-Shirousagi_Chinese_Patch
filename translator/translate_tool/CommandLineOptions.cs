namespace TranslateTool;

internal sealed class CommandLineOptions
{
    public string? InputFile { get; private set; }
    public string ConfigFile { get; private set; } = "translator-config.json";
    public bool ConfigWasSpecified { get; private set; }
    public string? OutputFile { get; private set; }
    public string? CreateConfigFile { get; private set; }
    public bool OverwriteInput { get; private set; }
    public bool DryRun { get; private set; }
    public bool ShowHelp { get; private set; }

    public static CommandLineOptions Parse(string[] args)
    {
        var result = new CommandLineOptions();
        for (var index = 0; index < args.Length; index++)
        {
            var arg = args[index];
            switch (arg)
            {
                case "-h":
                case "--help":
                    result.ShowHelp = true;
                    break;
                case "-c":
                case "--config":
                    result.ConfigFile = ReadValue(args, ref index, arg);
                    result.ConfigWasSpecified = true;
                    break;
                case "-o":
                case "--output":
                    result.OutputFile = ReadValue(args, ref index, arg);
                    break;
                case "--overwrite-input":
                    result.OverwriteInput = true;
                    break;
                case "--dry-run":
                    result.DryRun = true;
                    break;
                case "--create-config":
                    result.CreateConfigFile = index + 1 < args.Length && !args[index + 1].StartsWith('-')
                        ? args[++index]
                        : "translator-config.json";
                    break;
                default:
                    if (arg.StartsWith('-'))
                    {
                        throw new ArgumentException($"未知参数：{arg}");
                    }

                    if (result.InputFile is not null)
                    {
                        throw new ArgumentException("只能指定一个输入表格文件。 ");
                    }

                    result.InputFile = arg;
                    break;
            }
        }

        if (result.OutputFile is not null && result.OverwriteInput)
        {
            throw new ArgumentException("--output 和 --overwrite-input 不能同时使用。 ");
        }

        return result;
    }

    private static string ReadValue(string[] args, ref int index, string option)
    {
        if (++index >= args.Length)
        {
            throw new ArgumentException($"参数 {option} 缺少值。 ");
        }

        return args[index];
    }

    public static void PrintUsage()
    {
        Console.WriteLine("表格 AI 翻译工具 (.NET 8)");
        Console.WriteLine();
        Console.WriteLine("用法：");
        Console.WriteLine("  translate_tool                         自动识别配置并弹出文件选择框");
        Console.WriteLine("  translate_tool <表格.xlsx|csv|tsv> [--config 配置.json] [--output 输出文件]");
        Console.WriteLine("  translate_tool <表格.xlsx|csv|tsv> --overwrite-input");
        Console.WriteLine("  translate_tool --create-config [配置.json]");
        Console.WriteLine();
        Console.WriteLine("选项：");
        Console.WriteLine("  -c, --config <文件>     配置文件，默认 translator-config.json");
        Console.WriteLine("  -o, --output <文件>     输出文件，默认 <原名>.translated.<扩展名>");
        Console.WriteLine("      --overwrite-input   直接覆盖输入文件");
        Console.WriteLine("      --dry-run           只扫描，不调用 API、不写文件");
        Console.WriteLine("      --create-config     创建示例配置文件");
        Console.WriteLine("  -h, --help              显示帮助");
    }
}

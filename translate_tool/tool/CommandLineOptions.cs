namespace TranslateTool;

internal sealed class CommandLineOptions
{
    public string? InputFile { get; private set; }
    public string? OutputFile { get; private set; }
    public bool OverwriteInput { get; private set; }
    public bool DryRun { get; private set; }
    public bool SelfTest { get; private set; }
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
                case "--self-test":
                    result.SelfTest = true;
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
        Console.WriteLine("  tool                                   弹出文件选择框并使用 GlobalSettings.cs");
        Console.WriteLine("  tool <表格.xlsx|csv|tsv> [--output 输出文件]");
        Console.WriteLine("  tool <表格.xlsx|csv|tsv> --overwrite-input");
        Console.WriteLine("  tool --self-test");
        Console.WriteLine();
        Console.WriteLine("选项：");
        Console.WriteLine("  -o, --output <文件>     输出文件，默认 <原名>.translated.<扩展名>");
        Console.WriteLine("      --overwrite-input   直接覆盖输入文件");
        Console.WriteLine("      --dry-run           只扫描，不调用 API、不写文件");
        Console.WriteLine("      --self-test         离线验证全部供应商的请求和响应格式");
        Console.WriteLine("  -h, --help              显示帮助");
        Console.WriteLine();
        Console.WriteLine("配置位置：项目中的 GlobalSettings.cs（修改后重新编译）。");
    }
}


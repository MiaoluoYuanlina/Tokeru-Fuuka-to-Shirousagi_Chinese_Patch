using TranslateTool;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        return TranslationApplication.RunAsync(args).GetAwaiter().GetResult();
    }
}

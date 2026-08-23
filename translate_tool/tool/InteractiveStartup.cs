using System.Runtime.ExceptionServices;
using System.Windows.Forms;

namespace TranslateTool;

internal static class InteractiveStartup
{
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
}

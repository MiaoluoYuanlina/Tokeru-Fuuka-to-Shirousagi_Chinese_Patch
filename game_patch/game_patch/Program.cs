using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.IO.Compression;
using System.Threading;
namespace game_patch    
{
    internal class Program
    {
        static string game_path = Directory.GetCurrentDirectory();
        static int game_int = 0;
        static void Main(string[] args)
        {
            bool gameFoundInCurrentDirectory = false;
            game_int = Description_Get_Pid("とける風花とシロうさぎ　体験版");
            if (game_int == 0)
            {
                game_int = Description_Get_Pid("とける風花とシロうさぎ");
            }

            if (File.Exists($"{game_path}\\kazeshiro_demo.exe"))
            {
                gameFoundInCurrentDirectory = true;
                Console.WriteLine("已经定位到游戏位置:" + game_path);
            }else if (File.Exists($"{game_path}\\とける風花とシロうさぎ.exe"))
            {
                gameFoundInCurrentDirectory = true;
                Console.WriteLine("已经定位到游戏位置:" + game_path);
            }

            if (game_int != 0)
            {
                Console.WriteLine("已经定位到游戏进程，PID为:" + game_int);
                game_path = Path_Get_Directory(PID_Get_Path(game_int));
                PID_Kill(game_int);
                Console.WriteLine("游戏路径为:" + game_path);
            }
            else if (!gameFoundInCurrentDirectory)
            {
                Console.WriteLine("未找到游戏路径，先提前启动游戏后在运行，或将本程序放在游戏目录下运行。");
                Console.WriteLine("确保先提前运行游戏在运行补丁程序。");
                Console.ReadKey();
                return;
            }

            StopPatchRelatedProcesses(game_path);



            // 解压到游戏目录

            Console.WriteLine("开始安装补丁...");

            if (ExtractDomeZip(game_path))
            {
                Console.WriteLine("补丁安装完成！");
            }
            else
            {
                Console.WriteLine("补丁安装失败！");
            }

            Console.WriteLine("按任意键退出...");
            Console.ReadKey();
        }

        static bool ExtractDomeZip(string targetDirectory)
        {
            try
            {
                Assembly assembly = Assembly.GetExecutingAssembly();

                string resourceName = null;

                // 找到嵌入资源 dome.zip
                foreach (string name in assembly.GetManifestResourceNames())
                {
                    if (name.EndsWith("patch.zip", StringComparison.OrdinalIgnoreCase))
                    {
                        resourceName = name;
                        break;
                    }
                }

                if (resourceName == null)
                {
                    Console.WriteLine("错误：程序内没有找到 patch.zip");
                    return false;
                }

                using (Stream zipStream = assembly.GetManifestResourceStream(resourceName))
                {
                    if (zipStream == null)
                    {
                        Console.WriteLine("错误：无法读取 patch.zip");
                        return false;
                    }

                    using (ZipArchive archive = new ZipArchive(zipStream, ZipArchiveMode.Read))
                    {
                        foreach (ZipArchiveEntry entry in archive.Entries)
                        {
                            if (IsTransientPayloadEntry(entry.FullName))
                            {
                                Console.WriteLine("跳过临时备份：" + entry.FullName);
                                continue;
                            }

                            string filePath = Path.Combine(
                                targetDirectory,
                                entry.FullName
                            );

                            // ZIP 内的文件夹
                            if (string.IsNullOrEmpty(entry.Name))
                            {
                                Directory.CreateDirectory(filePath);
                                continue;
                            }

                            string directory = Path.GetDirectoryName(filePath);

                            if (!string.IsNullOrEmpty(directory))
                            {
                                Directory.CreateDirectory(directory);
                            }

                            Console.WriteLine("写入：" + entry.FullName);

                            ExtractEntryWithRetry(entry, filePath);
                        }
                    }
                }

                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine("解压失败：" + ex.Message);
                return false;
            }
        }

        static bool IsTransientPayloadEntry(string entryName)
        {
            string fileName = Path.GetFileName(entryName);
            return (fileName.StartsWith("patch.previous.", StringComparison.OrdinalIgnoreCase)
                    && fileName.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                || (fileName.StartsWith("KazeshiroLauncher.before_", StringComparison.OrdinalIgnoreCase)
                    && fileName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase));
        }

        static void ExtractEntryWithRetry(ZipArchiveEntry entry, string filePath)
        {
            const int maximumAttempts = 6;
            for (int attempt = 1; attempt <= maximumAttempts; attempt++)
            {
                try
                {
                    entry.ExtractToFile(filePath, true);
                    return;
                }
                catch (IOException) when (attempt < maximumAttempts)
                {
                    Console.WriteLine("文件暂时被占用，正在重试（" + attempt + "/" + maximumAttempts + "）：" + entry.FullName);
                    Thread.Sleep(700);
                }
                catch (UnauthorizedAccessException) when (attempt < maximumAttempts)
                {
                    Console.WriteLine("文件暂时无法写入，正在重试（" + attempt + "/" + maximumAttempts + "）：" + entry.FullName);
                    Thread.Sleep(700);
                }
            }
        }

        static void StopPatchRelatedProcesses(string targetDirectory)
        {
            string normalizedTarget;
            try
            {
                normalizedTarget = Path.GetFullPath(targetDirectory)
                    .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
            }
            catch
            {
                return;
            }

            int currentProcessId = Process.GetCurrentProcess().Id;
            foreach (Process process in Process.GetProcesses())
            {
                try
                {
                    if (process.Id == currentProcessId)
                        continue;

                    string executablePath = process.MainModule.FileName;
                    if (string.IsNullOrEmpty(executablePath)
                        || !executablePath.StartsWith(normalizedTarget, StringComparison.OrdinalIgnoreCase))
                        continue;

                    string processName = Path.GetFileNameWithoutExtension(executablePath);
                    bool shouldStop = processName.IndexOf("KazeshiroLauncher", StringComparison.OrdinalIgnoreCase) >= 0
                        || processName.StartsWith("KazeshiroLocaleRuntime", StringComparison.OrdinalIgnoreCase)
                        || processName.Equals("kazeshiro_demo", StringComparison.OrdinalIgnoreCase)
                        || processName.Equals("とける風花とシロうさぎ", StringComparison.OrdinalIgnoreCase);

                    if (!shouldStop)
                        continue;

                    Console.WriteLine("正在关闭占用补丁文件的程序：" + processName + " (PID " + process.Id + ")");
                    process.Kill();
                    process.WaitForExit(5000);
                }
                catch
                {
                    // 无权限访问或进程已经退出时继续安装，具体文件仍会在写入阶段重试。
                }
                finally
                {
                    process.Dispose();
                }
            }
        }
        static bool ZIP_Extract_Resource(string targetDirectory)
        {
            try
            {
                Assembly assembly = Assembly.GetExecutingAssembly();

                // 自动查找结尾为 patch.zip 的嵌入资源
                string resourceName = null;

                foreach (string name in assembly.GetManifestResourceNames())
                {
                    if (name.EndsWith("patch.zip", StringComparison.OrdinalIgnoreCase))
                    {
                        resourceName = name;
                        break;
                    }
                }

                if (resourceName == null)
                {
                    Console.WriteLine("没有找到嵌入资源 patch.zip");
                    return false;
                }

                Directory.CreateDirectory(targetDirectory);

                using (Stream zipStream = assembly.GetManifestResourceStream(resourceName))
                using (ZipArchive archive = new ZipArchive(zipStream, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string filePath = Path.Combine(targetDirectory, entry.FullName);

                        // 文件夹
                        if (string.IsNullOrEmpty(entry.Name))
                        {
                            Directory.CreateDirectory(filePath);
                            continue;
                        }

                        string directory = Path.GetDirectoryName(filePath);

                        if (!string.IsNullOrEmpty(directory))
                        {
                            Directory.CreateDirectory(directory);
                        }

                        // true = 已存在则覆盖
                        entry.ExtractToFile(filePath, true);
                    }
                }

                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine("解压失败：" + ex.Message);
                return false;
            }
        }


        static int Name_Get_Pid(string name)
        {
            Process[] processes = Process.GetProcessesByName(name);

            if (processes.Length > 0)
            {
                return processes[0].Id;
            }

            return 0;
        }
        static int Description_Get_Pid(string description)
        {
            foreach (Process process in Process.GetProcesses())
            {
                try
                {
                    string filePath = process.MainModule.FileName;

                    if (string.IsNullOrEmpty(filePath))
                        continue;

                    string fileDescription =
                        FileVersionInfo.GetVersionInfo(filePath).FileDescription;

                    if (fileDescription == description)
                    {
                        return process.Id;
                    }
                }
                catch
                {
                    // 某些进程无权限读取，跳过
                }
                finally
                {
                    process.Dispose();
                }
            }
            return 0;
        }
        static string PID_Get_Path(int pid)
        {
            try
            {
                Process process = Process.GetProcessById(pid);

                string path = process.MainModule.FileName;

                process.Dispose();

                return path;
            }
            catch
            {
                return "";
            }
        }

        static string Path_Get_Directory(string path)
        {
            string dir = Path.GetDirectoryName(path);

            if (string.IsNullOrEmpty(dir))
                return "";

            return dir + "\\";
        }
        static bool PID_Kill(int pid)
        {
            try
            {
                Process process = Process.GetProcessById(pid);
                process.Kill();
                process.Dispose();

                return true;
            }
            catch
            {
                return false;
            }
        }
    }
}

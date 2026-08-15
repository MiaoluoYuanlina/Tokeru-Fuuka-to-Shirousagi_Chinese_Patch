using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.IO.Compression;
namespace game_patch
{
    internal class Program
    {
        static string game_path = Directory.GetCurrentDirectory();
        static int game_int = 0;
        static void Main(string[] args)
        {
            game_int = Description_Get_Pid("とける風花とシロうさぎ　体験版");

            if (File.Exists($"{game_path}\\kazeshiro_demo.exe"))
            {
                Console.WriteLine("已经定位到游戏位置:" + game_path);
            }
            else if (game_int != 0)
            {
                Console.WriteLine("已经定位到游戏进程，PID为:" + game_int);
                game_path = Path_Get_Directory(PID_Get_Path(game_int));
                PID_Kill(game_int);
                Console.WriteLine("游戏路径为:" + game_path);

            }
            else
            {
                Console.WriteLine("未找到游戏路径，先提前启动游戏后在运行，或将本程序放在游戏目录下运行。");
                Console.WriteLine("确保进程名未经过修改为\"kazeshiro_demo.exe\"或\"\",在或者先提前运行游戏在运行补丁程序。");
                Console.ReadKey();
                return;
            }



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
                    if (name.EndsWith("dome.zip", StringComparison.OrdinalIgnoreCase))
                    {
                        resourceName = name;
                        break;
                    }
                }

                if (resourceName == null)
                {
                    Console.WriteLine("错误：程序内没有找到 dome.zip");
                    return false;
                }

                using (Stream zipStream = assembly.GetManifestResourceStream(resourceName))
                {
                    if (zipStream == null)
                    {
                        Console.WriteLine("错误：无法读取 dome.zip");
                        return false;
                    }

                    using (ZipArchive archive = new ZipArchive(zipStream, ZipArchiveMode.Read))
                    {
                        foreach (ZipArchiveEntry entry in archive.Entries)
                        {
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

                            // true = 存在同名文件时覆盖
                            entry.ExtractToFile(filePath, true);
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
        static bool ZIP_Extract_Resource(string targetDirectory)
        {
            try
            {
                Assembly assembly = Assembly.GetExecutingAssembly();

                // 自动查找结尾为 dome.zip 的嵌入资源
                string resourceName = null;

                foreach (string name in assembly.GetManifestResourceNames())
                {
                    if (name.EndsWith("dome.zip", StringComparison.OrdinalIgnoreCase))
                    {
                        resourceName = name;
                        break;
                    }
                }

                if (resourceName == null)
                {
                    Console.WriteLine("没有找到嵌入资源 dome.zip");
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

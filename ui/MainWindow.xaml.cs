using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media;

namespace EvadedApp
{
    public partial class MainWindow : Window
    {
        private Process? engineProcess;
        private bool isStoppingEngine;

        public MainWindow()
        {
            InitializeComponent();
            this.Closed += MainWindow_Closed;
        }

        private async void BtnToggle_Click(object sender, RoutedEventArgs e)
        {
            if (engineProcess == null || engineProcess.HasExited)
            {
                await StartEngineAsync();
            }
            else
            {
                StopEngine();
            }
        }

        private async Task StartEngineAsync()
        {
            try
            {
                string? enginePath = ResolveEnginePath();

                if (string.IsNullOrEmpty(enginePath))
                {
                    Log("Engine executable not found. Build the C++ engine first.");
                    SetStatus("Status: Engine Missing", Color.FromRgb(255, 82, 82), "Start Engine");
                    return;
                }

                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = enginePath,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    RedirectStandardInput = true,
                    WorkingDirectory = Path.GetDirectoryName(enginePath)
                };

                engineProcess = new Process
                {
                    StartInfo = psi,
                    EnableRaisingEvents = true
                };
                engineProcess.OutputDataReceived += (s, args) =>
                {
                    if (!string.IsNullOrEmpty(args.Data))
                    {
                        Dispatcher.Invoke(() => Log(args.Data));
                    }
                };
                engineProcess.ErrorDataReceived += (s, args) =>
                {
                    if (!string.IsNullOrEmpty(args.Data))
                    {
                        Dispatcher.Invoke(() => Log($"ERROR: {args.Data}"));
                    }
                };
                engineProcess.Exited += (s, args) =>
                {
                    if (s is Process process)
                    {
                        Dispatcher.Invoke(() => HandleEngineExit(process.ExitCode));
                    }
                };

                engineProcess.Start();
                engineProcess.BeginOutputReadLine();
                engineProcess.BeginErrorReadLine();
                engineProcess.StandardInput.WriteLine(txtProcessList.Text.Trim()); 

                Log($"Engine launch requested: {enginePath}");
                SetStatus("Status: Starting", Color.FromRgb(255, 193, 7), "Stop Engine");

                await Task.Delay(600);
                if (engineProcess != null && !engineProcess.HasExited)
                {
                    Log("Engine is running.");
                    SetStatus("Status: Running", Color.FromRgb(0, 230, 118), "Stop Engine");
                }
            }
            catch (Exception ex)
            {
                Log($"Error starting engine: {ex.Message}");
                SetStatus("Status: Start Failed", Color.FromRgb(255, 82, 82), "Start Engine");
            }
        }

        private void StopEngine()
        {
            if (engineProcess == null)
            {
                SetStatus("Status: Stopped", Color.FromRgb(255, 82, 82), "Start Engine");
                return;
            }

            isStoppingEngine = true;

            try
            {
                if (!engineProcess.HasExited)
                {
                    Log("Sending stop command to engine.");
                    engineProcess.StandardInput.WriteLine("stop");
                    if (!engineProcess.WaitForExit(2000))
                    {
                        Log("Engine did not stop in time. Terminating process.");
                        engineProcess.Kill();
                    }
                }
            }
            catch (Exception ex)
            {
                Log($"Error stopping engine: {ex.Message}");
                HandleEngineExit(-1);
            }
        }

        private void Log(string message)
        {
            txtLogs.Text += $"[{DateTime.Now:HH:mm:ss}] {message}\n";
            logScroll.ScrollToEnd();
        }

        private void HandleEngineExit(int exitCode)
        {
            if (engineProcess != null)
            {
                engineProcess.Dispose();
                engineProcess = null;
            }

            if (isStoppingEngine)
            {
                isStoppingEngine = false;
                Log("Engine stopped.");
                SetStatus("Status: Stopped", Color.FromRgb(255, 82, 82), "Start Engine");
                return;
            }

            if (exitCode == 0)
            {
                Log("Engine exited.");
            }
            else
            {
                Log($"Engine exited with code {exitCode}. If WinDivert fails to open, run the app as administrator.");
            }

            SetStatus("Status: Stopped", Color.FromRgb(255, 82, 82), "Start Engine");
        }

        private void SetStatus(string text, Color color, string buttonText)
        {
            txtStatus.Text = text;
            txtStatus.Foreground = new SolidColorBrush(color);
            btnToggle.Content = buttonText;
        }

        private static string? ResolveEnginePath()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string[] candidates =
            {
                Path.GetFullPath(Path.Combine(baseDir, @"..\..\..\..\engine\build\Release\Engine.exe")),
                Path.GetFullPath(Path.Combine(baseDir, @"engine\build\Release\Engine.exe"))
            };

            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }

            return null;
        }

        private void MainWindow_Closed(object? sender, EventArgs e)
        {
            StopEngine();
        }
    }
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Net.Http

# ── File logging ──────────────────────────────────────────────────────────
$logPath = Join-Path $PSScriptRoot "agent.log"
$logMaxBytes = 512000

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    try {
        if (Test-Path $logPath) {
            $len = (Get-Item $logPath).Length
            if ($len -gt $logMaxBytes) {
                $old = "$logPath.old"
                if (Test-Path $old) { Remove-Item $old -Force -ErrorAction SilentlyContinue }
                Move-Item $logPath $old -Force -ErrorAction SilentlyContinue
            }
        }
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $logPath -Value "$stamp [$Level] $Message" -Encoding UTF8
    } catch {}
}

Write-Log "agent.ps1 starting"

# Read Configuration
$configPath = Join-Path $PSScriptRoot "config.ini"
if (-not (Test-Path $configPath)) {
    Write-Log "config.ini missing at $configPath — exiting" "ERROR"
    exit
}
$configContent = Get-Content $configPath -Raw
$serverUrl = ([regex]"(?m)^server_url=(.*)$").Match($configContent).Groups[1].Value.Trim()
$token = ([regex]"(?m)^token=(.*)$").Match($configContent).Groups[1].Value.Trim()

if (-not $serverUrl -or -not $token) {
    Write-Log "Missing token or server_url in config.ini — exiting" "ERROR"
    exit
}

$deviceIdMatch = ([regex]"(?m)^device_id=(.*)$").Match($configContent)
if ($deviceIdMatch.Success) {
    $deviceId = $deviceIdMatch.Groups[1].Value.Trim()
} else {
    $deviceId = [guid]::NewGuid().ToString()
    Add-Content -Path $configPath -Value "`ndevice_id=$deviceId" -Encoding UTF8
}

Write-Log "Config loaded: server=$serverUrl device=$deviceId token=$($token.Substring(0, [Math]::Min(8, $token.Length)))..."

# Tray Icon setup
$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Icon = [System.Drawing.SystemIcons]::Information
$notifyIcon.Visible = $false  # Silent; no tray icon
$notifyIcon.Text = "ClueZero Background Agent"

function Show-Toast($title, $message) {
    # Disabled for silence; can be re-enabled for debugging if needed.
    # $notifyIcon.ShowBalloonTip(3000, $title, $message, [System.Windows.Forms.ToolTipIcon]::Info)
}

$sessionId = ""
$timer = New-Object System.Windows.Forms.Timer

function Open-Session() {
    try {
        $reqBody = @{ platform = "windows"; device_id = $deviceId } | ConvertTo-Json -Compress
        $resp = Invoke-RestMethod -Uri "$serverUrl/session/open" -Method Post -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } -Body $reqBody
        $script:sessionId = $resp.session_id
        $hb = $resp.heartbeat_seconds
        Write-Log "Session open: $sessionId (HB: ${hb}s)"
        
        $timer.Interval = $hb * 1000
        $timer.Add_Tick({ Ping-Session })
        $timer.Start()
    } catch {
        Write-Log "Failed to open session: $_" "ERROR"
        Show-Toast "Agent Error" "Authentication failed. Token invalid."
        exit
    }
}

function Ping-Session() {
    try {
        Invoke-RestMethod -Uri "$serverUrl/session/ping" -Method Post -Headers @{ Authorization = "Bearer $token"; "X-Session-Id" = $sessionId } | Out-Null
    } catch {
        Write-Log "Ping failed (Revoked?): $_" "ERROR"
        # If server revokes session, exist silently just like Python client
        if ($_.Exception.Message -match "401") { exit }
    }
}

function Take-Screenshot() {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $gfx.Dispose()
    
    $tempFile = [System.IO.Path]::GetTempFileName() + ".png"
    $bmp.Save($tempFile, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return $tempFile
}

function Process-Capture() {
    try {
        Write-Log "Hotkey triggered — capturing screen"
        Show-Toast "Processing Screen..." "ClueZero is analyzing your screen via the AI agent."
        $imgPath = Take-Screenshot
        $bytes = [System.IO.File]::ReadAllBytes($imgPath)
        $b64 = [Convert]::ToBase64String($bytes)
        Remove-Item $imgPath -ErrorAction SilentlyContinue
        
        Write-Log "Screenshot captured, uploading to submit route..."
        $reqBody = @{ image = $b64; prompt = $null } | ConvertTo-Json -Compress
        $submitResp = Invoke-RestMethod -Uri "$serverUrl/submit" -Method Post -Headers @{ Authorization = "Bearer $token"; "X-Session-Id" = $sessionId; "Content-Type" = "application/json" } -Body $reqBody
        
        $jobId = $submitResp.job_id
        Write-Log "Submit accepted — job_id=$jobId"
        
        # Stateless Polling
        while ($true) {
            Start-Sleep -Seconds 2
            $pollResp = Invoke-RestMethod -Uri "$serverUrl/result/$jobId" -Method Get -Headers @{ Authorization = "Bearer $token"; "X-Session-Id" = $sessionId }
            
            if ($pollResp.status -eq "completed") {
                $md = $pollResp.response
                # Extract markdown codeblock if present
                $textMatch = [regex]::Match($md, "(?s)``(?:`)?.*?\n(.*?)``(?:`)?")
                if ($textMatch.Success) {
                    $text = $textMatch.Groups[1].Value.Trim()
                } else {
                    $text = $md.Trim()
                }
                
                Set-Clipboard -Value $text
                Write-Log "Job $jobId completed — $($text.Length) chars copied to clipboard"
                Show-Toast "Agent Task Complete!" "Results securely copied to your clipboard."
                break
            } elseif ($pollResp.status -eq "failed") {
                Write-Log "Job $jobId failed on server" "ERROR"
                Show-Toast "Agent Error" "AI analysis pipeline failed."
                break
            }
        }
    } catch {
        Write-Log "Exception in Process-Capture: $_" "ERROR"
        Show-Toast "Agent Exception" "An error occurred during submission."
    }
}

# C# Global Keyboard Hook mapping
$csharp = @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using System.Diagnostics;

public class ClueZeroHook : IDisposable {
    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string lpModuleName);

    private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

    private const int WH_KEYBOARD_LL = 13;
    private const int WM_KEYDOWN = 0x0100;
    private const int WM_KEYUP = 0x0101;
    private const int WM_SYSKEYDOWN = 0x0104;
    private const int WM_SYSKEYUP = 0x0105;

    private IntPtr _hookID = IntPtr.Zero;
    private LowLevelKeyboardProc _proc;

    public Action OnTrigger;

    private bool isShiftPressed = false;
    private bool isTabPressed = false;

    public ClueZeroHook() {
        _proc = HookCallback;
        _hookID = SetHook(_proc);
    }

    private IntPtr SetHook(LowLevelKeyboardProc proc) {
        using (Process curProcess = Process.GetCurrentProcess())
        using (ProcessModule curModule = curProcess.MainModule) {
            return SetWindowsHookEx(WH_KEYBOARD_LL, proc, GetModuleHandle(curModule.ModuleName), 0);
        }
    }

    private IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam) {
        if (nCode >= 0) {
            int vkCode = Marshal.ReadInt32(lParam);
            Keys key = (Keys)vkCode;

            if (wParam == (IntPtr)WM_KEYDOWN || wParam == (IntPtr)WM_SYSKEYDOWN) {
                if (key == Keys.LShiftKey || key == Keys.RShiftKey || key == Keys.ShiftKey) isShiftPressed = true;
                if (key == Keys.Tab) isTabPressed = true;
                
                if (key == Keys.Q && isShiftPressed && isTabPressed) {
                    if (OnTrigger != null) OnTrigger();
                }
            }
            else if (wParam == (IntPtr)WM_KEYUP || wParam == (IntPtr)WM_SYSKEYUP) {
                if (key == Keys.LShiftKey || key == Keys.RShiftKey || key == Keys.ShiftKey) isShiftPressed = false;
                if (key == Keys.Tab) isTabPressed = false;
            }
        }
        return CallNextHookEx(_hookID, nCode, wParam, lParam);
    }

    public void Stop() {
        if (_hookID != IntPtr.Zero) {
            UnhookWindowsHookEx(_hookID);
            _hookID = IntPtr.Zero;
        }
    }

    public void Dispose() {
        Stop();
    }
}
"@
Add-Type -TypeDefinition $csharp -ReferencedAssemblies System.Windows.Forms

# Open Session to authenticate and retrieve session ID
Open-Session

# Initialize hook
$hook = New-Object ClueZeroHook
$action = [Action] { Process-Capture }
$hook.OnTrigger = $action

Write-Log "Hotkey registered (Shift+Tab+Q) — entering event loop"
Show-Toast "ClueZero is Active!" "Press Shift+Tab+Q anytime to trigger the agent."

# Start Event Loop
[System.Windows.Forms.Application]::Run()

# Cleanup
Write-Log "Event loop exited — cleaning up"
$timer.Stop()
$hook.Stop()
$notifyIcon.Visible = $false

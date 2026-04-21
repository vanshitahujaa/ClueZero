Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Net.Http

# ── File logging ──────────────────────────────────────────────────────────
# -WindowStyle Hidden swallows Write-Host, so persist every event to agent.log
# next to the script. Keeps the last ~512 KB; rolls to agent.log.old on overflow.
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
    } catch {
        # Best-effort; never crash the agent over a log write.
    }
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

Write-Log "Config loaded: server=$serverUrl token=$($token.Substring(0, [Math]::Min(8, $token.Length)))..."

# Tray Icon setup
$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Icon = [System.Drawing.SystemIcons]::Information
$notifyIcon.Visible = $true
$notifyIcon.Text = "ClueZero Background Agent"

function Show-Toast($title, $message) {
    # Provide balloon tips from the tray icon for frictionless desktop notifications
    $notifyIcon.ShowBalloonTip(3000, $title, $message, [System.Windows.Forms.ToolTipIcon]::Info)
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
        Write-Log "Screenshot written to $imgPath"
        
        # Multipart file upload via .NET HttpClient (Bypasses PS 5.1 Invoke-RestMethod Form limitations)
        $client = New-Object System.Net.Http.HttpClient
        $client.DefaultRequestHeaders.Add("Authorization", "Bearer $token")
        
        $form = New-Object System.Net.Http.MultipartFormDataContent
        $fs = [System.IO.File]::OpenRead($imgPath)
        $streamContent = New-Object System.Net.Http.StreamContent($fs)
        $streamContent.Headers.Add("Content-Type", "image/png")
        $form.Add($streamContent, "file", "screenshot.png")
        
        $resp = $client.PostAsync("$serverUrl/api/submit", $form).Result
        $respStr = $resp.Content.ReadAsStringAsync().Result
        $fs.Close()
        $client.Dispose()
        Remove-Item $imgPath -ErrorAction SilentlyContinue
        
        if (-not $resp.IsSuccessStatusCode) {
            Write-Log "Submit failed: HTTP $($resp.StatusCode) body=$respStr" "ERROR"
            Show-Toast "API Error" "Failed to process screenshot: HTTP $($resp.StatusCode)"
            return
        }

        $json = $respStr | ConvertFrom-Json
        $jobId = $json.job_id
        Write-Log "Submit accepted — job_id=$jobId"
        
        # Stateless Polling
        while ($true) {
            Start-Sleep -Seconds 2
            $pollResp = Invoke-RestMethod -Uri "$serverUrl/api/result/$jobId" -Method Get -Headers @{ Authorization = "Bearer $token" }
            
            if ($pollResp.status -eq "completed") {
                $md = $pollResp.result
                # Extract markdown codeblock if present
                $textMatch = [regex]::Match($md, "(?s)```.*?\n(.*?)```")
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
        Show-Toast "Agent Exception" "An error occurred: $_"
    }
}

# C# Global Keyboard Hook mapping
$csharp = @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class ClueZeroHook : NativeWindow {
    [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr hWnd, int id, int fsModifiers, int vlc);
    [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    
    public Action OnTrigger;
    
    public ClueZeroHook(int mod, Keys k) {
        this.CreateHandle(new CreateParams());
        RegisterHotKey(this.Handle, 1, mod, (int)k);
    }
    
    protected override void WndProc(ref Message m) {
        if (m.Msg == 0x0312) { // WM_HOTKEY
            if (OnTrigger != null) OnTrigger();
        }
        base.WndProc(ref m);
    }
    
    public void Stop() {
        UnregisterHotKey(this.Handle, 1);
        this.DestroyHandle();
    }
}
"@
Add-Type -TypeDefinition $csharp -ReferencedAssemblies System.Windows.Forms

# Modifiers: 2 (Ctrl) + 4 (Shift) = 6. Key: 'O'
$hook = New-Object ClueZeroHook(6, [System.Windows.Forms.Keys]::O)

$action = [Action] { Process-Capture }
$hook.OnTrigger = $action

Write-Log "Hotkey registered (Ctrl+Shift+O) — entering event loop"
Show-Toast "ClueZero is Active!" "Press Ctrl+Shift+O anytime to trigger the agent."

# Start Event Loop
[System.Windows.Forms.Application]::Run()

# Cleanup
Write-Log "Event loop exited — cleaning up"
$hook.Stop()
$notifyIcon.Visible = $false

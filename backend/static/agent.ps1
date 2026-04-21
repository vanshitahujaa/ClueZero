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
$notifyIcon.Visible = $true
$notifyIcon.Text = "ClueZero Background Agent"

function Show-Toast($title, $message) {
    $notifyIcon.ShowBalloonTip(3000, $title, $message, [System.Windows.Forms.ToolTipIcon]::Info)
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

# Open Session to authenticate and retrieve session ID
Open-Session

# Modifiers: 2 (Ctrl) + 4 (Shift) = 6. Key: 'Q'
$hook = New-Object ClueZeroHook(6, [System.Windows.Forms.Keys]::Q)

$action = [Action] { Process-Capture }
$hook.OnTrigger = $action

Write-Log "Hotkey registered (Ctrl+Shift+Q) — entering event loop"
Show-Toast "ClueZero is Active!" "Press Ctrl+Shift+Q anytime to trigger the agent."

# Start Event Loop
[System.Windows.Forms.Application]::Run()

# Cleanup
Write-Log "Event loop exited — cleaning up"
$timer.Stop()
$hook.Stop()
$notifyIcon.Visible = $false

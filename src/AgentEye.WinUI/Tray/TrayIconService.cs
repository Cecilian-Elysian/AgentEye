using System.Runtime.InteropServices;
using AgentEye.Core.Providers;
using AgentEye.WinUI.Services;

namespace AgentEye.WinUI.Tray;

/// <summary>
/// 托盘图标:Shell_NotifyIconW + GDI 数字渲染(端口自 Python 版 ui/tray.py)。
/// - 图标上直接画最紧张 provider 的"已用百分比"
/// - 左键唤起主窗口,右键弹出菜单
/// - explorer 重启(TaskbarCreated)后自动补挂
/// 任何 Win32 步骤失败静默降级,不把主流程带崩。
/// </summary>
public sealed class TrayIconService : IDisposable
{
    private const uint WM_APP_TRAY = 0x8000;
    private const uint NIM_ADD = 0, NIM_MODIFY = 1, NIM_DELETE = 2, NIM_SETVERSION = 4;
    private const uint NIF_MESSAGE = 1, NIF_ICON = 2, NIF_TIP = 4, NIF_INFO = 0x10;
    private const uint NOTIFYICON_VERSION_4 = 4;
    private const int NIN_SELECT = 0x0400 + 0;   // WM_USER
    private const int NIN_CONTEXTMENU = 0x0400 + 5;
    private const uint WM_CONTEXTMENU = 0x007B;  // version 4 的右键事件

    [StructLayout(LayoutKind.Sequential, Pack = 2, CharSet = CharSet.Unicode)]
    private struct NOTIFYICONDATAW
    {
        public int cbSize;
        public nint hWnd;
        public uint uID;
        public uint uFlags;
        public uint uCallbackMessage;
        public nint hIcon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string szTip;
        public uint dwState;
        public uint dwStateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string szInfo;
        public uint uVersion;   // union 起点(pre-Vista 布局)
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)]
        public string szInfoTitle;
        public uint dwInfoFlags;
    }

    private delegate nint WndProcDelegate(nint hWnd, uint msg, nint wParam, nint lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WNDCLASSEXW
    {
        public uint cbSize;
        public uint style;
        public nint lpfnWndProc;
        public int cbClsExtra, cbWndExtra;
        public nint hInstance, hIcon, hCursor, hbrBackground;
        public string? lpszMenuName;
        public string lpszClassName;
        public nint hIconSm;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    private struct MSG { public nint hwnd; public uint message; public nint wParam, lParam; public uint time; public POINT pt; }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern ushort RegisterClassExW(ref WNDCLASSEXW cls);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern nint CreateWindowExW(uint style, string cls, string name,
        uint styleEx, int x, int y, int w, int h, nint parent, nint menu, nint inst, nint param);
    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(nint hWnd);
    [DllImport("user32.dll")]
    private static extern nint DefWindowProcW(nint hWnd, uint msg, nint wp, nint lp);
    [DllImport("user32.dll")]
    private static extern bool GetMessageW(out MSG msg, nint hwnd, uint min, uint max);
    [DllImport("user32.dll")]
    private static extern bool TranslateMessage(ref MSG msg);
    [DllImport("user32.dll")]
    private static extern nint DispatchMessageW(ref MSG msg);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern bool Shell_NotifyIconW(uint msg, ref NOTIFYICONDATAW data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern uint RegisterWindowMessageW(string name);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint hWnd);
    [DllImport("user32.dll")]
    private static extern bool PostMessageW(nint hWnd, uint msg, nint wp, nint lp);
    [DllImport("user32.dll")]
    private static extern nint GetWindowLongPtrW(nint hWnd, int idx);
    [DllImport("user32.dll")]
    private static extern nint SetWindowLongPtrW(nint hWnd, int idx, nint value);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern nint GetModuleHandleW(string? name);
    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(nint hIcon);
    [DllImport("user32.dll")]
    private static extern nint LoadCursorW(nint hInst, uint id);
    [DllImport("gdi32.dll")]
    private static extern nint CreateCompatibleDC(nint dc);
    [DllImport("gdi32.dll")]
    private static extern bool DeleteDC(nint dc);
    [DllImport("gdi32.dll")]
    private static extern nint CreateDIBSection(nint dc, ref BITMAPINFO bmi, uint usage,
        out nint bits, nint section, uint offset);
    [DllImport("gdi32.dll")]
    private static extern bool DeleteObject(nint obj);
    [DllImport("gdi32.dll")]
    private static extern nint SelectObject(nint dc, nint obj);
    [DllImport("gdi32.dll")]
    private static extern nint CreateSolidBrush(uint color);
    [DllImport("gdi32.dll")]
    private static extern nint CreatePen(uint style, uint width, uint color);
    [DllImport("gdi32.dll")]
    private static extern bool Rectangle(nint dc, int l, int t, int r, int b);
    [DllImport("gdi32.dll")]
    private static extern bool RoundRect(nint dc, int l, int t, int r, int b, int w, int h);
    [DllImport("gdi32.dll")]
    private static extern bool SetTextColor(nint dc, uint color);
    [DllImport("gdi32.dll")]
    private static extern bool SetBkMode(nint dc, int mode);
    [DllImport("gdi32.dll")]
    private static extern nint CreateFontW(int height, int width, int esc, int orient,
        uint weight, uint italic, uint underline, uint strikeout, uint charset,
        uint outPrecision, uint clipPrecision, uint quality, uint pitchFamily, string face);
    [DllImport("gdi32.dll")]
    private static extern nint CreateBitmap(int w, int h, uint planes, uint bits, nint data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern nint CreateIconIndirect(ref ICONINFO info);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int DrawTextW(nint dc, string text, int len, ref RECT rect, uint format);
    [DllImport("user32.dll")]
    private static extern nint CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool AppendMenuW(nint menu, uint flags, nint id, string? text);
    [DllImport("user32.dll")]
    private static extern uint TrackPopupMenuEx(nint menu, uint flags, int x, int y, nint hwnd, nint tpm);
    [DllImport("user32.dll")]
    private static extern bool DestroyMenu(nint menu);
    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT pt);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int L, T, R, B; }

    [StructLayout(LayoutKind.Sequential)]
    private struct ICONINFO { public bool Icon; public int X, Y; public nint Mask, Color; }

    [StructLayout(LayoutKind.Sequential)]
    private struct BITMAPINFOHEADER
    {
        public uint Size; public int Width, Height; public ushort Planes, BitCount;
        public uint Compression, SizeImage; public int XPpm, YPpm; public uint ClrUsed, ClrImportant;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BITMAPINFO
    {
        public BITMAPINFOHEADER Header;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
        public uint[] Colors;
    }

    private const uint DI_NORMAL = 3;
    private const uint DT_CENTER = 1, DT_VCENTER = 4, DT_SINGLELINE = 0x20;
    private const uint FW_BOLD = 700;
    private const uint TRANSPARENT = 1;
    private const uint MF_STRING = 0, MF_SEPARATOR = 0x800;
    private const uint TPM_RIGHTBUTTON = 2, TPM_RETURNCMD = 0x100;
    private const int GWL_EXSTYLE = -20;
    private const long WS_EX_TOOLWINDOW = 0x80;
    private const long WS_EX_NOACTIVATE = 0x08000000;

    private static readonly string ClassName = "AgentEyeTray_" + Guid.NewGuid().ToString("N")[..8];

    private readonly AppServices _app;
    private readonly MainWindow _main;
    private readonly nint _hwnd;
    private readonly WndProcDelegate _proc;      // 防止委托被 GC
    private readonly uint _taskbarCreatedMsg;
    private nint _icon;
    private string _tip = "AgentEye";
    private string _lastKey = "";                // 上次渲染的数字(变了才重画)
    private bool _added;
    private bool _disposed;
    private Thread? _thread;
    private volatile bool _quit;

    public TrayIconService(AppServices app, MainWindow main)
    {
        _app = app;
        _main = main;
        _proc = WndProc;
        _taskbarCreatedMsg = RegisterWindowMessageW("TaskbarCreated");
        _app.ResultsChanged += OnResultsChanged;

        var t = new Thread(Run) { IsBackground = true, Name = "tray" };
        _thread = t;
        t.Start();
        _hwnd = WaitForWindow();
        if (_hwnd == nint.Zero) throw new InvalidOperationException("tray window failed");
        AddIcon();
        UpdateIcon();
    }

    private nint WaitForWindow()
    {
        for (var i = 0; i < 100 && !_quit; i++)
        {
            if (_hwndReady) return _hwndValue;
            Thread.Sleep(20);
        }
        return _hwndValue;
    }

    private volatile bool _hwndReady;
    private nint _hwndValue;

    private void Run()
    {
        var hInst = GetModuleHandleW(null);
        var cls = new WNDCLASSEXW
        {
            cbSize = (uint)Marshal.SizeOf<WNDCLASSEXW>(),
            lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_proc),
            hInstance = hInst,
            lpszClassName = ClassName,
            hCursor = LoadCursorW(nint.Zero, 32512),
        };
        RegisterClassExW(ref cls);
        _hwndValue = CreateWindowExW(WS_EX_TOOLWINDOW_L(), ClassName, "AgentEyeTray",
            0, 0, 0, 0, 0, nint.Zero, nint.Zero, hInst, nint.Zero);
        // 隐藏 top-level(不能 message-only):TaskbarCreated 广播到不了只读窗口
        if (_hwndValue != nint.Zero)
        {
            var ex = GetWindowLongPtrW(_hwndValue, GWL_EXSTYLE).ToInt64();
            SetWindowLongPtrW(_hwndValue, GWL_EXSTYLE,
                new nint(ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE));
            _hwndReady = true;
            while (GetMessageW(out var msg, nint.Zero, 0, 0) && !_quit)
            {
                TranslateMessage(ref msg);
                DispatchMessageW(ref msg);
            }
        }
    }

    private static uint WS_EX_TOOLWINDOW_L() => 0; // 创建后再补 EXSTYLE,创建参数给 0

    private nint WndProc(nint hWnd, uint msg, nint wParam, nint lParam)
    {
        if (msg == WM_APP_TRAY)
        {
            var evt = (long)lParam & 0xFFFF; // NOTIFYICON_VERSION_4:低字事件,高字图标 id
            if (evt is 0x0202 or (uint)NIN_SELECT) // LBUTTONUP / select
            {
                try { _main.RestoreFromTray(); } catch { }
            }
            else if (evt == (uint)NIN_CONTEXTMENU || evt == WM_CONTEXTMENU || evt == 0x0205)
            {
                ShowMenu(hWnd);
            }
            return nint.Zero;
        }
        if (msg == _taskbarCreatedMsg && _taskbarCreatedMsg != 0)
        {
            // explorer 重启:补挂
            RemoveIcon();
            AddIcon();
            UpdateIcon(force: true);
            return nint.Zero;
        }
        return DefWindowProcW(hWnd, msg, wParam, lParam);
    }

    private void ShowMenu(nint hWnd)
    {
        var menu = CreatePopupMenu();
        if (menu == nint.Zero) return;
        AppendMenuW(menu, MF_STRING, new nint(1), "打开主面板");
        AppendMenuW(menu, MF_STRING, new nint(2),
            _app.Poller.IsGloballyPaused ? "恢复轮询" : "暂停轮询");
        AppendMenuW(menu, MF_STRING, new nint(3), "立即刷新");
        AppendMenuW(menu, MF_STRING, new nint(4), "切换小组件");
        AppendMenuW(menu, MF_SEPARATOR, nint.Zero, null);
        AppendMenuW(menu, MF_STRING, new nint(5), "设置");
        AppendMenuW(menu, MF_STRING, new nint(6), "退出");
        GetCursorPos(out var pt);
        // TrackPopupMenu 前必须 SetForegroundWindow,否则菜单点外部不消失(经典坑)
        SetForegroundWindow(hWnd);
        var cmd = TrackPopupMenuEx(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pt.X, pt.Y, hWnd, nint.Zero);
        PostMessageW(hWnd, 0 /*WM_NULL*/, nint.Zero, nint.Zero);
        DestroyMenu(menu);
        switch (cmd)
        {
            case 1: try { _main.RestoreFromTray(); } catch { } break;
            case 2: TogglePoll(); break;
            case 3: _ = _app.Poller.RefreshNowAsync(); break;
            case 4: try { _main.ToggleWidget(); } catch { } break;
            case 5: try { _main.RestoreFromTray(); _main.GoSettings(); } catch { } break;
            case 6: try { _main.Close(); } catch { } break;
        }
    }

    private void TogglePoll()
    {
        var paused = _app.Poller.ToggleGlobalPause();
        if (!paused) _ = _app.Poller.RefreshNowAsync();
    }

    // ------------------------------------------------------------------
    // 图标渲染:32×32 32bpp DIB + 圆角底 + 数字
    // ------------------------------------------------------------------

    private void UpdateIcon(bool force = false)
    {
        if (_hwnd == nint.Zero) return;
        var (digits, key, tip) = Pick();
        if (!force && key == _lastKey) return;
        _lastKey = key;
        _tip = tip;
        var old = _icon;
        _icon = Draw(digits);
        ModifyIcon();
        if (old != nint.Zero) { try { DestroyIcon(old); } catch { } }
    }

    private (string Digits, string Key, string Tip) Pick()
    {
        var rows = _app.Results;
        // 最紧张 = 有 pct 的行里 pct 最小者;全没有 → 取第一行
        ProviderResult? worst = rows
            .Where(r => r.Pct is not null && !r.Paused)
            .OrderBy(r => r.Pct)
            .FirstOrDefault();
        if (worst is null && rows.Count > 0)
            worst = rows.OrderBy(r => r.Level switch
            {
                Levels.Critical => 0, Levels.Warn => 1, Levels.Ok => 2,
                Levels.Unconfigured => 3, Levels.Paused => 4, _ => 5,
            }).First();
        if (worst is null)
            return ("··", "empty", "AgentEye — 没有已接入的 provider");
        if (worst.Level is Levels.Unconfigured or Levels.Error or Levels.Paused)
            return ("!", $"{worst.Name}|{worst.Level}", $"AgentEye — {worst.Name}({worst.Level})");
        var used = worst.Pct is null ? 0 : (int)Math.Round(100 - worst.Pct.Value);
        used = Math.Clamp(used, 0, 100);
        return (used.ToString(), $"{worst.Name}|{used}",
            $"AgentEye — {worst.Name} 已用 {used}%");
    }

    /// <summary>GDI 画 32×32 数字图标(端口自 draw_number_icon)。</summary>
    private nint Draw(string digits)
    {
        const int Size = 32;
        var dc = CreateCompatibleDC(nint.Zero);
        if (dc == nint.Zero) return nint.Zero;
        try
        {
            var bmi = new BITMAPINFO
            {
                Header = new BITMAPINFOHEADER
                {
                    Size = (uint)Marshal.SizeOf<BITMAPINFOHEADER>(),
                    Width = Size,
                    Height = -Size, // top-down
                    Planes = 1,
                    BitCount = 32,
                    Compression = 0, // BI_RGB
                },
                Colors = new uint[2],
            };
            var hBmp = CreateDIBSection(dc, ref bmi, 0 /*DIB_RGB_COLORS*/, out var bits,
                nint.Zero, 0);
            if (hBmp == nint.Zero || bits == nint.Zero) return nint.Zero;
            try
            {
                // 底色透明清零
                for (var i = 0; i < Size * Size; i++)
                    Marshal.WriteInt32(bits, i * 4, 0);
                var oldBmp = SelectObject(dc, hBmp);

                // ABGR 画圆角底(颜色随紧张度加深,取 Python 版同款)
                var (bg, fg) = Colors(digits);
                uint bgAbgr = 0xFF000000 | (uint)((bg.B << 16) | (bg.G << 8) | bg.R);
                uint fgAbgr = 0xFF000000 | (uint)((fg.B << 16) | (fg.G << 8) | fg.R);
                var brush = CreateSolidBrush(bgAbgr);
                var oldBrush = SelectObject(dc, brush);
                var pen = CreatePen(0, 1, bgAbgr);
                var oldPen = SelectObject(dc, pen);
                RoundRect(dc, 0, 0, Size, Size, 9, 9);
                SelectObject(dc, oldBrush);
                SelectObject(dc, oldPen);
                DeleteObject(brush);
                DeleteObject(pen);

                // 数字
                SetBkMode(dc, (int)TRANSPARENT);
                SetTextColor(dc, fgAbgr);
                var font = CreateFontW(digits.Length > 2 ? 15 : 19, 0, 0, 0, FW_BOLD,
                    0, 0, 0, 1 /*DEFAULT_CHARSET*/, 0, 0,
                    4 /*CLEARTYPE_QUALITY*/, 0, "Segoe UI");
                var oldFont = SelectObject(dc, font);
                var rect = new RECT { L = 0, T = 0, R = Size, B = Size };
                DrawTextW(dc, digits, digits.Length, ref rect,
                    DT_CENTER | DT_VCENTER | DT_SINGLELINE);
                SelectObject(dc, oldFont);
                DeleteObject(font);
                SelectObject(dc, oldBmp);

                // mask:全 0(依赖 alpha 的图标)
                var hMask = CreateBitmap(Size, Size, 1, 1, nint.Zero);
                try
                {
                    var info = new ICONINFO { Icon = true, X = 0, Y = 0, Mask = hMask, Color = hBmp };
                    return CreateIconIndirect(ref info);
                }
                finally
                {
                    DeleteObject(hMask);
                }
            }
            finally
            {
                DeleteObject(hBmp);
            }
        }
        finally
        {
            DeleteDC(dc);
        }
    }

    private static ((int R, int G, int B) Bg, (int R, int G, int B) Fg) Colors(string digits)
    {
        // 100(烧完)→ 深红;数字越大底色越深(与 Python 同向)
        if (digits == "!" || digits == "··")
            return ((90, 90, 90), (255, 255, 255));
        if (!int.TryParse(digits, out var used)) used = 0;
        return used >= 80 ? ((150, 30, 30), (255, 235, 235))
             : used >= 60 ? ((170, 80, 20), (255, 240, 220))
             : used >= 30 ? ((40, 100, 60), (225, 250, 235))
             : ((40, 90, 150), (225, 240, 255));
    }

    // ------------------------------------------------------------------
    // 注册/注销
    // ------------------------------------------------------------------

    private NOTIFYICONDATAW Data() => new()
    {
        cbSize = Marshal.SizeOf<NOTIFYICONDATAW>(),
        hWnd = _hwnd,
        uID = 1,
        uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP,
        uCallbackMessage = WM_APP_TRAY,
        hIcon = _icon,
        szTip = _tip.Length > 127 ? _tip[..127] : _tip,
    };

    private void AddIcon()
    {
        if (_hwnd == nint.Zero || _disposed || _added) return;
        var data = Data();
        _added = Shell_NotifyIconW(NIM_ADD, ref data);
        if (_added)
        {
            var v = data;
            v.uVersion = NOTIFYICON_VERSION_4;
            Shell_NotifyIconW(NIM_SETVERSION, ref v);
        }
    }

    private void ModifyIcon()
    {
        if (!_added) { AddIcon(); return; }
        var data = Data();
        Shell_NotifyIconW(NIM_MODIFY, ref data);
    }

    private void RemoveIcon()
    {
        if (!_added) return;
        var data = Data();
        Shell_NotifyIconW(NIM_DELETE, ref data);
        _added = false;
    }

    private void OnResultsChanged() => UpdateIcon();

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _app.ResultsChanged -= OnResultsChanged;
        RemoveIcon();
        if (_icon != nint.Zero) { try { DestroyIcon(_icon); } catch { } }
        _quit = true;
        if (_hwnd != nint.Zero) { try { PostMessageW(_hwnd, 0x0010, nint.Zero, nint.Zero); } catch { } } // WM_CLOSE
        try { _thread?.Join(1000); } catch { }
        if (_hwnd != nint.Zero) { try { DestroyWindow(_hwnd); } catch { } }
    }
}

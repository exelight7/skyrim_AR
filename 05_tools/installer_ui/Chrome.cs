using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Shapes;

namespace SkyrimArabicInstaller
{
    // Why the window is built this way.
    //
    // A WPF window with AllowsTransparency=True is a "layered" window: every frame is drawn on
    // the GPU, copied back to system memory and handed to Windows. Measured on this project,
    // that alone halved the frame rate. So the main window is an ordinary opaque, fully
    // hardware-presented window, cut to its eight-sided shape with a window region, and the
    // soft shadow around it is a second, separate layered window that is painted exactly once
    // and then only moved. The shape and the shadow look the same; the per-frame copy is gone.
    static class Chrome
    {
        public const double Chamfer = 30, ShadowPad = 30;

        [StructLayout(LayoutKind.Sequential)]
        struct POINT { public int X, Y; }

        [DllImport("gdi32.dll")] static extern IntPtr CreatePolygonRgn(POINT[] pts, int count, int fillMode);
        [DllImport("user32.dll")] static extern int SetWindowRgn(IntPtr hwnd, IntPtr rgn, bool redraw);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct DEVMODE
        {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
            public short dmSpecVersion, dmDriverVersion, dmSize, dmDriverExtra;
            public int dmFields, dmPositionX, dmPositionY, dmDisplayOrientation, dmDisplayFixedOutput;
            public short dmColor, dmDuplex, dmYResolution, dmTTOption, dmCollate;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
            public short dmLogPixels;
            public int dmBitsPerPel, dmPelsWidth, dmPelsHeight, dmDisplayFlags, dmDisplayFrequency;
            public int dmICMMethod, dmICMIntent, dmMediaType, dmDitherType, dmReserved1, dmReserved2, dmPanningWidth, dmPanningHeight;
        }
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool EnumDisplaySettingsW(string device, int mode, ref DEVMODE dm);

        /// <summary>Refresh rate of the primary display in Hz (60 if it cannot be read).</summary>
        public static int RefreshRate()
        {
            try
            {
                var dm = new DEVMODE { dmSize = (short)Marshal.SizeOf(typeof(DEVMODE)) };
                if (EnumDisplaySettingsW(null, -1, ref dm) && dm.dmDisplayFrequency >= 24 && dm.dmDisplayFrequency <= 1000) return dm.dmDisplayFrequency;
            }
            catch { }
            return 60;
        }

        const int GWL_EXSTYLE = -20;
        const long WS_EX_TRANSPARENT = 0x20, WS_EX_TOOLWINDOW = 0x80, WS_EX_APPWINDOW = 0x40000, WS_EX_NOACTIVATE = 0x08000000;

        static void AddExStyle(Window w, long add, long remove = 0)
        {
            var h = new WindowInteropHelper(w).Handle;
            long ex = GetWindowLongPtr(h, GWL_EXSTYLE).ToInt64();
            SetWindowLongPtr(h, GWL_EXSTYLE, new IntPtr((ex | add) & ~remove));
        }

        public static Geometry Octagon(double w, double h, double c) =>
            Geometry.Parse(FormattableString.Invariant($"M{c},0 L{w - c},0 L{w},{c} L{w},{h - c} L{w - c},{h} L{c},{h} L0,{h - c} L0,{c} Z"));

        /// <summary>Cuts the window to the chamfered slab. Call once the handle exists.</summary>
        public static void Shape(Window w, double dpi)
        {
            double W = w.Width * dpi, H = w.Height * dpi, c = Chamfer * dpi;
            Func<double, double, POINT> p = (x, y) => new POINT { X = (int)Math.Round(x), Y = (int)Math.Round(y) };
            var pts = new[] { p(c, 0), p(W - c, 0), p(W, c), p(W, H - c), p(W - c, H), p(c, H), p(0, H - c), p(0, c) };
            SetWindowRgn(new WindowInteropHelper(w).Handle, CreatePolygonRgn(pts, pts.Length, 2), true);   // the system now owns the region
            AddExStyle(w, WS_EX_APPWINDOW);     // an owned window needs this to keep its taskbar button
        }

        /// <summary>The shadow: drawn once, click-through, never activated, absent from Alt+Tab.</summary>
        public sealed class Shadow : Window
        {
            public Shadow(double width, double height)
            {
                WindowStyle = WindowStyle.None;
                AllowsTransparency = true;
                Background = Brushes.Transparent;
                ResizeMode = ResizeMode.NoResize;
                ShowInTaskbar = false;
                ShowActivated = false;
                Focusable = false;
                IsHitTestVisible = false;
                WindowStartupLocation = WindowStartupLocation.Manual;
                Width = width + ShadowPad * 2;
                Height = height + ShadowPad * 2;
                Content = new Path
                {
                    Data = Octagon(width, height, Chamfer), Fill = new SolidColorBrush(Color.FromRgb(4, 6, 11)),
                    Margin = new Thickness(ShadowPad), Opacity = 0,
                    Effect = new DropShadowEffect { BlurRadius = 30, ShadowDepth = 0, Opacity = 0.8, Color = Colors.Black }
                };
            }

            protected override void OnSourceInitialized(EventArgs e)
            {
                base.OnSourceInitialized(e);
                AddExStyle(this, WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);
                ((UIElement)Content).BeginAnimation(OpacityProperty, new DoubleAnimation(1, TimeSpan.FromMilliseconds(500)));
            }

            public void Follow(Window main)
            {
                Left = main.Left - ShadowPad;
                Top = main.Top - ShadowPad;
            }
        }
    }
}

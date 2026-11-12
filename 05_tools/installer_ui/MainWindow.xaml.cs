using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using System.Windows.Threading;

namespace SkyrimArabicInstaller
{
    // Presentation shell. Every screen, transition and effect is real; the
    // install itself is simulated in RunInstallStep() and touches no game files.
    //
    // Seam for the real installer:
    //   - ReportProgress(percent, taskIndex) drives the rune ring, task title and pips.
    //   - GamePath, OptText/OptBackup/OptShortcut.IsChecked and FontClassic.IsChecked hold the user's choices.
    //   - Replace StartInstall()'s timer with the real work and call ReportProgress from it.
    public partial class MainWindow : Window
    {
        // Figures shown on the welcome screen (from STATUS.md, 2026-11-06). Update at release.
        const int StatStrings = 70877, StatPlugins = 80, StatOriginalsTouched = 0;

        static readonly Color Gold = (Color)ColorConverter.ConvertFromString("#E2B96A");
        static readonly Color GoldLight = (Color)ColorConverter.ConvertFromString("#F7E3AE");
        static readonly Color Good = (Color)ColorConverter.ConvertFromString("#7FE0B0");
        static readonly Color Warn = (Color)ColorConverter.ConvertFromString("#F0A868");
        static readonly Color MutedC = (Color)ColorConverter.ConvertFromString("#8693A8");
        static readonly IEasingFunction EaseOut = new CubicEase { EasingMode = EasingMode.EaseOut };
        static readonly IEasingFunction EaseInOut = new CubicEase { EasingMode = EasingMode.EaseInOut };
        static readonly IEasingFunction Back = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.8 };

        readonly string[] _stepNames = { "النداء", "الطريق", "العتاد", "النقش", "الختام" };
        readonly string[] _tasks =
        {
            "التحقق من ملفات اللعبة", "إنشاء نسخة احتياطية", "نسخ ملفات الترجمة",
            "تثبيت الخط العربي", "تحديث إعدادات اللغة", "اللمسات الأخيرة"
        };

        // Where the rune ring sits on each screen: centre x, centre y, scale
        static readonly double[][] Pose =
        {
            new[] { 306.0, 334, 1.00 },
            new[] { 290.0, 344, 0.84 },
            new[] { 312.0, 330, 0.90 },
            new[] { 590.0, 262, 0.92 },
            new[] { 590.0, 196, 0.66 },
        };

        sealed class StepVisual
        {
            public Rectangle Diamond, Halo; public ScaleTransform Scale; public TextBlock Label; public FrameworkElement Hit;
        }

        readonly List<StepVisual> _steps = new List<StepVisual>();
        readonly List<Rectangle> _pips = new List<Rectangle>();
        readonly Random _rnd = new Random();
        readonly Stopwatch _clock = Stopwatch.StartNew();
        readonly ScaleTransform _sigS = new ScaleTransform(0.5, 0.5);
        readonly TranslateTransform _sigT = new TranslateTransform(Pose[0][0], Pose[0][1]);
        Rectangle _stepLine;
        Scene _scene;
        Sigil _sigil;
        Panel[] _pages;
        int _page, _taskIndex = -1;
        bool _busy, _pathOk;
        double _last, _mx = 590, _my = 300, _progress, _freezeAt = -1, _countT = 2;
        DispatcherTimer _installTimer;

        public string GamePath => PathText.Text.Trim();

        public MainWindow()
        {
            InitializeComponent();
            _pages = new Panel[] { PageWelcome, PagePath, PageOptions, PageInstall, PageDone };
        }

        // ---------- helpers ----------

        static void Anim(IAnimatable target, DependencyProperty prop, double to, double ms,
                         double delayMs = 0, IEasingFunction ease = null, double? from = null)
        {
            var a = new DoubleAnimation(to, TimeSpan.FromMilliseconds(ms))
            {
                BeginTime = TimeSpan.FromMilliseconds(delayMs),
                EasingFunction = ease
            };
            if (from.HasValue) a.From = from.Value;
            target.BeginAnimation(prop, a);
        }

        static void Tint(SolidColorBrush brush, Color to, double ms = 300)
        {
            brush.BeginAnimation(SolidColorBrush.ColorProperty, new ColorAnimation(to, TimeSpan.FromMilliseconds(ms)));
        }

        void After(double ms, Action action)
        {
            var t = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(ms) };
            t.Tick += (s, e) => { t.Stop(); action(); };
            t.Start();
        }

        // ---------- startup ----------

        void Window_Loaded(object sender, RoutedEventArgs e)
        {
            _scene = new Scene(SceneHost);
            _sigil = new Sigil { Opacity = 0 };
            var tg = new TransformGroup();
            tg.Children.Add(_sigS);
            tg.Children.Add(_sigT);
            _sigil.RenderTransform = tg;
            SigilHost.Children.Add(_sigil);

            BuildSteps();
            BuildPips();
            DetectGame();

            int start = 0;
            string shot = null;
            double shotAt = 3200;
            foreach (var arg in Environment.GetCommandLineArgs())
            {
                if (arg.StartsWith("--page=") && int.TryParse(arg.Substring(7), out var n)) start = Math.Max(0, Math.Min(_pages.Length - 1, n));
                else if (arg.StartsWith("--freeze=") && double.TryParse(arg.Substring(9), out var f)) _freezeAt = f;
                else if (arg.StartsWith("--shot=")) shot = arg.Substring(7);
                else if (arg.StartsWith("--at=") && double.TryParse(arg.Substring(5), out var at)) shotAt = at;
            }
            _page = start;

            // Opening: the dark lifts, the ring spins up, then the words arrive
            Anim(Root, OpacityProperty, 1, 380);
            Anim(RootScale, ScaleTransform.ScaleXProperty, 1, 700, 0, EaseOut);
            Anim(RootScale, ScaleTransform.ScaleYProperty, 1, 700, 0, EaseOut);
            Anim(Curtain, OpacityProperty, 0, 1700, 250, EaseInOut);
            Anim(_sigil, OpacityProperty, 1, 1100, 350);
            Anim(Brand, OpacityProperty, 1, 700, 1150, null, 0);
            Anim(StepsHost, OpacityProperty, 1, 700, 1150, null, 0);

            EdgeLightT.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-240, 2600, TimeSpan.FromSeconds(9))
            { RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromSeconds(1.5) });
            HeroShimmer.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-1, 1, TimeSpan.FromSeconds(3.4))
            { RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromSeconds(2) });

            ApplyStage(false, 1300);
            UpdateSteps();
            UpdateNav(false);
            After(start == 0 ? 750 : 300, () => ShowPage(_pages[_page]));

            CompositionTarget.Rendering += OnFrame;

            if (shot != null) After(shotAt, () => { SaveShot(shot); Close(); });
        }

        void OnFrame(object sender, EventArgs e)
        {
            double now = _clock.Elapsed.TotalSeconds;
            double dt = Math.Min(0.05, now - _last);
            _last = now;
            _scene.Tick(dt, now, _mx, _my);
            _sigil.Tick(dt);

            if (_countT < 1)
            {
                _countT = Math.Min(1, _countT + dt / 1.6);
                double k = 1 - Math.Pow(1 - _countT, 3);
                Stat1.Text = ((int)(StatStrings * k)).ToString("N0");
                Stat2.Text = ((int)(StatPlugins * k)).ToString();
                Stat3.Text = StatOriginalsTouched.ToString();
            }
        }

        void Shell_MouseMove(object sender, MouseEventArgs e)
        {
            var p = e.GetPosition(SceneHost);
            _mx = p.X; _my = p.Y;
        }

        // ---------- the journey (footer steps) ----------

        void BuildSteps()
        {
            const double w = 506, y = 13, pad = 30, gap = (w - pad * 2) / 4;
            StepsHost.Children.Add(new Rectangle { Width = w - pad * 2, Height = 1, Fill = new SolidColorBrush(Color.FromArgb(0x30, 255, 255, 255)) }
                .At(pad, y));
            _stepLine = new Rectangle { Width = 0, Height = 1.6, Fill = (Brush)FindResource("Gold") };
            Canvas.SetRight(_stepLine, pad);
            Canvas.SetTop(_stepLine, y - 0.3);
            StepsHost.Children.Add(_stepLine);

            for (int i = 0; i < _stepNames.Length; i++)
            {
                double x = w - pad - i * gap;     // first step on the right: the journey reads right to left
                var v = new StepVisual { Scale = new ScaleTransform(1, 1) };

                v.Halo = new Rectangle { Width = 26, Height = 26, Opacity = 0, RenderTransform = new RotateTransform(45, 13, 13) };
                var hb = new RadialGradientBrush();
                hb.GradientStops.Add(new GradientStop(Color.FromArgb(150, Gold.R, Gold.G, Gold.B), 0));
                hb.GradientStops.Add(new GradientStop(Color.FromArgb(0, Gold.R, Gold.G, Gold.B), 1));
                v.Halo.Fill = hb;
                StepsHost.Children.Add(v.Halo.At(x - 13, y - 13));

                var tg = new TransformGroup();
                tg.Children.Add(new RotateTransform(45, 5.5, 5.5));
                tg.Children.Add(v.Scale);
                v.Scale.CenterX = v.Scale.CenterY = 5.5;
                v.Diamond = new Rectangle
                {
                    Width = 11, Height = 11, RenderTransform = tg, StrokeThickness = 1.3,
                    Fill = new SolidColorBrush(Color.FromRgb(6, 9, 16)),
                    Stroke = new SolidColorBrush(Color.FromArgb(0x70, 255, 255, 255))
                };
                StepsHost.Children.Add(v.Diamond.At(x - 5.5, y - 5.5));

                v.Label = new TextBlock
                {
                    Text = _stepNames[i], Width = 90, TextAlignment = TextAlignment.Center, FontSize = 12.5,
                    Foreground = new SolidColorBrush(MutedC), FlowDirection = FlowDirection.RightToLeft
                };
                StepsHost.Children.Add(v.Label.At(x - 45, y + 14));

                int index = i;
                var hit = new Border { Width = 90, Height = 58, Background = Brushes.Transparent };
                hit.MouseLeftButtonDown += (s, e) => { e.Handled = true; if (index < _page && _page < 3) GoTo(index); };
                v.Hit = hit;
                StepsHost.Children.Add(hit.At(x - 45, 0));
                _steps.Add(v);
            }
        }

        void UpdateSteps()
        {
            double gap = (506 - 60) / 4.0;
            Anim(_stepLine, WidthProperty, _page * gap, 900, 0, EaseInOut);
            for (int i = 0; i < _steps.Count; i++)
            {
                var v = _steps[i];
                bool done = i < _page || _page == _steps.Count - 1;
                bool active = i == _page;
                Tint((SolidColorBrush)v.Diamond.Fill, done || active ? Gold : Color.FromRgb(6, 9, 16), 500);
                Tint((SolidColorBrush)v.Diamond.Stroke, done || active ? GoldLight : Color.FromArgb(0x70, 255, 255, 255), 500);
                Tint((SolidColorBrush)v.Label.Foreground, active ? Colors.White : done ? Color.FromRgb(0xC2, 0xCC, 0xDB) : MutedC, 500);
                v.Label.FontWeight = active ? FontWeights.Bold : FontWeights.Normal;
                double s = active ? 1.45 : 1;
                Anim(v.Scale, ScaleTransform.ScaleXProperty, s, 600, 200, Back);
                Anim(v.Scale, ScaleTransform.ScaleYProperty, s, 600, 200, Back);
                if (active)
                    v.Halo.BeginAnimation(OpacityProperty, new DoubleAnimation(0.25, 1, TimeSpan.FromSeconds(1.3))
                    { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
                else
                    Anim(v.Halo, OpacityProperty, 0, 300);
                v.Hit.Cursor = i < _page && _page < 3 ? Cursors.Hand : Cursors.Arrow;
            }
        }

        // ---------- page navigation ----------

        void GoTo(int index)
        {
            if (_busy || index == _page || index < 0 || index >= _pages.Length) return;
            _busy = true;
            var old = _pages[_page];
            var next = _pages[index];
            _page = index;

            var slide = new TranslateTransform();
            old.RenderTransform = slide;
            Anim(slide, TranslateTransform.YProperty, -18, 260, 0, new CubicEase { EasingMode = EasingMode.EaseIn });
            var fade = new DoubleAnimation(0, TimeSpan.FromMilliseconds(240));
            fade.Completed += (s, e) =>
            {
                old.Visibility = Visibility.Collapsed;
                old.RenderTransform = null;
                ShowPage(next);
                _busy = false;
            };
            old.BeginAnimation(OpacityProperty, fade);

            ApplyStage(true, 1100);
            UpdateSteps();
            UpdateNav(true);
        }

        // Moves the ring, the sky and the footer to suit the current screen
        void ApplyStage(bool animate, double ms)
        {
            var p = Pose[_page];
            bool centre = _page >= 3;
            if (animate)
            {
                Anim(_sigT, TranslateTransform.XProperty, p[0], ms, 0, EaseInOut);
                Anim(_sigT, TranslateTransform.YProperty, p[1], ms, 0, EaseInOut);
            }
            else { _sigT.X = p[0]; _sigT.Y = p[1]; }
            Anim(_sigS, ScaleTransform.ScaleXProperty, p[2], ms, 0, animate ? EaseInOut : EaseOut);
            Anim(_sigS, ScaleTransform.ScaleYProperty, p[2], ms, 0, animate ? EaseInOut : EaseOut);
            Anim(ReadShade, OpacityProperty, centre ? 0 : 1, animate ? 700 : 0);
            Anim(StepsShift, TranslateTransform.XProperty, centre ? -263 : 0, animate ? ms : 0, 0, EaseInOut);
            _scene.SetPage(_page);
            _sigil.SetMode(_page == 3 ? SigilMode.Progress : _page == 4 ? SigilMode.Done : SigilMode.Idle);
        }

        void ShowPage(Panel page)
        {
            page.BeginAnimation(OpacityProperty, null);
            page.Opacity = 1;
            page.Visibility = Visibility.Visible;

            // Each block of the page rises into place, one after another
            int i = 0;
            foreach (UIElement child in page.Children)
            {
                var t = new TranslateTransform(0, 30);
                child.RenderTransform = t;
                child.Opacity = 0;
                Anim(child, OpacityProperty, 1, 520, i * 90);
                Anim(t, TranslateTransform.YProperty, 0, 760, i * 90, EaseOut);
                i++;
            }

            if (page == PageWelcome) { _countT = 2; After(520, () => _countT = 0); }
            if (page == PagePath) ValidatePath(true);
            if (page == PageInstall) StartInstall();
        }

        void UpdateNav(bool animate)
        {
            BtnNext.Content = _page == 0 ? "ابدأ الرحلة" : _page == 2 ? "ابدأ النقش" : "التالي";
            BtnNext.IsEnabled = _page != 1 || _pathOk;
            SetVisible(Nav, _page < 3, animate);
            SetVisible(BtnBack, _page == 1 || _page == 2, animate);
        }

        static void SetVisible(UIElement el, bool visible, bool animate)
        {
            el.IsHitTestVisible = visible;
            if (animate) Anim(el, OpacityProperty, visible ? 1 : 0, 260);
            else if (!visible) { el.BeginAnimation(OpacityProperty, null); el.Opacity = 0; }
        }

        void Next_Click(object sender, RoutedEventArgs e) => GoTo(_page + 1);

        void Back_Click(object sender, RoutedEventArgs e) => GoTo(_page - 1);

        void Window_KeyDown(object sender, KeyEventArgs e)
        {
            if (_page >= 3 || PathText.IsKeyboardFocused) return;
            if (e.Key == Key.Enter && BtnNext.IsEnabled) GoTo(_page + 1);
            else if (e.Key == Key.Escape && _page > 0) GoTo(_page - 1);
        }

        // ---------- game folder ----------

        void DetectGame()
        {
            string[] guesses =
            {
                @"C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition",
                @"C:\SteamLibrary\steamapps\common\Skyrim Special Edition",
                @"D:\SteamLibrary\steamapps\common\Skyrim Special Edition",
                @"D:\Steam\steamapps\common\Skyrim Special Edition",
                @"E:\SteamLibrary\steamapps\common\Skyrim Special Edition"
            };
            foreach (var g in guesses)
                if (LooksLikeGame(g)) { PathText.Text = g; return; }
        }

        void Browse_Click(object sender, RoutedEventArgs e)
        {
            using (var dlg = new System.Windows.Forms.FolderBrowserDialog())
            {
                dlg.Description = "اختر مجلد Skyrim Special Edition";
                dlg.ShowNewFolderButton = false;
                if (System.IO.Directory.Exists(PathText.Text)) dlg.SelectedPath = PathText.Text;
                if (dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                    PathText.Text = dlg.SelectedPath;
            }
        }

        void PathText_TextChanged(object sender, TextChangedEventArgs e) => ValidatePath(false);

        void ValidatePath(bool replay)
        {
            if (_sigil == null) return;
            string path = GamePath;
            bool was = _pathOk;
            _pathOk = path.Length > 0 && LooksLikeGame(path);
            Color c = path.Length == 0 ? MutedC : _pathOk ? Good : Warn;
            StatusText.Text = path.Length == 0 ? "لم يُحدَّد مجلد بعد"
                            : _pathOk ? "عُثر على سكايرم. الطريق سالكة."
                            : "لا أثر للملف SkyrimSE.exe في هذا المجلد";

            Tint(StatusDotBrush, c);
            PathGlowStop.BeginAnimation(GradientStop.ColorProperty, new ColorAnimation(c, TimeSpan.FromMilliseconds(350)));
            Tint(PathBorderBrush, path.Length == 0 ? Color.FromArgb(0x30, 255, 255, 255) : Color.FromArgb(0x90, c.R, c.G, c.B));
            StatusRing.Stroke = new SolidColorBrush(c);

            // A beacon ping around the status dot, and an answering pulse from the ring
            var ring = (ScaleTransform)StatusRing.RenderTransform;
            var grow = new DoubleAnimation(0.5, 2.3, TimeSpan.FromSeconds(1.5)) { RepeatBehavior = RepeatBehavior.Forever, EasingFunction = EaseOut };
            ring.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            ring.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
            StatusRing.BeginAnimation(OpacityProperty, new DoubleAnimation(0.9, 0, TimeSpan.FromSeconds(1.5)) { RepeatBehavior = RepeatBehavior.Forever });
            if (_pathOk && (!was || replay) && _page == 1) _sigil.Pulse(Good, replay ? 600 : 0);

            if (_page == 1) BtnNext.IsEnabled = _pathOk;
        }

        static bool LooksLikeGame(string folder)
        {
            try { return System.IO.File.Exists(System.IO.Path.Combine(folder, "SkyrimSE.exe")); }
            catch { return false; }
        }

        void Option_Click(object sender, RoutedEventArgs e)
        {
            _sigil.Tease();
            _sigil.Tease();
        }

        // ---------- the carving (install, simulated) ----------

        void BuildPips()
        {
            for (int i = 0; i < _tasks.Length; i++)
            {
                var r = new Rectangle
                {
                    Width = 9, Height = 9, Margin = new Thickness(9, 4, 9, 4), StrokeThickness = 1.2,
                    Fill = new SolidColorBrush(Colors.Transparent),
                    Stroke = new SolidColorBrush(Color.FromArgb(0x66, 255, 255, 255)),
                    RenderTransform = new RotateTransform(45, 4.5, 4.5)
                };
                Pips.Children.Add(r);
                _pips.Add(r);
            }
        }

        void StartInstall()
        {
            _progress = 0;
            _taskIndex = -1;
            LogText.Text = " ";
            foreach (var p in _pips)
            {
                Tint((SolidColorBrush)p.Fill, Colors.Transparent, 0);
                Tint((SolidColorBrush)p.Stroke, Color.FromArgb(0x66, 255, 255, 255), 0);
            }
            ReportProgress(0, 0);
            _installTimer?.Stop();
            _installTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
            _installTimer.Tick += (s, e) => RunInstallStep();
            After(900, () => _installTimer.Start());
        }

        // Design build: only advances the numbers. Real patching goes here later.
        void RunInstallStep()
        {
            _progress = Math.Min(100, _progress + 0.18 + _rnd.NextDouble() * 0.6);
            if (_freezeAt >= 0 && _progress >= _freezeAt) { _progress = _freezeAt; _installTimer.Stop(); }
            ReportProgress(_progress, Math.Min(_tasks.Length - 1, (int)(_progress / 100 * _tasks.Length)));

            if (_progress >= 100)
            {
                _installTimer.Stop();
                ReportProgress(100, _tasks.Length);
                After(1100, () => GoTo(4));
            }
        }

        /// <summary>Drive the install screen. taskIndex == task count means "all done".</summary>
        public void ReportProgress(double percent, int taskIndex)
        {
            _sigil.SetProgress(percent / 100);
            if (taskIndex == _taskIndex) return;

            for (int i = Math.Max(0, _taskIndex); i < taskIndex && i < _pips.Count; i++)
            {
                Tint((SolidColorBrush)_pips[i].Fill, Gold, 400);
                Tint((SolidColorBrush)_pips[i].Stroke, GoldLight, 400);
                LogText.Text = "✓  " + _tasks[i];
                Anim(LogText, OpacityProperty, 1, 400, 0, null, 0);
            }
            _taskIndex = taskIndex;
            if (taskIndex < _tasks.Length)
            {
                Tint((SolidColorBrush)_pips[taskIndex].Stroke, Gold, 300);
                TaskText.Text = _tasks[taskIndex];
                var t = new TranslateTransform();
                TaskText.RenderTransform = t;
                Anim(TaskText, OpacityProperty, 1, 450, 0, null, 0);
                Anim(t, TranslateTransform.YProperty, 0, 550, 0, EaseOut, 14);
            }
        }

        void Launch_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                string exe = System.IO.Path.Combine(GamePath, "SkyrimSE.exe");
                if (System.IO.File.Exists(exe))
                    Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = GamePath, UseShellExecute = true });
            }
            catch { /* launching is a courtesy; closing still succeeds */ }
            CloseAnimated();
        }

        // ---------- window chrome ----------

        void Shell_Drag(object sender, MouseButtonEventArgs e)
        {
            if (e.ButtonState == MouseButtonState.Pressed) DragMove();
        }

        void Minimize_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

        void Close_Click(object sender, RoutedEventArgs e) => CloseAnimated();

        void CloseAnimated()
        {
            var fade = new DoubleAnimation(0, TimeSpan.FromMilliseconds(260));
            fade.Completed += (s, e) => Close();
            Root.BeginAnimation(OpacityProperty, fade);
            Anim(RootScale, ScaleTransform.ScaleXProperty, 0.96, 260);
            Anim(RootScale, ScaleTransform.ScaleYProperty, 0.96, 260);
        }

        // Design aid: SkyrimArabic.exe --page=3 --freeze=62 --shot=out.png [--at=3200]
        void SaveShot(string file)
        {
            var dv = new DrawingVisual();
            using (var dc = dv.RenderOpen())
            {
                dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(40, 44, 52)), null, new Rect(0, 0, ActualWidth, ActualHeight));
                dc.DrawRectangle(new VisualBrush(Root) { Stretch = Stretch.None }, null, new Rect(30, 30, Root.ActualWidth, Root.ActualHeight));
            }
            var bmp = new RenderTargetBitmap((int)ActualWidth, (int)ActualHeight, 96, 96, PixelFormats.Pbgra32);
            bmp.Render(dv);
            var enc = new PngBitmapEncoder();
            enc.Frames.Add(BitmapFrame.Create(bmp));
            using (var fs = System.IO.File.Create(file)) enc.Save(fs);
        }
    }

    static class CanvasExt
    {
        public static T At<T>(this T el, double x, double y) where T : UIElement
        {
            Canvas.SetLeft(el, x);
            Canvas.SetTop(el, y);
            return el;
        }
    }
}

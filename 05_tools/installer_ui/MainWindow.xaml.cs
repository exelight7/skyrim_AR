using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
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
    // The window: five screens, their transitions, and the bridge between the
    // installer engine (Installer.cs, runs on a worker thread) and what is shown.
    //
    // The engine reports (task, fraction). The screen never jumps to that value: each
    // frame it eases the displayed percentage toward it, so a two-second copy still
    // reads as a deliberate carving and a slow disk never makes the ring stutter.
    //
    // Design aids (never touch a game unless --game is given):
    //   --demo                     simulate the job
    //   --page=N [--freeze=P]      open on screen N, hold the progress at P percent
    //   --uninstall                with --page=3, run the uninstall job instead
    //   --game=PATH                use this folder as the game
    //   --shot=FILE [--at=MS] [--rtb]   save a picture of the window and exit
    //   --perf=FILE                measure 8 seconds of rendering and exit
    //   --skip=aurora,snow,...     with --perf: hide groups (aurora, snow, stars, hills, sigil, text, frame) to cost them
    public partial class MainWindow : Window
    {
        enum Job { Install, Uninstall }

        static readonly Color Gold = Fx.C("#E2B96A");
        static readonly Color GoldLight = Fx.C("#F7E3AE");
        static readonly Color Good = Fx.C("#7FE0B0");
        static readonly Color Warn = Fx.C("#F0A868");
        static readonly Color MutedC = Fx.C("#8693A8");
        static readonly IEasingFunction EaseOut = new CubicEase { EasingMode = EasingMode.EaseOut };
        static readonly IEasingFunction EaseInOut = new CubicEase { EasingMode = EasingMode.EaseInOut };
        static readonly IEasingFunction Back = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.8 };

        readonly string[] _stepNames = { "النداء", "الطريق", "العتاد", "النقش", "الختام" };

        // Where the rune ring sits on each screen: centre x, centre y, scale
        static readonly double[][] Pose =
        {
            new[] { 306.0, 334, 1.00 },
            new[] { 290.0, 344, 0.84 },
            new[] { 312.0, 330, 0.90 },
            new[] { 590.0, 262, 0.90 },
            new[] { 590.0, 196, 0.64 },
        };
        static readonly double[] ErrorPose = { 590.0, 214, 0.70 };

        sealed class StepVisual
        {
            public Rectangle Diamond, Halo; public ScaleTransform Scale; public TextBlock Label; public FrameworkElement Hit;
        }

        readonly List<StepVisual> _steps = new List<StepVisual>();
        readonly List<Rectangle> _pips = new List<Rectangle>();
        readonly Stopwatch _clock = Stopwatch.StartNew();
        readonly ScaleTransform _sigS = new ScaleTransform(0.5, 0.5);
        readonly TranslateTransform _sigT = new TranslateTransform(Pose[0][0], Pose[0][1]);
        Rectangle _stepLine;
        Chrome.Shadow _shadow;
        Scene _scene;
        Sigil _sigil;
        Panel[] _pages;
        int _page, _taskIndex = -1;
        bool _busy, _pathOk, _demo;
        double _last, _mx = 590, _my = 300, _freezeAt = -1, _countT = 2;

        // The running job. Worker writes _wTask/_wFrac/_wDone/_wError; the UI thread only reads them.
        Job _job = Job.Install;
        string[] _tasks = Installer.InstallTasks;
        double[] _weights = Installer.InstallWeights;
        volatile int _wTask;
        double _wFrac;
        volatile bool _wDone, _working;
        volatile Exception _wError;
        JobResult _wResult;
        bool _running;
        double _shown;

        int _perfFrames; double _perfTick; string _perfFile;

        public string GamePath => PathText.Text.Trim().TrimEnd('\\');

        public MainWindow()
        {
            InitializeComponent();
            _pages = new Panel[] { PageWelcome, PagePath, PageOptions, PageInstall, PageDone };

            var area = SystemParameters.WorkArea;
            Left = area.Left + (area.Width - Width) / 2;
            Top = area.Top + (area.Height - Height) / 2;
            _shadow = new Chrome.Shadow(Width, Height);
            _shadow.Follow(this);
            _shadow.Show();
            Owner = _shadow;                         // an owned window always stays above its owner
            LocationChanged += (s, e) => _shadow.Follow(this);
            StateChanged += (s, e) => _shadow.Visibility = WindowState == WindowState.Minimized ? Visibility.Hidden : Visibility.Visible;
            Closed += (s, e) => _shadow.Close();
        }

        protected override void OnSourceInitialized(EventArgs e)
        {
            base.OnSourceInitialized(e);
            var src = PresentationSource.FromVisual(this);
            if (src?.CompositionTarget != null) Fx.Dpi = src.CompositionTarget.TransformToDevice.M11;
            Chrome.Shape(this, Fx.Dpi);
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
            // Layers that never change are rasterised once (see Fx)
            HeroGlowHost.CacheMode = Fx.Cache(0.5);     // a blur; half resolution is invisible
            FrameHost.CacheMode = Fx.Cache();
            Brand.CacheMode = Fx.Cache();
            Nav.CacheMode = Fx.Cache();                 // re-rasterised only while a button is animating

            _scene = new Scene(SceneHost);
            _sigil = new Sigil { Opacity = 0 };
            var tg = new TransformGroup();
            tg.Children.Add(_sigS);
            tg.Children.Add(_sigT);
            _sigil.RenderTransform = tg;
            SigilHost.Children.Add(_sigil);

            int start = 0;
            string shot = null, game = null;
            double shotAt = 3200;
            bool rtb = false;
            foreach (var arg in Environment.GetCommandLineArgs())
            {
                if (arg.StartsWith("--page=") && int.TryParse(arg.Substring(7), out var n)) start = Math.Max(0, Math.Min(_pages.Length - 1, n));
                else if (arg.StartsWith("--freeze=") && double.TryParse(arg.Substring(9), out var f)) _freezeAt = f;
                else if (arg.StartsWith("--shot=")) shot = arg.Substring(7);
                else if (arg.StartsWith("--at=") && double.TryParse(arg.Substring(5), out var at)) shotAt = at;
                else if (arg.StartsWith("--perf=")) _perfFile = arg.Substring(7);
                else if (arg.StartsWith("--game=")) game = arg.Substring(7);
                else if (arg == "--demo") _demo = true;
                else if (arg == "--uninstall") _job = Job.Uninstall;
                else if (arg == "--rtb") rtb = true;
                else if (arg.StartsWith("--skip="))
                    foreach (var part in arg.Substring(7).Split(','))
                    {
                        if (part == "sigil") SigilHost.Visibility = Visibility.Collapsed;
                        else if (part == "text") { PageHost.Visibility = Nav.Visibility = StepsHost.Visibility = Visibility.Collapsed; }
                        else if (part == "frame") FrameHost.Visibility = Visibility.Collapsed;
                        else _scene.Skip(part);
                    }
            }
            // A design run must never write to a real game by accident
            if ((shot != null || _perfFile != null || start >= 3) && game == null) _demo = true;
            _page = start;

            BuildSteps();
            ShowPayloadFigures();
            PathText.Text = game ?? Installer.FindGame() ?? "";

            // Opening: the dark lifts, the ring spins up, then the words arrive
            Anim(Curtain, OpacityProperty, 0, 1700, 250, EaseInOut);
            After(2100, () => Curtain.Visibility = Visibility.Collapsed);
            Anim(_sigil, OpacityProperty, 1, 1100, 350);
            Anim(Brand, OpacityProperty, 1, 700, 1150, null, 0);
            Anim(StepsHost, OpacityProperty, 1, 700, 1150, null, 0);

            EdgeLightT.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-240, 2600, TimeSpan.FromSeconds(9))
            { RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromSeconds(1.5) });

            ApplyStage(false, 1300);
            UpdateSteps();
            UpdateNav(false);
            After(start == 0 ? 750 : 300, () => ShowPage(_pages[_page]));

            // The scene is advanced by an animation clock, not by CompositionTarget.Rendering: it then
            // ticks on exactly the same beat as every other animation (see App), so one frame is
            // drawn per beat instead of one for the scene and another for the storyboards.
            BeginAnimation(BeatProperty, new DoubleAnimation(0, 1, TimeSpan.FromSeconds(1)) { RepeatBehavior = RepeatBehavior.Forever });

            if (shot != null)
            {
                if (!rtb) Topmost = true;
                After(shotAt, () => { SaveShot(shot, rtb); Close(); });
            }
            if (_perfFile != null) After(4000, StartPerfProbe);
        }

        void ShowPayloadFigures()
        {
            var info = Installer.Info;
            SumStrings.Text = info.Strings.ToString("N0");
            SumFiles.Text = info.StringFiles.ToString();
            SumUi.Text = info.InterfaceFiles.ToString();
            SpaceText.Text = info.Present ? "نحو " + Math.Max(1, (int)Math.Round(info.Bytes / 1048576.0)) + " ميغابايت" : "—";
            SupportedText.Text = info.GameVersion ?? "—";
        }

        static readonly DependencyProperty BeatProperty = DependencyProperty.Register("Beat", typeof(double), typeof(MainWindow),
            new PropertyMetadata(0.0, (d, e) => ((MainWindow)d).OnFrame()));

        void OnFrame()
        {
            double now = _clock.Elapsed.TotalSeconds;
            double dt = Math.Min(0.05, now - _last);
            _last = now;
            if (WindowState == WindowState.Minimized) return;       // nothing to draw: do no work

            _scene.Tick(dt, now, _mx, _my);
            _sigil.Tick(dt);
            if (_running) StepJob(dt);

            if (_countT < 1)
            {
                var info = Installer.Info;
                _countT = Math.Min(1, _countT + dt / 1.6);
                double k = 1 - Math.Pow(1 - _countT, 3);
                Stat1.Text = ((int)(info.Strings * k)).ToString("N0");
                Stat2.Text = ((int)(info.Plugins * k)).ToString();
                Stat3.Text = "0";
            }
            _perfFrames++; _perfTick += (_clock.Elapsed.TotalSeconds - now) * 1000;
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
            var halos = new Canvas();
            var still = new Canvas { Width = w, Height = 58, CacheMode = Fx.Cache(1.5) };     // line, diamonds, labels: redrawn only when a step changes
            StepsHost.Children.Add(halos);
            StepsHost.Children.Add(still);
            still.Children.Add(new Rectangle { Width = w - pad * 2, Height = 1, Fill = new SolidColorBrush(Color.FromArgb(0x30, 255, 255, 255)) }
                .Put(pad, y));
            _stepLine = new Rectangle { Width = 0, Height = 1.6, Fill = (Brush)FindResource("Gold") };
            Canvas.SetRight(_stepLine, pad);
            Canvas.SetTop(_stepLine, y - 0.3);
            still.Children.Add(_stepLine);


            for (int i = 0; i < _stepNames.Length; i++)
            {
                double x = w - pad - i * gap;     // first step on the right: the journey reads right to left
                var v = new StepVisual { Scale = new ScaleTransform(1, 1) };

                v.Halo = new Rectangle { Width = 34, Height = 34, Opacity = 0, Fill = new RadialGradientBrush(Fx.A(Gold, 150), Fx.A(Gold, 0)) };
                halos.Children.Add(v.Halo.Put(x - 17, y - 17));

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
                still.Children.Add(v.Diamond.Put(x - 5.5, y - 5.5));

                v.Label = new TextBlock
                {
                    Text = _stepNames[i], Width = 90, TextAlignment = TextAlignment.Center, FontSize = 12.5,
                    Foreground = new SolidColorBrush(MutedC), FlowDirection = FlowDirection.RightToLeft
                };
                still.Children.Add(v.Label.Put(x - 45, y + 14));

                int index = i;
                var hit = new Border { Width = 90, Height = 58, Background = Brushes.Transparent };
                hit.MouseLeftButtonDown += (s, e) => { e.Handled = true; if (index < _page && _page < 3) GoTo(index); };
                v.Hit = hit;
                StepsHost.Children.Add(hit.Put(x - 45, 0));
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
                v.Halo.Opacity = active ? 1 : 0;       // only the current step's halo is drawn at all
                if (active)
                    v.Halo.Fill.BeginAnimation(Brush.OpacityProperty, new DoubleAnimation(0.25, 1, TimeSpan.FromSeconds(1.3))
                    { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
                else
                    v.Halo.Fill.BeginAnimation(Brush.OpacityProperty, null);
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
            bool centre = _page >= 3, undo = _job == Job.Uninstall;
            MoveSigil(Pose[_page], animate, ms);
            Anim(ReadShade, OpacityProperty, centre ? 0 : 1, animate ? 700 : 0);
            Anim(StepsShift, TranslateTransform.XProperty, centre ? -259 : 0, animate ? ms : 0, 0, EaseInOut);
            _scene.SetPage(_page, undo);
            _sigil.Reverse = centre && undo;
            _sigil.SetMode(_page == 3 ? SigilMode.Progress : _page == 4 ? SigilMode.Done : SigilMode.Idle);
        }

        void MoveSigil(double[] p, bool animate, double ms)
        {
            if (animate)
            {
                Anim(_sigT, TranslateTransform.XProperty, p[0], ms, 0, EaseInOut);
                Anim(_sigT, TranslateTransform.YProperty, p[1], ms, 0, EaseInOut);
            }
            else { _sigT.X = p[0]; _sigT.Y = p[1]; }
            Anim(_sigS, ScaleTransform.ScaleXProperty, p[2], ms, 0, animate ? EaseInOut : EaseOut);
            Anim(_sigS, ScaleTransform.ScaleYProperty, p[2], ms, 0, animate ? EaseInOut : EaseOut);
        }

        void ShowPage(Panel page)
        {
            if (page == PageDone) SetUpDone();
            if (page == PageInstall) ResetInstallScreen();

            page.BeginAnimation(OpacityProperty, null);
            page.Opacity = 1;
            page.Visibility = Visibility.Visible;
            page.CacheMode = null;

            // Each block of the page rises into place, one after another
            int i = 0;
            foreach (UIElement child in page.Children)
            {
                if (child.Visibility != Visibility.Visible) continue;
                var t = new TranslateTransform(0, 30);
                child.RenderTransform = t;
                child.Opacity = 0;
                Anim(child, OpacityProperty, 1, 520, i * 90);
                Anim(t, TranslateTransform.YProperty, 0, 760, i * 90, EaseOut);
                i++;
            }

            // Once its entrance has played, a page is a still image: keep it as one texture.
            // (The install screen keeps changing, so it is left live.)
            if (page != PageInstall)
                After(i * 90 + 900 + (page == PageWelcome ? 1800 : 0), () =>
                {
                    if (_pages[_page] == page && !_busy) page.CacheMode = Fx.Cache();
                });

            if (page == PageWelcome)
            {
                _countT = 2;
                After(520, () => _countT = 0);
                // A glint crosses the title every seven seconds; between passes nothing is redrawn
                var sweep = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromSeconds(7), RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromSeconds(1.2) };
                sweep.KeyFrames.Add(new DiscreteDoubleKeyFrame(-1, KeyTime.FromPercent(0)));
                sweep.KeyFrames.Add(new EasingDoubleKeyFrame(1, KeyTime.FromPercent(0.24), new SineEase { EasingMode = EasingMode.EaseInOut }));
                sweep.KeyFrames.Add(new DiscreteDoubleKeyFrame(1, KeyTime.FromPercent(1)));
                HeroShimmer.BeginAnimation(TranslateTransform.XProperty, sweep);
            }
            else HeroShimmer.BeginAnimation(TranslateTransform.XProperty, null);     // no hidden animation left running
            if (page == PagePath) ValidatePath(true);
            if (page == PageInstall) StartJob();
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

        void Next_Click(object sender, RoutedEventArgs e)
        {
            if (_page == 2) _job = Job.Install;
            GoTo(_page + 1);
        }

        void Back_Click(object sender, RoutedEventArgs e) => GoTo(_page - 1);

        void Window_KeyDown(object sender, KeyEventArgs e)
        {
            if (_page >= 3 || PathText.IsKeyboardFocused) return;
            if (e.Key == Key.Enter && BtnNext.IsEnabled) Next_Click(null, null);
            else if (e.Key == Key.Escape && _page > 0) GoTo(_page - 1);
        }

        // ---------- game folder ----------

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
            string path = GamePath, built = Installer.Info.GameVersion;
            bool was = _pathOk, found = Installer.LooksLikeGame(path);
            string version = found ? Installer.GameVersion(path) : null;
            bool match = Installer.SameVersion(version, built), installed = found && Installer.IsInstalled(path);
            _pathOk = found || (_demo && path.Length > 0);

            Color c = path.Length == 0 ? MutedC : !found ? Warn : match ? Good : Warn;
            StatusText.Text = path.Length == 0 ? "لم يُحدَّد مجلد بعد"
                : !found ? "لا أثر للملف SkyrimSE.exe في هذا المجلد"
                : !match ? "وُجدت اللعبة بالإصدار " + version + "، والتعريب مبنيّ للإصدار " + built + ". قد تغيب بعض النصوص."
                : installed ? "سكايرم هنا، ومعرَّبة من قبل. سيُحدَّث التعريب إلى أحدث نقش."
                : "عُثر على سكايرم. الطريق سالكة.";
            YourVersionText.Text = version ?? "—";
            YourVersionText.Foreground = new SolidColorBrush(found && !match ? Warn : Fx.C("#EEF2F8"));
            BtnUninstall.Visibility = installed ? Visibility.Visible : Visibility.Collapsed;

            Tint(StatusDotBrush, c);
            PathGlowStop.BeginAnimation(GradientStop.ColorProperty, new ColorAnimation(c, TimeSpan.FromMilliseconds(350)));
            Tint(PathBorderBrush, path.Length == 0 ? Color.FromArgb(0x30, 255, 255, 255) : Color.FromArgb(0x90, c.R, c.G, c.B));
            StatusRing.Stroke = new SolidColorBrush(c);

            // A beacon ping around the status dot, and an answering pulse from the ring
            var ring = (ScaleTransform)StatusRing.RenderTransform;
            if (_page == 1)
            {
                var grow = new DoubleAnimation(0.5, 2.3, TimeSpan.FromSeconds(1.5)) { RepeatBehavior = new RepeatBehavior(3), FillBehavior = FillBehavior.Stop, EasingFunction = EaseOut };
                ring.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
                ring.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
                StatusRing.BeginAnimation(OpacityProperty, new DoubleAnimation(0.9, 0, TimeSpan.FromSeconds(1.5)) { RepeatBehavior = new RepeatBehavior(3), FillBehavior = FillBehavior.Stop });
                if (found && (!was || replay)) _sigil.Pulse(c, replay ? 600 : 0);
                BtnNext.IsEnabled = _pathOk;
            }
        }

        void Option_Click(object sender, RoutedEventArgs e)
        {
            _sigil.Tease();
            _sigil.Tease();
        }

        void Uninstall_Click(object sender, RoutedEventArgs e)
        {
            _job = Job.Uninstall;
            GoTo(3);
        }

        // ---------- the carving ----------

        void ResetInstallScreen()
        {
            bool undo = _job == Job.Uninstall;
            _tasks = undo ? Installer.UninstallTasks : Installer.InstallTasks;
            _weights = undo ? Installer.UninstallWeights : Installer.InstallWeights;
            InstallEyebrow.Text = undo ? "يُمحى النقش" : "يُنقَش الآن";
            TaskText.Foreground = (Brush)FindResource("Text");
            TaskText.Text = _tasks[0];
            LogText.Text = " ";
            LogText.Foreground = (Brush)FindResource("Muted");
            ErrorNav.Visibility = Visibility.Collapsed;
            Pips.Visibility = Visibility.Visible;

            Pips.Children.Clear();
            _pips.Clear();
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

        void StartJob()
        {
            _taskIndex = -1;
            _shown = 0;
            _wTask = 0; Volatile.Write(ref _wFrac, 0); _wDone = false; _wError = null; _wResult = null;
            ReportProgress(0, 0);

            var opts = new InstallOptions { GameDir = GamePath, Backup = OptBackup.IsChecked == true, Shortcut = OptShortcut.IsChecked == true };
            var job = _job;
            bool demo = _demo;
            int count = _tasks.Length;
            Action<int, double> report = (t, f) => { _wTask = t; Volatile.Write(ref _wFrac, f); };

            _working = true;
            BtnClose.IsEnabled = false;
            // Let the ring settle into its starting pose before the first letters strike
            After(900, () =>
            {
                _running = true;
                Task.Run(() =>
                {
                    try
                    {
                        _wResult = demo ? Installer.Demo(count, report)
                                 : job == Job.Uninstall ? Installer.Uninstall(opts.GameDir, report)
                                 : Installer.Install(opts, report);
                    }
                    catch (Exception ex) { _wError = ex; }
                    finally { _wDone = true; _working = false; }
                });
            });
        }

        // Called every frame while a job is running
        void StepJob(double dt)
        {
            if (_wError != null) { _running = false; BtnClose.IsEnabled = true; ShowError(_wError); return; }

            double target = 100;
            if (!_wDone)
            {
                int t = Math.Min(_wTask, _weights.Length - 1);
                double before = 0;
                for (int i = 0; i < t; i++) before += _weights[i];
                target = (before + _weights[t] * Math.Max(0, Math.Min(1, Volatile.Read(ref _wFrac)))) * 100;
            }
            // Ease toward the real figure: never faster than the eye can follow, never stalling behind it
            _shown = Math.Min(target, _shown + (14 + (target - _shown) * 0.12) * dt);
            if (_freezeAt >= 0 && _shown >= _freezeAt) _shown = _freezeAt;

            double acc = 0;
            int idx = _weights.Length - 1;
            for (int i = 0; i < _weights.Length; i++) { acc += _weights[i] * 100; if (_shown < acc) { idx = i; break; } }
            ReportProgress(_shown, idx);

            if (_wDone && _shown >= 100)
            {
                _running = false;
                BtnClose.IsEnabled = true;
                ReportProgress(100, _tasks.Length);
                After(1100, () => GoTo(4));
            }
        }

        /// <summary>Drive the install screen. taskIndex == task count means "all done".</summary>
        void ReportProgress(double percent, int taskIndex)
        {
            _sigil.SetProgress(percent / 100);
            if (taskIndex == _taskIndex) return;

            for (int i = Math.Max(0, _taskIndex); i < taskIndex && i < _pips.Count; i++)
            {
                Tint((SolidColorBrush)_pips[i].Fill, Gold, 400);
                Tint((SolidColorBrush)_pips[i].Stroke, GoldLight, 400);
                LogText.Text = "✓  " + _tasks[i];
                Anim(LogText, OpacityProperty, 1, 400, 0, null, 0);
                _sigil.Pulse(Gold);                  // each finished task rings out from the circle
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

        void ShowError(Exception ex)
        {
            bool undo = _job == Job.Uninstall;
            InstallEyebrow.Text = undo ? "توقّف المحو" : "توقّف النقش";
            TaskText.Text = undo ? "تعذّرت إزالة التعريب" : "تعذّر إكمال النقش";
            TaskText.Foreground = new SolidColorBrush(Warn);
            LogText.Text = ex is InstallException ? ex.Message : "خطأ غير متوقَّع: " + ex.Message;
            LogText.Foreground = (Brush)FindResource("Soft");
            Pips.Visibility = Visibility.Collapsed;
            ErrorNav.Visibility = Visibility.Visible;
            Anim(ErrorNav, OpacityProperty, 1, 400, 0, null, 0);
            ErrorNav.RenderTransform = null;
            MoveSigil(ErrorPose, true, 700);
            _sigil.Reverse = false;
            _sigil.SetMode(SigilMode.Idle);
            _scene.SetPage(1);
        }

        void Retry_Click(object sender, RoutedEventArgs e)
        {
            ResetInstallScreen();
            MoveSigil(Pose[3], true, 700);
            _scene.SetPage(3, _job == Job.Uninstall);
            _sigil.Reverse = _job == Job.Uninstall;
            _sigil.SetMode(SigilMode.Progress);
            StartJob();
        }

        void ErrorBack_Click(object sender, RoutedEventArgs e)
        {
            _job = Job.Install;
            GoTo(1);
        }

        // ---------- the end ----------

        void SetUpDone()
        {
            bool undo = _job == Job.Uninstall;
            var r = _wResult ?? new JobResult();
            DoneEyebrow.Text = undo ? "اكتمل المحو" : "اكتمل النقش";
            DoneTitle.Text = undo ? "عادت سكايرم إلى أصلها" : "سكايرم تتكلّم العربية";
            DoneLead.Text = undo ? "أُزيل التعريب من اللعبة. يمكنك نقشه من جديد متى شئت."
                                 : "كل شيء في مكانه، والملفات الأصلية لم تُمَسّ. رحلة موفّقة يا دوفاكين.";
            DoneNote.Text = _demo ? "عرض تجريبي: لم يُكتب أي ملف."
                : undo ? "الملفات المُزالة: " + r.Files + (r.Restored > 0 ? "  ·  المُعادة من النسخة الاحتياطية: " + r.Restored : "")
                         + (r.LeftInPlace > 0 ? "  ·  المتروكة لأنها تغيّرت: " + r.LeftInPlace : "")
                : "الملفات المنقوشة: " + r.Files + (r.BackedUp > 0 ? "  ·  المحفوظة في النسخة الاحتياطية: " + r.BackedUp : "");
            BtnLaunch.Visibility = undo ? Visibility.Collapsed : Visibility.Visible;
        }

        void Launch_Click(object sender, RoutedEventArgs e)
        {
            if (!_demo)
                try { Installer.Launch(GamePath); }
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

        // Files are being moved: closing now could leave the game half-patched
        protected override void OnClosing(CancelEventArgs e)
        {
            if (_working) e.Cancel = true;
            base.OnClosing(e);
        }

        void CloseAnimated()
        {
            if (_working) return;
            Curtain.Visibility = Visibility.Visible;
            var fade = new DoubleAnimation(1, TimeSpan.FromMilliseconds(240));
            fade.Completed += (s, e) => Close();
            Curtain.BeginAnimation(OpacityProperty, fade);
        }

        // ---------- design aids ----------

        // By default this photographs the real window, so cached layers and hardware
        // effects are captured exactly as the user sees them. --rtb renders off-screen instead.
        void SaveShot(string file, bool rtb)
        {
            if (rtb)
            {
                // Off-screen: draws the window's own content and never reads the screen
                var bmp = new RenderTargetBitmap((int)Math.Round(Root.ActualWidth * Fx.Dpi), (int)Math.Round(Root.ActualHeight * Fx.Dpi), 96 * Fx.Dpi, 96 * Fx.Dpi, PixelFormats.Pbgra32);
                bmp.Render(Root);
                var enc = new PngBitmapEncoder();
                enc.Frames.Add(BitmapFrame.Create(bmp));
                using (var fs = System.IO.File.Create(file)) enc.Save(fs);
                return;
            }
            double pad = Chrome.ShadowPad;                 // include the shadow window in the picture
            var origin = PointToScreen(new Point(-pad, -pad));
            int w = (int)Math.Round((ActualWidth + pad * 2) * Fx.Dpi), h = (int)Math.Round((ActualHeight + pad * 2) * Fx.Dpi);
            using (var shot = new System.Drawing.Bitmap(w, h))
            {
                using (var g = System.Drawing.Graphics.FromImage(shot))
                    g.CopyFromScreen((int)origin.X, (int)origin.Y, 0, 0, new System.Drawing.Size(w, h));
                shot.Save(file, System.Drawing.Imaging.ImageFormat.Png);
            }
        }

        void StartPerfProbe()
        {
            var proc = Process.GetCurrentProcess();
            var cpu0 = proc.TotalProcessorTime;
            var w0 = _clock.Elapsed;
            _perfFrames = 0; _perfTick = 0;
            After(8000, () =>
            {
                proc.Refresh();
                double wall = (_clock.Elapsed - w0).TotalSeconds;
                System.IO.File.WriteAllText(_perfFile, string.Format(System.Globalization.CultureInfo.InvariantCulture,
                    "page={0} fps={1:F1} cpu={2:F1}% of one core, tick={3:F3} ms/frame, tier={4}, display={5} Hz",
                    _page, _perfFrames / wall, (proc.TotalProcessorTime - cpu0).TotalSeconds / wall * 100,
                    _perfTick / Math.Max(1, _perfFrames), RenderCapability.Tier >> 16, Chrome.RefreshRate()));
                Close();
            });
        }
    }
}

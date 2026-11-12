using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Shapes;
using System.Windows.Threading;

namespace SkyrimArabicInstaller
{
    public enum SigilMode { Idle, Progress, Done }

    // The centrepiece: a ring of 28 northern runes around an eight-pointed star.
    // As the install advances, each rune is re-struck as one of the 28 Arabic
    // letters, running counter-clockwise (the direction Arabic is written).
    // Drawn around (0,0); the window positions and scales it.
    //
    // Every part that only spins is its own cached layer, so a frame of the idle
    // animation is a handful of textured quads rather than hundreds of re-tessellated shapes.
    public sealed class Sigil : Canvas
    {
        public const int N = 28;
        const string Runes = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟᚪᚫᚣᛡ";
        const string Letters = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي";
        const double GlyphR = 151, ArcR = 175;

        static readonly Color Gold = Fx.C("#E2B96A");
        static readonly Color GoldLight = Fx.C("#F7E3AE");
        static readonly Color Ice = Fx.C("#9FDCF0");
        static readonly IEasingFunction Out = new CubicEase { EasingMode = EasingMode.EaseOut };
        static readonly IEasingFunction InOut = new CubicEase { EasingMode = EasingMode.EaseInOut };
        static readonly IEasingFunction Back = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 1.1 };

        sealed class Slot
        {
            public TextBlock Rune, Letter; public ScaleTransform LetterScale; public Rectangle Flash; public bool Lit;
        }
        sealed class Spark
        {
            public Brush B; public Rectangle E; public TranslateTransform T; public double X, Y, Vx, Vy, Life, Max;
        }

        readonly Slot[] _slots = new Slot[N];
        readonly List<Spark> _sparks = new List<Spark>();
        readonly Random _rnd = new Random();
        readonly RotateTransform _glyphRot = new RotateTransform();
        readonly Canvas _fx = new Canvas();
        readonly FrameworkElement _head, _headGlow, _percent, _dad;
        readonly Path _arc, _arcGlowA, _arcGlowB, _check;
        readonly TextBlock _digits;
        readonly DispatcherTimer _tease;
        SigilMode _mode = SigilMode.Idle;
        double _p, _hx, _hy = -ArcR, _emit;

        /// <summary>Uninstall: the ring starts fully Arabic and the letters fall back to runes.</summary>
        public bool Reverse { get; set; }

        public Sigil()
        {
            IsHitTestVisible = false;
            var cairo = (FontFamily)Application.Current.Resources["Cairo"];
            var amiri = (FontFamily)Application.Current.Resources["Amiri"];
            var runes = (FontFamily)Application.Current.Resources["Runes"];
            var metal = (Brush)Application.Current.Resources["GoldMetalHot"];

            // Breathing halo
            // (fades through its brush: element opacity would cost a 570px blend layer every frame)
            var glowBrush = Fx.Radial(Fx.A(Gold, 120), Fx.A(Gold, 0));
            Children.Add(Square(285, glowBrush));
            glowBrush.BeginAnimation(Brush.OpacityProperty, new DoubleAnimation(0.45, 0.95, TimeSpan.FromSeconds(3.2))
            { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });

            // ---- static base: dark plate, forged outer band, studs, progress track ----
            var basePlate = new Canvas { CacheMode = Fx.Cache() };
            var plate = Fx.Radial(Color.FromArgb(215, 4, 6, 12), Color.FromArgb(0, 4, 6, 12));
            plate.GradientStops.Insert(1, new GradientStop(Color.FromArgb(190, 4, 6, 12), 0.78));
            basePlate.Children.Add(Disc(232, Fx.Frozen(plate)));

            // The outer band reads as worked metal: light from the upper left, shade lower right
            var band = new LinearGradientBrush { StartPoint = new Point(0.1, 0), EndPoint = new Point(0.9, 1) };
            band.GradientStops.Add(new GradientStop(Fx.C("#FFF4D2"), 0));
            band.GradientStops.Add(new GradientStop(Fx.C("#C99A45"), 0.28));
            band.GradientStops.Add(new GradientStop(Fx.C("#6E4C17"), 0.55));
            band.GradientStops.Add(new GradientStop(Fx.C("#D9AE5C"), 0.8));
            band.GradientStops.Add(new GradientStop(Fx.C("#FBE6B0"), 1));
            basePlate.Children.Add(RingB(201.5, Fx.Frozen(band), 2.4, 0.95));
            basePlate.Children.Add(Ring(197, Gold, 1, 0.3));
            basePlate.Children.Add(Ring(205.5, Gold, 1, 0.22));
            for (int i = 0; i < 8; i++)
            {
                bool major = i % 2 == 0;
                double sz = major ? 10 : 5;
                var d = new Rectangle { Width = sz, Height = sz, Fill = metal };
                var tg = new TransformGroup();
                tg.Children.Add(new RotateTransform(45, sz / 2, sz / 2));
                tg.Children.Add(new TranslateTransform(-sz / 2, -201.5 - sz / 2));
                tg.Children.Add(new RotateTransform(i * 45));
                d.RenderTransform = tg;
                basePlate.Children.Add(d);
            }
            basePlate.Children.Add(Ring(ArcR, Colors.White, 1, 0.13));
            Children.Add(basePlate);

            // ---- tick ring, slowly turning ----
            var ticks = new Canvas { CacheMode = Fx.Cache() };
            var t1 = Ring(188, Gold, 6, 0.5);
            t1.StrokeDashArray = new DoubleCollection { 0.22, 2.4049 };
            var t2 = Ring(188, GoldLight, 10, 0.8);
            t2.StrokeDashArray = new DoubleCollection { 0.16, 16.714 };
            ticks.Children.Add(t1);
            ticks.Children.Add(t2);
            Spin(ticks, 0, 360, 140);
            Children.Add(ticks);

            // A highlight that circles the outer band, as if a torch were carried around it
            var glint = new Canvas { CacheMode = Fx.Cache() };
            var gb = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(1, 0) };
            gb.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0));
            gb.GradientStops.Add(new GradientStop(Color.FromArgb(255, 255, 252, 235), 0.5));
            gb.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1));
            glint.Children.Add(new Path
            {
                Data = Geometry.Parse("M-78,-185.8 A201.5,201.5 0 0 1 78,-185.8"),
                Stroke = Fx.Frozen(gb), StrokeThickness = 2.6
            });
            Spin(glint, 0, 360, 11);
            Children.Add(glint);

            // ---- the glyph ring ----
            // Each cell is its own small cached tile: the ring turns as 28 textured quads, and a rune
            // that is being re-struck re-rasterises only its own tile.
            var glyphs = new Canvas { RenderTransform = _glyphRot };
            var flash = Fx.Frozen(Fx.Radial(Color.FromArgb(200, 255, 226, 150), Color.FromArgb(0, 255, 226, 150)));
            var iceBrush = Fx.Frozen(new SolidColorBrush(Ice));
            var letterBrush = Fx.Frozen(new SolidColorBrush(GoldLight));
            for (int i = 0; i < N; i++)
            {
                double deg = -i * 360.0 / N, a = deg * Math.PI / 180;
                var s = new Slot { LetterScale = new ScaleTransform(0.3, 0.3) };
                var cell = new Grid { Width = 46, Height = 46, RenderTransform = new RotateTransform(deg, 23, 23), CacheMode = Fx.Cache(1.25) };
                SetLeft(cell, Math.Sin(a) * GlyphR - 23);
                SetTop(cell, -Math.Cos(a) * GlyphR - 23);

                s.Flash = new Rectangle { Margin = new Thickness(-9), Opacity = 0, Fill = flash };
                s.Rune = new TextBlock
                {
                    Text = Runes[i].ToString(), FontFamily = runes, FontSize = 23, Opacity = 0.62, Foreground = iceBrush,
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center
                };
                s.Letter = new TextBlock
                {
                    Text = Letters[i].ToString(), FontFamily = amiri, FontWeight = FontWeights.Bold, FontSize = 25, Opacity = 0,
                    Foreground = letterBrush, FlowDirection = FlowDirection.RightToLeft,
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
                    Margin = new Thickness(0, -8, 0, 0),
                    RenderTransform = s.LetterScale, RenderTransformOrigin = new Point(0.5, 0.5)
                };
                cell.Children.Add(s.Flash);
                cell.Children.Add(s.Rune);
                cell.Children.Add(s.Letter);
                glyphs.Children.Add(cell);
                _slots[i] = s;
            }
            Children.Add(glyphs);

            // ---- progress arc: a hot core over two wide soft strokes (no blur) ----
            _arcGlowA = ArcPath(new SolidColorBrush(Fx.A(Gold, 34)), 17);
            _arcGlowB = ArcPath(new SolidColorBrush(Fx.A(Gold, 80)), 8.5);
            _arc = ArcPath(metal, 3.2);
            _headGlow = Square(20, Fx.Frozen(Fx.Radial(Color.FromArgb(255, 255, 246, 214), Color.FromArgb(150, 255, 214, 130), Color.FromArgb(0, 255, 200, 110))));
            _head = Square(4.5, Fx.Frozen(Fx.Radial(Colors.White, Colors.White, Color.FromArgb(0, 255, 255, 255))));
            _headGlow.RenderTransform = _head.RenderTransform = new TranslateTransform(0, -ArcR);
            foreach (var el in new UIElement[] { _arcGlowA, _arcGlowB, _arc, _headGlow, _head }) { el.Opacity = 0; Children.Add(el); }

            // ---- inner machinery: dashed ice ring and the eight-pointed star ----
            var ice = new Canvas { CacheMode = Fx.Cache() };
            var iceRing = Ring(124, Ice, 1.2, 0.6);
            iceRing.StrokeDashArray = new DoubleCollection { 14, 5, 2, 5 };
            ice.Children.Add(iceRing);
            Spin(ice, 360, 0, 50);
            Children.Add(ice);

            var star = new Canvas { CacheMode = Fx.Cache() };
            for (int i = 0; i < 2; i++)
            {
                var sq = new Rectangle
                {
                    Width = 158, Height = 158, Stroke = new SolidColorBrush(Gold), StrokeThickness = 1.3, Opacity = 0.7,
                    RenderTransform = new RotateTransform(i * 45, 79, 79)
                };
                SetLeft(sq, -79); SetTop(sq, -79);
                star.Children.Add(sq);
            }
            for (int i = 0; i < 8; i++)   // a bead at every point of the star
            {
                double a = i * Math.PI / 4;
                var bead = Square(2.6, Fx.Frozen(Fx.Radial(GoldLight, GoldLight, Fx.A(Gold, 0))));
                bead.RenderTransform = new TranslateTransform(Math.Sin(a) * 111.7, -Math.Cos(a) * 111.7);
                star.Children.Add(bead);
            }
            Spin(star, 0, 360, 110);
            Children.Add(star);

            var hub = new Canvas { CacheMode = Fx.Cache() };
            hub.Children.Add(Ring(116, Gold, 1, 0.3));
            var disc = Disc(79, Fx.Frozen(Fx.Radial(Color.FromArgb(255, 22, 34, 54), Color.FromArgb(255, 9, 14, 24), Color.FromArgb(255, 4, 6, 12))));
            disc.Stroke = metal; disc.StrokeThickness = 1.8;
            hub.Children.Add(disc);
            hub.Children.Add(Ring(72, Gold, 1, 0.28));
            Children.Add(hub);

            // ---- centre: the letter Dad (Arabic is "the language of the Dad"), then the percentage, then the seal ----
            // The glow is baked into a cached layer once; fading it later costs nothing.
            var dadHost = new Canvas { CacheMode = Fx.Cache() };
            var dad = new TextBlock
            {
                Text = "ض", FontFamily = amiri, FontWeight = FontWeights.Bold, FontSize = 104, Foreground = metal,
                Width = 240, TextAlignment = TextAlignment.Center, FlowDirection = FlowDirection.RightToLeft,
                Effect = new DropShadowEffect { Color = Gold, BlurRadius = 26, ShadowDepth = 0, Opacity = 0.75 }
            };
            SetLeft(dad, -120); SetTop(dad, -108);
            dadHost.Children.Add(Square(170, Brushes.Transparent));     // gives the cache room for the glow
            dadHost.Children.Add(dad);
            _dad = dadHost;
            Children.Add(dadHost);

            _digits = new TextBlock { Text = "0", FontFamily = cairo, FontWeight = FontWeights.Black, FontSize = 62, Foreground = metal };
            var pc = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
            pc.Children.Add(_digits);
            pc.Children.Add(new TextBlock
            {
                Text = "%", FontFamily = cairo, FontWeight = FontWeights.Bold, FontSize = 22, Opacity = 0.8,
                Foreground = new SolidColorBrush(Gold), VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(3, 0, 0, 26)
            });
            var pg = new Grid { Width = 200, Height = 160, Opacity = 0 };
            pg.Children.Add(pc);
            SetLeft(pg, -100); SetTop(pg, -80);
            _percent = pg;
            Children.Add(pg);

            var checkHost = new Canvas { CacheMode = Fx.Cache() };
            _check = new Path
            {
                Data = Geometry.Parse("M-30,2 L-9,23 L32,-20"), Stroke = metal, StrokeThickness = 9,
                StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round,
                StrokeDashArray = new DoubleCollection { 10.2, 10.2 }, StrokeDashOffset = 10.2,
                Effect = new DropShadowEffect { Color = Gold, BlurRadius = 22, ShadowDepth = 0, Opacity = 0.9 }
            };
            checkHost.Children.Add(Square(90, Brushes.Transparent));
            checkHost.Children.Add(_check);
            Children.Add(checkHost);

            // ---- orbiting motes ----
            double[] orbitR = { 216, 136, 96 };
            for (int i = 0; i < 3; i++)
            {
                var orbit = new Canvas();
                Color c = i == 1 ? Ice : GoldLight;
                var m = Square(i == 0 ? 9 : 7, Fx.Frozen(Fx.Radial(Colors.White, c, Fx.A(c, 70), Fx.A(c, 0))));
                m.RenderTransform = new TranslateTransform(0, -orbitR[i]);
                orbit.Children.Add(m);
                Spin(orbit, i % 2 == 0 ? 0 : 360, i % 2 == 0 ? 360 : 0, 17 + i * 9);
                Children.Add(orbit);
            }

            Children.Add(_fx);
            var hot = Fx.Frozen(Fx.Radial(Colors.White, GoldLight, Fx.A(Gold, 0)));
            var warm = Fx.Frozen(Fx.Radial(Fx.C("#FFE2B0"), Color.FromRgb(255, 170, 90), Color.FromArgb(0, 255, 140, 60)));
            for (int i = 0; i < 48; i++)
            {
                var sp = new Spark { T = new TranslateTransform() };
                double sz = 3 + _rnd.NextDouble() * 4;
                sp.B = (_rnd.NextDouble() < 0.5 ? hot : warm).Clone();
                sp.B.Opacity = 0;
                sp.E = new Rectangle { Width = sz, Height = sz, Margin = new Thickness(-sz / 2), RenderTransform = sp.T, Fill = sp.B, Opacity = 0 };
                _fx.Children.Add(sp.E);
                _sparks.Add(sp);
            }

            StartIdleSpin();
            _tease = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
            _tease.Tick += (s, e) => Tease();
            _tease.Start();
        }

        // ---------------- public surface ----------------

        public void SetMode(SigilMode mode)
        {
            if (mode == _mode) return;
            _mode = mode;
            if (mode == SigilMode.Idle)
            {
                _tease.Start();
                for (int i = 0; i < N; i++) Strike(i, false, i * 14);
                _p = 0;
                Fade(_arc, 0, 300); Fade(_arcGlowA, 0, 300); Fade(_arcGlowB, 0, 300); Fade(_head, 0, 200); Fade(_headGlow, 0, 200);
                Fade(_percent, 0, 250); Fade(_dad, 1, 600, 200);
                _check.BeginAnimation(Shape.StrokeDashOffsetProperty, null);
                StartIdleSpin();
            }
            else if (mode == SigilMode.Progress)
            {
                _tease.Stop();
                for (int i = 0; i < N; i++) Strike(i, Reverse, Reverse ? i * 12 : 0);
                // Settle the ring so the first letter sits at twelve o'clock
                double cur = _glyphRot.Angle;
                _glyphRot.BeginAnimation(RotateTransform.AngleProperty,
                    new DoubleAnimation(cur, Math.Round(cur / 360) * 360, TimeSpan.FromMilliseconds(900)) { EasingFunction = InOut });
                _check.BeginAnimation(Shape.StrokeDashOffsetProperty, null);
                Fade(_dad, 0, 350);
                Fade(_percent, 1, 500, 300);
                Fade(_arc, 1, 400, 500); Fade(_arcGlowA, 1, 400, 500); Fade(_arcGlowB, 1, 400, 500);
                Fade(_head, 1, 300, 600); Fade(_headGlow, 1, 300, 600);
                SetProgress(0);
            }
            else
            {
                _tease.Stop();
                for (int i = 0; i < N; i++) Strike(i, !Reverse, i * 10);
                Fade(_percent, 0, 300); Fade(_dad, 0, 300);
                Fade(_head, 0, 400); Fade(_headGlow, 0, 400);
                if (Reverse) { Fade(_arc, 0, 600); Fade(_arcGlowA, 0, 600); Fade(_arcGlowB, 0, 600); }
                _check.BeginAnimation(Shape.StrokeDashOffsetProperty,
                    new DoubleAnimation(10.2, 0, TimeSpan.FromMilliseconds(620)) { BeginTime = TimeSpan.FromMilliseconds(380), EasingFunction = Out });
                if (Reverse) Pulse(Ice, 0);
                else { Pulse(GoldLight, 0); Pulse(Gold, 260); Pulse(Ice, 520); }
                StartIdleSpin();
            }
        }

        /// <summary>0..1. Draws the arc and re-strikes runes as Arabic letters (or back, when Reverse).</summary>
        public void SetProgress(double p)
        {
            p = Math.Max(0, Math.Min(1, p));
            if (_mode == SigilMode.Progress && Math.Abs(p - _p) < 0.0004 && p > 0 && p < 1) return;
            _p = p;
            _digits.Text = ((int)Math.Round(p * 100)).ToString();

            double q = Reverse ? 1 - p : p;          // how much of the ring is Arabic
            double phi = Math.Min(q, 0.9995) * 2 * Math.PI;
            _hx = -Math.Sin(phi) * ArcR; _hy = -Math.Cos(phi) * ArcR;
            var fig = new PathFigure { StartPoint = new Point(0, -ArcR) };
            fig.Segments.Add(new ArcSegment(new Point(_hx, _hy), new Size(ArcR, ArcR), 0, q > 0.5, SweepDirection.Counterclockwise, true));
            var g = new PathGeometry();
            g.Figures.Add(fig);
            g.Freeze();
            _arc.Data = _arcGlowA.Data = _arcGlowB.Data = g;
            var ht = (TranslateTransform)_head.RenderTransform;
            ht.X = _hx; ht.Y = _hy;

            int lit = (int)Math.Floor(q * N + 0.5);
            for (int i = 0; i < N; i++)
            {
                if (i < lit && !_slots[i].Lit) Strike(i, true, 0);
                else if (Reverse && i >= lit && _slots[i].Lit && _mode == SigilMode.Progress && p > 0) Strike(i, false, 0);
            }
        }

        /// <summary>An expanding ring of light, used as feedback.</summary>
        public void Pulse(Color c, double delayMs = 0)
        {
            var ring = Ring(ArcR, c, 2.2, 0);
            var st = new ScaleTransform(1, 1);
            ring.RenderTransform = st;
            ring.CacheMode = Fx.Cache(1.6);
            _fx.Children.Add(ring);
            var d = TimeSpan.FromMilliseconds(1300);
            var b = TimeSpan.FromMilliseconds(delayMs);
            var grow = new DoubleAnimation(0.9, 1.75, d) { BeginTime = b, EasingFunction = Out };
            var fade = new DoubleAnimation(0.95, 0, d) { BeginTime = b };
            fade.Completed += (s, e) => _fx.Children.Remove(ring);
            st.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            st.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
            ring.BeginAnimation(OpacityProperty, fade);
        }

        /// <summary>Briefly shows one rune's Arabic face. A hint of what's coming.</summary>
        public void Tease()
        {
            if (_mode != SigilMode.Idle) return;
            var s = _slots[_rnd.Next(N)];
            if (s.Lit) return;
            Keys(s.Letter, OpacityProperty, 0, 1, 1, 0);
            Keys(s.Rune, OpacityProperty, 0.62, 0, 0, 0.62);
            Keys(s.Flash, OpacityProperty, 0, 0.8, 0.15, 0);
            Keys(s.LetterScale, ScaleTransform.ScaleXProperty, 0.3, 1, 1, 0.3);
            Keys(s.LetterScale, ScaleTransform.ScaleYProperty, 0.3, 1, 1, 0.3);
        }

        public void Tick(double dt)
        {
            if (_mode == SigilMode.Progress && _p > 0 && _p < 1)
            {
                _emit += dt * 46;
                while (_emit >= 1)
                {
                    _emit -= 1;
                    var sp = _sparks.Find(x => x.Life <= 0);
                    if (sp == null) break;
                    // Fly off roughly along the tangent, trailing behind the head
                    double phi = (Reverse ? 1 - _p : _p) * 2 * Math.PI, dir = Reverse ? -1 : 1;
                    double tx = Math.Cos(phi) * dir, ty = -Math.Sin(phi) * dir;
                    double spd = 30 + _rnd.NextDouble() * 110, spread = (_rnd.NextDouble() - 0.5) * 1.5;
                    sp.X = _hx; sp.Y = _hy;
                    sp.Vx = tx * spd + _hx / ArcR * spd * spread;
                    sp.Vy = ty * spd + _hy / ArcR * spd * spread;
                    sp.Max = sp.Life = 0.35 + _rnd.NextDouble() * 0.7;
                    sp.E.Opacity = 1;                 // a dead spark is not drawn at all
                }
            }
            foreach (var sp in _sparks)
            {
                if (sp.Life <= 0) continue;
                sp.Life -= dt;
                sp.Vy += 120 * dt;
                sp.X += sp.Vx * dt; sp.Y += sp.Vy * dt;
                sp.T.X = sp.X; sp.T.Y = sp.Y;
                if (sp.Life <= 0) { sp.E.Opacity = 0; continue; }
                sp.B.Opacity = Math.Min(1, sp.Life / sp.Max * 1.4);
            }
        }

        // ---------------- internals ----------------

        void Strike(int i, bool lit, double delayMs)
        {
            var s = _slots[i];
            s.Lit = lit;
            Fade(s.Letter, lit ? 1 : 0, lit ? 260 : 300, delayMs);
            Fade(s.Rune, lit ? 0 : 0.62, 260, delayMs);
            var grow = new DoubleAnimation(lit ? 1 : 0.3, TimeSpan.FromMilliseconds(lit ? 520 : 250))
            { BeginTime = TimeSpan.FromMilliseconds(delayMs), EasingFunction = lit ? Back : null };
            if (lit) grow.From = 1.9;
            s.LetterScale.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            s.LetterScale.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
            if (lit)
                s.Flash.BeginAnimation(OpacityProperty, new DoubleAnimation(1, 0.22, TimeSpan.FromMilliseconds(900))
                { BeginTime = TimeSpan.FromMilliseconds(delayMs), EasingFunction = Out });
            else
                Fade(s.Flash, 0, 250, delayMs);
        }

        void StartIdleSpin()
        {
            double cur = _glyphRot.Angle % 360;
            _glyphRot.BeginAnimation(RotateTransform.AngleProperty,
                new DoubleAnimation(cur, cur - 360, TimeSpan.FromSeconds(120)) { RepeatBehavior = RepeatBehavior.Forever });
        }

        static Path ArcPath(Brush stroke, double thickness) => new Path
        {
            Stroke = stroke, StrokeThickness = thickness,
            StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round
        };

        static void Keys(IAnimatable target, DependencyProperty prop, double a, double b, double c, double d)
        {
            var k = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromSeconds(2.4) };
            k.KeyFrames.Add(new DiscreteDoubleKeyFrame(a, KeyTime.FromPercent(0)));
            k.KeyFrames.Add(new EasingDoubleKeyFrame(b, KeyTime.FromPercent(0.14), Out));
            k.KeyFrames.Add(new LinearDoubleKeyFrame(c, KeyTime.FromPercent(0.72)));
            k.KeyFrames.Add(new LinearDoubleKeyFrame(d, KeyTime.FromPercent(1)));
            target.BeginAnimation(prop, k);
        }

        static void Fade(UIElement el, double to, double ms, double delayMs = 0)
        {
            el.BeginAnimation(OpacityProperty, new DoubleAnimation(to, TimeSpan.FromMilliseconds(ms)) { BeginTime = TimeSpan.FromMilliseconds(delayMs) });
        }

        static void Spin(UIElement el, double from, double to, double seconds)
        {
            var r = new RotateTransform();
            el.RenderTransform = r;
            r.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(from, to, TimeSpan.FromSeconds(seconds)) { RepeatBehavior = RepeatBehavior.Forever });
        }

        static Ellipse Disc(double r, Brush fill)
        {
            var e = new Ellipse { Width = r * 2, Height = r * 2, Fill = fill };
            SetLeft(e, -r); SetTop(e, -r);
            return e;
        }

        // A soft round sprite: a square with a radial brush that is clear at the edge
        static Rectangle Square(double r, Brush fill)
        {
            var e = new Rectangle { Width = r * 2, Height = r * 2, Fill = fill };
            SetLeft(e, -r); SetTop(e, -r);
            return e;
        }

        // A stroked circle of radius r centred on the origin (stroke centred on r)
        static Ellipse Ring(double r, Color c, double thickness, double opacity) =>
            RingB(r, new SolidColorBrush(c), thickness, opacity);

        static Ellipse RingB(double r, Brush stroke, double thickness, double opacity)
        {
            double o = r + thickness / 2;
            var e = new Ellipse
            {
                Width = o * 2, Height = o * 2, Stroke = stroke, StrokeThickness = thickness,
                Opacity = opacity, RenderTransformOrigin = new Point(0.5, 0.5)
            };
            SetLeft(e, -o); SetTop(e, -o);
            return e;
        }
    }
}

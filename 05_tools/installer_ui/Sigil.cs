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
    public sealed class Sigil : Canvas
    {
        public const int N = 28;
        const string Runes = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟᚪᚫᚣᛡ";
        const string Letters = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي";
        const double GlyphR = 151, ArcR = 175;

        static readonly Color Gold = (Color)ColorConverter.ConvertFromString("#E2B96A");
        static readonly Color GoldLight = (Color)ColorConverter.ConvertFromString("#F7E3AE");
        static readonly Color Ice = (Color)ColorConverter.ConvertFromString("#9FDCF0");
        static readonly IEasingFunction Out = new CubicEase { EasingMode = EasingMode.EaseOut };
        static readonly IEasingFunction InOut = new CubicEase { EasingMode = EasingMode.EaseInOut };
        static readonly IEasingFunction Back = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 1.1 };

        sealed class Slot
        {
            public TextBlock Rune, Letter; public ScaleTransform LetterScale; public Ellipse Flash; public bool Lit;
        }
        sealed class Spark
        {
            public Ellipse E; public TranslateTransform T; public double X, Y, Vx, Vy, Life, Max;
        }

        readonly Slot[] _slots = new Slot[N];
        readonly List<Spark> _sparks = new List<Spark>();
        readonly Random _rnd = new Random();
        readonly RotateTransform _glyphRot = new RotateTransform();
        readonly Canvas _fx = new Canvas();
        readonly Ellipse _glow, _head, _headGlow;
        readonly Path _arc, _arcGlow, _check;
        readonly TextBlock _dad, _digits;
        readonly FrameworkElement _percent;
        readonly DispatcherTimer _tease;
        SigilMode _mode = SigilMode.Idle;
        double _p, _hx, _hy = -ArcR, _emit;

        public Sigil()
        {
            IsHitTestVisible = false;
            var cairo = (FontFamily)Application.Current.Resources["Cairo"];
            var amiri = (FontFamily)Application.Current.Resources["Amiri"];
            var runes = (FontFamily)Application.Current.Resources["Runes"];
            var metal = (Brush)Application.Current.Resources["GoldMetalHot"];

            // Breathing halo
            _glow = Disc(285, Radial(Color.FromArgb(120, Gold.R, Gold.G, Gold.B), Color.FromArgb(0, Gold.R, Gold.G, Gold.B)));
            Children.Add(_glow);
            Loop(_glow, OpacityProperty, 0.45, 0.95, 3.2);

            // Dark plate so glyphs stay legible over the aurora
            var plate = Radial(Color.FromArgb(215, 4, 6, 12), Color.FromArgb(0, 4, 6, 12));
            plate.GradientStops.Insert(1, new GradientStop(Color.FromArgb(190, 4, 6, 12), 0.78));
            Children.Add(Disc(232, plate));

            Children.Add(Ring(199, Gold, 1, 0.45));
            var ticks = Ring(190, Gold, 6, 0.5);
            ticks.StrokeDashArray = new DoubleCollection { 0.22, 2.432 };
            Spin(ticks, 0, 360, 140);
            Children.Add(ticks);
            var ticks2 = Ring(190, GoldLight, 10, 0.75);
            ticks2.StrokeDashArray = new DoubleCollection { 0.16, 16.892 / 1.0 };
            Spin(ticks2, 0, 360, 140);
            Children.Add(ticks2);

            // Cardinal studs
            for (int i = 0; i < 4; i++)
            {
                var d = new Rectangle { Width = 9, Height = 9, Fill = metal };
                var tg = new TransformGroup();
                tg.Children.Add(new RotateTransform(45, 4.5, 4.5));
                tg.Children.Add(new TranslateTransform(-4.5, -199 - 4.5));
                tg.Children.Add(new RotateTransform(i * 90));
                d.RenderTransform = tg;
                Children.Add(d);
            }

            // The glyph ring
            var glyphs = new Canvas { RenderTransform = _glyphRot };
            for (int i = 0; i < N; i++)
            {
                double deg = -i * 360.0 / N, a = deg * Math.PI / 180;
                var s = new Slot { LetterScale = new ScaleTransform(0.3, 0.3) };
                var cell = new Grid { Width = 46, Height = 46, RenderTransform = new RotateTransform(deg, 23, 23) };
                SetLeft(cell, Math.Sin(a) * GlyphR - 23);
                SetTop(cell, -Math.Cos(a) * GlyphR - 23);

                s.Flash = new Ellipse { Margin = new Thickness(-9), Opacity = 0, Fill = Radial(Color.FromArgb(200, 255, 226, 150), Color.FromArgb(0, 255, 226, 150)) };
                s.Rune = new TextBlock
                {
                    Text = Runes[i].ToString(), FontFamily = runes, FontSize = 23, Opacity = 0.62,
                    Foreground = new SolidColorBrush(Ice),
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center
                };
                s.Letter = new TextBlock
                {
                    Text = Letters[i].ToString(), FontFamily = amiri, FontWeight = FontWeights.Bold, FontSize = 25, Opacity = 0,
                    Foreground = new SolidColorBrush(GoldLight), FlowDirection = FlowDirection.RightToLeft,
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

            // Progress track, arc and comet head
            Children.Add(Ring(ArcR, Colors.White, 1, 0.13));
            _arcGlow = new Path
            {
                Stroke = new SolidColorBrush(Gold), StrokeThickness = 9, Opacity = 0.75,
                StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round,
                Effect = new BlurEffect { Radius = 12 }
            };
            _arc = new Path
            {
                Stroke = metal, StrokeThickness = 3.2,
                StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round
            };
            _headGlow = Disc(17, Radial(Color.FromArgb(255, 255, 240, 200), Color.FromArgb(0, 255, 200, 110)));
            _head = Disc(4, Brushes.White);
            _headGlow.RenderTransform = _head.RenderTransform = new TranslateTransform(0, -ArcR);
            _arc.Opacity = _arcGlow.Opacity = _head.Opacity = _headGlow.Opacity = 0;
            Children.Add(_arcGlow);
            Children.Add(_arc);
            Children.Add(_headGlow);
            Children.Add(_head);

            // Inner machinery: dashed ice ring and the eight-pointed star
            var ice = Ring(124, Ice, 1.2, 0.6);
            ice.StrokeDashArray = new DoubleCollection { 14, 5, 2, 5 };
            Spin(ice, 360, 0, 50);
            Children.Add(ice);
            Children.Add(Ring(116, Gold, 1, 0.3));

            var star = new Canvas();
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
            Spin(star, 0, 360, 110);
            Children.Add(star);

            var core = Radial(Color.FromArgb(255, 20, 30, 48), Color.FromArgb(255, 5, 8, 14));
            var disc = Disc(79, core);
            disc.Stroke = metal; disc.StrokeThickness = 1.6;
            Children.Add(disc);
            Children.Add(Ring(72, Gold, 1, 0.28));

            // Centre: the letter Dad (Arabic is "the language of the Dad"), then the percentage, then the seal
            _dad = new TextBlock
            {
                Text = "ض", FontFamily = amiri, FontWeight = FontWeights.Bold, FontSize = 104, Foreground = metal,
                Width = 200, TextAlignment = TextAlignment.Center, FlowDirection = FlowDirection.RightToLeft,
                Effect = new DropShadowEffect { Color = Gold, BlurRadius = 26, ShadowDepth = 0, Opacity = 0.75 }
            };
            SetLeft(_dad, -100); SetTop(_dad, -108);
            Children.Add(_dad);

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

            _check = new Path
            {
                Data = Geometry.Parse("M-30,2 L-9,23 L32,-20"), Stroke = metal, StrokeThickness = 9,
                StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round,
                StrokeDashArray = new DoubleCollection { 10.2, 10.2 }, StrokeDashOffset = 10.2,
                Effect = new DropShadowEffect { Color = Gold, BlurRadius = 22, ShadowDepth = 0, Opacity = 0.9 }
            };
            Children.Add(_check);

            // Orbiting motes
            double[] orbitR = { 212, 136, 96 };
            for (int i = 0; i < 3; i++)
            {
                var orbit = new Canvas();
                var m = Disc(i == 0 ? 2.6 : 2, new SolidColorBrush(i == 1 ? Ice : GoldLight));
                m.RenderTransform = new TranslateTransform(0, -orbitR[i]);
                m.Effect = new DropShadowEffect { Color = i == 1 ? Ice : Gold, BlurRadius = 10, ShadowDepth = 0, Opacity = 1 };
                orbit.Children.Add(m);
                Spin(orbit, i % 2 == 0 ? 0 : 360, i % 2 == 0 ? 360 : 0, 17 + i * 9);
                Children.Add(orbit);
            }

            Children.Add(_fx);
            for (int i = 0; i < 44; i++)
            {
                var sp = new Spark { T = new TranslateTransform() };
                double sz = 1.4 + _rnd.NextDouble() * 2.2;
                sp.E = new Ellipse { Width = sz, Height = sz, Opacity = 0, RenderTransform = sp.T, Fill = new SolidColorBrush(_rnd.NextDouble() < 0.5 ? GoldLight : Color.FromRgb(255, 170, 90)) };
                _fx.Children.Add(sp.E);
                _sparks.Add(sp);
            }

            StartIdleSpin();
            _tease = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(520) };
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
                Fade(_arc, 0, 300); Fade(_arcGlow, 0, 300); Fade(_head, 0, 200); Fade(_headGlow, 0, 200);
                Fade(_percent, 0, 250); Fade(_dad, 1, 600, 200);
                _check.BeginAnimation(Shape.StrokeDashOffsetProperty, null);
                StartIdleSpin();
            }
            else if (mode == SigilMode.Progress)
            {
                _tease.Stop();
                for (int i = 0; i < N; i++) Strike(i, false, 0);
                // Settle the ring so the first letter sits at twelve o'clock
                double cur = _glyphRot.Angle;
                _glyphRot.BeginAnimation(RotateTransform.AngleProperty,
                    new DoubleAnimation(cur, Math.Round(cur / 360) * 360, TimeSpan.FromMilliseconds(900)) { EasingFunction = InOut });
                Fade(_dad, 0, 350);
                Fade(_percent, 1, 500, 300);
                Fade(_arc, 1, 400, 500); Fade(_arcGlow, 0.75, 400, 500); Fade(_head, 1, 300, 600); Fade(_headGlow, 1, 300, 600);
                SetProgress(0);
            }
            else
            {
                _tease.Stop();
                for (int i = 0; i < N; i++) Strike(i, true, i * 10);
                Fade(_percent, 0, 300); Fade(_dad, 0, 300);
                Fade(_head, 0, 400); Fade(_headGlow, 0, 400);
                _check.BeginAnimation(Shape.StrokeDashOffsetProperty,
                    new DoubleAnimation(10.2, 0, TimeSpan.FromMilliseconds(620)) { BeginTime = TimeSpan.FromMilliseconds(380), EasingFunction = Out });
                Pulse(GoldLight, 0); Pulse(Gold, 260); Pulse(Ice, 520);
                StartIdleSpin();
            }
        }

        /// <summary>0..1. Draws the arc and re-strikes runes as Arabic letters.</summary>
        public void SetProgress(double p)
        {
            p = Math.Max(0, Math.Min(1, p));
            _p = p;
            _digits.Text = ((int)Math.Round(p * 100)).ToString();

            double phi = Math.Min(p, 0.9995) * 2 * Math.PI;
            _hx = -Math.Sin(phi) * ArcR; _hy = -Math.Cos(phi) * ArcR;
            var fig = new PathFigure { StartPoint = new Point(0, -ArcR) };
            fig.Segments.Add(new ArcSegment(new Point(_hx, _hy), new Size(ArcR, ArcR), 0, p > 0.5, SweepDirection.Counterclockwise, true));
            var g = new PathGeometry();
            g.Figures.Add(fig);
            g.Freeze();
            _arc.Data = _arcGlow.Data = g;
            var ht = (TranslateTransform)_head.RenderTransform;
            ht.X = _hx; ht.Y = _hy;

            int lit = (int)Math.Floor(p * N + 0.5);
            for (int i = 0; i < N; i++)
                if (i < lit && !_slots[i].Lit) Strike(i, true, 0);
        }

        /// <summary>An expanding ring of light, used as feedback.</summary>
        public void Pulse(Color c, double delayMs = 0)
        {
            var ring = Ring(ArcR, c, 2.2, 0);
            var st = new ScaleTransform(1, 1);
            ring.RenderTransform = st;
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
                    double phi = _p * 2 * Math.PI, tx = Math.Cos(phi), ty = -Math.Sin(phi);
                    double spd = 30 + _rnd.NextDouble() * 110, spread = (_rnd.NextDouble() - 0.5) * 1.5;
                    sp.X = _hx; sp.Y = _hy;
                    sp.Vx = tx * spd + _hx / ArcR * spd * spread;
                    sp.Vy = ty * spd + _hy / ArcR * spd * spread;
                    sp.Max = sp.Life = 0.35 + _rnd.NextDouble() * 0.7;
                }
            }
            foreach (var sp in _sparks)
            {
                if (sp.Life <= 0) continue;
                sp.Life -= dt;
                sp.Vy += 120 * dt;
                sp.X += sp.Vx * dt; sp.Y += sp.Vy * dt;
                sp.T.X = sp.X; sp.T.Y = sp.Y;
                sp.E.Opacity = sp.Life <= 0 ? 0 : Math.Min(1, sp.Life / sp.Max * 1.4);
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

        static void Loop(UIElement el, DependencyProperty prop, double from, double to, double seconds)
        {
            el.BeginAnimation(prop, new DoubleAnimation(from, to, TimeSpan.FromSeconds(seconds))
            { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
        }

        static void Spin(UIElement el, double from, double to, double seconds)
        {
            var r = new RotateTransform();
            el.RenderTransform = r;
            r.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(from, to, TimeSpan.FromSeconds(seconds)) { RepeatBehavior = RepeatBehavior.Forever });
        }

        static RadialGradientBrush Radial(Color inner, Color outer)
        {
            var b = new RadialGradientBrush();
            b.GradientStops.Add(new GradientStop(inner, 0));
            b.GradientStops.Add(new GradientStop(outer, 1));
            return b;
        }

        static Ellipse Disc(double r, Brush fill)
        {
            var e = new Ellipse { Width = r * 2, Height = r * 2, Fill = fill };
            SetLeft(e, -r); SetTop(e, -r);
            return e;
        }

        // A stroked circle of radius r centred on the origin (stroke centred on r)
        static Ellipse Ring(double r, Color c, double thickness, double opacity)
        {
            double o = r + thickness / 2;
            var e = new Ellipse
            {
                Width = o * 2, Height = o * 2, Stroke = new SolidColorBrush(c), StrokeThickness = thickness,
                Opacity = opacity, RenderTransformOrigin = new Point(0.5, 0.5)
            };
            SetLeft(e, -o); SetTop(e, -o);
            return e;
        }
    }
}

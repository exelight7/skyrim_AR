using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;

namespace SkyrimArabicInstaller
{
    // The living backdrop: a northern night with aurora curtains, two moons,
    // layered ridgelines that parallax with the cursor, drifting fog and snow.
    // Purely visual. Everything is drawn in code, no image assets.
    public sealed class Scene
    {
        const double W = 1180, H = 700;

        static Color C(string hex) => (Color)ColorConverter.ConvertFromString(hex);

        sealed class Ray
        {
            public TranslateTransform T; public ScaleTransform S; public Ellipse E;
            public double X, Phase; public int Band;
        }
        sealed class Flake
        {
            public TranslateTransform T; public double X, Y, Speed, Sway, Phase, Depth; public bool Ember; public Ellipse E;
        }

        readonly Canvas _root;
        readonly Random _rnd = new Random(7);
        readonly List<Ray> _rays = new List<Ray>();
        readonly List<Flake> _flakes = new List<Flake>();
        readonly TranslateTransform _farT = new TranslateTransform(), _midT = new TranslateTransform(),
                                    _nearT = new TranslateTransform(), _skyT = new TranslateTransform(),
                                    _fog1 = new TranslateTransform(), _fog2 = new TranslateTransform(),
                                    _lightT = new TranslateTransform(-600, -600);
        readonly GradientStop[] _bandCore = new GradientStop[3], _bandMid = new GradientStop[3];
        readonly Canvas _aurora = new Canvas(), _raysOfDawn = new Canvas(), _embers = new Canvas();
        double _px, _py, _lx = 590, _ly = 300, _wind, _auroraGain = 1, _auroraGainTo = 1, _emberGain, _emberGainTo;

        public Scene(Canvas host)
        {
            _root = host;
            BuildSky();
            BuildAurora();
            BuildMountains();
            BuildSnow();
            BuildOverlays();
        }

        // ---------------- sky ----------------

        void BuildSky()
        {
            var sky = new Rectangle { Width = W, Height = H };
            var g = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0, 1) };
            g.GradientStops.Add(new GradientStop(C("#04060C"), 0));
            g.GradientStops.Add(new GradientStop(C("#081221"), 0.45));
            g.GradientStops.Add(new GradientStop(C("#11243A"), 0.78));
            g.GradientStops.Add(new GradientStop(C("#1A3046"), 1));
            sky.Fill = g;
            _root.Children.Add(sky);

            var stars = new Canvas { RenderTransform = _skyT };
            for (int i = 0; i < 130; i++)
            {
                double s = _rnd.NextDouble() < 0.12 ? 2.2 + _rnd.NextDouble() * 1.2 : 0.8 + _rnd.NextDouble() * 1.3;
                var e = new Ellipse
                {
                    Width = s, Height = s,
                    Fill = new SolidColorBrush(_rnd.NextDouble() < 0.25 ? C("#BFE6FF") : Colors.White),
                    Opacity = 0.25 + _rnd.NextDouble() * 0.6
                };
                Canvas.SetLeft(e, _rnd.NextDouble() * (W + 40) - 20);
                Canvas.SetTop(e, Math.Pow(_rnd.NextDouble(), 1.5) * 470);
                if (i % 3 == 0)
                    e.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(e.Opacity, 0.08, TimeSpan.FromSeconds(1.2 + _rnd.NextDouble() * 3))
                    {
                        AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever,
                        BeginTime = TimeSpan.FromSeconds(_rnd.NextDouble() * 4),
                        EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
                    });
                stars.Children.Add(e);
            }

            // Two moons, one large and pale, one small and warm
            stars.Children.Add(Moon(858, 124, 120, "#30BFE0FF", "#00BFE0FF"));
            stars.Children.Add(Moon(858, 124, 29, "#F2F6FF", "#B9C7DE", true));
            stars.Children.Add(Moon(912, 168, 42, "#30E8B48A", "#00E8B48A"));
            stars.Children.Add(Moon(912, 168, 10, "#F3D6BC", "#C59276", true));
            _root.Children.Add(stars);
        }

        static Ellipse Moon(double cx, double cy, double r, string inner, string outer, bool solid = false)
        {
            var b = new RadialGradientBrush { GradientOrigin = new Point(solid ? 0.36 : 0.5, solid ? 0.34 : 0.5) };
            b.GradientStops.Add(new GradientStop(C(inner), 0));
            b.GradientStops.Add(new GradientStop(C(outer), 1));
            var e = new Ellipse { Width = r * 2, Height = r * 2, Fill = b };
            Canvas.SetLeft(e, cx - r);
            Canvas.SetTop(e, cy - r);
            return e;
        }

        // ---------------- aurora ----------------

        static readonly string[][] Moods =
        {
            //            band 0 (low, bright)   band 1 (high veil)     band 2 (far)
            new[] { "#46F2C4", "#1FA98F", "#7C6BFF", "#4B3FC2", "#3FD0F0", "#1F7FA8" },   // night: teal + violet
            new[] { "#FFC85A", "#E07B22", "#FF7A3C", "#B23A1E", "#FFE9B0", "#D9A441" },   // forge: ember gold
            new[] { "#FFE9A8", "#E2B96A", "#7CF0D0", "#2FA98F", "#FFF6DC", "#E2B96A" },   // dawn: gold over teal
        };

        void BuildAurora()
        {
            var brushes = new RadialGradientBrush[3];
            for (int b = 0; b < 3; b++)
            {
                var br = new RadialGradientBrush
                {
                    Center = new Point(0.5, 0.6), GradientOrigin = new Point(0.5, 0.84),
                    RadiusX = 0.5, RadiusY = 0.4
                };
                _bandCore[b] = new GradientStop(C(Moods[0][b * 2]), 0);
                _bandMid[b] = new GradientStop(Color.FromArgb(90, 0, 0, 0), 0.4);
                br.GradientStops.Add(_bandCore[b]);
                br.GradientStops.Add(_bandMid[b]);
                br.GradientStops.Add(new GradientStop(Color.FromArgb(0, 0, 0, 0), 1));
                brushes[b] = br;
            }
            ApplyMood(0, 0);

            int[] counts = { 30, 24, 18 };
            double[] widths = { 120, 170, 140 };
            for (int b = 2; b >= 0; b--)
                for (int j = 0; j < counts[b]; j++)
                {
                    var r = new Ray
                    {
                        T = new TranslateTransform(), S = new ScaleTransform(1, 1),
                        X = -120 + j * (W + 240) / counts[b] + _rnd.NextDouble() * 18,
                        Phase = _rnd.NextDouble() * Math.PI * 2, Band = b
                    };
                    var tg = new TransformGroup();
                    tg.Children.Add(r.S);
                    tg.Children.Add(r.T);
                    r.E = new Ellipse
                    {
                        Width = widths[b], Height = 400, Fill = brushes[b],
                        RenderTransform = tg, RenderTransformOrigin = new Point(0.5, 1)
                    };
                    _aurora.Children.Add(r.E);
                    _rays.Add(r);
                }
            _root.Children.Add(_aurora);
        }

        void ApplyMood(int mood, double ms)
        {
            for (int b = 0; b < 3; b++)
            {
                Color core = C(Moods[mood][b * 2]), mid = C(Moods[mood][b * 2 + 1]);
                mid.A = 90;
                if (ms <= 0) { _bandCore[b].Color = core; _bandMid[b].Color = mid; continue; }
                var d = TimeSpan.FromMilliseconds(ms);
                _bandCore[b].BeginAnimation(GradientStop.ColorProperty, new ColorAnimation(core, d));
                _bandMid[b].BeginAnimation(GradientStop.ColorProperty, new ColorAnimation(mid, d));
            }
        }

        /// <summary>0..4 = wizard page. Shifts the sky's colour and energy.</summary>
        public void SetPage(int page)
        {
            ApplyMood(page == 3 ? 1 : page == 4 ? 2 : 0, 1800);
            _auroraGainTo = page == 3 ? 1.25 : page == 4 ? 1.5 : page == 0 ? 1 : 0.8;
            _emberGainTo = page == 3 ? 1 : page == 4 ? 0.55 : 0.12;
            _raysOfDawn.Visibility = page == 4 ? Visibility.Visible : Visibility.Collapsed;
            _raysOfDawn.BeginAnimation(UIElement.OpacityProperty,
                new DoubleAnimation(page == 4 ? 1 : 0, TimeSpan.FromSeconds(page == 4 ? 2.2 : 0.6)));
        }

        // ---------------- mountains ----------------

        void BuildMountains()
        {
            var far = Ridge(446, 330, 0.6, 11, out _);
            far.Fill = Vertical("#2A4468", "#0F1C30", 330, 560);
            far.RenderTransform = _farT;
            far.Stroke = new SolidColorBrush(Color.FromArgb(46, 159, 220, 240));
            far.StrokeThickness = 1;
            _root.Children.Add(far);

            var fogA = Fog(1100, 150, 40);
            Canvas.SetLeft(fogA, -200); Canvas.SetTop(fogA, 470);
            fogA.RenderTransform = _fog1;
            _root.Children.Add(fogA);

            var mid = Ridge(566, 240, 0.63, 41, out _);
            mid.Fill = Vertical("#152742", "#080F1C", 470, 640);
            mid.RenderTransform = _midT;
            _root.Children.Add(mid);

            var fogB = Fog(1300, 130, 30);
            Canvas.SetLeft(fogB, 100); Canvas.SetTop(fogB, 560);
            fogB.RenderTransform = _fog2;
            _root.Children.Add(fogB);

            var near = Ridge(628, 44, 0.5, 5, out var pts);
            // A pine forest along the nearest ridge
            var geo = (PathGeometry)near.Data;
            var pr = new Random(3);
            for (int i = 0; i < 64; i++)
            {
                var p = pts[pr.Next(pts.Count)];
                double x = p.X + pr.NextDouble() * 16, h = 20 + pr.NextDouble() * 34, w = h * 0.36, y = p.Y + 6;
                var f = new PathFigure { StartPoint = new Point(x - w, y), IsClosed = true };
                f.Segments.Add(new LineSegment(new Point(x - w * 0.45, y - h * 0.42), true));
                f.Segments.Add(new LineSegment(new Point(x - w * 0.7, y - h * 0.42), true));
                f.Segments.Add(new LineSegment(new Point(x, y - h), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.7, y - h * 0.42), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.45, y - h * 0.42), true));
                f.Segments.Add(new LineSegment(new Point(x + w, y), true));
                geo.Figures.Add(f);
            }
            geo.FillRule = FillRule.Nonzero;
            near.Fill = Vertical("#060A13", "#03050A", 590, 700);
            near.RenderTransform = _nearT;
            _root.Children.Add(near);
        }

        static Brush Vertical(string top, string bottom, double y0, double y1)
        {
            var g = new LinearGradientBrush { MappingMode = BrushMappingMode.Absolute, StartPoint = new Point(0, y0), EndPoint = new Point(0, y1) };
            g.GradientStops.Add(new GradientStop(C(top), 0));
            g.GradientStops.Add(new GradientStop(C(bottom), 1));
            return g;
        }

        static Ellipse Fog(double w, double h, byte alpha)
        {
            var b = new RadialGradientBrush();
            b.GradientStops.Add(new GradientStop(Color.FromArgb(alpha, 190, 220, 240), 0));
            b.GradientStops.Add(new GradientStop(Color.FromArgb(0, 190, 220, 240), 1));
            return new Ellipse { Width = w, Height = h, Fill = b };
        }

        // Midpoint-displacement ridgeline, deterministic per seed
        static Path Ridge(double baseY, double amp, double rough, int seed, out List<Point> pts)
        {
            var r = new Random(seed);
            const int n = 129;
            var h = new double[n];
            h[0] = r.NextDouble() - 0.5; h[n - 1] = r.NextDouble() - 0.5;
            double a = 1;
            for (int step = n - 1; step > 1; step /= 2, a *= rough)
                for (int i = step / 2; i < n; i += step)
                    h[i] = (h[i - step / 2] + h[i + step / 2]) / 2 + (r.NextDouble() - 0.5) * a;

            pts = new List<Point>();
            var fig = new PathFigure { StartPoint = new Point(-60, H + 40), IsClosed = true };
            for (int i = 0; i < n; i++)
            {
                var p = new Point(-60 + i * (W + 120) / (n - 1), baseY - h[i] * amp);
                pts.Add(p);
                fig.Segments.Add(new LineSegment(p, true));
            }
            fig.Segments.Add(new LineSegment(new Point(W + 60, H + 40), true));
            var g = new PathGeometry();
            g.Figures.Add(fig);
            return new Path { Data = g };
        }

        // ---------------- snow & embers ----------------

        void BuildSnow()
        {
            var snow = new Canvas();
            for (int i = 0; i < 120; i++)
            {
                bool ember = i >= 84;
                double depth = _rnd.NextDouble();               // 0 far .. 1 near
                double size = ember ? 1.6 + _rnd.NextDouble() * 2.2 : 1 + depth * 3.6;
                var f = new Flake
                {
                    T = new TranslateTransform(), Depth = depth, Ember = ember,
                    X = _rnd.NextDouble() * W, Y = _rnd.NextDouble() * H,
                    Speed = ember ? 16 + _rnd.NextDouble() * 34 : 16 + depth * 52 + _rnd.NextDouble() * 10,
                    Sway = 6 + _rnd.NextDouble() * 22, Phase = _rnd.NextDouble() * Math.PI * 2
                };
                f.E = new Ellipse
                {
                    Width = size, Height = size, RenderTransform = f.T,
                    Fill = ember ? (Brush)new SolidColorBrush(_rnd.NextDouble() < 0.5 ? C("#FFD98A") : C("#FF9D5A")) : Brushes.White,
                    Opacity = ember ? 0 : 0.14 + depth * 0.5
                };
                (ember ? _embers : snow).Children.Add(f.E);
                _flakes.Add(f);
            }
            _root.Children.Add(snow);
            _root.Children.Add(_embers);
        }

        // ---------------- overlays ----------------

        void BuildOverlays()
        {
            // Shafts of dawn light, only lit on the final screen
            _raysOfDawn.Opacity = 0;
            _raysOfDawn.Effect = new System.Windows.Media.Effects.BlurEffect { Radius = 22 };
            for (int i = 0; i < 9; i++)
            {
                double ang = -52 + i * 13 + _rnd.NextDouble() * 6;
                var b = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0, 1) };
                b.GradientStops.Add(new GradientStop(Color.FromArgb(44, 255, 233, 168), 0));
                b.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 233, 168), 1));
                var rot = new RotateTransform(ang, 0, 0);
                var p = new Path
                {
                    Data = Geometry.Parse(i % 2 == 0 ? "M-4,0 L4,0 L44,820 L-44,820 Z" : "M-3,0 L3,0 L22,820 L-22,820 Z"), Fill = b, RenderTransform = rot,
                    Opacity = 0.5
                };
                Canvas.SetLeft(p, 590); Canvas.SetTop(p, -60);
                rot.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(ang - 4, ang + 4, TimeSpan.FromSeconds(7 + i))
                { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
                p.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.25, 0.75, TimeSpan.FromSeconds(3 + i * 0.7))
                { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever });
                _raysOfDawn.Children.Add(p);
            }
            _root.Children.Add(_raysOfDawn);

            // Soft light that trails the cursor, like a torch held up to the dark
            var lb = new RadialGradientBrush();
            lb.GradientStops.Add(new GradientStop(Color.FromArgb(34, 200, 235, 255), 0));
            lb.GradientStops.Add(new GradientStop(Color.FromArgb(0, 200, 235, 255), 1));
            _root.Children.Add(new Ellipse { Width = 620, Height = 620, Fill = lb, RenderTransform = _lightT });

            var vg = new RadialGradientBrush { RadiusX = 0.75, RadiusY = 0.8 };
            vg.GradientStops.Add(new GradientStop(Color.FromArgb(0, 0, 0, 0), 0.55));
            vg.GradientStops.Add(new GradientStop(Color.FromArgb(215, 2, 3, 8), 1));
            _root.Children.Add(new Rectangle { Width = W, Height = H, Fill = vg });
        }

        // ---------------- per-frame ----------------

        /// <param name="mx">cursor x in scene pixels</param>
        public void Tick(double dt, double t, double mx, double my)
        {
            // Parallax: eased toward the cursor
            double tx = (mx / W - 0.5) * 2, ty = (my / H - 0.5) * 2;
            _px += (tx - _px) * Math.Min(1, dt * 3);
            _py += (ty - _py) * Math.Min(1, dt * 3);
            _skyT.X = -_px * 5; _skyT.Y = -_py * 3;
            _farT.X = -_px * 9; _farT.Y = -_py * 3;
            _midT.X = -_px * 17; _midT.Y = -_py * 5;
            _nearT.X = -_px * 30; _nearT.Y = -_py * 8;
            _fog1.X = Math.Sin(t * 0.05) * 160 - _px * 12;
            _fog2.X = Math.Cos(t * 0.04) * 200 - _px * 22;

            _lx += (mx - _lx) * Math.Min(1, dt * 5);
            _ly += (my - _ly) * Math.Min(1, dt * 5);
            _lightT.X = _lx - 310; _lightT.Y = _ly - 310;

            _auroraGain += (_auroraGainTo - _auroraGain) * Math.Min(1, dt * 0.9);
            _emberGain += (_emberGainTo - _emberGain) * Math.Min(1, dt * 1.2);

            // Aurora: each soft ray rides a slow travelling wave
            foreach (var r in _rays)
            {
                double x = r.X - _px * (4 + r.Band * 3);
                double baseY = r.Band == 0 ? 120 : r.Band == 1 ? 40 : 170;
                double wave = Math.Sin(x * 0.0042 + t * (0.16 + r.Band * 0.05) + r.Band * 2.1) * 62
                            + Math.Sin(x * 0.0118 - t * 0.24 + r.Band) * 24;
                double shimmer = 0.5 + 0.5 * Math.Sin(x * 0.019 + t * (0.9 + r.Band * 0.3) + r.Phase);
                double curtain = 0.5 + 0.5 * Math.Sin(x * 0.0061 - t * 0.21 + r.Band * 1.3);
                r.T.X = x;
                r.T.Y = baseY + wave;
                r.S.ScaleY = 0.62 + 0.5 * curtain + 0.16 * shimmer;
                double a = (r.Band == 0 ? 0.44 : r.Band == 1 ? 0.3 : 0.2) * (0.25 + 0.75 * curtain) * (0.7 + 0.3 * shimmer);
                r.E.Opacity = Math.Min(0.7, a * _auroraGain);
            }

            // Snow falls, embers rise; a slow gust leans everything
            _wind = Math.Sin(t * 0.23) * 26 + Math.Sin(t * 0.61) * 10;
            foreach (var f in _flakes)
            {
                if (f.Ember)
                {
                    f.Y -= f.Speed * dt * (0.5 + _emberGain);
                    if (f.Y < -10) { f.Y = H + 10; f.X = _rnd.NextDouble() * W; }
                    double life = Math.Max(0, Math.Min(1, f.Y / H));
                    f.E.Opacity = _emberGain * (0.25 + 0.75 * life) * (0.6 + 0.4 * Math.Sin(t * 5 + f.Phase));
                    f.T.X = f.X + Math.Sin(t * 1.1 + f.Phase) * f.Sway;
                }
                else
                {
                    f.Y += f.Speed * dt;
                    f.X += _wind * (0.3 + f.Depth) * dt;
                    if (f.Y > H + 8) { f.Y = -8; f.X = _rnd.NextDouble() * W; }
                    if (f.X > W + 10) f.X -= W + 20; else if (f.X < -10) f.X += W + 20;
                    f.T.X = f.X + Math.Sin(t * 0.8 + f.Phase) * f.Sway - _px * 26 * f.Depth;
                }
                f.T.Y = f.Y;
            }
        }
    }
}

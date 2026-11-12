using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;

namespace SkyrimArabicInstaller
{
    // Shared drawing helpers. The performance rules the whole UI follows:
    //   - anything that only moves, rotates or fades as a rigid body is rasterised once (BitmapCache)
    //     so the render thread never re-tessellates it;
    //   - soft glows are gradients or pre-blurred cached layers, never a live BlurEffect;
    //   - soft particles are rectangles with a radial brush (two triangles, no curve tessellation);
    //   - the cost of a frame is the NUMBER of things drawn, not their size: fields of particles are
    //     baked into a few tiling textures and scrolled, instead of moving each particle;
    //   - anything that fades every frame fades through its BRUSH, never UIElement.Opacity: element
    //     opacity makes the renderer open a separate blend layer per element per frame.
    static class Fx
    {
        /// <summary>Device pixels per WPF unit, set once the window has a presentation source.</summary>
        public static double Dpi = 1;

        public static Color C(string hex) => (Color)ColorConverter.ConvertFromString(hex);

        public static BitmapCache Cache(double scale = 1) =>
            new BitmapCache { RenderAtScale = Dpi * scale, EnableClearType = false, SnapsToDevicePixels = false };

        public static T Frozen<T>(T f) where T : Freezable { f.Freeze(); return f; }

        public static RadialGradientBrush Radial(params Color[] stops)
        {
            var b = new RadialGradientBrush();
            for (int i = 0; i < stops.Length; i++)
                b.GradientStops.Add(new GradientStop(stops[i], stops.Length == 1 ? 0 : (double)i / (stops.Length - 1)));
            return b;
        }

        public static Color A(Color c, byte a) => Color.FromArgb(a, c.R, c.G, c.B);

        /// <summary>
        /// Draws once into a bitmap. The pixels are copied out into an ordinary immutable bitmap,
        /// which the renderer uploads once and keeps (a RenderTargetBitmap is treated as live).
        /// scale = device pixels per unit; pass 1 for tiles that must keep an exact pixel size.
        /// </summary>
        public static BitmapSource Bake(double w, double h, Action<DrawingContext> draw, double scale = 0)
        {
            if (scale <= 0) scale = Dpi;
            var dv = new DrawingVisual();
            using (var dc = dv.RenderOpen()) draw(dc);
            int pw = (int)Math.Ceiling(w * scale), ph = (int)Math.Ceiling(h * scale);
            var rtb = new RenderTargetBitmap(pw, ph, 96 * scale, 96 * scale, PixelFormats.Pbgra32);
            rtb.Render(dv);
            var px = new byte[pw * ph * 4];
            rtb.CopyPixels(px, pw * 4, 0);
            var bmp = BitmapSource.Create(pw, ph, 96 * scale, 96 * scale, PixelFormats.Pbgra32, null, px, pw * 4);
            bmp.Freeze();
            return bmp;
        }

        /// <summary>A soft dot, repeated at the tile edges so the tile wraps without a seam.</summary>
        public static void Dot(DrawingContext dc, Brush b, double x, double y, double size, double opacity, double tw, double th)
        {
            dc.PushOpacity(opacity);
            for (int ix = -1; ix <= 1; ix++)
                for (int iy = -1; iy <= 1; iy++)
                {
                    double px = x + ix * tw, py = y + iy * th;
                    if (px + size < 0 || px > tw || py + size < 0 || py > th) continue;
                    dc.DrawRectangle(b, null, new Rect(px, py, size, size));
                }
            dc.Pop();
        }
    }

    // The living backdrop: a northern night with aurora curtains, two moons,
    // four ridgelines that parallax with the cursor, drifting fog and snow.
    // Purely visual. Everything is drawn in code, no image assets.
    public sealed class Scene
    {
        const double W = 1180, H = 700;

        static Color C(string hex) => Fx.C(hex);

        sealed class Ray
        {
            public TranslateTransform T; public ScaleTransform S; public Brush B; public Rectangle E; public bool Hidden;
            public double X, Phase, Lift; public int Band;
        }
        // A sheet of baked particles that scrolls and wraps: one quad, however many flakes are on it
        sealed class Sheet
        {
            public TranslateTransform T; public ImageBrush B; public double X, Y, Speed, Sway, Phase, Depth; public bool Ember;
        }
        const double TW = 512, TH = 1024;      // powers of two: such textures repeat natively on any GPU

        readonly Canvas _root;
        readonly Random _rnd = new Random(7);
        readonly List<Ray> _rays = new List<Ray>();
        readonly List<Sheet> _sheets = new List<Sheet>();
        readonly TranslateTransform _farT = new TranslateTransform(), _midT = new TranslateTransform(),
                                    _nearT = new TranslateTransform(), _skyT = new TranslateTransform(),
                                    _backT = new TranslateTransform(),
                                    _fog1 = new TranslateTransform(), _fog2 = new TranslateTransform(),
                                    _lightT = new TranslateTransform(-600, -600);
        readonly GradientStop[] _bandCore = new GradientStop[3], _bandMid = new GradientStop[3];
        readonly Canvas _aurora = new Canvas(), _dawn = new Canvas(), _embers = new Canvas();
        Rectangle _meteor;
        double _px, _py, _lx = 590, _ly = 300, _wind, _auroraGain = 1, _auroraGainTo = 1, _emberGain, _emberGainTo, _meteorIn = 5;

        /// <summary>Profiling aid: switch whole groups off to see what each one costs.</summary>
        public void Skip(string what)
        {
            foreach (UIElement c in _root.Children)
                if (c is FrameworkElement fe && fe.Tag as string == what) fe.Visibility = Visibility.Collapsed;
        }

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
            var g = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0, 1) };
            g.GradientStops.Add(new GradientStop(C("#04060C"), 0));
            g.GradientStops.Add(new GradientStop(C("#071120"), 0.42));
            g.GradientStops.Add(new GradientStop(C("#10243B"), 0.74));
            g.GradientStops.Add(new GradientStop(C("#1D3550"), 1));
            _root.Children.Add(new Rectangle { Width = W, Height = H, Fill = Fx.Frozen(g) });

            // Fixed stars and both moons are drawn once; only the twinklers stay live.
            var still = new Canvas();
            var live = new Canvas();
            var white = Fx.Frozen(new SolidColorBrush(Colors.White));
            var blue = Fx.Frozen(new SolidColorBrush(C("#BFE6FF")));
            var soft = Fx.Frozen(Fx.Radial(Colors.White, Color.FromArgb(150, 220, 240, 255), Color.FromArgb(0, 200, 230, 255)));
            // Twinkling stars are baked into five sparse sheets; each sheet breathes as one texture
            var twinkle = new List<double[]>[5];
            for (int k = 0; k < twinkle.Length; k++) twinkle[k] = new List<double[]>();
            for (int i = 0; i < 170; i++)
            {
                double x = _rnd.NextDouble() * (W + 40) - 20, y = Math.Pow(_rnd.NextDouble(), 1.5) * 480;
                if (i % 4 == 0)
                {
                    double s = 3.5 + _rnd.NextDouble() * 4.5, o = 0.45 + _rnd.NextDouble() * 0.55;
                    twinkle[i / 4 % twinkle.Length].Add(new[] { x, y, s, o });
                }
                else
                {
                    double s = 0.8 + _rnd.NextDouble() * 1.2;
                    var e = new Rectangle { Width = s, Height = s, Fill = _rnd.NextDouble() < 0.25 ? blue : white, Opacity = 0.2 + _rnd.NextDouble() * 0.55 };
                    Canvas.SetLeft(e, x); Canvas.SetTop(e, y);
                    still.Children.Add(e);
                }
            }

            for (int k = 0; k < twinkle.Length; k++)
            {
                var group = twinkle[k];
                var sheet = new ImageBrush(Fx.Bake(W + 40, 500, dc =>
                {
                    foreach (var st in group) { dc.PushOpacity(st[3]); dc.DrawRectangle(soft, null, new Rect(st[0] + 20, st[1], st[2], st[2])); dc.Pop(); }
                })) { Stretch = Stretch.Fill };
                live.Children.Add(new Rectangle { Width = W + 40, Height = 500, Fill = sheet }.Put(-20, 0));
                sheet.BeginAnimation(Brush.OpacityProperty, new DoubleAnimation(1, 0.12, TimeSpan.FromSeconds(1.6 + k * 0.7))
                {
                    AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, BeginTime = TimeSpan.FromSeconds(k * 0.9),
                    EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
                });
            }

            // Two moons: one large and pale with a thin halo, one small and warm
            still.Children.Add(Moon(858, 124, 132, "#2CBFE0FF", "#00BFE0FF"));
            still.Children.Add(new Ellipse { Width = 124, Height = 124, Stroke = new SolidColorBrush(Color.FromArgb(26, 200, 230, 255)), StrokeThickness = 1 }.Put(858 - 62, 124 - 62));
            still.Children.Add(Moon(858, 124, 29, "#F4F8FF", "#AFC0DA", true));
            foreach (var cr in new[] { new[] { 868.0, 116, 7 }, new[] { 850.0, 134, 5 }, new[] { 864.0, 138, 3.5 }, new[] { 846.0, 114, 4 }, new[] { 872.0, 130, 2.5 } })
                still.Children.Add(new Ellipse { Width = cr[2] * 2, Height = cr[2] * 2, Fill = new SolidColorBrush(Color.FromArgb(30, 70, 90, 130)) }.Put(cr[0] - cr[2], cr[1] - cr[2]));
            still.Children.Add(Moon(912, 168, 44, "#30E8B48A", "#00E8B48A"));
            still.Children.Add(Moon(912, 168, 10, "#F6DAC0", "#BF8A6E", true));
            still.CacheMode = Fx.Cache();

            // A falling star, now and then
            var mg = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(1, 0) };
            mg.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0));
            mg.GradientStops.Add(new GradientStop(Color.FromArgb(120, 200, 235, 255), 0.7));
            mg.GradientStops.Add(new GradientStop(Colors.White, 1));
            _meteor = new Rectangle { Width = 150, Height = 1.8, Fill = Fx.Frozen(mg), Opacity = 0, RadiusX = 1, RadiusY = 1 };
            live.Children.Add(_meteor);

            var sky = new Canvas { RenderTransform = _skyT, Tag = "stars" };
            sky.Children.Add(still);
            sky.Children.Add(live);
            _root.Children.Add(sky);
        }

        static Ellipse Moon(double cx, double cy, double r, string inner, string outer, bool solid = false)
        {
            var b = new RadialGradientBrush { GradientOrigin = new Point(solid ? 0.36 : 0.5, solid ? 0.34 : 0.5) };
            b.GradientStops.Add(new GradientStop(C(inner), 0));
            b.GradientStops.Add(new GradientStop(C(outer), 1));
            return new Ellipse { Width = r * 2, Height = r * 2, Fill = b }.Put(cx - r, cy - r);
        }

        void LaunchMeteor()
        {
            double dir = _rnd.NextDouble() < 0.5 ? -1 : 1, dx = dir * (240 + _rnd.NextDouble() * 160), dy = 90 + _rnd.NextDouble() * 70;
            double x = 180 + _rnd.NextDouble() * 820, y = 20 + _rnd.NextDouble() * 170;
            var tt = new TranslateTransform(x, y);
            var tg = new TransformGroup();
            tg.Children.Add(new RotateTransform(Math.Atan2(dy, dx) * 180 / Math.PI, 150, 0.9));
            tg.Children.Add(tt);
            _meteor.RenderTransform = tg;
            var d = TimeSpan.FromSeconds(0.85);
            tt.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(x, x + dx, d));
            tt.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(y, y + dy, d));
            var o = new DoubleAnimationUsingKeyFrames { Duration = d };
            o.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromPercent(0)));
            o.KeyFrames.Add(new LinearDoubleKeyFrame(0.9, KeyTime.FromPercent(0.25)));
            o.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromPercent(1)));
            _meteor.BeginAnimation(UIElement.OpacityProperty, o);
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
            // One set of colour stops per band, shared by every ray of that band, so a mood
            // change recolours the whole curtain while each ray keeps its own brush opacity.
            var stops = new GradientStopCollection[3];
            for (int b = 0; b < 3; b++)
            {
                _bandCore[b] = new GradientStop(C(Moods[0][b * 2]), 0);
                _bandMid[b] = new GradientStop(Color.FromArgb(90, 0, 0, 0), 0.4);
                stops[b] = new GradientStopCollection { _bandCore[b], _bandMid[b], new GradientStop(Color.FromArgb(0, 0, 0, 0), 1) };
            }
            ApplyMood(0, 0);

            // Bands 0-2 are the soft body of each curtain; band 3 is a set of thin bright
            // needles that ride band 0 and give the curtain its rayed texture.
            int[] counts = { 20, 16, 12, 30 };
            double[] widths = { 180, 250, 210, 44 }, heights = { 400, 400, 400, 330 };
            foreach (int b in new[] { 2, 1, 0, 3 })
                for (int j = 0; j < counts[b]; j++)
                {
                    var r = new Ray
                    {
                        T = new TranslateTransform(), S = new ScaleTransform(1, 1),
                        X = -120 + j * (W + 240) / counts[b] + _rnd.NextDouble() * 18,
                        Phase = _rnd.NextDouble() * Math.PI * 2, Band = b, Lift = 400 - heights[b]
                    };
                    var tg = new TransformGroup();
                    tg.Children.Add(r.S);
                    tg.Children.Add(r.T);
                    // Bright near the lower edge, a long fade upward, fully clear before the shape ends
                    r.B = new RadialGradientBrush
                    {
                        Center = new Point(0.5, 0.6), GradientOrigin = new Point(0.5, 0.84),
                        RadiusX = 0.5, RadiusY = 0.4, GradientStops = stops[b == 3 ? 0 : b], Opacity = 0
                    };
                    r.E = new Rectangle
                    {
                        Width = widths[b], Height = heights[b], Fill = r.B,
                        RenderTransform = tg, RenderTransformOrigin = new Point(0.5, 1)
                    };
                    _aurora.Children.Add(r.E);
                    _rays.Add(r);
                }
            _aurora.Tag = "aurora";
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
        public void SetPage(int page, bool calm = false)
        {
            bool forge = page == 3 && !calm, dawn = page == 4 && !calm;
            ApplyMood(forge ? 1 : dawn ? 2 : 0, 1800);
            _auroraGainTo = forge ? 1.25 : dawn ? 1.5 : page == 0 ? 1 : 0.8;
            _emberGainTo = forge ? 1 : dawn ? 0.55 : 0.12;
            _dawn.Visibility = dawn ? Visibility.Visible : Visibility.Collapsed;
            _dawn.BeginAnimation(UIElement.OpacityProperty,
                new DoubleAnimation(dawn ? 1 : 0, TimeSpan.FromSeconds(dawn ? 2.2 : 0.6)));
        }

        // ---------------- mountains ----------------

        void BuildMountains()
        {
            // 1. A pale range on the horizon
            var back = Ridge(432, 210, 0.55, 77, out _);
            back.Fill = Vertical("#1D3454", "#152841", 340, 520);
            _root.Children.Add(Layer(_backT, back));

            // 2. The high peaks, with a snow line that catches the sky
            var far = Ridge(446, 330, 0.6, 11, out var farPts);
            far.Fill = Vertical("#2C4870", "#0F1C30", 320, 560);
            far.Stroke = new SolidColorBrush(Color.FromArgb(46, 159, 220, 240));
            far.StrokeThickness = 1;
            _root.Children.Add(Layer(_farT, far, SnowCaps(farPts, 404)));

            _root.Children.Add(Fog(1100, 150, 40, -200, 470, _fog1));

            // 3. Middle hills
            var mid = Ridge(566, 240, 0.63, 41, out _);
            mid.Fill = Vertical("#152742", "#080F1C", 470, 640);
            _root.Children.Add(Layer(_midT, mid));

            _root.Children.Add(Fog(1300, 130, 30, 100, 560, _fog2));

            // 4. A pine forest along the nearest ridge
            var near = Ridge(628, 44, 0.5, 5, out var pts);
            var geo = (PathGeometry)near.Data;
            var pr = new Random(3);
            for (int i = 0; i < 72; i++)
            {
                var p = pts[pr.Next(pts.Count)];
                double x = p.X + pr.NextDouble() * 16, h = 20 + pr.NextDouble() * 38, w = h * 0.34, y = p.Y + 6;
                var f = new PathFigure { StartPoint = new Point(x - w, y), IsClosed = true };
                f.Segments.Add(new LineSegment(new Point(x - w * 0.42, y - h * 0.36), true));
                f.Segments.Add(new LineSegment(new Point(x - w * 0.74, y - h * 0.36), true));
                f.Segments.Add(new LineSegment(new Point(x - w * 0.24, y - h * 0.68), true));
                f.Segments.Add(new LineSegment(new Point(x - w * 0.46, y - h * 0.68), true));
                f.Segments.Add(new LineSegment(new Point(x, y - h), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.46, y - h * 0.68), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.24, y - h * 0.68), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.74, y - h * 0.36), true));
                f.Segments.Add(new LineSegment(new Point(x + w * 0.42, y - h * 0.36), true));
                f.Segments.Add(new LineSegment(new Point(x + w, y), true));
                geo.Figures.Add(f);
            }
            geo.FillRule = FillRule.Nonzero;
            near.Fill = Vertical("#060A13", "#03050A", 590, 700);
            _root.Children.Add(Layer(_nearT, near));
        }

        // Each range is rasterised once; parallax then only slides a texture.
        static Canvas Layer(TranslateTransform t, params UIElement[] parts)
        {
            var c = new Canvas { RenderTransform = t, CacheMode = Fx.Cache(), Tag = "hills" };
            foreach (var p in parts) c.Children.Add(p);
            return c;
        }

        static Brush Vertical(string top, string bottom, double y0, double y1)
        {
            var g = new LinearGradientBrush { MappingMode = BrushMappingMode.Absolute, StartPoint = new Point(0, y0), EndPoint = new Point(0, y1) };
            g.GradientStops.Add(new GradientStop(C(top), 0));
            g.GradientStops.Add(new GradientStop(C(bottom), 1));
            return Fx.Frozen(g);
        }

        static Rectangle Fog(double w, double h, byte alpha, double x, double y, Transform t)
        {
            var b = Fx.Frozen(Fx.Radial(Color.FromArgb(alpha, 190, 220, 240), Color.FromArgb(0, 190, 220, 240)));
            return new Rectangle { Width = w, Height = h, Fill = b, RenderTransform = t }.Put(x, y);
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

        // Everything above the snow line, with a ragged lower edge
        static Path SnowCaps(List<Point> ridge, double line)
        {
            var g = new PathGeometry();
            int i = 0;
            while (i < ridge.Count)
            {
                if (ridge[i].Y >= line) { i++; continue; }
                int a = i;
                while (i < ridge.Count && ridge[i].Y < line) i++;
                int b = i - 1;
                var fig = new PathFigure { StartPoint = new Point(ridge[a].X - 4, line), IsClosed = true };
                for (int k = a; k <= b; k++) fig.Segments.Add(new LineSegment(ridge[k], true));
                fig.Segments.Add(new LineSegment(new Point(ridge[b].X + 4, line), true));
                for (int k = b; k >= a; k--)
                {
                    double depth = line - ridge[k].Y;                         // how far this point pokes above the line
                    double y = ridge[k].Y + depth * (k % 2 == 0 ? 0.92 : 0.5);  // snow runs down in tongues
                    fig.Segments.Add(new LineSegment(new Point(ridge[k].X + (k % 2 == 0 ? 3 : -2), y), true));
                }
                g.Figures.Add(fig);
            }
            var fill = new LinearGradientBrush { MappingMode = BrushMappingMode.Absolute, StartPoint = new Point(0, 300), EndPoint = new Point(0, line) };
            fill.GradientStops.Add(new GradientStop(Color.FromArgb(150, 214, 234, 255), 0));
            fill.GradientStops.Add(new GradientStop(Color.FromArgb(34, 180, 212, 245), 1));
            return new Path { Data = g, Fill = Fx.Frozen(fill) };
        }

        // ---------------- snow & embers ----------------

        void BuildSnow()
        {
            var snow = new Canvas { Tag = "snow" };
            _embers.Tag = "snow";
            var dot = Fx.Frozen(Fx.Radial(Colors.White, Color.FromArgb(205, 255, 255, 255), Color.FromArgb(0, 255, 255, 255)));
            var bokeh = Fx.Frozen(Fx.Radial(Color.FromArgb(120, 235, 245, 255), Color.FromArgb(95, 235, 245, 255), Color.FromArgb(70, 235, 245, 255), Color.FromArgb(0, 235, 245, 255)));
            var warmA = Fx.Frozen(Fx.Radial(C("#FFF1C4"), C("#FFD98A"), Color.FromArgb(0, 255, 190, 100)));
            var warmB = Fx.Frozen(Fx.Radial(C("#FFE0B0"), C("#FF9D5A"), Color.FromArgb(0, 255, 130, 60)));

            // Seven depths of snow, far to near, then one sheet of out-of-focus flakes close to the lens
            const int depths = 7;
            for (int k = 0; k <= depths; k++)
            {
                bool big = k == depths;
                double depth = big ? 1.25 : (double)k / (depths - 1);
                int count = big ? 5 : 8;
                var tile = Fx.Bake(TW, TH, dc =>
                {
                    for (int i = 0; i < count * 1.14; i++)
                    {
                        double size = big ? 13 + _rnd.NextDouble() * 11 : (2.2 + depth * 5.2) * (0.8 + _rnd.NextDouble() * 0.4);
                        Fx.Dot(dc, big ? bokeh : dot, _rnd.NextDouble() * TW, _rnd.NextDouble() * TH, size,
                               big ? 0.5 : (0.2 + depth * 0.6) * (0.75 + _rnd.NextDouble() * 0.25), TW, TH);
                    }
                }, 1);
                snow.Children.Add(AddSheet(tile, depth, false, 16 + depth * 56));
            }
            // Two sheets of embers that rise; their brightness follows the mood
            for (int k = 0; k < 2; k++)
            {
                var tile = Fx.Bake(TW, TH, dc =>
                {
                    for (int i = 0; i < 9; i++)
                        Fx.Dot(dc, _rnd.NextDouble() < 0.5 ? warmA : warmB, _rnd.NextDouble() * TW, _rnd.NextDouble() * TH,
                               3.5 + _rnd.NextDouble() * 4, 0.55 + _rnd.NextDouble() * 0.45, TW, TH);
                }, 1);
                _embers.Children.Add(AddSheet(tile, 0.5 + k * 0.5, true, 22 + k * 20));
            }
            _root.Children.Add(snow);
            _root.Children.Add(_embers);
        }

        Rectangle AddSheet(ImageSource tile, double depth, bool ember, double speed)
        {
            var s = new Sheet
            {
                T = new TranslateTransform(), Depth = depth, Ember = ember, Speed = speed,
                X = _rnd.NextDouble() * TW, Y = _rnd.NextDouble() * TH,
                Sway = 8 + _rnd.NextDouble() * 18, Phase = _rnd.NextDouble() * Math.PI * 2,
                B = new ImageBrush(tile) { TileMode = TileMode.Tile, Viewport = new Rect(0, 0, TW, TH), ViewportUnits = BrushMappingMode.Absolute, Stretch = Stretch.Fill }
            };
            if (ember) s.B.Opacity = 0; else s.B.Freeze();
            _sheets.Add(s);
            // One tile larger than the window on each axis, so any wrapped offset still covers it
            return new Rectangle { Width = Math.Ceiling(W / TW + 1) * TW, Height = Math.Ceiling(H / TH + 1) * TH, Fill = s.B, RenderTransform = s.T };
        }

        // ---------------- overlays ----------------

        void BuildOverlays()
        {
            // Shafts of dawn light for the final screen. Blurred once, cached at half
            // resolution, then only swayed and faded as two whole fans.
            _dawn.Opacity = 0;
            _dawn.Visibility = Visibility.Collapsed;
            for (int fan = 0; fan < 2; fan++)
            {
                var inner = new Canvas { Effect = new BlurEffect { Radius = 20 } };
                for (int i = fan; i < 10; i += 2)
                {
                    double ang = -56 + i * 12.5 + _rnd.NextDouble() * 6;
                    var b = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0, 1) };
                    b.GradientStops.Add(new GradientStop(Color.FromArgb(58, 255, 233, 168), 0));
                    b.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 233, 168), 1));
                    inner.Children.Add(new Path
                    {
                        Data = Geometry.Parse(fan == 0 ? "M-4,0 L4,0 L46,820 L-46,820 Z" : "M-3,0 L3,0 L24,820 L-24,820 Z"),
                        Fill = b, RenderTransform = new RotateTransform(ang)
                    });
                }
                var rot = new RotateTransform();
                var outer = new Canvas { CacheMode = Fx.Cache(0.5), RenderTransform = rot };
                outer.Children.Add(inner);
                Canvas.SetLeft(outer, 590); Canvas.SetTop(outer, -60);
                rot.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(fan == 0 ? -4 : 5, fan == 0 ? 4 : -5, TimeSpan.FromSeconds(9 + fan * 4))
                { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
                outer.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.45, 1, TimeSpan.FromSeconds(3.4 + fan * 1.7))
                { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut } });
                _dawn.Children.Add(outer);
            }
            _root.Children.Add(_dawn);

            // Soft light that trails the cursor, like a torch held up to the dark
            var lb = Fx.Frozen(Fx.Radial(Color.FromArgb(34, 200, 235, 255), Color.FromArgb(0, 200, 235, 255)));
            _root.Children.Add(new Rectangle { Width = 620, Height = 620, Fill = lb, RenderTransform = _lightT });

            var vg = new RadialGradientBrush { RadiusX = 0.75, RadiusY = 0.8 };
            vg.GradientStops.Add(new GradientStop(Color.FromArgb(0, 0, 0, 0), 0.55));
            vg.GradientStops.Add(new GradientStop(Color.FromArgb(215, 2, 3, 8), 1));
            _root.Children.Add(new Rectangle { Width = W, Height = H, Fill = Fx.Frozen(vg) });
        }

        // ---------------- per-frame ----------------

        /// <param name="mx">cursor x in scene pixels</param>
        public void Tick(double dt, double t, double mx, double my)
        {
            // Parallax: eased toward the cursor
            double tx = (mx / W - 0.5) * 2, ty = (my / H - 0.5) * 2;
            _px += (tx - _px) * Math.Min(1, dt * 3);
            _py += (ty - _py) * Math.Min(1, dt * 3);
            _skyT.X = -_px * 4; _skyT.Y = -_py * 2;
            _backT.X = -_px * 6; _backT.Y = -_py * 2;
            _farT.X = -_px * 11; _farT.Y = -_py * 3;
            _midT.X = -_px * 19; _midT.Y = -_py * 5;
            _nearT.X = -_px * 32; _nearT.Y = -_py * 8;
            _fog1.X = Math.Sin(t * 0.05) * 160 - _px * 12;
            _fog2.X = Math.Cos(t * 0.04) * 200 - _px * 22;

            _lx += (mx - _lx) * Math.Min(1, dt * 5);
            _ly += (my - _ly) * Math.Min(1, dt * 5);
            _lightT.X = _lx - 310; _lightT.Y = _ly - 310;

            _auroraGain += (_auroraGainTo - _auroraGain) * Math.Min(1, dt * 0.9);
            _emberGain += (_emberGainTo - _emberGain) * Math.Min(1, dt * 1.2);

            if ((_meteorIn -= dt) <= 0) { LaunchMeteor(); _meteorIn = 7 + _rnd.NextDouble() * 9; }

            // Aurora: each soft ray rides a slow travelling wave
            foreach (var r in _rays)
            {
                int band = r.Band == 3 ? 0 : r.Band;
                double x = r.X - _px * (4 + band * 3);
                double baseY = band == 0 ? 120 : band == 1 ? 40 : 170;
                double wave = Math.Sin(x * 0.0042 + t * (0.16 + band * 0.05) + band * 2.1) * 62
                            + Math.Sin(x * 0.0118 - t * 0.24 + band) * 24;
                double curtain = 0.5 + 0.5 * Math.Sin(x * 0.0061 - t * 0.21 + band * 1.3);
                r.T.X = x;
                r.T.Y = baseY + wave + r.Lift;
                double a;
                if (r.Band == 3)
                {
                    double flick = 0.5 + 0.5 * Math.Sin(x * 0.05 + t * 1.7 + r.Phase);
                    r.S.ScaleY = 0.55 + 0.45 * curtain + 0.35 * flick;
                    a = 0.34 * (0.15 + 0.85 * curtain) * flick * flick;
                }
                else
                {
                    double shimmer = 0.5 + 0.5 * Math.Sin(x * 0.019 + t * (0.9 + band * 0.3) + r.Phase);
                    r.S.ScaleY = 0.62 + 0.5 * curtain + 0.16 * shimmer;
                    a = (band == 0 ? 0.44 : band == 1 ? 0.3 : 0.2) * (0.25 + 0.75 * curtain) * (0.7 + 0.3 * shimmer);
                }
                a = Math.Min(0.7, a * _auroraGain);
                // A ray too faint to see is not drawn at all (opacity 0 is culled; 1 costs no blend layer)
                bool hide = a < 0.012;
                if (hide != r.Hidden) { r.Hidden = hide; r.E.Opacity = hide ? 0 : 1; }
                if (hide) continue;
                r.B.Opacity = a;
            }

            // Snow falls, embers rise; a slow gust leans everything
            _wind = Math.Sin(t * 0.23) * 26 + Math.Sin(t * 0.61) * 10;
            foreach (var s in _sheets)
            {
                if (s.Ember)
                {
                    s.Y -= s.Speed * dt * (0.5 + _emberGain);
                    s.B.Opacity = _emberGain * (0.7 + 0.3 * Math.Sin(t * 3.1 + s.Phase));
                    s.T.X = Wrap(s.X + Math.Sin(t * 1.1 + s.Phase) * s.Sway, TW);
                }
                else
                {
                    s.Y += s.Speed * dt;
                    s.X += _wind * (0.3 + s.Depth) * dt;
                    s.T.X = Wrap(s.X + Math.Sin(t * 0.8 + s.Phase) * s.Sway - _px * 26 * s.Depth, TW);
                }
                s.T.Y = Wrap(s.Y, TH);
            }
        }

        // Any offset, folded into (-size, 0]
        static double Wrap(double v, double size) => -(((-v % size) + size) % size);
    }

    static class CanvasExt
    {
        public static T Put<T>(this T el, double x, double y) where T : UIElement
        {
            Canvas.SetLeft(el, x);
            Canvas.SetTop(el, y);
            return el;
        }
    }
}

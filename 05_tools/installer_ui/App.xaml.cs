using System;
using System.Windows;

namespace SkyrimArabicInstaller
{
    public partial class App : Application
    {
        static App()
        {
            // Nothing here moves fast enough to need more than about 60 updates a second, but a 144 Hz
            // or 240 Hz display would otherwise run every animation, and the whole redraw, 2-4x as often.
            // On such displays everything is paced to every 2nd/3rd/4th refresh. A 60-75 Hz display
            // is left exactly as WPF drives it. (Asking for slightly more than the target keeps the
            // tick safely inside the intended refresh instead of slipping to the next one.)
            int hz = Chrome.RefreshRate(), every = Math.Max(1, (int)Math.Round(hz / 60.0));
            if (every > 1)
                System.Windows.Media.Animation.Timeline.DesiredFrameRateProperty.OverrideMetadata(
                    typeof(System.Windows.Media.Animation.Timeline),
                    new FrameworkPropertyMetadata { DefaultValue = (int?)(int)Math.Ceiling(hz / (double)every * 1.06) });
        }
    }
}

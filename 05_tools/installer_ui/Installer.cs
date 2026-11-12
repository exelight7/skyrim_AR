using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Microsoft.Win32;

namespace SkyrimArabicInstaller
{
    /// <summary>A failure the user can act on. Message is Arabic and shown as-is.</summary>
    public sealed class InstallException : Exception
    {
        public InstallException(string message, Exception inner = null) : base(message, inner) { }
    }

    public sealed class InstallOptions
    {
        public string GameDir;
        public bool Backup = true, Shortcut;
    }

    public sealed class PayloadInfo
    {
        public bool Present;
        public int Strings, StringFiles, InterfaceFiles, Plugins;
        public long Bytes;
        public string GameVersion;
    }

    public sealed class JobResult
    {
        public int Files, BackedUp, Restored, LeftInPlace;
    }

    // Installs the translation that is embedded in this EXE (payload.zip, packed at build
    // time from 07_patch\SkyrimArabic) as loose files under <game>\Data.
    //
    // Guarantees, matching the project's PowerShell scripts:
    //   - the game's own BSA/ESM files are never opened for writing;
    //   - everything is first unpacked and hashed in a staging folder, so a bad payload or a
    //     full disk fails before the game folder is touched;
    //   - any file already sitting where one of ours goes is moved to a backup (if asked), not lost;
    //   - a receipt (path + SHA-256) records exactly what was placed, and uninstall removes only
    //     files that still match it;
    //   - if placing files fails half-way, what was placed is removed and backups are put back.
    //
    // State lives in <game>\Data\SkyrimArabic\ : receipt.tsv, backup\, LICENSES\.
    public static class Installer
    {
        const string StateName = "SkyrimArabic";
        const string SteamAppId = "489830";
        const string ShortcutName = "سكايرم بالعربية.url";

        public static readonly string[] InstallTasks =
        {
            "التحقق من اللعبة", "تجهيز النصوص العربية", "تهيئة مجلد اللعبة",
            "نقش النصوص والواجهة", "التحقق من سلامة الملفات", "اللمسات الأخيرة"
        };
        public static readonly double[] InstallWeights = { 0.05, 0.40, 0.10, 0.25, 0.16, 0.04 };

        public static readonly string[] UninstallTasks =
        {
            "التحقق من التثبيت", "إزالة ملفات التعريب", "إعادة الملفات السابقة", "التنظيف"
        };
        public static readonly double[] UninstallWeights = { 0.10, 0.55, 0.20, 0.15 };

        // ---------------- payload ----------------

        static PayloadInfo _info;

        static ZipArchive OpenPayload()
        {
            var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip");
            return s == null ? null : new ZipArchive(s, ZipArchiveMode.Read);
        }

        // Entry name -> path relative to Data, or null for entries that are not installed
        static string Target(ZipArchiveEntry e)
        {
            string rel = e.FullName.Replace('/', '\\');
            if (rel.EndsWith("\\") || rel.Contains("..") || Path.IsPathRooted(rel)) return null;
            if (rel.StartsWith("Strings\\", StringComparison.OrdinalIgnoreCase) ||
                rel.StartsWith("Interface\\", StringComparison.OrdinalIgnoreCase)) return rel;
            if (rel.StartsWith("LICENSES\\", StringComparison.OrdinalIgnoreCase)) return StateName + "\\" + rel;
            return null;
        }

        public static PayloadInfo Info
        {
            get
            {
                if (_info != null) return _info;
                var info = new PayloadInfo();
                try
                {
                    using (var zip = OpenPayload())
                    {
                        if (zip != null)
                        {
                            var plugins = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                            foreach (var e in zip.Entries)
                            {
                                string rel = Target(e);
                                if (rel == null)
                                {
                                    if (e.Name.Equals("build_report.json", StringComparison.OrdinalIgnoreCase))
                                        using (var r = new StreamReader(e.Open(), Encoding.UTF8))
                                        {
                                            string json = r.ReadToEnd();
                                            var m = Regex.Match(json, "\"strings_written\"\\s*:\\s*(\\d+)");
                                            if (m.Success) info.Strings = int.Parse(m.Groups[1].Value);
                                            m = Regex.Match(json, "\"ui_keys\"\\s*:\\s*(\\d+)");
                                            if (m.Success) info.Strings += int.Parse(m.Groups[1].Value);
                                            m = Regex.Match(json, "\"game_version\"\\s*:\\s*\"([^\"]+)\"");
                                            if (m.Success) info.GameVersion = m.Groups[1].Value;
                                        }
                                    continue;
                                }
                                info.Bytes += e.Length;
                                if (rel.StartsWith("Strings\\", StringComparison.OrdinalIgnoreCase))
                                {
                                    info.StringFiles++;
                                    int cut = e.Name.LastIndexOf("_english.", StringComparison.OrdinalIgnoreCase);
                                    if (cut > 0) plugins.Add(e.Name.Substring(0, cut));
                                }
                                else if (rel.StartsWith("Interface\\", StringComparison.OrdinalIgnoreCase)) info.InterfaceFiles++;
                            }
                            info.Plugins = plugins.Count;
                            info.Present = info.StringFiles > 0;
                        }
                    }
                }
                catch { info.Present = false; }
                return _info = info;
            }
        }

        // ---------------- finding the game ----------------

        public static bool LooksLikeGame(string folder)
        {
            try { return !string.IsNullOrWhiteSpace(folder) && File.Exists(Path.Combine(folder, "SkyrimSE.exe")); }
            catch { return false; }
        }

        public static string GameVersion(string folder)
        {
            try
            {
                var v = FileVersionInfo.GetVersionInfo(Path.Combine(folder, "SkyrimSE.exe"));
                return v.FileMajorPart == 0 && v.FileMinorPart == 0 ? null
                     : v.FileMajorPart + "." + v.FileMinorPart + "." + v.FileBuildPart + "." + v.FilePrivatePart;
            }
            catch { return null; }
        }

        /// <summary>True when the first three parts of both versions agree.</summary>
        public static bool SameVersion(string a, string b)
        {
            if (a == null || b == null) return true;      // unknown: do not raise a false alarm
            var x = a.Split('.'); var y = b.Split('.');
            for (int i = 0; i < 3; i++)
                if ((i < x.Length ? x[i] : "0") != (i < y.Length ? y[i] : "0")) return false;
            return true;
        }

        public static string FindGame()
        {
            const string sub = @"steamapps\common\Skyrim Special Edition";
            var candidates = new List<string>();
            Action<RegistryKey, string, string> reg = (root, key, value) =>
            {
                try { using (var k = root.OpenSubKey(key)) { var v = k?.GetValue(value) as string; if (!string.IsNullOrEmpty(v)) candidates.Add(v); } }
                catch { }
            };
            // The game's own registry entry, then every Steam library
            reg(Registry.LocalMachine, @"SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim Special Edition", "Installed Path");
            var steam = new List<string>();
            int mark = candidates.Count;
            reg(Registry.CurrentUser, @"Software\Valve\Steam", "SteamPath");
            reg(Registry.LocalMachine, @"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath");
            steam.AddRange(candidates.Skip(mark).Select(p => p.Replace('/', '\\')));
            candidates.RemoveRange(mark, candidates.Count - mark);
            foreach (var root in steam.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                candidates.Add(Path.Combine(root, sub));
                try
                {
                    string vdf = Path.Combine(root, @"steamapps\libraryfolders.vdf");
                    if (File.Exists(vdf))
                        foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                            candidates.Add(Path.Combine(m.Groups[1].Value.Replace(@"\\", @"\"), sub));
                }
                catch { }
            }
            foreach (var d in new[] { "C", "D", "E", "F", "G" })
            {
                candidates.Add(d + @":\SteamLibrary\" + sub);
                candidates.Add(d + @":\Steam\" + sub);
                candidates.Add(d + @":\Program Files (x86)\Steam\" + sub);
            }
            return candidates.Select(c => c.TrimEnd('\\')).FirstOrDefault(LooksLikeGame);
        }

        public static bool IsInstalled(string game)
        {
            try { return File.Exists(ReceiptPath(game)); } catch { return false; }
        }

        static string Data(string game) => Path.Combine(game, "Data");
        static string State(string game) => Path.Combine(Data(game), StateName);
        static string ReceiptPath(string game) => Path.Combine(State(game), "receipt.tsv");
        static string BackupDir(string game) => Path.Combine(State(game), "backup");

        // ---------------- receipt ----------------

        sealed class Receipt
        {
            public readonly List<KeyValuePair<string, string>> Files = new List<KeyValuePair<string, string>>();  // rel -> sha256
            public readonly List<string> Backups = new List<string>();                                          // rel
            public string Shortcut;

            public static Receipt Load(string game)
            {
                string path = ReceiptPath(game);
                if (!File.Exists(path)) return null;
                var r = new Receipt();
                foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
                {
                    var p = line.Split('\t');
                    if (p[0] == "F" && p.Length >= 3) r.Files.Add(new KeyValuePair<string, string>(p[1], p[2]));
                    else if (p[0] == "B" && p.Length >= 2) r.Backups.Add(p[1]);
                    else if (p[0] == "S" && p.Length >= 2) r.Shortcut = p[1];
                }
                return r;
            }

            public void Save(string game)
            {
                var sb = new StringBuilder();
                sb.Append("# SkyrimArabic install receipt. Paths are relative to Data. Do not edit.\r\n");
                sb.Append("V\t1\t").Append(Info.GameVersion).Append('\t').Append(DateTime.UtcNow.ToString("s")).Append("Z\r\n");
                foreach (var f in Files) sb.Append("F\t").Append(f.Key).Append('\t').Append(f.Value).Append("\r\n");
                foreach (var b in Backups) sb.Append("B\t").Append(b).Append("\r\n");
                if (Shortcut != null) sb.Append("S\t").Append(Shortcut).Append("\r\n");
                Directory.CreateDirectory(State(game));
                File.WriteAllText(ReceiptPath(game), sb.ToString(), new UTF8Encoding(false));
            }
        }

        // ---------------- install ----------------

        public static JobResult Install(InstallOptions o, Action<int, double> report)
        {
            string game = o.GameDir, data = Data(game), state = State(game), stage = Path.Combine(state, "staging");
            var result = new JobResult();

            // 0 · checks, before anything is written
            report(0, 0);
            Precheck(game);
            if (!Info.Present) throw new InstallException("هذه النسخة من المثبّت لا تحمل ملفات التعريب. أعد بناءها بعد تجهيز التعريب.");
            try
            {
                Directory.CreateDirectory(state);
                string probe = Path.Combine(state, ".write-test");
                File.WriteAllText(probe, "");
                File.Delete(probe);
            }
            catch (UnauthorizedAccessException ex)
            {
                throw new InstallException("لا نملك صلاحية الكتابة في مجلد اللعبة. شغّل المثبّت كمسؤول ثم أعد المحاولة.", ex);
            }
            report(0, 1);

            var staged = new List<KeyValuePair<string, string>>();    // rel -> sha256
            var placed = new List<string>();
            Receipt receipt = null;
            bool touchedGame = false;
            try
            {
                // 1 · unpack and hash into staging
                if (Directory.Exists(stage)) Directory.Delete(stage, true);
                using (var zip = OpenPayload())
                {
                    var entries = zip.Entries.Select(e => new { e, rel = Target(e) }).Where(x => x.rel != null).ToList();
                    long total = Math.Max(1, entries.Sum(x => x.e.Length)), done = 0;
                    var buf = new byte[81920];
                    foreach (var x in entries)
                    {
                        string path = Path.Combine(stage, x.rel);
                        Directory.CreateDirectory(Path.GetDirectoryName(path));
                        using (var sha = SHA256.Create())
                        {
                            using (var src = x.e.Open())
                            using (var dst = File.Create(path))
                            {
                                int n;
                                while ((n = src.Read(buf, 0, buf.Length)) > 0)
                                {
                                    dst.Write(buf, 0, n);
                                    sha.TransformBlock(buf, 0, n, null, 0);
                                    done += n;
                                }
                            }
                            sha.TransformFinalBlock(buf, 0, 0);
                            staged.Add(new KeyValuePair<string, string>(x.rel, Hex(sha.Hash)));
                        }
                        report(1, (double)done / total);
                    }
                }

                // 2 · clear the way: remove our previous version, set aside anything else in our places
                receipt = new Receipt();
                var old = Receipt.Load(game);
                touchedGame = true;
                if (old != null)
                {
                    foreach (var f in old.Files)
                    {
                        string p = Path.Combine(data, f.Key);
                        if (File.Exists(p) && HashFile(p) == f.Value) File.Delete(p);
                    }
                    receipt.Backups.AddRange(old.Backups);      // earlier backups stay valid
                    receipt.Shortcut = old.Shortcut;
                }
                for (int i = 0; i < staged.Count; i++)
                {
                    string rel = staged[i].Key, target = Path.Combine(data, rel);
                    if (File.Exists(target))
                    {
                        string keep = Path.Combine(BackupDir(game), rel);
                        if (o.Backup && !File.Exists(keep))
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(keep));
                            File.Move(target, keep);
                            receipt.Backups.Add(rel);
                            result.BackedUp++;
                        }
                        else File.Delete(target);
                    }
                    report(2, (i + 1.0) / staged.Count);
                }

                // 3 · place (a rename on the same volume, so this is quick and all-or-nothing per file)
                for (int i = 0; i < staged.Count; i++)
                {
                    string rel = staged[i].Key, target = Path.Combine(data, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Move(Path.Combine(stage, rel), target);
                    placed.Add(rel);
                    report(3, (i + 1.0) / staged.Count);
                }

                // 4 · read every placed file back and compare
                for (int i = 0; i < staged.Count; i++)
                {
                    if (HashFile(Path.Combine(data, staged[i].Key)) != staged[i].Value)
                        throw new InstallException("ملف لم يُكتب سليماً: " + staged[i].Key);
                    receipt.Files.Add(staged[i]);
                    report(4, (i + 1.0) / staged.Count);
                }
                result.Files = staged.Count;
                receipt.Save(game);
            }
            catch (Exception ex)
            {
                if (touchedGame) RollBack(game, placed, receipt);
                TryDelete(stage);
                Tidy(game);
                if (ex is InstallException && !touchedGame) throw;
                throw new InstallException(touchedGame
                    ? "تعذّر إكمال النقش، فأُعيدت اللعبة إلى حالها قبل التعريب.\n" + Describe(ex)
                    : "تعذّر تجهيز الملفات، ولم يُمَسّ مجلد اللعبة.\n" + Describe(ex), ex);
            }
            TryDelete(stage);

            // 5 · courtesy steps; a failure here never undoes a good install
            report(5, 0);
            if (o.Shortcut)
                try { receipt.Shortcut = WriteShortcut(game); receipt.Save(game); } catch { }
            report(5, 1);
            return result;
        }

        static void RollBack(string game, List<string> placed, Receipt receipt)
        {
            string data = Data(game);
            foreach (var rel in placed) TryDeleteFile(Path.Combine(data, rel));
            if (receipt != null) RestoreBackups(game, receipt.Backups);
            TryDeleteFile(ReceiptPath(game));
            Tidy(game);
        }

        static int RestoreBackups(string game, IEnumerable<string> backups)
        {
            int n = 0;
            foreach (var rel in backups)
            {
                try
                {
                    string keep = Path.Combine(BackupDir(game), rel), target = Path.Combine(Data(game), rel);
                    if (!File.Exists(keep) || File.Exists(target)) continue;
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Move(keep, target);
                    n++;
                }
                catch { }
            }
            return n;
        }

        // ---------------- uninstall ----------------

        public static JobResult Uninstall(string game, Action<int, double> report)
        {
            var result = new JobResult();
            report(0, 0);
            Precheck(game);
            var receipt = Receipt.Load(game);
            if (receipt == null) throw new InstallException("لا يوجد تعريب مثبَّت في هذا المجلد.");
            report(0, 1);
            try
            {
                string data = Data(game);
                for (int i = 0; i < receipt.Files.Count; i++)
                {
                    string p = Path.Combine(data, receipt.Files[i].Key);
                    if (File.Exists(p))
                    {
                        // Only files that are still exactly ours are removed
                        if (HashFile(p) == receipt.Files[i].Value) { File.Delete(p); result.Files++; }
                        else result.LeftInPlace++;
                    }
                    report(1, (i + 1.0) / receipt.Files.Count);
                }
                result.Restored = RestoreBackups(game, receipt.Backups);
                report(2, 1);
                if (receipt.Shortcut != null) TryDeleteFile(receipt.Shortcut);
                File.Delete(ReceiptPath(game));
                Tidy(game);
                report(3, 1);
            }
            catch (UnauthorizedAccessException ex)
            {
                throw new InstallException("لا نملك صلاحية التعديل في مجلد اللعبة. شغّل المثبّت كمسؤول ثم أعد المحاولة.", ex);
            }
            catch (IOException ex)
            {
                throw new InstallException("تعذّرت إزالة بعض الملفات. تأكد من إغلاق اللعبة ثم أعد المحاولة.\n" + ex.Message, ex);
            }
            return result;
        }

        /// <summary>Design mode: the same pacing as a real run, touching nothing.</summary>
        public static JobResult Demo(int tasks, Action<int, double> report)
        {
            for (int t = 0; t < tasks; t++)
                for (int i = 0; i <= 10; i++) { report(t, i / 10.0); Thread.Sleep(35); }
            return new JobResult { Files = Info.StringFiles + Info.InterfaceFiles };
        }

        // ---------------- small things ----------------

        static void Precheck(string game)
        {
            if (!LooksLikeGame(game)) throw new InstallException("لم يُعثر على SkyrimSE.exe في المجلد المحدَّد.");
            if (!Directory.Exists(Data(game))) throw new InstallException("مجلد Data غير موجود داخل مجلد اللعبة.");
            bool running;
            try { running = Process.GetProcessesByName("SkyrimSE").Length > 0; } catch { running = false; }
            if (running) throw new InstallException("سكايرم تعمل الآن. أغلقها ثم أعد المحاولة.");
        }

        // Removes our folders when (and only when) they have ended up empty
        static void Tidy(string game)
        {
            foreach (var dir in new[] { Path.Combine(State(game), "staging"), Path.Combine(State(game), "LICENSES"), BackupDir(game), State(game),
                                        Path.Combine(Data(game), "Strings"), Path.Combine(Data(game), "Interface") })
                RemoveIfEmpty(dir);
        }

        static void RemoveIfEmpty(string dir)
        {
            try
            {
                if (!Directory.Exists(dir)) return;
                foreach (var sub in Directory.GetDirectories(dir)) RemoveIfEmpty(sub);
                if (!Directory.EnumerateFileSystemEntries(dir).Any()) Directory.Delete(dir);
            }
            catch { }
        }

        static bool IsSteam(string game) => File.Exists(Path.Combine(game, "steam_api64.dll"));

        static string WriteShortcut(string game)
        {
            string exe = Path.Combine(game, "SkyrimSE.exe");
            string url = IsSteam(game) ? "steam://rungameid/" + SteamAppId : new Uri(exe).AbsoluteUri;
            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), ShortcutName);
            File.WriteAllText(path, "[InternetShortcut]\r\nURL=" + url + "\r\nIconFile=" + exe + "\r\nIconIndex=0\r\n", Encoding.Unicode);
            return path;
        }

        public static void Launch(string game)
        {
            if (IsSteam(game)) Process.Start(new ProcessStartInfo("steam://rungameid/" + SteamAppId) { UseShellExecute = true });
            else Process.Start(new ProcessStartInfo(Path.Combine(game, "SkyrimSE.exe")) { WorkingDirectory = game, UseShellExecute = true });
        }

        static string HashFile(string path)
        {
            using (var sha = SHA256.Create())
            using (var s = File.OpenRead(path))
                return Hex(sha.ComputeHash(s));
        }

        static string Hex(byte[] b)
        {
            var sb = new StringBuilder(b.Length * 2);
            foreach (var x in b) sb.Append(x.ToString("X2"));
            return sb.ToString();
        }

        static string Describe(Exception ex) =>
            ex is InstallException ? ex.Message
            : ex is UnauthorizedAccessException ? "لا نملك صلاحية الكتابة في مجلد اللعبة. شغّل المثبّت كمسؤول."
            : ex is IOException ? "خطأ في القرص أو ملف مستخدَم من برنامج آخر: " + ex.Message
            : ex.Message;

        static void TryDelete(string dir) { try { if (Directory.Exists(dir)) Directory.Delete(dir, true); } catch { } }
        static void TryDeleteFile(string file) { try { if (File.Exists(file)) File.Delete(file); } catch { } }
    }
}

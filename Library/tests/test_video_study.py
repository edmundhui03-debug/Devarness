"""video-study: caption cleanup, time handling, the repository guard and a real ffmpeg run, offline."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "video-study"
LOADER = importlib.machinery.SourceFileLoader("video_study", str(SCRIPT))
SPEC = importlib.util.spec_from_loader("video_study", LOADER)
WATCH = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(WATCH)

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
first<00:00:00.500><c> line</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
first line

00:00:02.010 --> 00:00:04.000 align:start position:0%
first line
second &gt;&gt; line.

00:00:31.000 --> 00:00:33.000 align:start position:0%
second &gt;&gt; line.
third line.

01:05.000 --> 01:07.000
fourth line
"""


class CaptionsAndTime(unittest.TestCase):
    def test_rolling_captions_state_each_line_once(self):
        self.assertEqual(WATCH.caption_lines(ROLLING_VTT), [
            (0.0, "first line"), (2.01, "second >> line."), (31.0, "third line."), (65.0, "fourth line")])

    def test_paragraphs_close_on_a_sentence_after_the_span(self):
        text = WATCH.render_transcript(WATCH.paragraphs(WATCH.caption_lines(ROLLING_VTT)))
        self.assertEqual(text, "[00:00] first line second >> line. third line.\n\n[01:05] fourth line\n\n")

    def test_times_parse_in_every_form_and_refuse_nonsense(self):
        for text, seconds in (("45", 45.0), ("1:05", 65.0), ("00:28:30", 1710.0), ("1:02:03.5", 3723.5)):
            with self.subTest(text=text):
                self.assertEqual(WATCH.parse_time(text), seconds)
        for bad in ("", "a:b", "1.5:30", "1:2:3:4", "12:"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    WATCH.parse_time(bad)

    def test_space_only_lines_inside_a_cue_keep_text_with_its_time(self):
        # YouTube separates a cue's timing from its text with a line holding one space.
        spaced = ("WEBVTT\n\n"
                  "00:00:15.000 --> 00:00:17.000 align:start position:0%\n \nopening words\n\n"
                  "00:00:17.000 --> 00:00:17.010 align:start position:0%\nopening words\n \n\n"
                  "00:00:17.010 --> 00:00:20.000 align:start position:0%\nopening words\nnext words.\n")
        self.assertEqual(WATCH.caption_lines(spaced), [(15.0, "opening words"), (17.01, "next words.")])

    def test_unpunctuated_captions_still_break_into_paragraphs(self):
        lines = [(float(t), "words without an ending") for t in range(0, 200, 10)]
        self.assertEqual([start for start, _ in WATCH.paragraphs(lines)], [0.0, 100.0])

    def test_clock_and_ffmpeg_time(self):
        self.assertEqual(WATCH.clock(65), "01:05")
        self.assertEqual(WATCH.clock(3723), "1:02:03")
        self.assertEqual(WATCH.ffmpeg_time(3723.5), "01:02:03.500")

    def test_scene_log_pairs_times_with_scores(self):
        log = ("frame:0    pts:16      pts_time:8\nlavfi.scene_score=0.123456\n"
               "frame:1    pts:31      pts_time:15.5\nlavfi.scene_score=0.5\n")
        self.assertEqual(WATCH.parse_scene_log(log), [{"t": 8.0, "score": 0.1235}, {"t": 15.5, "score": 0.5}])

    def test_showinfo_times_come_from_showinfo_lines_only(self):
        log = ("[Parsed_showinfo_3 @ 0x1] n:   0 pts:      0 pts_time:0       duration:1\n"
               "[Parsed_showinfo_3 @ 0x1] color_range:tv\n"
               "[other @ 0x2] pts_time:99\n"
               "[Parsed_showinfo_3 @ 0x1] n:   1 pts:      4 pts_time:2       duration:1\n")
        self.assertEqual(WATCH.parse_showinfo(log), [0.0, 2.0])


class CommandsAndGuard(unittest.TestCase):
    def test_filter_paths_escape_drive_colons_and_quotes(self):
        self.assertEqual(WATCH.filter_path("C:\\Windows\\Fonts\\arial.ttf"), "C\\:/Windows/Fonts/arial.ttf")
        self.assertEqual(WATCH.filter_path("/fonts/it's.ttf"), "/fonts/it\\'s.ttf")

    def test_sheet_graph_selects_by_interval_and_logs_scenes(self):
        graph = WATCH.sheet_graph(5.0, 6, 5, None, 0.015)
        self.assertIn("gte(t-prev_selected_t\\,5.0)", graph)
        self.assertIn("showinfo", graph)
        self.assertIn("tile=6x5", graph)
        self.assertIn("gt(scene\\,0.015)", graph)
        self.assertNotIn("drawtext", graph)
        self.assertIn("drawtext=fontfile='/f.ttf'", WATCH.sheet_graph(5.0, 6, 5, "/f.ttf", 0.015))

    def test_download_commands_prefer_bitrate_within_height_and_captions_first(self):
        out = Path("out")
        video = WATCH.ytdlp_video_cmd("https://youtu.be/abcdefghijk", out, 1080)
        self.assertEqual(video[video.index("-f") + 1], "bv*[height<=?1080]/b[height<=?1080]")
        self.assertEqual(video[video.index("-S") + 1], "res,tbr")
        captions = WATCH.ytdlp_caption_cmd("https://youtu.be/abcdefghijk", out)
        self.assertIn("--skip-download", captions)
        self.assertEqual(captions[captions.index("--sub-format") + 1], "vtt")

    def test_youtube_ids_name_a_default_directory_outside_dev(self):
        self.assertEqual(WATCH.youtube_id("https://www.youtube.com/watch?v=19HDQ9HppOA&t=677s"), "19HDQ9HppOA")
        self.assertIsNone(WATCH.youtube_id("https://example.com/video.mp4"))
        self.assertFalse(WATCH.inside_root(WATCH.default_out("19HDQ9HppOA")))
        self.assertTrue(WATCH.inside_root(WATCH.ROOT / "Library"))
        self.assertTrue(WATCH.inside_root(WATCH.ROOT / "not-yet" / "created"))

    def test_a_case_variant_of_the_root_is_still_inside_it(self):
        variant = Path(str(WATCH.ROOT).swapcase())
        if not variant.exists():
            self.skipTest("case-sensitive file system: the variant is a different path")
        self.assertTrue(WATCH.inside_root(variant / "Library" / "not-yet"))

    def test_ffmpeg_features_follow_version_and_filters(self):
        def fake(version_line, filters):
            def run(cmd, **kwargs):
                text = version_line if "-version" in cmd else filters
                return subprocess.CompletedProcess(cmd, 0, text, "")
            return run
        with patch.object(WATCH.shutil, "which", return_value="ffmpeg"):
            with patch.object(WATCH.subprocess, "run", fake("ffmpeg version 4.4.2 Copyright", " ... scale  V->V  Scale\n")):
                self.assertEqual(WATCH.ffmpeg_features(), {"version": "4.4", "fps_mode": False, "drawtext": False})
            with patch.object(WATCH.subprocess, "run", fake("ffmpeg version 7.1 Copyright", " T.C drawtext  V->V  Draw text\n")):
                self.assertEqual(WATCH.ffmpeg_features(), {"version": "7.1", "fps_mode": True, "drawtext": True})

    def test_a_caption_failure_is_recorded_and_the_study_goes_on(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            failed = subprocess.CompletedProcess([], 1, None, None)
            with patch.object(WATCH.subprocess, "run", return_value=failed):
                record = WATCH.fetch_transcript("https://youtu.be/abcdefghijk", out)
            self.assertIn("error", record)
            self.assertFalse((out / "transcript.txt").exists())

    def test_a_different_source_or_height_marks_the_old_video_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "video.mp4").write_bytes(b"old")
            (out / "video.en.vtt").write_text("WEBVTT\n")
            (out / "study.json").write_text(json.dumps({"source": "https://youtu.be/abcdefghijk", "height": 720}))
            self.assertEqual(WATCH.stale_videos(out, "https://youtu.be/abcdefghijk", 720), [])
            self.assertEqual(WATCH.stale_videos(out, "https://youtu.be/abcdefghijk", 1080), [out / "video.mp4"])


class Guard(unittest.TestCase):
    def test_output_inside_dev_is_refused_before_anything_is_written(self):
        target = WATCH.ROOT / "Library" / "video-study-must-not-exist"
        self.assertEqual(WATCH.main(["study", "https://youtu.be/abcdefghijk", "--out", str(target)]), 1)
        self.assertFalse(target.exists())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are needed")
class RealFfmpeg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc=size=320x240:rate=10:duration=12", "-pix_fmt", "yuv420p",
                        "-y", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_study_of_a_local_file_writes_sheets_with_true_tile_times(self):
        out = self.root / "study"
        self.assertEqual(WATCH.main(["study", str(self.video), "--out", str(out), "--every", "2"]), 0)
        record = json.loads((out / "study.json").read_text())
        self.assertIsNone(record["transcript"])
        self.assertEqual(record["sheets"]["sheets"], 1)
        tiles = json.loads((out / "sheets.json").read_text())
        self.assertEqual(len(tiles), 6)
        for index, tile in enumerate(tiles):
            with self.subTest(tile=index):
                self.assertAlmostEqual(tile["t"], 2 * index, delta=0.6)

    def test_frames_land_at_exact_times_and_crop_separately(self):
        out = self.root / "frames"
        self.assertEqual(WATCH.main(["frames", str(self.video), "--at", "1,00:05.5", "--out", str(out)]), 0)
        self.assertEqual(len(list(out.glob("frame_*.jpg"))), 2)
        self.assertEqual(WATCH.main(["frames", str(self.video), "--at", "2", "--crop", "100:80:0:0",
                                     "--out", str(out)]), 0)
        self.assertEqual(len(list(out.glob("frame_*crop*.jpg"))), 1)

    def test_a_time_past_the_end_fails_loudly(self):
        self.assertEqual(WATCH.main(["frames", str(self.video), "--at", "59", "--out", str(self.root / "late")]), 1)


if __name__ == "__main__":
    unittest.main()

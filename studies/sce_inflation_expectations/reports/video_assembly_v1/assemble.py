"""Assemble the author's ten trimmed recordings without touching the originals."""
from __future__ import annotations

import argparse
import concurrent.futures
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


def run(args: list[str], log: Path | None = None) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    if log:
        log.write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]}\n{result.stderr[-3000:]}")
    return result.stdout if args[0] == "ffprobe" else result.stderr


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def measure(path: Path, stream: int, log: Path) -> dict:
    stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                  "-map", f"0:{stream}", "-vn", "-af",
                  "aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                  "-f", "null", "-"], log)
    return json.JSONDecoder().raw_decode(stderr[stderr.rfind("{"):])[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="A new output directory")
    args = parser.parse_args()
    args.clips = args.clips.resolve()
    args.out = args.out.resolve()
    if args.out.exists():
        raise SystemExit("Output already exists; choose a new version directory.")
    sources = sorted(p for p in args.clips.glob("part_*") if p.is_file())
    numbers = [int(re.match(r"part_(\d+)_", p.name).group(1)) for p in sources]
    if numbers != list(range(1, 11)):
        raise SystemExit("Expected exactly one trimmed part_01 through part_10, in order.")
    args.out.mkdir(parents=True)
    work = args.out / "processing"
    work.mkdir()
    source_data = [(p, sha(p), probe(p)) for p in sources]
    duration_sum = sum(float(data[2]["format"]["duration"]) for data in source_data)
    # Only accelerate when necessary, leaving a two-second margin below five minutes.
    speed = max(1.0, duration_sum / 298.0)

    def encode(item: tuple[int, tuple]) -> dict:
        index, (source, source_sha, info) = item
        duration = float(info["format"]["duration"])
        tracks = []
        for stream in info["streams"]:
            if stream["codec_type"] == "audio":
                stats = measure(source, stream["index"], work / f"part_{index:02d}_audio_{stream['index']}.log")
                tracks.append({"stream": stream["index"], "stats": stats})
        # WPS exports often contain a silent system track and a separate microphone.
        audible = [t for t in tracks if math.isfinite(float(t["stats"]["input_i"]))]
        if not audible:
            raise RuntimeError(f"No audible recording in {source.name}")
        selected = max(audible, key=lambda t: float(t["stats"]["input_i"]))
        stats = selected["stats"]
        loudnorm = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={stats['input_i']}:"
                    f"measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:"
                    f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true")
        # Preserve input audio timestamps (including initial silence) and hold static
        # slide frames through the full speech duration, even when the video track ends early.
        audio = f"aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,{loudnorm},apad"
        if speed > 1:
            audio += f",atempo={speed:.12f}"
        audio += ",aresample=48000"
        video = ("scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
                 "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x101725,setsar=1,"
                 f"setpts=(PTS-STARTPTS)/{speed:.12f},fps=30,"
                 f"tpad=stop_mode=clone:stop_duration={duration:.9f}")
        segment = work / f"part_{index:02d}.mp4"
        run(["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-n", "-i", str(source),
             "-map", "0:v:0", "-map", f"0:{selected['stream']}", "-vf", video, "-af", audio,
             "-t", f"{duration / speed:.9f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-threads", "4", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-ac", "2", "-video_track_timescale", "90000", "-map_metadata", "-1",
             "-movflags", "+faststart", str(segment)], work / f"part_{index:02d}_encode.log")
        actual = probe(segment)
        print(f"Normalized {index:02d}/10: {source.name} | microphone stream {selected['stream']}", flush=True)
        return {"part": index, "source": str(source), "source_sha256": source_sha,
                "source_duration_seconds": duration, "source_probe": info,
                "audio_tracks": tracks, "selected_audio_stream": selected["stream"],
                "segment": str(segment), "segment_probe": actual,
                "title": re.sub(r"\.mp4(?:\.mov)?$", "", source.name.split("_", 2)[2])}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        parts = list(executor.map(encode, enumerate(source_data, 1)))
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{Path(p['segment']).name}'\n" for p in parts))
    chapters = [";FFMETADATA1", "title=SCE通胀预期模拟项目展示"]
    elapsed = 0.0
    for part in parts:
        part["start_seconds"] = elapsed
        elapsed += float(part["segment_probe"]["format"]["duration"])
        chapters += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(part['start_seconds'] * 1000)}",
                     f"END={round(elapsed * 1000)}", f"title={part['part']:02d} {part['title']}"]
    metadata = work / "chapters.ffmetadata"
    metadata.write_text("\n".join(chapters) + "\n", encoding="utf-8")
    version = re.fullmatch(r"assembled_(v\d+)", args.out.name)
    output = args.out / (f"SCE_demo_{version[1]}.mp4" if version else "SCE_demo.mp4")
    run(["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-n", "-f", "concat", "-safe", "0",
         "-i", str(concat), "-f", "ffmetadata", "-i", str(metadata), "-map", "0:v:0", "-map", "0:a:0",
         "-map_metadata", "1", "-map_chapters", "1", "-vf", "fps=30",
         "-af", "aresample=48000:async=1:first_pts=0", "-c:v", "libx264", "-crf", "16",
         "-preset", "medium", "-threads", "4", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output)],
        work / "concat.log")
    final_probe = probe(output)
    run(["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-i", str(output),
         "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], work / "decode_check.log")
    final_stats = measure(output, 1, work / "final_audio.log")
    unchanged = all(sha(source) == digest for source, digest, _ in source_data)
    final_duration = float(final_probe["format"]["duration"])
    assert unchanged and final_duration < 300
    assert abs(final_duration - duration_sum / speed) < 0.75
    final_video = next(s for s in final_probe["streams"] if s["codec_type"] == "video")
    assert Fraction(final_video["avg_frame_rate"]) == 30
    manifest = {"schema": "sce_video_assembly/v1", "parts": parts,
                "speed_factor": speed, "original_total_seconds": duration_sum,
                "output": str(output), "output_sha256": sha(output), "output_probe": final_probe,
                "output_loudness": final_stats, "source_files_unchanged": unchanged,
                "assembly_code_sha256": sha(Path(__file__)),
                "full_decode_check_passed": True, "duration_under_five_minutes": True,
                "frame_policy": "Fit with padding, no crop or stretch; hold last frame through speech",
                "audio_policy": "Select audible microphone; two-pass stereo -16 LUFS/-1.5 dBTP normalization",
                "API_calls": 0}
    (args.out / "assembly_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (args.out / "chapters.txt").write_text("\n".join(
        f"{int(p['start_seconds']) // 60:02d}:{p['start_seconds'] % 60:06.3f}  {p['part']:02d} {p['title']}" for p in parts) + "\n")
    print(json.dumps({"output": str(output), "duration": final_duration, "speed": speed,
                      "loudness": final_stats, "originals_unchanged": unchanged}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

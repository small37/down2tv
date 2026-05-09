#!/usr/bin/env python3
"""
Use the yt_dlp Python API to download an m3u8 video in the background.

Example:
  python download_movie.py "电影名" "https://hn.bfvvs.com/play/RdG7xDKd/index.m3u8"
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import sys
import time
import traceback
from contextlib import contextmanager
import yt_dlp

DEFAULT_OUTPUT_DIR = "/home/webmovie/movie"
# DEFAULT_OUTPUT_DIR = "movie"
SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv")
CONCURRENT_FRAGMENT_DOWNLOADS = 5
DOWNLOAD_REGISTRY = ".downloads.json"


def clean_movie_name(name):
    name = os.path.basename(str(name or "")).strip()
    for ext in VIDEO_EXTENSIONS:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    name = SAFE_NAME_RE.sub("_", name).strip(" ._")
    return name or "index"


def url_key(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def registry_path(output_dir):
    return os.path.join(output_dir, DOWNLOAD_REGISTRY)


def lock_path(output_dir):
    return os.path.join(output_dir, f"{DOWNLOAD_REGISTRY}.lock")


@contextmanager
def locked_registry(output_dir):
    import fcntl

    os.makedirs(output_dir, exist_ok=True)
    lock_file_path = lock_path(output_dir)
    with open(lock_file_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        path = registry_path(output_dir)
        try:
            with open(path, "r", encoding="utf-8") as registry_file:
                registry = json.load(registry_file)
        except (FileNotFoundError, json.JSONDecodeError):
            registry = {}

        yield registry

        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as registry_file:
            json.dump(registry, registry_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def process_is_running(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def matching_output_files(output_dir, movie_name):
    files = []
    prefix = f"{movie_name}."
    for filename in os.listdir(output_dir):
        if not filename.startswith(prefix):
            continue
        lower_filename = filename.lower()
        if lower_filename.endswith(VIDEO_EXTENSIONS):
            files.append(os.path.join(output_dir, filename))
    return files


def part_file_exists(output_dir, movie_name):
    prefix = f"{movie_name}."
    return any(
        filename.startswith(prefix) and ".part" in filename
        for filename in os.listdir(output_dir)
    )


def format_bytes(value):
    if not value:
        return "Unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:6.2f}{unit}"
        size /= 1024


def format_eta(value):
    if value is None:
        return "Unknown"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "Unknown"
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class FileLogger:
    def __init__(self, log_file):
        self.log_file = log_file

    def debug(self, message):
        self.write(message)

    def info(self, message):
        self.write(message)

    def warning(self, message):
        self.write(f"WARNING: {message}")

    def error(self, message):
        self.write(f"ERROR: {message}")

    def write(self, message):
        if message:
            cleaned_message = str(message).replace("\r", "\n")
            self.log_file.write(cleaned_message + "\n")
            self.log_file.flush()


def write_progress(log_file, info):
    if info.get("status") == "downloading":
        downloaded = info.get("downloaded_bytes") or 0
        total = info.get("total_bytes") or info.get("total_bytes_estimate")
        percent = downloaded / total * 100 if total else 0
        speed = format_bytes(info.get("speed"))
        eta = format_eta(info.get("eta"))
        fragment_index = info.get("fragment_index")
        fragment_count = info.get("fragment_count")
        fragment_text = ""
        if fragment_index and fragment_count:
            fragment_text = f" (frag {fragment_index}/{fragment_count})"
        log_file.write(
            f"[download] {percent:5.1f}% of ~ {format_bytes(total)} "
            f"at {speed}/s ETA {eta}{fragment_text}\n"
        )
        log_file.flush()
    elif info.get("status") == "finished":
        filename = info.get("filename") or ""
        log_file.write(f"[download] 100.0% 下载完成: {filename}\n")
        log_file.flush()


def mark_download_status(output_dir, url, status, **updates):
    key = url_key(url)
    with locked_registry(output_dir) as registry:
        entry = registry.get(key, {})
        entry.update(
            {
                "url": url,
                "status": status,
                "updated_at": int(time.time()),
                **updates,
            }
        )
        registry[key] = entry


def run_download(movie_name, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, f"{movie_name}.%(ext)s")
    log_path = os.path.join(output_dir, f"{movie_name}.txt")

    with open(log_path, "a", encoding="utf-8", buffering=1) as log_file:
        os.dup2(log_file.fileno(), sys.stdout.fileno())
        os.dup2(log_file.fileno(), sys.stderr.fileno())

        try:
            log_file.write(f"[download] Destination: {output_template}\n")
            log_file.flush()
            ydl_opts = {
                "outtmpl": output_template,
                "fragment_retries": 10,
                "concurrent_fragment_downloads": CONCURRENT_FRAGMENT_DOWNLOADS,
                "logger": FileLogger(log_file),
                "progress_hooks": [lambda info: write_progress(log_file, info)],
                "noprogress": False,
                "progress_with_newline": True,
                "continuedl": True,
                "nopart": False,
                "restrictfilenames": False,
                "windowsfilenames": False,
                "no_color": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            log_file.write("[download] 任务结束\n")
            log_file.flush()
            final_files = matching_output_files(output_dir, movie_name)
            mark_download_status(
                output_dir,
                url,
                "finished",
                movie_name=movie_name,
                pid=os.getpid(),
                output=output_template,
                log=log_path,
                files=final_files,
            )
        except Exception:
            log_file.write("[download] 任务失败\n")
            log_file.write(traceback.format_exc())
            log_file.flush()
            mark_download_status(
                output_dir,
                url,
                "failed",
                movie_name=movie_name,
                pid=os.getpid(),
                output=output_template,
                log=log_path,
            )
            raise


def start_download(movie_name, url, output_dir):
    if not url.startswith(("http://", "https://")):
        raise ValueError("下载地址必须是 http 或 https URL")

    os.makedirs(output_dir, exist_ok=True)
    movie_name = clean_movie_name(movie_name)
    output_template = os.path.join(output_dir, f"{movie_name}.%(ext)s")
    log_path = os.path.join(output_dir, f"{movie_name}.txt")

    key = url_key(url)
    with locked_registry(output_dir) as registry:
        existing = registry.get(key)
        if existing:
            existing_pid = existing.get("pid")
            existing_name = existing.get("movie_name") or movie_name
            final_files = [
                path for path in existing.get("files", []) if os.path.exists(path)
            ] or matching_output_files(output_dir, existing_name)
            if final_files:
                existing.update(
                    {
                        "status": "finished",
                        "files": final_files,
                        "updated_at": int(time.time()),
                    }
                )
                registry[key] = existing
                return {
                    **existing,
                    "duplicate": True,
                    "message": "该链接已下载完成",
                    "pid": existing_pid,
                    "output": existing.get("output")
                    or os.path.join(output_dir, f"{existing_name}.%(ext)s"),
                    "log": existing.get("log")
                    or os.path.join(output_dir, f"{existing_name}.txt"),
                    "method": "yt_dlp.YoutubeDL",
                }
            if process_is_running(existing_pid):
                return {
                    **existing,
                    "duplicate": True,
                    "message": "该链接正在下载中",
                    "pid": existing_pid,
                    "output": existing.get("output")
                    or os.path.join(output_dir, f"{existing_name}.%(ext)s"),
                    "log": existing.get("log")
                    or os.path.join(output_dir, f"{existing_name}.txt"),
                    "method": "yt_dlp.YoutubeDL",
                }

        if matching_output_files(output_dir, movie_name):
            final_files = matching_output_files(output_dir, movie_name)
            registry[key] = {
                "url": url,
                "movie_name": movie_name,
                "status": "finished",
                "pid": None,
                "output": output_template,
                "log": log_path,
                "files": final_files,
                "updated_at": int(time.time()),
            }
            return {
                **registry[key],
                "duplicate": True,
                "message": "同名视频已存在",
                "method": "yt_dlp.YoutubeDL",
            }

        if part_file_exists(output_dir, movie_name):
            stale_part_message = "检测到同名未完成文件，将继续断点续传"
        else:
            stale_part_message = ""

    process = multiprocessing.Process(
        target=run_download,
        args=(movie_name, url, output_dir),
        name=f"yt_dlp_download:{movie_name}",
    )
    process.start()

    with locked_registry(output_dir) as registry:
        registry[key] = {
            "url": url,
            "movie_name": movie_name,
            "status": "downloading",
            "pid": process.pid,
            "output": output_template,
            "log": log_path,
            "method": "yt_dlp.YoutubeDL",
            "message": stale_part_message or "已开始后台下载",
            "updated_at": int(time.time()),
        }

    return {
        "pid": process.pid,
        "movie_name": movie_name,
        "status": "downloading",
        "duplicate": False,
        "output": output_template,
        "log": log_path,
        "method": "yt_dlp.YoutubeDL",
        "message": stale_part_message or "已开始后台下载",
    }


def main():
    parser = argparse.ArgumentParser(
        description="后台调用 yt_dlp Python API 下载 m3u8 视频"
    )
    parser.add_argument("name", help="电影名，例如：电影名")
    parser.add_argument(
        "url",
        nargs="?",
        default="https://hn.bfvvs.com/play/RdG7xDKd/index.m3u8",
        help="m3u8 地址",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("DOWNLOAD_DIR", DEFAULT_OUTPUT_DIR),
        help=f"输出目录，默认：{DEFAULT_OUTPUT_DIR}",
    )
    args = parser.parse_args()

    result = start_download(args.name, args.url, args.output_dir)
    print("已开始后台下载")
    print(f"PID: {result['pid']}")
    print(f"输出: {result['output']}")
    print(f"日志: {result['log']}")
    print(f"调用方式: {result['method']}")


if __name__ == "__main__":
    main()

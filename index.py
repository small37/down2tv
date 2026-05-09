#!/usr/bin/env python3
"""
MediaHub Web 服务 - 视频文件管理和投屏
"""

import os
import http.server
import socketserver
import threading
import re
import shutil
import subprocess
from datetime import datetime
from urllib.parse import quote
import socket
from flask import Flask, render_template, jsonify, request, send_from_directory
from urllib.parse import urlparse

from download_movie import clean_movie_name, start_download
from go2tv import DLNACaster

app = Flask(__name__, template_folder=".", static_folder=".")

# --- 配置 ---
MOVIE_DIR = os.environ.get("MOVIE_DIR", "./movie")
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", MOVIE_DIR)
DEFAULT_DOWNLOAD_URL = "https://hn.bfvvs.com/play/en5rEk5d/index.m3u8"
dlnaname = "客厅的小米盒子"
app.config["MOVIE_DIR"] = MOVIE_DIR
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv")
PART_SUFFIX = ".part"
DOWNLOAD_PROGRESS_RE = re.compile(r"(\[download\]\s+[^\r\n]+)")
DOWNLOAD_PERCENT_SPEED_RE = re.compile(
    r"\[download\]\s+"
    r"(?P<percent>\d+(?:\.\d+)?)%\s+"
    r".*?\bat\s+"
    r"(?P<speed>\S+(?:\s*\S+)?)/s\b",
    re.IGNORECASE,
)
FFMPEG_DURATION_RE = re.compile(
    r"Duration:\s+(?P<duration>\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
    re.IGNORECASE,
)
FFMPEG_PROGRESS_RE = re.compile(
    r"frame=.*?\btime=(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?).*?"
    r"\bspeed=\s*(?P<speed>[0-9.]+x)",
    re.IGNORECASE,
)


def ensure_movie_dir():
    if not os.path.exists(MOVIE_DIR):
        os.makedirs(MOVIE_DIR, exist_ok=True)


def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def format_size(size):
    size_gb = size / (1024 * 1024 * 1024)
    return f"{size_gb:.2f} GB"


def format_disk_size(size):
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def empty_progress():
    return {"text": "", "percent": "", "speed": ""}


def time_to_seconds(value):
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def start_yt_dlp_download(movie_name, url):
    ensure_download_dir()
    return start_download(movie_name, url, DOWNLOAD_DIR)


def movie_name_from_url(url):
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-1].lower().endswith(".m3u8"):
        return clean_movie_name(parts[-2])
    if parts:
        return clean_movie_name(os.path.splitext(parts[-1])[0])
    return "index"


def download_request_data():
    json_data = request.get_json(silent=True) or {}
    return {
        "url": str(
            json_data.get("url") or request.values.get("url") or ""
        ).strip(),
        "movie_name": (
            json_data.get("name")
            or json_data.get("movie_name")
            or request.values.get("name")
            or request.values.get("movie_name")
            or ""
        ),
    }


def progress_file_for(part_filename):
    final_filename = part_filename[: -len(PART_SUFFIX)]
    base, _ = os.path.splitext(final_filename)
    return os.path.join(MOVIE_DIR, f"{base}.txt")


def get_download_progress(part_filename):
    progress_path = progress_file_for(part_filename)
    if not os.path.exists(progress_path):
        return empty_progress()

    try:
        with open(
            progress_path, "r", encoding="utf-8", errors="ignore"
        ) as progress_file:
            content = progress_file.read()
    except Exception as e:
        print(f"读取下载进度失败: {progress_path}, {e}")
        return empty_progress()

    normalized_content = content.replace("\x1b[K", "").replace("\r", "\n")
    matches = DOWNLOAD_PROGRESS_RE.findall(normalized_content)
    for line in reversed(matches):
        download_match = DOWNLOAD_PERCENT_SPEED_RE.search(line)
        if download_match:
            percent = f"{download_match.group('percent')}%"
            speed = " ".join(download_match.group("speed").split())
            return {
                "text": f"{percent} / {speed}/s",
                "percent": percent,
                "speed": f"{speed}/s",
            }

    duration_matches = FFMPEG_DURATION_RE.findall(normalized_content)
    ffmpeg_matches = FFMPEG_PROGRESS_RE.findall(normalized_content)
    if duration_matches and ffmpeg_matches:
        duration_seconds = time_to_seconds(duration_matches[-1])
        current_time, current_speed = ffmpeg_matches[-1]
        current_seconds = time_to_seconds(current_time)
        percent_value = min(current_seconds / duration_seconds * 100, 100)
        percent = f"{percent_value:.1f}%"
        speed = " ".join(current_speed.split())
        return {
            "text": f"{percent} / {speed}",
            "percent": percent,
            "speed": speed,
        }

    if matches:
        return {"text": matches[-1].strip(), "percent": "", "speed": ""}

    return empty_progress()


def get_video_files():
    ensure_movie_dir()
    video_files = []
    try:
        raw = os.listdir(MOVIE_DIR)
        print(f"[get_video_files] 扫描目录: {MOVIE_DIR}, 发现 {len(raw)} 个条目: {raw}")
        for file in raw:
            # 跳过隐藏文件、目录、macOS 系统文件
            if file.startswith(".") or file == "movie":
                continue

            file_path = os.path.join(MOVIE_DIR, file)
            if not os.path.isfile(file_path):
                continue

            lower_file = file.lower()
            is_video = lower_file.endswith(VIDEO_EXTENSIONS)
            is_downloading = lower_file.endswith(
                tuple(f"{ext}{PART_SUFFIX}" for ext in VIDEO_EXTENSIONS)
            )

            # yt_dlp 会产生 xxx.mp4.part-Frag91.part 这类分片临时文件，不作为列表项展示。
            if not is_video and not is_downloading:
                continue

            size = os.path.getsize(file_path)
            modified_time = os.path.getmtime(file_path)
            progress = get_download_progress(file) if is_downloading else {}
            video_files.append(
                {
                    "name": file,
                    "path": file_path,
                    "size": format_size(size),
                    "size_bytes": size,
                    "modified_time": modified_time,
                    "modified_at": format_timestamp(modified_time),
                    "status": "downloading" if is_downloading else "ready",
                    "progress": progress.get("text", "") if is_downloading else "",
                    "progress_percent": (
                        progress.get("percent", "") if is_downloading else ""
                    ),
                    "progress_speed": (
                        progress.get("speed", "") if is_downloading else ""
                    ),
                }
            )

        video_files.sort(key=lambda x: x["modified_time"], reverse=True)
        print(
            f"[get_video_files] 过滤后剩余 {len(video_files)} 个视频: {[v['name'] for v in video_files]}"
        )
    except Exception as e:
        print(f"获取视频文件列表失败: {e}")
    return video_files


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/videos")
def get_videos():
    return jsonify({"videos": get_video_files()})


@app.route("/api/disk")
def get_disk_usage():
    ensure_movie_dir()
    total, used, free = shutil.disk_usage(MOVIE_DIR)
    percent = round(used / total * 100, 1) if total else 0
    return jsonify(
        {
            "success": True,
            "path": os.path.abspath(MOVIE_DIR),
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
            "total_text": format_disk_size(total),
            "used_text": format_disk_size(used),
            "free_text": format_disk_size(free),
        }
    )


@app.route("/api/hermes-chat", methods=["POST"])
def hermes_chat():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or request.values.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"success": False, "message": "请输入聊天内容"}), 400

    try:
        result = subprocess.run(
            ["hermes", "chat", "-Q", "-q", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=os.getcwd(),
        )
    except FileNotFoundError:
        return jsonify({"success": False, "message": "未找到 hermes 命令"}), 500
    except subprocess.TimeoutExpired as e:
        output = "\n".join(filter(None, [e.stdout, e.stderr]))
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Hermes 响应超时",
                    "output": output,
                }
            ),
            504,
        )

    output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
    if result.returncode != 0:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Hermes 执行失败，退出码 {result.returncode}",
                    "output": output,
                }
            ),
            500,
        )

    return jsonify({"success": True, "output": output})


@app.route("/api/download", methods=["GET", "POST"])
def download_video():
    data = download_request_data()
    url = data["url"]
    movie_name = clean_movie_name(data["movie_name"] or movie_name_from_url(url))

    if not url:
        return jsonify({"success": False, "message": "未指定下载地址 url"}), 400

    try:
        result = start_yt_dlp_download(movie_name, url)
        message = result.get("message") or f"已开始下载: {result['movie_name']}"
        return jsonify(
            {
                "success": True,
                "message": message,
                "status": result.get("status", "downloading"),
                "duplicate": result.get("duplicate", False),
                "url": url,
                "movie_name": result["movie_name"],
                "pid": result["pid"],
                "output": result["output"],
                "log": result["log"],
                "method": result["method"],
            }
        )
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/download/default", methods=["GET", "POST"])
def download_default_video():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or DEFAULT_DOWNLOAD_URL).strip()
    movie_name = clean_movie_name(
        data.get("name") or data.get("movie_name") or movie_name_from_url(url)
    )

    try:
        result = start_yt_dlp_download(movie_name, url)
        message = result.get("message") or f"已开始下载: {result['movie_name']}"
        return jsonify(
            {
                "success": True,
                "message": message,
                "status": result.get("status", "downloading"),
                "duplicate": result.get("duplicate", False),
                "url": url,
                "movie_name": result["movie_name"],
                "pid": result["pid"],
                "output": result["output"],
                "log": result["log"],
                "method": result["method"],
            }
        )
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/movie/<path:filename>")
def serve_movie(filename):
    return send_from_directory(MOVIE_DIR, filename)


@app.route("/api/cast", methods=["POST"])
def cast_video():
    data = request.json
    video_file = data.get("file")
    # device_name = data.get("device")
    device_name = dlnaname
    print(f"[cast_video] 请求投屏: file={video_file}, device={dlnaname}")
    if not video_file:
        return jsonify({"success": False, "message": "未指定视频文件"}), 400
    if not dlnaname:
        return jsonify({"success": False, "message": "未指定设备"}), 400
    video_file = os.path.basename(video_file)
    video_path = os.path.join(MOVIE_DIR, video_file)

    if not os.path.exists(video_path):
        return jsonify({"success": False, "message": "视频文件不存在"}), 404
    # return
    try:
        caster = DLNACaster(timeout=5)
        video_url = f"http://{request.host}/movie/{quote(video_file)}"
        print(f"正在投屏: {video_url} -> {device_name}")
        success, msg = caster.cast(video_url, device_name)
        if success:
            print(f"投屏成功: {video_file} -> {device_name}")
            return jsonify({"success": True, "message": f"正在投屏: {video_file}"})
        else:
            print(f"投屏失败: {msg}")
            return jsonify({"success": False, "message": msg}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
def delete_video():
    data = request.json
    video_file = data.get("file")

    if not video_file:
        return jsonify({"success": False, "message": "未指定视频文件"}), 400

    video_path = os.path.join(MOVIE_DIR, video_file)
    if not os.path.abspath(video_path).startswith(os.path.abspath(MOVIE_DIR)):
        return jsonify({"success": False, "message": "非法的文件路径"}), 400

    if not os.path.exists(video_path):
        return jsonify({"success": False, "message": "视频文件不存在"}), 404

    try:
        os.remove(video_path)
        return jsonify({"success": True, "message": f"已删除: {video_file}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 这个地址不会真的连接，只是用来获取本机出口IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    ensure_movie_dir()
    ip = get_local_ip()
    port = 5001

    print(f"本机访问: http://127.0.0.1:{port}")
    print(f"局域网访问: http://{ip}:{port}")

    app.run(debug=True, host="0.0.0.0", port=port)

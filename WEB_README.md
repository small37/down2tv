# MediaHub Web 版本 - 使用说明

## 项目概述

这是一个 Web 版本的 MediaHub，可以通过浏览器访问，管理和投屏本地视频文件。

## 功能特性

✅ **视频列表展示** - 自动扫描 movie 目录中的视频文件  
✅ **投屏播放** - 点击"投屏播放"按钮执行 go2tv.py 脚本  
✅ **删除视频** - 点击"删除"按钮删除视频文件  
✅ **搜索功能** - 支持按文件名搜索视频  
✅ **响应式设计** - 支持桌面和移动设备  

## 快速开始

### 1. 安装依赖

```bash
cd /Users/one/Documents/项目/测试1
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 创建 movie 目录

```bash
mkdir -p /Users/one/Documents/项目/测试1/movie
# 将MP4视频文件放入这个目录
```

### 3. 启动 Web 服务

```bash
python index.py
```

### 4. 访问 Web 界面

打开浏览器，访问：`http://localhost:5000`

## 目录结构

```
/Users/one/Documents/项目/测试1/
├── index.py              # Flask 后端应用
├── index.html            # Web 前端页面
├── styles.css            # CSS 样式文件（已内联到HTML）
├── requirements.txt      # 依赖配置
├── go2tv.py             # 投屏脚本（需要现有）
├── movie/               # 视频文件存放目录
│   ├── video1.mp4
│   ├── video2.mp4
│   └── ...
└── venv/                # Python 虚拟环境
```

## API 接口说明

### 1. 获取视频列表

**请求：**
```
GET /api/videos
```

**响应示例：**
```json
{
  "videos": [
    {
      "name": "星际穿越.mp4",
      "path": "./movie/星际穿越.mp4",
      "size": "2.45 GB",
      "size_bytes": 2630000000
    },
    ...
  ]
}
```

### 2. 投屏视频

**请求：**
```
POST /api/cast
Content-Type: application/json

{
  "file": "星际穿越.mp4",
  "device": 1
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "正在投屏: 星际穿越.mp4",
  "output": "..."
}
```

### 3. 删除视频

**请求：**
```
POST /api/delete
Content-Type: application/json

{
  "file": "星际穿越.mp4"
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "已删除: 星际穿越.mp4"
}
```

### 4. 获取 DLNA 设备列表（可选）

**请求：**
```
GET /api/devices
```

**响应示例：**
```json
{
  "devices": [
    {"id": 1, "name": "客厅电视"},
    {"id": 2, "name": "卧室投影仪"}
  ]
}
```

### 5. 后台下载 m3u8 视频

**请求参数：**

- `url`：视频 m3u8 地址，必填
- `name` 或 `movie_name`：电影名称，可选；不传时会从 URL 自动推导

**JSON 调用：**
```
POST /api/download
Content-Type: application/json

{
  "url": "https://hn.bfvvs.com/play/en5rEk5d/index.m3u8",
  "name": "电影名"
}
```

**curl 示例：**
```bash
curl -X POST "http://localhost:5001/api/download" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://hn.bfvvs.com/play/en5rEk5d/index.m3u8","name":"电影名"}'
```

**表单调用：**
```bash
curl -X POST "http://localhost:5001/api/download" \
  -d "url=https://hn.bfvvs.com/play/en5rEk5d/index.m3u8" \
  -d "name=电影名"
```

**URL 参数调用：**
```bash
curl "http://localhost:5001/api/download?url=https%3A%2F%2Fhn.bfvvs.com%2Fplay%2Fen5rEk5d%2Findex.m3u8&name=%E7%94%B5%E5%BD%B1%E5%90%8D"
```

**响应示例：**
```json
{
  "success": true,
  "message": "已开始后台下载",
  "status": "downloading",
  "duplicate": false,
  "url": "https://hn.bfvvs.com/play/en5rEk5d/index.m3u8",
  "movie_name": "电影名",
  "pid": 12345,
  "output": "./movie/电影名.%(ext)s",
  "log": "./movie/电影名.txt",
  "method": "yt_dlp.YoutubeDL"
}
```

下载目录默认使用 `MOVIE_DIR`，也可以启动前设置：

```bash
DOWNLOAD_DIR=/home/webmovie/movie MOVIE_DIR=/home/webmovie/movie python index.py
```

也可以直接使用脚本：

```bash
python download_movie.py "电影名" "https://hn.bfvvs.com/play/RdG7xDKd/index.m3u8"
```

接口会按下载链接去重：同一个 URL 已经下载完成或正在下载时，会返回 `duplicate: true`，不会重复启动后台进程。

### 6. 下载默认视频链接

默认链接为：`https://hn.bfvvs.com/play/en5rEk5d/index.m3u8`

**请求：**
```
GET /api/download/default
```

也可以使用 POST 覆盖链接或名称：

```
POST /api/download/default
Content-Type: application/json

{
  "url": "https://hn.bfvvs.com/play/en5rEk5d/index.m3u8",
  "name": "en5rEk5d"
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "已开始后台下载",
  "status": "downloading",
  "duplicate": false,
  "url": "https://hn.bfvvs.com/play/en5rEk5d/index.m3u8",
  "movie_name": "en5rEk5d",
  "pid": 12345,
  "output": "./movie/en5rEk5d.%(ext)s",
  "log": "./movie/en5rEk5d.txt",
  "method": "yt_dlp.YoutubeDL"
}
```

## 配置说明

### 修改视频目录

编辑 `index.py` 的第 14 行：
```python
MOVIE_DIR = './movie'  # 修改为实际目录路径
```

### 修改投屏脚本路径

编辑 `index.py` 的第 15 行：
```python
GO2TV_SCRIPT = './go2tv.py'  # 修改为实际脚本路径
```

### 修改 Web 服务器端口

编辑 `index.py` 最后一行：
```python
app.run(debug=True, host='0.0.0.0', port=5000)  # 修改端口号
```

## 支持的视频格式

- MP4 (.mp4) ✓
- AVI (.avi) ✓
- Matroska (.mkv) ✓
- MOV (.mov) ✓
- FLV (.flv) ✓
- WMV (.wmv) ✓

## 常见问题

### Q: 为什么看不到视频列表？

**可能原因：**
1. `movie` 目录不存在或为空
2. 目录中没有支持的视频格式文件
3. Web 服务没有正确启动

**解决方案：**
```bash
# 检查目录是否存在
ls -la /Users/one/Documents/项目/测试1/movie

# 检查视频文件格式
file /Users/one/Documents/项目/测试1/movie/*.mp4

# 重新启动服务
python index.py
```

### Q: 投屏时出现 "go2tv.py not found" 错误

**解决方案：**
1. 确认 `go2tv.py` 文件存在
2. 检查 `index.py` 中的 `GO2TV_SCRIPT` 路径是否正确
3. 确保 `go2tv.py` 有执行权限

### Q: 删除文件后页面没有更新

**解决方案：**
1. 手动刷新浏览器 (Ctrl+R 或 Cmd+R)
2. 检查浏览器开发者工具的网络标签是否有错误

### Q: Web 服务启动失败

**解决方案：**
```bash
# 检查 Flask 是否已安装
pip list | grep Flask

# 重新安装依赖
pip install -r requirements.txt

# 检查端口是否被占用
lsof -i :5000
```

## 高级用法

### 部署到服务器

修改启动命令：
```python
app.run(debug=False, host='0.0.0.0', port=80)
```

### 使用生产环境服务器（Gunicorn）

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:80 index:app
```

### 配置 SSL 证书

```bash
pip install pyopenssl
# 修改 app.run() 中添加 ssl_context='adhoc'
```

## 浏览器兼容性

- Chrome / Edge ✓
- Firefox ✓
- Safari ✓
- 移动浏览器 ✓

## 故障排查

### 启用调试模式

编辑 `index.py` 最后一行，设置 `debug=True`：
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```

### 查看详细日志

```bash
# 启动时显示详细日志
python -u index.py
```

## 安全提示

⚠️ **注意：**
- 不要在公网上直接运行此服务（缺少身份验证）
- 仅在局域网环境中使用
- 确保 `go2tv.py` 脚本是安全的

## 许可证

MIT License

## 支持

遇到问题？检查以下内容：
1. 查看浏览器开发者工具的控制台（F12）
2. 查看后端服务的日志输出
3. 确认网络连接正常
4. 尝试清除浏览器缓存

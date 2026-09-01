from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp
import os
import threading
import static_ffmpeg
import re
import requests
import subprocess
import time
from pathlib import Path

app = Flask(__name__)

# ============ FFmpeg Setup ============
static_ffmpeg.add_paths()

# ============ Main Folder Structure ============
BASE_DIR = os.path.join(os.path.expanduser("~"), "Bebabu Saver Pro")
YOUTUBE_DIR = os.path.join(BASE_DIR, "YouTube")
STARMAKER_DIR = os.path.join(BASE_DIR, "StarMaker")

# Auto-create folders
for folder in [BASE_DIR, YOUTUBE_DIR, STARMAKER_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"[FOLDER] Created: {folder}")

print(f"\n📁 Main Folder: {BASE_DIR}")
print(f"   ├── YouTube: {YOUTUBE_DIR}")
print(f"   └── StarMaker: {STARMAKER_DIR}\n")

# ============ YouTube Download ============
def youtube_download(url, format_type):
    try:
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': False,
            'noplaylist': True,
        }
        
        if format_type == 'mp3':
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(YOUTUBE_DIR, '%(title)s.%(ext)s'),
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            ydl_opts = {
                **common_opts,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(YOUTUBE_DIR, '%(title)s.%(ext)s'),
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"[YOUTUBE SUCCESS] {format_type.upper()} saved in: {YOUTUBE_DIR}")
        return True
    except Exception as e:
        print(f"[YOUTUBE ERROR] {str(e)}")
        return False

# ============ StarMaker Download ============
def starmaker_download(url, format_type):
    try:
        match = re.search(r"recordingId=(\d+)", url)
        if not match:
            print("[STARMAKER ERROR] Recording ID not found!")
            return False
        
        rec_id = match.group(1)
        mp4_file = os.path.join(STARMAKER_DIR, f"bebabu_{rec_id}.mp4")
        mp3_file = os.path.join(STARMAKER_DIR, f"StarMaker_{rec_id}.mp3")
        
        direct_mp4_url = f"https://static.smintro.com/production/uploading/recordings/{rec_id}/master.mp4"
        
        print(f"[STARMAKER] Downloading recording ID: {rec_id}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(direct_mp4_url, headers=headers, stream=True)
        
        if response.status_code != 200:
            print(f"[STARMAKER ERROR] Server returned: {response.status_code}")
            return False
        
        # Download MP4
        with open(mp4_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
        print(f"[STARMAKER] MP4 downloaded: {mp4_file}")
        
        # If MP3 requested, convert
        if format_type == 'mp3':
            print("[STARMAKER] Converting to MP3...")
            ff_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe")
            if not os.path.exists(ff_path):
                ff_path = "ffmpeg"
            
            subprocess.run([ff_path, "-y", "-i", mp4_file, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3_file],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[STARMAKER] MP3 created: {mp3_file}")
            
            # Delete MP4 after conversion
            if os.path.exists(mp4_file):
                os.remove(mp4_file)
                print("[STARMAKER] Temporary MP4 deleted")
        
        print(f"[STARMAKER SUCCESS] {format_type.upper()} saved in: {STARMAKER_DIR}")
        return True
        
    except Exception as e:
        print(f"[STARMAKER ERROR] {str(e)}")
        return False

# ============ Background Download Handler ============
def bg_download(url, format_type, platform):
    if platform == 'youtube':
        youtube_download(url, format_type)
    elif platform == 'starmaker':
        starmaker_download(url, format_type)
    else:
        print(f"[ERROR] Unknown platform: {platform}")

# ============ Flask Routes ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/download', methods=['POST'])
def download_song():
    data = request.json
    url = data.get('url', '').strip()
    format_type = data.get('format_type', 'mp3')
    
    if not url:
        return jsonify({'success': False, 'message': 'Kripya ek valid URL daalein!'})
    
    if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
        platform = 'youtube'
    elif 'starmaker' in url.lower():
        platform = 'starmaker'
    else:
        return jsonify({'success': False, 'message': 'Sirf YouTube ya StarMaker URL daalein!'})
    
    try:
        download_thread = threading.Thread(target=bg_download, args=(url, format_type, platform))
        download_thread.start()
        
        folder_path = YOUTUBE_DIR if platform == 'youtube' else STARMAKER_DIR
        
        return jsonify({
            'success': True,
            'message': f'{platform.upper()} {format_type.upper()} download started!',
            'platform': platform,
            'folder': folder_path
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error: {str(e)}"})

@app.route('/list_downloads', methods=['GET'])
def list_downloads():
    try:
        youtube_files = []
        starmaker_files = []
        
        if os.path.exists(YOUTUBE_DIR):
            youtube_files = [f for f in os.listdir(YOUTUBE_DIR) if os.path.isfile(os.path.join(YOUTUBE_DIR, f))]
        
        if os.path.exists(STARMAKER_DIR):
            starmaker_files = [f for f in os.listdir(STARMAKER_DIR) if os.path.isfile(os.path.join(STARMAKER_DIR, f))]
        
        return jsonify({
            'success': True,
            'youtube': youtube_files,
            'starmaker': starmaker_files
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/downloads/<platform>/<filename>')
def download_file(platform, filename):
    if platform == 'youtube':
        folder = YOUTUBE_DIR
    elif platform == 'starmaker':
        folder = STARMAKER_DIR
    else:
        return "Invalid platform", 404
    return send_from_directory(folder, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
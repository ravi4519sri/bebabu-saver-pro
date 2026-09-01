from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
import yt_dlp
import os
import threading
import static_ffmpeg
import re
import requests
import subprocess
import time
import shutil
from pathlib import Path

app = Flask(__name__)

# ============ FFmpeg Setup ============
static_ffmpeg.add_paths()

# ============ Folder Paths ============
# Use temp folder for Render
if os.path.exists("/opt/render"):
    BASE_DIR = "/opt/render/Bebabu Saver Pro"
    TEMP_DIR = "/tmp/downloads"
else:
    BASE_DIR = os.path.join(os.path.expanduser("~"), "Bebabu Saver Pro")
    TEMP_DIR = os.path.join(os.getcwd(), "temp_downloads")

YOUTUBE_DIR = os.path.join(BASE_DIR, "YouTube")
STARMAKER_DIR = os.path.join(BASE_DIR, "StarMaker")

# Auto-create folders
for folder in [BASE_DIR, YOUTUBE_DIR, STARMAKER_DIR, TEMP_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"[FOLDER] Created: {folder}")

print(f"\n📁 Main Folder: {BASE_DIR}")
print(f"   ├── YouTube: {YOUTUBE_DIR}")
print(f"   └── StarMaker: {STARMAKER_DIR}")
print(f"   └── Temp: {TEMP_DIR}\n")

# ============ YouTube Download (Returns file path) ============
def youtube_download(url, format_type):
    try:
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': False,
            'noplaylist': True,
        }
        
        # Use TEMP_DIR for downloading
        download_path = TEMP_DIR
        
        if format_type == 'mp3':
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
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
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Handle MP3 extension change
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            print(f"[YOUTUBE SUCCESS] File downloaded: {filename}")
            return filename
        
    except Exception as e:
        print(f"[YOUTUBE ERROR] {str(e)}")
        return None

# ============ StarMaker Download (Returns file path) ============
def starmaker_download(url, format_type):
    try:
        match = re.search(r"recordingId=(\d+)", url)
        if not match:
            print("[STARMAKER ERROR] Recording ID not found!")
            return None
        
        rec_id = match.group(1)
        mp4_file = os.path.join(TEMP_DIR, f"bebabu_{rec_id}.mp4")
        mp3_file = os.path.join(TEMP_DIR, f"StarMaker_{rec_id}.mp3")
        
        direct_mp4_url = f"https://static.smintro.com/production/uploading/recordings/{rec_id}/master.mp4"
        
        print(f"[STARMAKER] Downloading recording ID: {rec_id}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(direct_mp4_url, headers=headers, stream=True)
        
        if response.status_code != 200:
            print(f"[STARMAKER ERROR] Server returned: {response.status_code}")
            return None
        
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
            return mp3_file
        
        return mp4_file
        
    except Exception as e:
        print(f"[STARMAKER ERROR] {str(e)}")
        return None

# ============ Background Download Handler ============
def bg_download(url, format_type, platform, download_id):
    try:
        if platform == 'youtube':
            file_path = youtube_download(url, format_type)
        elif platform == 'starmaker':
            file_path = starmaker_download(url, format_type)
        else:
            print(f"[ERROR] Unknown platform: {platform}")
            return
        
        if file_path and os.path.exists(file_path):
            # Store file path in a global dict for retrieval
            download_store[download_id] = file_path
            print(f"[SUCCESS] File ready for download: {file_path}")
        else:
            print(f"[ERROR] File not found after download")
            
    except Exception as e:
        print(f"[ERROR] Background download failed: {str(e)}")

# Store for completed downloads
download_store = {}

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
        return jsonify({'success': False, 'message': 'Please enter a valid URL!'})
    
    if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
        platform = 'youtube'
    elif 'starmaker' in url.lower():
        platform = 'starmaker'
    else:
        return jsonify({'success': False, 'message': 'Only YouTube or StarMaker URLs are supported!'})
    
    try:
        # Generate unique ID for this download
        download_id = str(int(time.time() * 1000))
        
        # Start background download
        download_thread = threading.Thread(target=bg_download, args=(url, format_type, platform, download_id))
        download_thread.start()
        
        return jsonify({
            'success': True,
            'message': f'{platform.upper()} {format_type.upper()} download started!',
            'platform': platform,
            'download_id': download_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error: {str(e)}"})

@app.route('/get_file/<download_id>')
def get_file(download_id):
    """Serve the downloaded file to user"""
    if download_id not in download_store:
        return jsonify({'success': False, 'message': 'File not ready yet!'}), 404
    
    file_path = download_store[download_id]
    
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found!'}), 404
    
    try:
        # Get filename from path
        filename = os.path.basename(file_path)
        
        # Clean up: remove from store after download
        del download_store[download_id]
        
        # Send file to user
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import yt_dlp
import os
import static_ffmpeg
import re
import requests
import subprocess
import time
import shutil
import tempfile

app = Flask(__name__)

# ============ FFmpeg Setup ============
try:
    static_ffmpeg.add_paths()
    print("[FFMPEG] Paths added successfully")
except Exception as e:
    print(f"[FFMPEG] Error: {e}")

# ============ Temp Folder ============
TEMP_DIR = tempfile.mkdtemp()
print(f"\n📁 Temp Folder: {TEMP_DIR}\n")

# ============ YouTube Download ============
def youtube_download(url, format_type):
    try:
        if '/shorts/' in url:
            video_id = url.split('/shorts/')[-1].split('?')[0]
            url = f'https://www.youtube.com/watch?v={video_id}'
            print(f"[YOUTUBE] Converted Shorts URL to: {url}")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'noplaylist': True,
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        if format_type == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        
        print(f"[YOUTUBE] Starting download...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            print(f"[YOUTUBE] File: {filename}")
            return filename
        
    except Exception as e:
        print(f"[YOUTUBE ERROR] {str(e)}")
        return None

# ============ StarMaker Download ============
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
        
        print(f"[STARMAKER] Downloading ID: {rec_id}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(direct_mp4_url, headers=headers, stream=True, timeout=60)
        
        if response.status_code != 200:
            print(f"[STARMAKER ERROR] Status: {response.status_code}")
            return None
        
        with open(mp4_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
        print(f"[STARMAKER] MP4 downloaded")
        
        if format_type == 'mp3':
            print("[STARMAKER] Converting to MP3...")
            ff_path = shutil.which('ffmpeg') or os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe")
            if not os.path.exists(ff_path):
                ff_path = 'ffmpeg'
            
            subprocess.run([ff_path, "-y", "-i", mp4_file, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3_file],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[STARMAKER] MP3 created")
            if os.path.exists(mp4_file):
                os.remove(mp4_file)
            return mp3_file
        
        return mp4_file
        
    except Exception as e:
        print(f"[STARMAKER ERROR] {str(e)}")
        return None

# ============ Routes ============
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
    try:
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format_type', 'mp3')
        
        if not url:
            return jsonify({'success': False, 'message': 'Please enter a valid URL!'}), 400
        
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower() or '/shorts/' in url:
            platform = 'youtube'
        elif 'starmaker' in url.lower():
            platform = 'starmaker'
        else:
            return jsonify({'success': False, 'message': 'Only YouTube or StarMaker URLs are supported!'}), 400
        
        print(f"[DOWNLOAD] Platform: {platform}, Format: {format_type}")
        
        if platform == 'youtube':
            file_path = youtube_download(url, format_type)
        else:
            file_path = starmaker_download(url, format_type)
        
        if not file_path or not os.path.exists(file_path):
            print(f"[DOWNLOAD] File not found: {file_path}")
            return jsonify({'success': False, 'message': 'Download failed! Please try again.'}), 500
        
        filename = os.path.basename(file_path)
        print(f"[DOWNLOAD] Sending file: {filename}")
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        print(f"[DOWNLOAD ERROR] {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
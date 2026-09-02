from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import yt_dlp
import os
import re
import requests
import subprocess
import uuid
import shutil
import time

app = Flask(__name__)

# ============ YouTube Download (Synchronous) ============
def download_youtube(url, format_type, job_dir):
    try:
        # CLEAN URL: Remove &list=... (playlist) part
        if '&list=' in url:
            url = url.split('&list=')[0]
            print(f"[YOUTUBE] Cleaned URL: {url}")

        # Handle Shorts
        if '/shorts/' in url:
            video_id = url.split('/shorts/')[-1].split('?')[0]
            url = f'https://www.youtube.com/watch?v={video_id}'
            print(f"[YOUTUBE] Converted Shorts URL to: {url}")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'noplaylist': True,
            'extract_flat': False,
            'outtmpl': os.path.join(job_dir, '%(title)s.%(ext)s'),
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            'cookiefile': None,  # Avoid cookie issues
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        if format_type == 'mp3':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return filename

    except Exception as e:
        print(f"[YOUTUBE ERROR] {e}")
        return None

# ============ StarMaker Download (Synchronous) ============
def download_starmaker(url, format_type, job_dir):
    try:
        match = re.search(r"recordingId=(\d+)", url)
        if not match:
            print("[STARMAKER] Recording ID not found")
            return None

        rec_id = match.group(1)
        mp4_path = os.path.join(job_dir, f"starmaker_{rec_id}.mp4")
        mp3_path = os.path.join(job_dir, f"starmaker_{rec_id}.mp3")

        download_url = f"https://static.smintro.com/production/uploading/recordings/{rec_id}/master.mp4"
        headers = {'User-Agent': 'Mozilla/5.0'}

        resp = requests.get(download_url, headers=headers, stream=True, timeout=60)
        if resp.status_code != 200:
            return None

        with open(mp4_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)

        if format_type == 'mp3':
            subprocess.run(['ffmpeg', '-y', '-i', mp4_path, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', mp3_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(mp4_path)
            return mp3_path

        return mp4_path

    except Exception as e:
        print(f"[STARMAKER ERROR] {e}")
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
def download():
    data = request.get_json()
    url = data.get('url', '').strip()
    format_type = data.get('format_type', 'mp3')

    if not url:
        return jsonify({'success': False, 'message': 'URL is required'}), 400

    # Detect platform
    if 'youtube.com' in url or 'youtu.be' in url:
        platform = 'youtube'
    elif 'starmaker' in url:
        platform = 'starmaker'
    else:
        return jsonify({'success': False, 'message': 'Unsupported URL'}), 400

    # Create unique temp folder
    job_id = str(uuid.uuid4())
    job_dir = f"/tmp/bebabu_{job_id}"
    os.makedirs(job_dir, exist_ok=True)

    try:
        if platform == 'youtube':
            file_path = download_youtube(url, format_type, job_dir)
        else:
            file_path = download_starmaker(url, format_type, job_dir)

        if not file_path or not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Download failed'}), 500

        return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

    finally:
        # Cleanup after response
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except:
            pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
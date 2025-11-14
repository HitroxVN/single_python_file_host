from flask import Flask, request, send_from_directory, redirect, url_for
import os, string, random, threading
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)

# Dir uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# max size file can uploads (MB)
MB = 10
app.config['MAX_CONTENT_LENGTH'] = 1024**2 * MB
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#Storage limited (free hosting)
total_storage_mb = 1024
total_storage_allow = total_storage_mb * 1024**2

#cache
total_upload_size_cache = 0
cache_lock = threading.Lock()

ENABLE_DEBUG = True
ENABLE_AUTO_DELETE = True

def log(msg):
    if ENABLE_DEBUG:
        print(msg)

def site_url() -> str:
    FORCE_HTTPS = False
    proto = 'https' if request.is_secure or FORCE_HTTPS else 'http'
    host = request.host
    return f"{proto}://{host}"

#generate a random string of characters with value
def rnd_str(length: int) -> str:
    chars = string.ascii_letters + string.digits + "-_"
    return ''.join(random.choice(chars) for _ in range(length))

def get_total_upload_size(force_recalc=False) -> int:
    global total_upload_size_cache
    if force_recalc or total_upload_size_cache == 0:
        total = sum(os.path.getsize(os.path.join(UPLOAD_FOLDER, f))
                    for f in os.listdir(UPLOAD_FOLDER)
                    if os.path.isfile(os.path.join(UPLOAD_FOLDER, f)))
        with cache_lock:
            total_upload_size_cache = total
    return total_upload_size_cache

def add_to_total_upload_size(size: int):
    global total_upload_size_cache
    with cache_lock:
        total_upload_size_cache += size

def subtract_from_total_upload_size(size: int):
    global total_upload_size_cache
    with cache_lock:
        total_upload_size_cache -= size

def free_space_if_needed():
    if not ENABLE_AUTO_DELETE:
        log("[INFO] Auto-delete disabled.")
        return
    
    total = get_total_upload_size()
    if total <= total_storage_allow:
        return
    
    files = [os.path.join(UPLOAD_FOLDER, f) for f in os.listdir(UPLOAD_FOLDER)]
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=lambda x: os.path.getmtime(x))  # xóa file cũ nhất
    
    for f in files:
        if total <= total_storage_allow:
            break
        try:
            size_removed = os.path.getsize(f)
            os.remove(f)
            subtract_from_total_upload_size(size_removed)
            total -= size_removed
            log(f"[INFO] Auto-removed: {f}")
        except Exception as e:
            log(f"[ERROR] Cannot delete {f}: {e}")
            continue

def format_size(bytes_size: int) -> str:
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024**2:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024**3:
        return f"{bytes_size / 1024**2:.2f} MB"
    elif bytes_size < 1024**4:
        return f"{bytes_size / 1024**3:.2f} GB"
    else:
        return f"{bytes_size / 1024**4:.2f} TB"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        total_used_bytes = get_total_upload_size()
        total_used_formatted = format_size(total_used_bytes)
        total_limit_formatted = format_size(total_storage_allow)
        return f'''
    <html>
        <head><title>Filehosting</title></head>
        <body>
    <pre>
 === Upload files ===
You can upload files to this site via a simple HTTP POST, using:
curl -F "file=@/path/to/your/file.txt" {site_url()}

Or if you want to redirect to curl and have a file extension, add a "test":
echo "hello world" | curl -F "file=@-;filename=test.txt" {site_url()}

Or simply choose a file and click "upload" below:
    </pre>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file">
        <button type="submit">upload</button>
    </form>
    <pre>
 === File Sizes etc. ===
The maximum allowed file size is {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} Mb.
Storage used: {total_used_formatted} / {total_limit_formatted}

 === Source ===
Python flask <a href="https://github.com/HitroxVN/single_python_file_host">Github</a>
    </pre>
    </body>
        </html>
    '''
    
    if request.method == 'POST':
        uploaded_file = request.files.get('file')
        if uploaded_file and uploaded_file.filename != '':
            filename = secure_filename(uploaded_file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)

            if get_total_upload_size() + file_size > total_storage_allow:
                return f"<pre>Storage full. Cannot upload file ({format_size(file_size)}).</pre>", 413

            # random name file duplicate
            if os.path.exists(save_path):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{rnd_str(6)}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            uploaded_file.save(save_path)
            
            add_to_total_upload_size(file_size)
            
            free_space_if_needed()
            download_url = f"{site_url()}/{filename}"

            return f'''
    <pre>Access your file here: <a href="{download_url}">{download_url}</a></pre>
    '''
        else:
            return redirect(url_for('index'))

#exception MAX_CONTENT_LENGTH 413
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return f'''
    <pre>The maximum allowed file size is {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} Mb.</pre>
    ''', 413

#router download file
@app.route('/<path:filename>')
def download_file(filename):
    safe_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    return send_from_directory(app.config['UPLOAD_FOLDER'], os.path.basename(safe_path), as_attachment=True)

#running in host:port, enable debug
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9418)
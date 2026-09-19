import os
import requests
from flask import Flask, request, jsonify, send_from_path

app = Flask(__name__)
STORAGE = '/tmp/render_uploads'
os.makedirs(STORAGE, exist_ok=True)

GITHUB_REPO = "your_username/your_repo_name"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Set this in Render Env vars

@app.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files['file']
    job_id = os.urandom(8).hex()
    
    # Save code script into memory local storage path
    job_dir = os.path.join(STORAGE, job_id)
    os.makedirs(job_dir, exist_ok=True)
    file.save(os.path.join(job_dir, 'main.py'))

    # Remotely trigger the free GitHub action runner pipeline 
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {
        "ref": "main", 
        "inputs": {"job_id": job_id}
    }
    url = f"https://github.com{GITHUB_REPO}/actions/workflows/build-apk.yml/dispatches"
    requests.post(url, json=data, headers=headers)

    return jsonify({"status": "Compiling via GitHub Runners...", "job_id": job_id})

@app.route('/fetch-script/<job_id>', methods=['GET'])
def send_to_github(job_id):
    # GitHub Runner hits this endpoint to grab the raw uploaded script
    return send_from_path(os.path.join(STORAGE, job_id), 'main.py')

@app.route('/upload-finished/<job_id>', methods=['POST'])
def accept_compiled_apk(job_id):
    # GitHub Runner hits this endpoint to drop off the finished .apk binary
    file = request.files['file']
    job_dir = os.path.join(STORAGE, job_id)
    file.save(os.path.join(job_dir, 'app.apk'))
    return jsonify({"status": "Saved"}), 200

@app.route('/download/<job_id>', methods=['GET'])
def download(job_id):
    return send_from_path(os.path.join(STORAGE, job_id), 'app.apk', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

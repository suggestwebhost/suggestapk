import os
from flask import Flask, request, jsonify, send_from_path
from werkzeug.utils import secure_filename
from tasks import compile_apk

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.py'):
        return jsonify({'error': 'Invalid file type. Only .py files allowed.'}), 400

    filename = secure_filename(file.filename)
    # Buildozer expects the entrypoint to be named main.py
    job_id = os.urandom(8).hex()
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    file.save(os.path.join(job_dir, 'main.py'))

    # Trigger Celery Task asynchronously
    task = compile_apk.delay(job_dir, job_id)
    
    return jsonify({
        'message': 'Compilation started',
        'job_id': job_id,
        'task_id': task.id,
        'status_url': f'/status/{task.id}'
    }), 202

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    task = compile_apk.AsyncResult(task_id)
    response = {'state': task.state}
    if task.state == 'SUCCESS':
        response['download_url'] = f"/download/{task.result['job_id']}/{task.result['apk_name']}"
    elif task.state == 'FAILURE':
        response['error'] = str(task.info)
    return jsonify(response)

@app.route('/download/<job_id>/<apk_name>', methods=['GET'])
def download(job_id, apk_name):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], job_id, 'bin')
    return send_from_path(directory, apk_name, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

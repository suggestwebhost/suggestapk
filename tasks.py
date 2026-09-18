import os
import subprocess
from celery import Celery

# Configure Celery with Redis broker
celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

@celery_app.task(bind=True)
def compile_apk(self, job_dir, job_id):
    try:
        # 1. Initialize buildozer inside the temporary directory
        subprocess.run(['buildozer', 'init'], cwd=job_dir, check=True)
        
        # 2. (Optional) Programmatically modify buildozer.spec if you need to alter requirements
        # By default, buildozer.spec assumes a basic kivy app requirement.
        
        # 3. Compile the Android Debug build
        # This will download the Android SDK/NDK on the first run inside the docker.
        process = subprocess.run(
            ['buildozer', 'android', 'debug'], 
            cwd=job_dir, 
            capture_output=True, 
            text=True
        )
        
        if process.returncode != 0:
            raise Exception(f"Buildozer compilation failed: {process.stderr}")
            
        # 4. Find the generated .apk file inside the 'bin' folder
        bin_dir = os.path.join(job_dir, 'bin')
        apks = [f for f in os.listdir(bin_dir) if f.endswith('.apk')]
        
        if not apks:
            raise Exception("APK compilation finished but file was not found.")
            
        return {
            'status': 'Success',
            'job_id': job_id,
            'apk_name': apks[0]
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e

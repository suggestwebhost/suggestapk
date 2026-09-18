import os
import re
import subprocess
from celery import Celery

celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

def extract_dependencies(file_path):
    """Parses a Python file to find top-level imported libraries."""
    dependencies = set()
    # Basic core Python libraries to completely ignore for Android packaging
    stdlib = {'os', 'sys', 'time', 'math', 'json', 're', 'random', 'collections'}
    
    with open(file_path, 'r') as f:
        content = f.read()
        
    # Matches: import package OR from package import ...
    imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
    for imp in imports:
        if imp not in stdlib:
            dependencies.add(imp)
            
    # Fallback default: framework UI engine (e.g., kivy) if nothing found
    if not dependencies:
        dependencies.add('kivy')
        
    return ", ".join(list(dependencies))

@celery_app.task(bind=True)
def compile_apk(self, job_dir, job_id):
    try:
        # 1. Initialize clean buildozer configurations
        subprocess.run(['buildozer', 'init'], cwd=job_dir, check=True)
        
        # 2. Extract dependencies from the uploaded script
        main_py_path = os.path.join(job_dir, 'main.py')
        detected_requirements = extract_dependencies(main_py_path)
        
        # 3. Dynamic replacement inside buildozer.spec
        spec_path = os.path.join(job_dir, 'buildozer.spec')
        with open(spec_path, 'r') as file:
            spec_content = file.read()
            
        # Target the requirements line and swap it with detected dependencies
        spec_content = re.sub(
            r'^requirements\s*=\s*.*$', 
            f'requirements = python3, {detected_requirements}', 
            spec_content, 
            flags=re.MULTILINE
        )
        
        with open(spec_path, 'w') as file:
            file.write(spec_content)
        
        # 4. Compile the target Android bundle
        process = subprocess.run(
            "yes|buildozer android debug", 
            cwd=job_dir, 
            capture_output=True,
            text=True
        )
        
        if process.returncode != 0:
            raise Exception(f"Buildozer engine compilation error: {process.stderr}")
            
        bin_dir = os.path.join(job_dir, 'bin')
        apks = [f for f in os.listdir(bin_dir) if f.endswith('.apk')]
        
        if not apks:
            raise Exception("Compilation finished, but APK generation vanished.")
            
        return {
            'status': 'Success',
            'job_id': job_id,
            'apk_name': apks[0]
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e

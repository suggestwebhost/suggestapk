import os
import re
import subprocess
from celery import Celery

# Configure Celery with Redis broker and backend storage
celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

def extract_dependencies(file_path):
    """
    Parses the uploaded Python file to detect top-level imported libraries.
    """
    dependencies = set()
    stdlib = {
        'os', 'sys', 'time', 'math', 'json', 're', 'random', 'collections', 
        'datetime', 'hashlib', 'socket', 'threading', 'itertools', 'functools'
    }
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        for imp in imports:
            if imp not in stdlib:
                dependencies.add(imp)
    except Exception:
        pass
        
    if not dependencies:
        dependencies.add('kivy')
    return ", ".join(list(dependencies))


@celery_app.task(bind=True)
def compile_apk(self, job_dir, job_id):
    try:
        # 1. Initialize clean buildozer configurations
        subprocess.run(['buildozer', 'init'], cwd=job_dir, check=True)
        
        # 2. Extract dependencies from the uploaded user script
        main_py_path = os.path.join(job_dir, 'main.py')
        detected_requirements = extract_dependencies(main_py_path)
        
        # 3. Dynamic adjustment of parameters inside buildozer.spec
        spec_path = os.path.join(job_dir, 'buildozer.spec')
        with open(spec_path, 'r', encoding='utf-8') as file:
            spec_content = file.read()
            
        # Target requirements line
        spec_content = re.sub(
            r'^requirements\s*=\s*.*$', 
            f'requirements = python3, {detected_requirements}', 
            spec_content, 
            flags=re.MULTILINE
        )
        
        # CRUCIAL FIX: Force log_level to max debug mode (2) so failures emit details
        spec_content = re.sub(
            r'^log_level\s*=\s*.*$', 
            'log_level = 2', 
            spec_content, 
            flags=re.MULTILINE
        )
        
        with open(spec_path, 'w', encoding='utf-8') as file:
            file.write(spec_content)
        
        # 4. Inject headless environment patches to force execution outside venvs
        # We append local bin tools to PATH to stop Buildozer from breaking on virtualenv binaries
        env_override = os.environ.copy()
        env_override["PATH"] = f"/home/builder/.local/bin:{env_override.get('PATH', '')}"
        
        # Execute compilation via shell using automatic prompt agreement
        process = subprocess.Popen(
            "yes | buildozer android debug", 
            cwd=job_dir, 
            shell=True,
            env=env_override,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            # We output stdout here because log_level = 2 dumps the exact compile trace to stdout
            raise Exception(f"Buildozer engine compilation error.\nSTDOUT_LOGS:\n{stdout}\nSTDERR_LOGS:\n{stderr}")
            
        # 5. Locate the generated output binary
        bin_dir = os.path.join(job_dir, 'bin')
        if not os.path.exists(bin_dir):
            raise Exception(f"Build finished successfully, but output directory was missing.\nLogs: {stdout}")

        apks = [f for f in os.listdir(bin_dir) if f.endswith('.apk')]
        if not apks:
            raise Exception("Compilation finished, but no .apk binary found in the bin directory.")
            
        return {
            'status': 'Success',
            'job_id': job_id,
            'apk_name': apks[0]
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e

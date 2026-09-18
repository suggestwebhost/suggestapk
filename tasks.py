import os
import re
import subprocess
from celery import Celery

# Configure Celery with Redis broker and backend storage
celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

def extract_dependencies(file_path):
    dependencies = set()
    stdlib = {'os', 'sys', 'time', 'math', 'json', 're', 'random', 'collections', 'datetime'}
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
        # 1. Initialize configurations
        subprocess.run(['buildozer', 'init'], cwd=job_dir, check=True)
        
        # 2. Update configurations
        main_py_path = os.path.join(job_dir, 'main.py')
        detected_requirements = extract_dependencies(main_py_path)
        
        spec_path = os.path.join(job_dir, 'buildozer.spec')
        with open(spec_path, 'r', encoding='utf-8') as file:
            spec_content = file.read()
            
        spec_content = re.sub(r'^requirements\s*=\s*.*$', f'requirements = python3, {detected_requirements}', spec_content, flags=re.MULTILINE)
        spec_content = re.sub(r'^log_level\s*=\s*.*$', 'log_level = 2', spec_content, flags=re.MULTILINE)
        
        # EXPLICIT LICENSE AUTO-ACCEPTANCE FOR DOCKER CONTEXTS
        if 'android.accept_sdk_license' in spec_content:
            spec_content = re.sub(r'^#?\s*android\.accept_sdk_license\s*=\s*.*$', 'android.accept_sdk_license = True', spec_content, flags=re.MULTILINE)
        else:
            spec_content += "\nandroid.accept_sdk_license = True\n"

        with open(spec_path, 'w', encoding='utf-8') as file:
            file.write(spec_content)
        
        # 3. Create a physical text file to catch internal crash dumps
        log_file_path = os.path.join(job_dir, "buildozer_output.log")
        
        # Force execution paths directly to where pip installs global CLI commands
        env_override = os.environ.copy()
        env_override["PATH"] = f"/home/builder/.local/bin:/usr/local/bin:/usr/bin:/bin:{env_override.get('PATH', '')}"
        
        # 4. Fire buildozer as an absolute tracking array writing directly to disk
        with open(log_file_path, "w") as log_file:
            process = subprocess.run(
                ["buildozer", "android", "debug"],
                cwd=job_dir,
                env=env_override,
                stdout=log_file,
                stderr=subprocess.STDOUT, # Merge errors directly into the same file
                text=True
            )
            
        # Read the file content to verify success or print to trace logs
        with open(log_file_path, "r") as log_file:
            console_dump = log_file.read()
        
        if process.returncode != 0:
            raise Exception(f"Buildozer exited early with code {process.returncode}.\nCRASH LOGS:\n{console_dump}")
            
        # 5. Extract output binary
        bin_dir = os.path.join(job_dir, 'bin')
        if not os.path.exists(bin_dir):
            raise Exception(f"Build finished cleanly, but target directory went missing.\nLogs:\n{console_dump}")

        apks = [f for f in os.listdir(bin_dir) if f.endswith('.apk')]
        if not apks:
            raise Exception(f"APK not generated.\nLogs:\n{console_dump}")
            
        return {
            'status': 'Success',
            'job_id': job_id,
            'apk_name': apks[0]
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e

import os
import re
import subprocess
from celery import Celery

# Configure Celery with Redis broker and backend storage
celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

def extract_dependencies(file_path):
    """
    Parses the uploaded Python file to detect top-level imported libraries.
    Automatically excludes basic standard libraries to avoid bloating the build.
    """
    dependencies = set()
    # Standard Python libraries that do not need to be requested in buildozer.spec
    stdlib = {
        'os', 'sys', 'time', 'math', 'json', 're', 'random', 'collections', 
        'datetime', 'hashlib', 'socket', 'threading', 'itertools', 'functools'
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Matches: "import package" OR "from package import ..."
        imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        for imp in imports:
            if imp not in stdlib:
                dependencies.add(imp)
    except Exception:
        pass  # Fallback gracefully if reading fails
            
    # Fallback default: framework UI engine (like kivy) if no dependencies detected
    if not dependencies:
        dependencies.add('kivy')
        
    return ", ".join(list(dependencies))


@celery_app.task(bind=True)
def compile_apk(self, job_dir, job_id):
    try:
        # 1. Initialize clean buildozer configurations inside the specific job directory
        subprocess.run(['buildozer', 'init'], cwd=job_dir, check=True)
        
        # 2. Extract dependencies from the uploaded user script
        main_py_path = os.path.join(job_dir, 'main.py')
        detected_requirements = extract_dependencies(main_py_path)
        
        # 3. Dynamic replacement of requirements inside buildozer.spec
        spec_path = os.path.join(job_dir, 'buildozer.spec')
        with open(spec_path, 'r', encoding='utf-8') as file:
            spec_content = file.read()
            
        # Target the requirements line and swap it with detected dependencies + core python3
        spec_content = re.sub(
            r'^requirements\s*=\s*.*$', 
            f'requirements = python3, {detected_requirements}', 
            spec_content, 
            flags=re.MULTILINE
        )
        
        with open(spec_path, 'w', encoding='utf-8') as file:
            file.write(spec_content)
        
        # 4. Compile the target Android bundle cleanly in headless mode.
        # We pipe 'yes' to automatically accept Android NDK/SDK licenses.
        process = subprocess.Popen(
            "yes | buildozer android debug", 
            cwd=job_dir, 
            shell=True,          # Required to support the pipe '|' operator
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        # Wait for compilation to complete and capture all internal shell logs
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            # If buildozer fails, expose full stdout context to make debugging clear
            raise Exception(f"Buildozer engine compilation error.\nSTDERR: {stderr}\nSTDOUT: {stdout}")
            
        # 5. Locate the generated output binary inside the 'bin' workspace folder
        bin_dir = os.path.join(job_dir, 'bin')
        if not os.path.exists(bin_dir):
            raise Exception("Compilation executed successfully, but output 'bin' folder does not exist.")

        apks = [f for f in os.listdir(bin_dir) if f.endswith('.apk')]
        
        if not apks:
            raise Exception("Compilation finished, but APK generation vanished from output folder.")
            
        return {
            'status': 'Success',
            'job_id': job_id,
            'apk_name': apks[0]  # Return the absolute first generated apk name
        }
        
    except Exception as e:
        # Save error message to task state metadata so the Flask status route can read it
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e

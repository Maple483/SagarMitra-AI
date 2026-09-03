import subprocess
import sys
import os

def run_command(command, cwd):
    print(f"[Executing] {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)

def start_services():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "orca-backend")
    frontend_dir = os.path.join(root_dir, "orca-frontend")

    # 1. Determine platform-specific executables
    if sys.platform == "win32":
        python_executable = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
        pip_executable = os.path.join(backend_dir, "venv", "Scripts", "pip.exe")
        npm_cmd = "npm.cmd"
    else:
        python_executable = os.path.join(backend_dir, "venv", "bin", "python")
        pip_executable = os.path.join(backend_dir, "venv", "bin", "pip")
        npm_cmd = "npm"

    # Fallback if venv python isn't built yet
    if not os.path.exists(python_executable):
        python_executable = "python" if sys.platform == "win32" else "python3"
        pip_executable = "pip"

    print("=== [ORCA] Starting Automated Environment Setup ===")

    # 2. Auto-install Python dependencies from requirements.txt
    requirements_path = os.path.join(backend_dir, "requirements.txt")
    if os.path.exists(requirements_path):
        try:
            print("[ORCA] Checking and installing Python requirements...")
            run_command([pip_executable, "install", "-r", "requirements.txt"], cwd=backend_dir)
        except Exception as e:
            print(f"[Warning] Pip installation encountered an issue: {e}")

    # 3. Auto-install Node modules if missing
    node_modules_path = os.path.join(frontend_dir, "node_modules")
    if not os.path.exists(node_modules_path):
        print("[ORCA] Frontend node_modules missing. Running 'npm install'...")
        try:
            run_command([npm_cmd, "install"], cwd=frontend_dir)
        except Exception as e:
            print(f"[Error] Npm install failed: {e}")
    else:
        print("[ORCA] Frontend node_modules already installed.")

    print("\n=== [ORCA] Launching Backend & Frontend Services ===")
    try:
        # Start Backend (FastAPI)
        backend_process = subprocess.Popen(
            [python_executable, "main.py"],
            cwd=backend_dir
        )

        # Start Frontend (Vite/React dev server)
        frontend_process = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=frontend_dir
        )

        # Keep alive until user interrupts
        backend_process.wait()
        frontend_process.wait()

    except KeyboardInterrupt:
        print("\n[ORCA] Shutting down all services gracefully...")
        backend_process.terminate()
        frontend_process.terminate()

if __name__ == "__main__":
    start_services()
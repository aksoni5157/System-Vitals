"""
================================================================================
 SisVi+ Smart Launcher
================================================================================
 Automatically finds the best Python version, installs dependencies,
 and launches the app. Double-click this file or run: python launch.py
================================================================================
"""
import subprocess, sys, os, shutil

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(APP_DIR, "app.py")
REQ_FILE = os.path.join(APP_DIR, "requirements.txt")

# MediaPipe-compatible Python versions (highest preferred)
COMPATIBLE = ["3.12", "3.11", "3.10", "3.9"]

def find_python():
    """Find the best available Python for MediaPipe compatibility."""
    # Try py launcher (Windows)
    for ver in COMPATIBLE:
        try:
            r = subprocess.run(
                ["py", f"-{ver}", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                exe = r.stdout.strip()
                print(f"[OK] Found Python {ver}: {exe}")
                return exe, ver
        except Exception:
            continue

    # Try pythonX.XX directly
    for ver in COMPATIBLE:
        for name in [f"python{ver}", f"python{ver.replace('.', '')}"]:
            path = shutil.which(name)
            if path:
                print(f"[OK] Found {name}: {path}")
                return path, ver

    # Fall back to current python
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"[!!] No Python 3.9-3.12 found. Using current Python {v}")
    print(f"     Gesture HUD may not work without MediaPipe support.")
    return sys.executable, v

def install_deps(python_exe):
    """Install all dependencies."""
    print("\n[..] Installing dependencies...")
    try:
        subprocess.run(
            [python_exe, "-m", "pip", "install", "-r", REQ_FILE, "--quiet"],
            cwd=APP_DIR, check=True)
        print("[OK] All dependencies installed!")
        return True
    except subprocess.CalledProcessError:
        print("[!!] Some packages failed to install. Trying core packages...")
        # Try installing core packages one by one
        core = ["customtkinter", "psutil", "Pillow"]
        optional = ["opencv-python", "mediapipe", "openai", "numpy"]
        for pkg in core:
            subprocess.run([python_exe, "-m", "pip", "install", pkg, "--quiet"],
                          cwd=APP_DIR)
        for pkg in optional:
            try:
                subprocess.run([python_exe, "-m", "pip", "install", pkg, "--quiet"],
                              cwd=APP_DIR, timeout=120)
            except Exception:
                print(f"[!!] Optional: {pkg} failed (non-critical)")
        return True

def launch(python_exe):
    """Launch the app."""
    print(f"\n{'='*50}")
    print(f"  Launching SisVi+ ...")
    print(f"{'='*50}\n")
    os.execv(python_exe, [python_exe, APP_FILE])

if __name__ == "__main__":
    print("=" * 50)
    print("  SisVi+ Smart Launcher")
    print("  Finding best Python version...")
    print("=" * 50)

    python_exe, ver = find_python()
    install_deps(python_exe)
    launch(python_exe)

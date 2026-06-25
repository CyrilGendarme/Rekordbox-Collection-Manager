import socket
import subprocess
import os
import sys
import shutil
import time
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(
    port: int,
    timeout_seconds: float = 8.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(port):
            return True
        time.sleep(poll_interval_seconds)

    return False


def find_chrome_executable() -> str:
    """
    Find Chrome executable on Windows / macOS / Linux
    """
    if sys.platform.startswith("win"):
        candidates = [
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        raise FileNotFoundError("Chrome executable not found on Windows")

    elif sys.platform.startswith("darwin"):
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(path):
            return path
        raise FileNotFoundError("Chrome executable not found on macOS")

    else:
        candidates = [
            shutil.which("google-chrome"),
            shutil.which("chrome"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
        ]
        for path in candidates:
            if path:
                return path
        raise FileNotFoundError("Chrome executable not found on Linux")


def ensure_profile_dir(chrome_profile_dir: str) -> None:
    os.makedirs(chrome_profile_dir, exist_ok=True)


def launch_chrome_with_debugging(
    width: int,
    height: int,
    DEBUG_PORT: int,
    CHROME_PROFILE_DIR: str,
    CHROME_DEV_CONSOLE: bool,
) -> subprocess.Popen:
    ensure_profile_dir(CHROME_PROFILE_DIR)

    chrome_cmd = find_chrome_executable()

    # Build base args
    args = [
        chrome_cmd,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        f"--window-size={width},{height}",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    # Conditionally add DevTools flags
    if CHROME_DEV_CONSOLE:
        args += [
            "--auto-open-devtools-for-tabs",
        ]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return proc


def get_or_attach_driver(
    width: int,
    height: int,
    DEBUG_PORT: int,
    CHROME_PROFILE_DIR: str,
    CHROME_DEV_CONSOLE: bool,
    HEADLESS_MODE: bool = False,
    shall_include_process: bool = False,
) -> webdriver.Chrome | tuple[webdriver.Chrome, subprocess.Popen | None]:

    proc: Optional[subprocess.Popen] = None

    ensure_profile_dir(CHROME_PROFILE_DIR)

    # -----------------------------
    # HEADLESS MODE (no debug attach)
    # -----------------------------
    if HEADLESS_MODE:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--window-size={width},{height}")
        options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=options)

        if shall_include_process:
            return driver, None
        return driver

    # -----------------------------
    # NORMAL DEBUG ATTACH MODE
    # -----------------------------
    if not is_port_open(DEBUG_PORT):
        proc = launch_chrome_with_debugging(
            width, height, DEBUG_PORT, CHROME_PROFILE_DIR, CHROME_DEV_CONSOLE
        )
        if not wait_for_port(DEBUG_PORT):
            if proc and proc.poll() is None:
                proc.terminate()
            raise RuntimeError(
                f"Chrome debugging port {DEBUG_PORT} did not open in time"
            )

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")

    driver = webdriver.Chrome(options=options)

    if shall_include_process:
        return driver, proc
    return driver

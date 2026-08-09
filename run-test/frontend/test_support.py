from __future__ import annotations

import os
import logging
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "rocky-interface"
BACKEND_DIR = ROOT / "rocky-backend"
WEB_HOST = os.getenv("ROCKY_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
WEB_PORT = os.getenv("ROCKY_WEB_PORT", "4173").strip() or "4173"
BASE_URL = f"http://{WEB_HOST}:{WEB_PORT}"
NPM_BIN = "npm.cmd" if os.name == "nt" else "npm"
PYTHON_BIN = sys.executable
logger = logging.getLogger("rocky.tests.frontend")


class FrontendBrowserTestCase(unittest.TestCase):
    STARTUP_TIMEOUT_SECONDS = 90

    @classmethod
    def _log(cls, message: str):
        logger.info("[frontend-e2e] %s", message)

    @classmethod
    def _tail_log_file(cls, log_path: Path, max_lines: int = 80) -> str:
        if not log_path.exists():
            return "<no log file>"

        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            return "".join(lines[-max_lines:]).strip() or "<empty log file>"
        except Exception as exc:
            return f"<unable to read log file: {exc}>"

    @classmethod
    def setUpClass(cls):
        try:
            cls._set_up_resources()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _set_up_resources(cls):
        cls._log("Seeding and starting backend API for browser tests.")
        subprocess.run([PYTHON_BIN, "seed_from_backend.py"], cwd=BACKEND_DIR, check=True)
        cls._process_log_dir = Path(tempfile.mkdtemp(prefix="rocky-e2e-process-logs-"))
        cls._backend_log_path = cls._process_log_dir / "backend.log"
        cls._frontend_log_path = cls._process_log_dir / "frontend.log"
        cls._backend_log_handle = cls._backend_log_path.open("w", encoding="utf-8", errors="replace")
        cls._frontend_log_handle = cls._frontend_log_path.open("w", encoding="utf-8", errors="replace")

        backend_env = os.environ.copy()
        backend_env.update(
            {
                "ROCKY_APP_ENV": "testing",
                "ROCKY_DB_BACKEND": "mongita",
                "ROCKY_ENABLE_DB_INSPECTOR": "false",
            }
        )

        cls.backend = subprocess.Popen(
            [PYTHON_BIN, "main.py"],
            cwd=BACKEND_DIR,
            env=backend_env,
            stdout=cls._backend_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_backend()

        cls._log("Starting frontend dev server for browser tests.")
        env = os.environ.copy()
        env.update(
            {
                "PUBLIC_APP_ENV": "testing",
                "PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
                "PUBLIC_ENABLE_DBTEST": "false",
                "PUBLIC_ENABLE_MICROSOFT_OAUTH": "false",
                "ROCKY_WEB_HOST": WEB_HOST,
                "ROCKY_WEB_PORT": WEB_PORT,
                "ROCKY_ALLOWED_HOSTS": f"{WEB_HOST},127.0.0.1,localhost",
            }
        )

        cls.frontend = subprocess.Popen(
            [
                NPM_BIN,
                "run",
                "dev",
                "--",
                "--host",
                WEB_HOST,
                "--port",
                WEB_PORT,
                "--strictPort",
            ],
            cwd=FRONTEND_DIR,
            env=env,
            stdout=cls._frontend_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_server()
        cls._log("Frontend dev server is reachable.")

        cls._chrome_profile_dir = tempfile.mkdtemp(prefix="rocky-selenium-profile-")
        cls.driver = cls._create_browser_driver()
        cls.wait = WebDriverWait(cls.driver, 15)
        cls._log("Browser WebDriver initialized.")

    @classmethod
    def _discover_chrome_binaries(cls) -> list[str | None]:
        candidates: list[str] = []

        env_bin = os.environ.get("CHROME_BIN", "").strip()
        if env_bin:
            candidates.append(env_bin)

        for cmd in ("chrome", "chrome.exe"):
            resolved = shutil.which(cmd)
            if resolved:
                candidates.append(resolved)

        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            program_files = os.environ.get("PROGRAMFILES", "")
            program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
            candidates.extend(
                [
                    str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
                ]
            )

        seen: set[str] = set()
        unique_existing: list[str] = []
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            if Path(normalized).exists():
                unique_existing.append(normalized)

        # None tells Selenium Manager to resolve browser location itself.
        return unique_existing + [None]

    @classmethod
    def _build_chrome_options(cls, headless_mode: str, chrome_bin: str | None, use_profile_dir: bool) -> Options:
        options = Options()

        if chrome_bin:
            options.binary_location = chrome_bin

        # Use an isolated profile to avoid DevToolsActivePort and profile lock issues.
        if use_profile_dir:
            options.add_argument(f"--user-data-dir={cls._chrome_profile_dir}")
        options.add_argument("--window-size=1600,1200")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-sync")
        options.add_argument("--remote-debugging-port=0")

        if headless_mode == "new":
            options.add_argument("--headless=new")
        elif headless_mode == "legacy":
            options.add_argument("--headless")

        return options

    @classmethod
    def _create_chrome_driver(cls):
        startup_errors: list[str] = []
        binaries = cls._discover_chrome_binaries()

        # Try explicit binaries first, with/without isolated profile, then let Selenium Manager resolve.
        for chrome_bin in binaries:
            for use_profile_dir in (True, False):
                for mode in ("new", "legacy", "none"):
                    try:
                        binary_label = chrome_bin or "selenium-manager"
                        profile_label = "isolated-profile" if use_profile_dir else "default-profile"
                        cls._log(
                            f"Attempting Chrome startup: binary={binary_label}, mode={mode}, profile={profile_label}"
                        )
                        options = cls._build_chrome_options(mode, chrome_bin, use_profile_dir)
                        service = Service()
                        return webdriver.Chrome(service=service, options=options)
                    except (SessionNotCreatedException, WebDriverException) as exc:
                        startup_errors.append(
                            f"binary={chrome_bin or 'selenium-manager'}, mode={mode}, profile={use_profile_dir}: {exc}"
                        )

        message = "Unable to start Chrome WebDriver. Attempts: " + " | ".join(startup_errors)
        raise RuntimeError(message)

    @classmethod
    def _discover_edge_binaries(cls) -> list[str | None]:
        candidates: list[str] = []

        env_bin = os.environ.get("EDGE_BIN", "").strip()
        if env_bin:
            candidates.append(env_bin)

        for cmd in ("msedge", "msedge.exe"):
            resolved = shutil.which(cmd)
            if resolved:
                candidates.append(resolved)

        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            program_files = os.environ.get("PROGRAMFILES", "")
            program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
            candidates.extend(
                [
                    str(Path(local_app_data) / "Microsoft/Edge/Application/msedge.exe"),
                    str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe"),
                    str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"),
                ]
            )

        seen: set[str] = set()
        unique_existing: list[str] = []
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            if Path(normalized).exists():
                unique_existing.append(normalized)

        return unique_existing + [None]

    @classmethod
    def _build_edge_options(cls, headless_mode: str, edge_bin: str | None, use_profile_dir: bool) -> EdgeOptions:
        options = EdgeOptions()
        options.use_chromium = True

        if edge_bin:
            options.binary_location = edge_bin

        if use_profile_dir:
            options.add_argument(f"--user-data-dir={cls._chrome_profile_dir}")
        options.add_argument("--window-size=1600,1200")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-sync")
        options.add_argument("--remote-debugging-port=0")

        if headless_mode == "new":
            options.add_argument("--headless=new")
        elif headless_mode == "legacy":
            options.add_argument("--headless")

        return options

    @classmethod
    def _create_edge_driver(cls):
        startup_errors: list[str] = []
        binaries = cls._discover_edge_binaries()

        for edge_bin in binaries:
            for use_profile_dir in (True, False):
                for mode in ("new", "legacy", "none"):
                    try:
                        binary_label = edge_bin or "selenium-manager"
                        profile_label = "isolated-profile" if use_profile_dir else "default-profile"
                        cls._log(
                            f"Attempting Edge startup: binary={binary_label}, mode={mode}, profile={profile_label}"
                        )
                        options = cls._build_edge_options(mode, edge_bin, use_profile_dir)
                        service = EdgeService()
                        return webdriver.Edge(service=service, options=options)
                    except (SessionNotCreatedException, WebDriverException) as exc:
                        startup_errors.append(
                            f"binary={edge_bin or 'selenium-manager'}, mode={mode}, profile={use_profile_dir}: {exc}"
                        )

        message = "Unable to start Edge WebDriver. Attempts: " + " | ".join(startup_errors)
        raise RuntimeError(message)

    @classmethod
    def _create_browser_driver(cls):
        errors: list[str] = []

        try:
            cls._log("Trying Chrome first for frontend e2e.")
            return cls._create_chrome_driver()
        except RuntimeError as exc:
            errors.append(str(exc))

        try:
            cls._log("Chrome unavailable; trying Edge fallback for frontend e2e.")
            return cls._create_edge_driver()
        except RuntimeError as exc:
            errors.append(str(exc))

        raise unittest.SkipTest("Unable to start any browser WebDriver. Attempts: " + " || ".join(errors))

    @classmethod
    def tearDownClass(cls):
        cls._log("Cleaning up browser and dev server.")
        if hasattr(cls, "driver"):
            cls.driver.quit()
        if hasattr(cls, "frontend") and cls.frontend.poll() is None:
            cls.frontend.terminate()
            try:
                cls.frontend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.frontend.kill()

        if hasattr(cls, "backend") and cls.backend.poll() is None:
            cls.backend.terminate()
            try:
                cls.backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.backend.kill()

        if hasattr(cls, "_chrome_profile_dir"):
            try:
                profile_path = Path(cls._chrome_profile_dir)
                if profile_path.exists():
                    for child in sorted(profile_path.rglob("*"), reverse=True):
                        if child.is_file() or child.is_symlink():
                            child.unlink(missing_ok=True)
                        elif child.is_dir():
                            child.rmdir()
                    profile_path.rmdir()
            except Exception:
                pass

        for handle_name in ("_frontend_log_handle", "_backend_log_handle"):
            if hasattr(cls, handle_name):
                try:
                    getattr(cls, handle_name).close()
                except Exception:
                    pass

    @classmethod
    def _wait_for_backend(cls):
        deadline = time.time() + cls.STARTUP_TIMEOUT_SECONDS
        while time.time() < deadline:
            if cls.backend.poll() is not None:
                tail = cls._tail_log_file(getattr(cls, "_backend_log_path", Path("backend.log")))
                raise RuntimeError(f"Backend server exited before tests started.\n--- backend.log tail ---\n{tail}")
            try:
                with urlopen("http://127.0.0.1:5001/health", timeout=2):
                    return
            except (URLError, TimeoutError):
                time.sleep(1)
        tail = cls._tail_log_file(getattr(cls, "_backend_log_path", Path("backend.log")))
        raise TimeoutError(f"Timed out waiting for backend server.\n--- backend.log tail ---\n{tail}")

    @classmethod
    def _wait_for_server(cls):
        deadline = time.time() + cls.STARTUP_TIMEOUT_SECONDS
        cls._log("Waiting for frontend server readiness.")
        while time.time() < deadline:
            if cls.frontend.poll() is not None:
                tail = cls._tail_log_file(getattr(cls, "_frontend_log_path", Path("frontend.log")))
                raise RuntimeError(f"Frontend dev server exited before tests started.\n--- frontend.log tail ---\n{tail}")
            try:
                # The first request compiles the Svelte route. Give that work
                # enough time to finish instead of repeatedly cancelling it.
                remaining_seconds = max(1, deadline - time.time())
                with urlopen(
                    f"{BASE_URL}/login/preview",
                    timeout=remaining_seconds,
                ):
                    return
            except (URLError, TimeoutError):
                time.sleep(1)
        tail = cls._tail_log_file(getattr(cls, "_frontend_log_path", Path("frontend.log")))
        raise TimeoutError(f"Timed out waiting for frontend dev server.\n--- frontend.log tail ---\n{tail}")

    def _assert_title(self, expected: str):
        def heading_matches(driver):
            try:
                return driver.find_element(By.CSS_SELECTOR, ".view-title h1").text.strip() == expected
            except (NoSuchElementException, StaleElementReferenceException):
                return False

        self.wait.until(heading_matches, message=f"Expected view title: {expected}")

    def _wait_for_post_login_navigation(self):
        try:
            self.wait.until(EC.url_contains("/"))
            self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".view-title h1")))
        except TimeoutException as exc:
            self._log(f"Login navigation timeout. Current URL: {self.driver.current_url}")
            raise exc

    def _click_element(self, by: By, value: str, retries: int = 3):
        for attempt in range(retries):
            try:
                element = self.wait.until(
                    EC.element_to_be_clickable((by, value)),
                    message=f"Expected clickable element: {by}={value}",
                )
                element.click()
                return
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    raise

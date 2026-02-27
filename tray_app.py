import pystray
from PIL import Image
import threading
import subprocess
import sys
import os
import shutil
from pathlib import Path
import webbrowser
import logging
import json
import tkinter as tk
from tkinter import messagebox, filedialog
import winreg
import platform
import atexit
import time
import requests
from tkinter import ttk

"""DocuGogglesTrayApp: system-tray controller with Meilisearch and background scanning."""


APP_DIR: Path = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

def get_appdata_path(app_name: str) -> Path:
    """Ensure and return the per-app data folder."""
    if platform.system() == "Windows":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / app_name
    else:
        base = Path.home() / f".{app_name.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base

LOG_DIR: Path = get_appdata_path("DocuGogglesTray")
CONFIG_DIR: Path = get_appdata_path("DocuGoggles")
LOG_FILE_PATH: Path = LOG_DIR / "scanner.log"
CONFIG_PATH: Path = CONFIG_DIR / "config.json"
ICON_PATH: Path = APP_DIR / "icon.ico"
DEFAULT_MEILI_URL = "http://127.0.0.1:7700"
APP_NAME = "DocuGogglesTrayApp"

# Logging setup
_orig_fh = logging.FileHandler

def _patched_filehandler(filename, *args, **kwargs):
    if filename == "scanner.log":
        filename = str(LOG_FILE_PATH)
    return _orig_fh(filename, *args, **kwargs)

logging.FileHandler = _patched_filehandler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.info("AppDir=%s, Config=%s, Log=%s", APP_DIR, CONFIG_PATH, LOG_FILE_PATH)
print("--- tray_app.py script started ---")


def setup_tk_root():
    try:
        root = tk.Tk()
        root.withdraw()
        root.update()
        return root
    except Exception as e:
        logging.warning("Tk root failed: %s", e)
        return None

HIDDEN_TK_ROOT = setup_tk_root()


try:
    from file_search.background_scanner import (
        load_config,
        start_scheduler,
        stop_scheduler,
        run_scan_now_threaded,
        scheduler_thread,
    )
except ImportError as exc:
    logging.exception("ImportError: %s", exc)
    messagebox.showerror("Import Error", str(exc))
    sys.exit(1)


def _startup_key():
    return r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"

def _self_cmd() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'

def add_to_startup() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _startup_key(), 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _self_cmd())
        return True
    except Exception:
        logging.exception("add_to_startup failed")
        return False

def remove_from_startup() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _startup_key(), 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        logging.exception("remove_from_startup failed")
        return False

def is_in_startup() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _startup_key(), 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        logging.exception("is_in_startup failed")
        return False


meili_proc: subprocess.Popen | None = None

def launch_meilisearch():
    global meili_proc
    appdata = get_appdata_path("DocuGoggles")
    exe = appdata / "meilisearch.exe"
    db_dir = appdata / "meili_data"; db_dir.mkdir(exist_ok=True)

    if not exe.exists():
        src = APP_DIR / "meilisearch.exe"
        if not src.exists():
            messagebox.showerror("Startup Error", f"meilisearch.exe not found: {src}")
            return
        shutil.copy2(src, exe)
        logging.info("Copied Meilisearch to %s", exe)

    logf = (LOG_DIR / "meilisearch_stdout.log").open("w", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = subprocess.SW_HIDE

    meili_proc = subprocess.Popen([str(exe), "--db-path", str(db_dir)],
                                  stdout=logf, stderr=subprocess.STDOUT,
                                  cwd=str(appdata), creationflags=flags,
                                  startupinfo=si)
    logging.info("Meilisearch PID %s", meili_proc.pid)

    # health-check
    for _ in range(10):
        if meili_proc.poll() is not None:
            messagebox.showerror("Meilisearch Error", "Process exited--see log")
            return
        try:
            if requests.get(f"{DEFAULT_MEILI_URL}/health", timeout=1).ok:
                logging.info("Meilisearch healthy")
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    messagebox.showerror("Meilisearch Error", "Health check timeout")


def cleanup_meilisearch():
    global meili_proc
    if meili_proc and meili_proc.poll() is None:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(meili_proc.pid)], check=False)
            logging.info("Meilisearch terminated")
        except Exception:
            logging.exception("cleanup_meilisearch failed")

atexit.register(cleanup_meilisearch)


def launch_search_ui():
    exe = APP_DIR / "DocuGogglesSearchUI" / "DocuGogglesSearchUI.exe"
    if exe.exists():
        subprocess.Popen([str(exe)], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        messagebox.showerror("Search UI", f"Executable not found: {exe}")


def open_config_window():
    print("--- open_config_window() called ---")
    logging.info("Opening configuration window...")
    global config 

    # Ensure config directory exists (should have been done at startup)
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        print(f"--- Config directory checked/created: {CONFIG_DIR} ---")
    except Exception as e:
        logging.exception("Error ensuring config directory exists in open_config_window")
        messagebox.showerror("Config Error", f"Could not access configuration directory:\n{e}")
        return

    # Load current config from the global variable 'config' first
    # If the global config is somehow None, try loading from file as fallback
    current_cfg = config 
    if current_cfg is None:
        print("--- Global config is None, attempting to load from file... ---")
        logging.warning("Global config object was None when opening config window. Reloading.")
        if not CONFIG_PATH.exists():
             print(f"--- Config file {CONFIG_PATH} doesn't exist. Creating default skeleton. ---")
             logging.warning(f"Config file {CONFIG_PATH} not found. Using empty dict.")
             # Create a minimal default if file doesn't exist, rather than calling load_config()
             current_cfg = {
                 "scan_path": "", 
                 "recursive_scan": True,
                 "process_pdfs": True,
                 "cache_path": "cache",
                 "meilisearch": {"url": DEFAULT_MEILI_URL, "api_key": None},
                 "schedule": {"type": "daily", "time": "02:00"}
             }
             try:
                 CONFIG_PATH.write_text(json.dumps(current_cfg, indent=2), encoding="utf-8")
                 print("--- Default config skeleton written. ---")
             except Exception as e:
                 logging.exception("Failed to write default config skeleton.")
                 messagebox.showerror("Config Error", f"Failed to create default configuration file:\n{e}")
                 # Proceed with empty config if write fails
                 current_cfg = {}
        else:
            try:
                print(f"--- Reading config from {CONFIG_PATH} ---")
                current_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                print("--- Config loaded from file successfully. ---")
            except Exception as e:
                logging.exception("Failed to load/parse config file in open_config_window")
                messagebox.showerror("Config Error", f"Could not read configuration file:\n{e}")
                current_cfg = {} # Use empty config as fallback
    else:
        print("--- Using existing global config object. ---")

    # Ensure current_cfg is a dictionary before proceeding
    if not isinstance(current_cfg, dict):
         logging.error(f"Loaded configuration is not a dictionary: {type(current_cfg)}")
         messagebox.showerror("Config Error", "Configuration data is invalid.")
         current_cfg = {} # Reset to empty dict
         
    print("--- Creating Toplevel window... ---")
    try:
        win = tk.Toplevel(master=HIDDEN_TK_ROOT)
        win.title("DocuGoggles Configuration")
        win.grab_set()
        win.resizable(True, True)
        print("--- Toplevel window created. --- ")
    except Exception as e:
        logging.exception("Failed to create Toplevel window")
        messagebox.showerror("UI Error", f"Failed to create configuration window:\n{e}")
        return

    main_frame = ttk.Frame(win, padding="10 10 10 10") 
    main_frame.pack(fill=tk.BOTH, expand=True)
    main_frame.columnconfigure(1, weight=1)

    # --- UI Variables --- 
    scan_path_var = tk.StringVar(value=current_cfg.get("scan_path", ""))
    recursive_scan_var = tk.BooleanVar(value=current_cfg.get("recursive_scan", True))
    process_pdfs_var = tk.BooleanVar(value=current_cfg.get("process_pdfs", True))
    cache_path_var = tk.StringVar(value=current_cfg.get("cache_path", "cache"))
    meili_url_var = tk.StringVar(value=current_cfg.get("meilisearch", {}).get("url", DEFAULT_MEILI_URL))
    meili_api_key_var = tk.StringVar(value=current_cfg.get("meilisearch", {}).get("api_key") or "") # Handle None
    schedule_type_var = tk.StringVar(value=current_cfg.get("schedule", {}).get("type", "daily"))
    schedule_time_var = tk.StringVar(value=current_cfg.get("schedule", {}).get("time", "02:00"))
    # TODO: Add vars for interval/weekday if adding those widgets

    print("--- Setting up widgets... ---")
    row_num = 0
    try:
        # --- General Settings --- Use ttk widgets --- 
        general_frame = ttk.LabelFrame(main_frame, text="General Settings", padding="5 5 5 5")
        general_frame.grid(row=row_num, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        general_frame.columnconfigure(1, weight=1)
        row_num += 1
        sub_row = 0
        
        ttk.Label(general_frame, text="Scan Path:").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        ttk.Entry(general_frame, textvariable=scan_path_var, width=50).grid(row=sub_row, column=1, sticky="ew", padx=5, pady=2)
        def browse_path():
             dir = filedialog.askdirectory()
             if dir: scan_path_var.set(dir)
        ttk.Button(general_frame, text="Browse...", command=browse_path).grid(row=sub_row, column=2, sticky="w", padx=5)
        sub_row += 1
        
        ttk.Checkbutton(general_frame, text="Scan Recursively", variable=recursive_scan_var).grid(row=sub_row, column=1, columnspan=2, sticky="w", padx=5)
        sub_row += 1
        ttk.Checkbutton(general_frame, text="Process PDFs (OCR)", variable=process_pdfs_var).grid(row=sub_row, column=1, columnspan=2, sticky="w", padx=5)
        sub_row += 1
        
        ttk.Label(general_frame, text="Cache Path (rel. to AppData):").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        ttk.Entry(general_frame, textvariable=cache_path_var, width=50).grid(row=sub_row, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        sub_row += 1

        # --- Meilisearch Settings --- Use ttk widgets --- 
        meili_frame = ttk.LabelFrame(main_frame, text="Meilisearch Settings", padding="5 5 5 5")
        meili_frame.grid(row=row_num, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        meili_frame.columnconfigure(1, weight=1)
        row_num += 1
        sub_row = 0
        
        ttk.Label(meili_frame, text="Server URL:").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        ttk.Entry(meili_frame, textvariable=meili_url_var, width=50).grid(row=sub_row, column=1, sticky="ew", padx=5, pady=2)
        sub_row += 1
        ttk.Label(meili_frame, text="API Key (Optional):").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        ttk.Entry(meili_frame, textvariable=meili_api_key_var, width=50).grid(row=sub_row, column=1, sticky="ew", padx=5, pady=2)
        sub_row += 1
        
        # --- Schedule Settings --- Use ttk widgets --- 
        schedule_frame = ttk.LabelFrame(main_frame, text="Schedule Settings", padding="5 5 5 5")
        schedule_frame.grid(row=row_num, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        schedule_frame.columnconfigure(1, weight=1)
        row_num += 1
        sub_row = 0
        
        ttk.Label(schedule_frame, text="Type:").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        schedule_types = ["daily", "hourly", "weekly", "interval", "manual"] # Add 'manual' or 'disabled'?
        schedule_combo = ttk.Combobox(schedule_frame, textvariable=schedule_type_var, values=schedule_types, state="readonly", width=18)
        schedule_combo.grid(row=sub_row, column=1, sticky="w", padx=5, pady=2)
        sub_row += 1
        
        ttk.Label(schedule_frame, text="Time (HH:MM):").grid(row=sub_row, column=0, sticky="w", pady=2, padx=2)
        ttk.Entry(schedule_frame, textvariable=schedule_time_var, width=10).grid(row=sub_row, column=1, sticky="w", padx=5, pady=2)
        # TODO: Enable/disable time based on type? Add interval/weekday fields?
        sub_row += 1

        print("    Widgets created.")

        # --- Save/Cancel Buttons --- Use ttk widgets --- 
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row_num, column=0, columnspan=3, sticky="e", pady=10)
        row_num += 1
        
        def _save():
            print("--- _save() called --- ")
            global config 
            new_cfg_data = { 
                 **current_cfg, 
                 "scan_path": scan_path_var.get(),
                 "recursive_scan": recursive_scan_var.get(),
                 "process_pdfs": process_pdfs_var.get(),
                 "cache_path": cache_path_var.get(),
                 "meilisearch": {
                     **(current_cfg.get("meilisearch", {}) if isinstance(current_cfg.get("meilisearch", {}), dict) else {}),
                     "url": meili_url_var.get(),
                     "api_key": meili_api_key_var.get() or None 
                 },
                 "schedule": {
                     **(current_cfg.get("schedule", {}) if isinstance(current_cfg.get("schedule", {}), dict) else {}),
                     "type": schedule_type_var.get(),
                     "time": schedule_time_var.get()
                 }
             }
             
            try:
                CONFIG_PATH.write_text(json.dumps(new_cfg_data, indent=2), encoding="utf-8")
                config = new_cfg_data # Update global config only on successful save
                logging.info("Configuration saved to %s", CONFIG_PATH)
                print("--- Configuration saved successfully. ---")
                messagebox.showinfo("Saved", "Configuration saved. Restart scanner to apply changes.", parent=win)
                win.destroy()
            except Exception as e:
                 logging.exception("Failed to save configuration.")
                 messagebox.showerror("Save Error", f"Could not write configuration file:\n{e}", parent=win)

        ttk.Button(button_frame, text="Save", command=_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=win.destroy).pack(side=tk.RIGHT)
        print("    Save/Cancel buttons created.")
        print("--- Widget setup complete. --- ")

    except Exception as e:
        # This block handles errors during widget *creation*
        logging.exception("Error creating configuration widgets")
        messagebox.showerror("UI Error", f"Error building configuration screen:\n{e}")
        try: 
            win.destroy() # Attempt to close window if widgets failed
        except Exception: 
            pass
        return

    # This code runs only if widget creation succeeded
    # Center window (optional, might interfere with resizing)
    # win.update_idletasks()
    # x = (win.winfo_screenwidth() // 2) - (win.winfo_width() // 2)
    # y = (win.winfo_screenheight() // 2) - (win.winfo_height() // 2)
    # win.geometry(f'+{x}+{y}')

    print("--- Starting window mainloop... ---")
    win.mainloop()
    print("--- Window mainloop finished. ---")

def get_status() -> str:
    return "Running" if scheduler_thread and scheduler_thread.is_alive() else "Stopped"


def update_menu():
    global icon
    if not icon:
        return
    running = scheduler_thread and scheduler_thread.is_alive()
    startup = is_in_startup()
    icon.menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Status: {get_status()}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start Scanner", lambda i, it: start_scheduler(config), enabled=not running),
        pystray.MenuItem("Stop Scanner", lambda i, it: stop_scheduler(), enabled=running),
        pystray.MenuItem("Scan Now", lambda i, it: run_scan_now_threaded(config)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Search UI", lambda i, it: threading.Thread(target=launch_search_ui, daemon=True).start()),
        pystray.MenuItem("Open Meili Dashboard", lambda i, it: webbrowser.open(config.get("meilisearch", {}).get("url", DEFAULT_MEILI_URL))),
        pystray.MenuItem("Configure…", lambda i, it: open_config_window()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Run on Startup", lambda i, it: (remove_from_startup() if startup else add_to_startup()), checked=lambda item: is_in_startup()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", lambda i, it: icon.stop()),
    )

def setup_tray_app():
    global config, icon
    logging.info("Starting DocuGoggles Tray…")
    config = load_config()
    launch_meilisearch()
    start_scheduler(config)
    try:
        img = Image.open(ICON_PATH)
    except Exception as e:
        logging.exception("Icon load failed: %s", e)
        messagebox.showerror("Icon Error", str(e))
        sys.exit(1)
    icon = pystray.Icon("DocuGoggles", img, "DocuGoggles")
    update_menu()
    icon.run()

if __name__ == "__main__":
    try:
        setup_tray_app()
    except Exception:
        logging.exception("Unhandled exception in main")
        try:
            messagebox.showerror("Fatal Error", "An unexpected error occurred. See logs.")
        except:
            pass
    finally:
        logging.info("DocuGoggles Tray exiting…")

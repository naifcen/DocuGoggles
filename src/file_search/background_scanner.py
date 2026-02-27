import schedule
import time
import threading
import json
import os
from datetime import datetime
from pathlib import Path
import sys
import logging
from typing import List, Dict
import subprocess

# --- Globals for Control ---
scheduler_thread = None
stop_event = threading.Event()

# --- Setup Logging ---
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format,
                    handlers=[
                        logging.FileHandler("scanner.log"),
                        logging.StreamHandler()
                    ])

# --- Path Setup ---
PROJECT_ROOT = Path.cwd()
SRC_DIR = PROJECT_ROOT / 'src'
if str(SRC_DIR) not in sys.path:
   sys.path.insert(0, str(SRC_DIR))

# --- Imports ---
try:
    from file_search.file_scanner.scanner import FileScanner
    from file_search.text_extractor.text_extractor import TextExtractor
    from file_search.cache.content_cache import ContentCache
    from file_search.search.meili_search_client import MeiliSearchClient
except ImportError as e:
    logging.error(f"Failed to import project modules: {e}")
    logging.error(f"Ensure required modules exist and dependencies are installed.")
    sys.exit(1)

# --- Configuration Loading ---
CONFIG_FILE = PROJECT_ROOT / 'config.json'
def load_config():
    """Loads and validates configuration from config.json."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        if "scan_path" not in config or config["scan_path"] == "EDIT_THIS_PATH":
            raise ValueError("scan_path is not set or is invalid in config.json")
        if "schedule" not in config or "type" not in config["schedule"]:
            raise ValueError("Schedule configuration is missing or invalid in config.json")
        if "meilisearch" not in config or "url" not in config["meilisearch"]:
            raise ValueError("Meilisearch configuration is missing or invalid in config.json")
        config['cache_path'] = config.get('cache_path', 'cache')
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {CONFIG_FILE}")
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {CONFIG_FILE}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Configuration Error: {e}")
        sys.exit(1)

# --- Core Scan and Index Job ---
def scan_and_index_job(config):
    """Performs the scanning, extraction, and indexing process."""
    logging.info("Starting background scan and index job...")
    try:
        scan_path = config['scan_path']
        recursive = config.get('recursive_scan', True)
        process_pdfs = config.get('process_pdfs', False)
        cache_path = config['cache_path']
        meili_config = config['meilisearch']

        scanner = FileScanner()
        extractor = TextExtractor()
        content_cache = ContentCache(cache_dir=cache_path)
        meili_client = MeiliSearchClient(host=meili_config['url'], api_key=meili_config.get('api_key'))

        # Set filterable attributes
        try:
            logging.info("Setting filterable attributes in Meilisearch: ['extension', 'size']")
            task_info = meili_client.index.update_filterable_attributes(["extension", "size"])
            logging.info("Filterable attributes update task submitted to Meilisearch.")
        except Exception:
            logging.exception("Failed to update filterable attributes in Meilisearch.")

        supported_extensions = list(extractor.supported_extensions.keys())
        if not process_pdfs and '.pdf' in supported_extensions:
            supported_extensions.remove('.pdf')
            logging.info("Skipping PDF files as per configuration.")

        logging.info(f"Scanning directory: {scan_path} (Recursive: {recursive})")
        scanner.scan_directory(scan_path, recursive=recursive)
        files_by_ext = scanner.group_files_by_extension(supported_extensions)

        if not files_by_ext:
            logging.info("No supported files found to process.")
            return

        logging.info(f"Found {sum(len(v) for v in files_by_ext.values())} supported files.")

        extracted_contents = extract_and_store_content(files_by_ext, extractor, content_cache)

        # Export and index in Meilisearch
        if extracted_contents:
            exported_documents = content_cache.export_for_meilisearch()
            if exported_documents:
                logging.info(f"Indexing {len(exported_documents)} documents in Meilisearch...")
                meili_client.index_documents(exported_documents)
                logging.info("Meilisearch indexing completed.")
            else:
                logging.info("No new or updated documents to index in Meilisearch.")
        else:
            logging.info("No content extracted, skipping Meilisearch indexing.")

        logging.info("Background scan and index job finished.")

    except FileNotFoundError as e:
        logging.error(f"Scan path error: {e}")
    except Exception:
        logging.exception("An unexpected error occurred during the scan and index job.")

# --- Helper function for content extraction with cache ---
def extract_and_store_content(files: Dict[str, List[Dict]], extractor: TextExtractor, content_cache: ContentCache) -> Dict[str, Dict]:
    """Extract content from supported files, using cache when available."""
    extracted_contents = {}
    files_to_process = []
    cached_files_loaded = 0

    for ext, files_list in files.items():
        if extractor.is_supported_extension(ext):
            for file_info in files_list:
                file_path_str = file_info['path']
                if content_cache.is_file_cached(file_path_str):
                    try:
                        index_entry = content_cache.cache_index.get("files", {}).get(file_path_str)
                        if index_entry and index_entry.get("doc_id"):
                            doc_id = index_entry["doc_id"]
                            doc_path = content_cache._get_document_path(doc_id)
                            if doc_path.exists():
                                with open(doc_path, 'r', encoding='utf-8') as f:
                                    doc_data = json.load(f)
                                extracted_contents[file_path_str] = {
                                    'content': doc_data.get('content', ''),
                                    'metadata': doc_data.get('metadata', {})
                                }
                                cached_files_loaded += 1
                            else:
                                logging.warning(f"Cache index points to non-existent doc file: {doc_path} for {file_path_str}")
                                files_to_process.append((file_info, ext))
                        else:
                            logging.warning(f"Cache index entry missing or invalid for {file_path_str}")
                            files_to_process.append((file_info, ext))
                    except Exception:
                        logging.exception(f"Error loading cached document for {file_path_str}")
                        files_to_process.append((file_info, ext))
                else:
                    files_to_process.append((file_info, ext))

    if cached_files_loaded > 0:
        logging.info(f"Loaded {cached_files_loaded} files from cache.")

    if files_to_process:
        logging.info(f"Extracting content from {len(files_to_process)} files...")
        processed_count = 0
        for file_info, ext in files_to_process:
            try:
                result = extractor.read_file(file_info['path'])
                content_data = {
                    'content': result['content'],
                    'metadata': result['metadata']
                }
                extracted_contents[file_info['path']] = content_data
                content_cache.save_document(file_info['path'], content_data)
                processed_count += 1
            except Exception as e:
                logging.error(f"Error processing {file_info['name']}: {str(e)}")
        logging.info(f"Finished extracting content from {processed_count} files.")

    content_cache._save_index()
    return extracted_contents

# --- Safe Wrapper for Scheduled Job ---
def safe_scan_job(config):
    """Wrapper function to run scan_and_index_job and catch exceptions."""
    try:
        scan_and_index_job(config)
    except Exception:
        logging.exception("Error occurred during scheduled scan_and_index_job execution.")

# --- Threading Helper for Manual Scan ---
def run_scan_now_threaded(config):
    """Runs a single scan job in a separate thread."""
    logging.info("Manual scan triggered.")
    job_thread = threading.Thread(target=scan_and_index_job, args=(config,))
    job_thread.start()

# --- Scheduler Loop Function ---
def scheduler_loop():
    """Runs the schedule checking loop."""
    logging.info("Scheduler loop started.")
    while not stop_event.is_set():
        schedule.run_pending()
        stop_event.wait(timeout=5)
    logging.info("Scheduler loop stopped.")

# --- Functions to Control the Scheduler ---
def start_scheduler(config):
    """Sets up the schedule and starts the scheduler loop in a thread."""
    global scheduler_thread, stop_event
    if scheduler_thread and scheduler_thread.is_alive():
        logging.warning("Scheduler is already running.")
        return

    logging.info("Setting up schedule...")
    schedule.clear()
    stop_event.clear()

    schedule_config = config['schedule']
    schedule_type = schedule_config['type'].lower()
    job_to_schedule = lambda: safe_scan_job(config)

    try:
        if schedule_type == "interval":
            minutes = schedule_config.get("minutes")
            hours = schedule_config.get("hours")
            if minutes:
                schedule.every(minutes).minutes.do(job_to_schedule)
                logging.info(f"Scheduled to run every {minutes} minutes.")
            elif hours:
                schedule.every(hours).hours.do(job_to_schedule)
                logging.info(f"Scheduled to run every {hours} hours.")
            else:
                raise ValueError("Interval schedule requires 'minutes' or 'hours' field.")
        elif schedule_type == "daily":
            run_time = schedule_config.get("time", "02:00")
            schedule.every().day.at(run_time).do(job_to_schedule)
            logging.info(f"Scheduled to run daily at {run_time}.")
        elif schedule_type == "weekly":
            run_time = schedule_config.get("time", "02:00")
            weekday = schedule_config.get("weekday", "sunday").lower()
            day_map = {
                "monday": schedule.every().monday,
                "tuesday": schedule.every().tuesday,
                "wednesday": schedule.every().wednesday,
                "thursday": schedule.every().thursday,
                "friday": schedule.every().friday,
                "saturday": schedule.every().saturday,
                "sunday": schedule.every().sunday
            }
            if weekday not in day_map:
                raise ValueError(f"Invalid weekday '{weekday}'. Choose from {list(day_map.keys())}.")
            day_map[weekday].at(run_time).do(job_to_schedule)
            logging.info(f"Scheduled to run weekly on {weekday.capitalize()} at {run_time}.")
        elif schedule_type == "hourly":
            schedule.every().hour.do(job_to_schedule)
            logging.info(f"Scheduled to run every hour.")
        else:
            raise ValueError(f"Unsupported schedule type: '{schedule_type}'")

        scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        scheduler_thread.start()
        logging.info("Scheduler thread started.")

    except ValueError as e:
        logging.error(f"Scheduling Error: {e}")
    except KeyError as e:
        logging.error(f"Scheduling Error: Missing required field '{e}' for schedule type '{schedule_type}'")
    except Exception:
        logging.exception("An unexpected error occurred during schedule setup.")

def stop_scheduler():
    """Signals the scheduler loop to stop."""
    global scheduler_thread
    if not scheduler_thread or not scheduler_thread.is_alive():
        logging.warning("Scheduler is not running.")
        return

    logging.info("Stopping scheduler loop...")
    stop_event.set()
    scheduler_thread.join(timeout=10)
    if scheduler_thread.is_alive():
        logging.warning("Scheduler thread did not stop gracefully.")
    else:
        logging.info("Scheduler thread stopped.")
    scheduler_thread = None
    schedule.clear()

# --- Action to Clear Cache ---
def clear_cache_action():
    """Clears the content cache AND the Meilisearch index."""
    success = True
    logging.info("Attempting to clear caches (local JSON and Meilisearch index)...")
    config = None
    try:
        config = load_config()
        cache_path = config.get('cache_path', 'cache')
        content_cache = ContentCache(cache_dir=cache_path)
        content_cache.clear_cache()
        logging.info(f"Local content cache cleared successfully from: {content_cache.cache_dir}")
    except Exception:
        logging.exception("Failed to clear local content cache.")
        success = False

    if config:
        try:
            meili_config = config['meilisearch']
            index_name_to_delete = "documents"
            logging.info(f"Attempting to delete Meilisearch index: '{index_name_to_delete}'...")
            meili_client = MeiliSearchClient(host=meili_config['url'], api_key=meili_config.get('api_key'))
            task_info = meili_client.client.delete_index(index_name_to_delete)
            logging.info(f"Meilisearch index deletion task submitted (UID: {task_info.task_uid}). Allow time for completion.")
        except ImportError:
             logging.error("Meilisearch client library not found. Cannot clear index.")
             success = False
        except Exception:
            logging.exception(f"Failed to delete Meilisearch index '{index_name_to_delete}'.")
            success = False
    else:
        logging.error("Config not loaded, cannot clear Meilisearch index.")
        success = False

    return success

# --- Helper to launch Meilisearch ---
def launch_meilisearch_if_needed(project_root: Path):
    """Checks for and launches the Meilisearch executable if found."""
    meili_exe_name = "meilisearch.exe"
    meili_exe_path = project_root / meili_exe_name
    if meili_exe_path.exists():
        try:
            already_running = False
            if sys.platform == "win32":
                tasklist_output = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {meili_exe_name}'], text=True)
                if meili_exe_name in tasklist_output:
                    already_running = True

            if not already_running:
                logging.info(f"Launching {meili_exe_name} silently in the background...")
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([str(meili_exe_path)], cwd=project_root, creationflags=creation_flags)
                logging.info(f"{meili_exe_name} launched. Allowing time for startup...")
                time.sleep(5)
            else:
                logging.info(f"{meili_exe_name} appears to be already running. Skipping launch.")

        except FileNotFoundError:
             logging.warning(f"Could not check if {meili_exe_name} is running (tasklist?). Attempting launch anyway...")
             try:
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([str(meili_exe_path)], cwd=project_root, creationflags=creation_flags)
                logging.info(f"{meili_exe_name} launched. Allowing time for startup...")
                time.sleep(5)
             except Exception as e_launch:
                 logging.exception(f"Failed to launch {meili_exe_name} after check failed.")
        except Exception:
            logging.exception(f"Failed to launch {meili_exe_name}.")
    else:
        logging.warning(f"Meilisearch executable not found: {meili_exe_path}")
        logging.warning("Please ensure Meilisearch server is running manually or place executable in project root.")

# --- Helper to run Streamlit ---
def run_streamlit_background(script_path: Path, cwd: Path):
    """Runs the Streamlit UI script using the current Python interpreter."""
    try:
        logging.info(f"Attempting to launch Streamlit UI ({script_path.name})...")
        command = [sys.executable, "-m", "streamlit", "run", str(script_path)]
        process = subprocess.Popen(command, cwd=cwd)
        logging.info(f"Streamlit UI process launched (PID: {process.pid}). Check console/browser.")
    except FileNotFoundError:
        logging.error(f"Error: Could not execute '{sys.executable}'. Python interpreter issue?")
    except Exception:
        logging.exception("An unexpected error occurred while launching Streamlit UI.") 
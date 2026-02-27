# 🥽 DocuGoggles – File Content Search and Management System

DocuGoggles scans specified directories for documents (including images with text), indexes their content using Meilisearch, and provides a Streamlit‑based web UI for searching. It runs as a background process managed by a system‑tray application.

## Features

- **Background Scanning:** Automatically scans configured directories for new or modified files on a schedule (daily, weekly, etc.) or via manual trigger.
- **OCR for Images:** Extracts text from image files (PNG, JPEG, etc.) using Tesseract OCR.
- **PDF SCANNING:** Extracts text from PDF files (optional, can be enabled in configuration).
- **Fast Search:** Uses Meilisearch for efficient indexing and full‑text search of content.
- **Web Search UI:** Provides a Streamlit web interface for intuitive document and image search.
- **System Tray Control:** Manage the scanner (Start, Stop, Scan Now), open the search UI, configure settings, view logs, and toggle startup behavior directly from the system tray.
- **Configuration:** Easy setup via `config.json` or the GUI settings window accessible from the tray icon.

## Dependencies

- **Python 3.8+**
- **Git**
- **Tesseract OCR Engine:** Required **only** if you need to process image files for OCR.
- **Meilisearch:** The search engine; the tray app will attempt to launch a local instance if none is detected.

## Quick Start (Executable Release)

For users who want to try the application without a Python setup:

1.  Visit the [**Releases**](https://github.com/Duquesne-Spring-2025-COSC-481/Naif-ALqurashi/releases) page of this repository.
2.  Download the latest installer (e.g., `DocuGoggles_Installer.exe`).
3.  Run the installer and follow prompts to install.
4.  Launch DocuGoggles from the Start menu or system tray.

> **Note:** The installer bundles Python and all required libraries. You still need to install Tesseract separately if you wish to enable OCR on images.

---

*The sections below are for developers and advanced users who want to run from source or contribute.*

## Installation from Source

1.  **Install Tesseract OCR (only for image OCR):**
    - **Windows:** Download from the [UB Mannheim page](https://github.com/UB-Mannheim/tesseract/wiki). Add to your PATH or note installation directory.
    - **macOS:** `brew install tesseract`
    - **Debian/Ubuntu:** `sudo apt-get update && sudo apt-get install tesseract-ocr`

2.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Duquesne-Spring-2025-COSC-481/Naif-ALqurashi.git
    cd Naif-ALqurashi
    ```

3.  **Create and Activate a Virtual Environment:**
    - **Windows:**
      ```bash
      python -m venv venv
      venv\Scripts\activate
      ```
    - **macOS/Linux:**
      ```bash
      python3 -m venv venv
      source venv/bin/activate
      ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Copy** `config.example.json` to `config.json` in the project root if it doesn’t exist.
2.  **Edit** `config.json` or use the tray icon’s **Configure** option:
    - `scan_path`: Absolute path of the directory to scan.
    - `recursive_scan`: `true` to include subdirectories.
    - `process_images`: `true` to enable OCR on image files.
    - `meilisearch.url` / `meilisearch.api_key`: Settings for your Meilisearch instance.
    - `schedule`: Frequency (`daily`, `weekly`, `hourly`, `interval`) and timing.

## Running the Application

With your virtual environment active:
```bash
python tray_app.py
```
This will:
- Start the system tray icon.
- Launch Meilisearch locally if needed.
- Load configuration.
- Begin scheduled scanning.

## Usage

Right‑click the DocuGoggles tray icon to access:
- **Status:** Shows if the scanner is running.
- **Start/Stop Scanner**
- **Scan Now**
- **Open Search UI**
- **Open Meilisearch Dashboard**
- **Configure** settings
- **View Logs**
- **Clear Cache** (resets index and file cache)
- **Run on Startup** (Windows)
- **Exit**

## Troubleshooting

- **Permission Errors:** Ensure write permissions for `scanner.log` and `config.json`. Logs are written to `%LOCALAPPDATA%/DocuGoggles` by default.
- **Tesseract Not Found:** Verify Tesseract installation and PATH.
- **Streamlit Command Not Found:** Confirm Streamlit is installed in your environment.
- **Meilisearch Connection Issues:** Check Meilisearch is running at the configured URL.

---


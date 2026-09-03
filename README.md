# புரா சேவைகள் | Pura Services

A modern, lightweight, private local-network dashboard for sharing files, clipboard text, links, and device tools between devices on the same Wi-Fi or LAN.

The app runs from a single standard Python file (`server.py`) and opens instantly in any modern web browser. It is built for personal, trusted-network use: transfer files between phone and PC, copy text across devices, scan a 100% offline QR code, stream media with seek support, and manage shared files without installing heavy dependencies or frameworks.

---

- **Resumable Uploads & Pause / Resume**: Reliable interrupted-upload recovery for multi-gigabyte transfers with interactive pause and resume controls without losing progress.
- **SHA-256 Integrity Verification**: Streaming end-to-end cryptographic integrity verification between browser and server without high memory consumption.
- **Folder Sharing & Directory Preservation**: Native folder upload preserving subdirectories and hierarchies, along with on-the-fly folder ZIP archive downloads.
- **Secure Random PIN & Dynamic Lock Screen**: Automatically generates a secure 4-digit PIN on startup to protect your sharing session. Easily enable or disable PIN/password protection directly in the **Tools > Security** tab.
- **Live Sync with Server-Sent Events (SSE)**: Real-time dashboard updates across all connected browsers without manual refresh or high polling overhead.
- **Refined Glassmorphism UI & Dark Mode**: Tactile, responsive design with light and dark mode preferences saved in local storage.
- **Full Keyboard Accessibility (A11y)**: Tab navigation with arrow keys, quick search with `/`, and modal dismissal with `Escape` or backdrop clicks.
- **100% Offline QR & Clipboard Fallbacks**: Generates QR codes locally without any internet connection. Robust clipboard handling ensures "Copy Text" works across Android, iOS, Windows, macOS, and Linux, even in HTTP environments.

---

## Requirements

- **Python**: Python 3.10 or newer (tested on Python 3.10 – 3.14).
- **Network**: Devices must be connected to the same Wi-Fi / Local Area Network (LAN) or mobile hotspot.
- **Browser**: Any modern browser (Chrome, Edge, Firefox, Safari).

---

## Quick Start

You can start the server using the provided launch scripts, which automatically find your Python installation and pass any command-line arguments:

- **Windows:** Double-click `Start_windows.bat`
- **Linux:** Run `./Start_linux.sh` (make sure it's executable via `chmod +x Start_linux.sh`)
- **macOS:** Run `./Start_mac.sh` (make sure it's executable via `chmod +x Start_mac.sh`)

Alternatively, run the server manually from your terminal:

```bash
python server.py
```

Then open in your browser:

- **Local Computer**: `http://127.0.0.1:8000/`
- **Phone / Other Devices**: Scan the QR code in the **Tools** tab or open the LAN URL printed in the terminal (e.g. `http://192.168.1.50:8000/`).

### Opening Page & Security

- **Lock OFF**: Click the prominent **Open dashboard** button to enter immediately.
- **Lock ON (Default)**: Enter the 4-digit random PIN shown in your server terminal and click **Open dashboard**.
- **Configure Security**: Open the **Tools** tab to toggle PIN protection ON/OFF or customize your PIN at any time. Preferences are saved automatically in `shared_files/.pura_config.json`.

---

## Command Line Options

```bash
# Custom port
python server.py --port 9000

# Custom sharing directory
python server.py --dir C:\SharedFolder

# Custom upload size limit in GB (Default: 10 GB)
python server.py --max-upload-gb 5

# Custom PIN or disable PIN on trusted private networks
python server.py --pin 5432
python server.py --pin ""
```

---

## Folder Structure

```text
.
├── assets/
│   ├── GooglePay_QR.png
│   ├── Picture1.jpg
│   └── Picture1_rev.jpg
├── shared_files/
│   └── .gitkeep
├── .gitignore
├── index.html
├── LICENSE
├── pyproject.toml
├── qrcode.min.js
├── README.md
├── server.py
├── Start_linux.sh
├── Start_mac.sh
├── Start_windows.bat
├── test_security.py
└── test_suite.py
```

- `shared_files/` is the default runtime directory for shared files. Uploaded files are ignored by `.gitignore` so personal files are never committed to version control.
- `assets/` contains bundled offline dashboard artwork and QR codes.
- `Start_windows.bat`, `Start_linux.sh`, `Start_mac.sh` provide portable cross-platform launchers.

---

## Transfer Foundation (Phase 1A)

### Resumable Uploads & Interrupted-Upload Recovery
- Multi-gigabyte uploads are chunked into 2 MB segments and streamed directly to disk without memory buffering.
- Interrupted or dropped network connections can be resumed without restarting the entire file from zero.

### Pause / Resume Controls
- Click **Pause** during an upload to hold transfer progress without discarding partially received data.
- Click **Resume** to continue seamlessly from the exact byte offset verified by the server.
- Click **Cancel** to abort and immediately clean up temporary upload artifacts.

### SHA-256 Integrity Verification
- End-to-end cryptographic checksum verification is performed automatically.
- The client hashes file content in streaming blocks via the browser's Web Crypto API.
- Upon completion, the server matches its calculated digest against the client hash before finalization, displaying `✓ SHA-256 verified`.

### Folder Sharing & Archive Downloads
- Click **Select folder** or drag-and-drop a folder to upload entire nested directory structures.
- Directory hierarchies are preserved safely with path traversal protection against `../`, absolute paths, drive letters, and Windows reserved names.
- Individual directories can be downloaded as on-the-fly streaming ZIP archives via `/api/files/download-folder/<folder_name>`.
- *Note:* Folder selection via `webkitdirectory` is supported on Chrome, Edge, and Firefox desktop/mobile. On mobile Safari / iOS where directory pickers may be restricted by the OS, multi-file selection serves as the standard fallback.

---

## User Experience Foundation (Phase 1B)

### Safe File Previews
- Instant browser previews for **Images** (PNG, JPG, GIF, WebP, SVG), **Text & Code** (TXT, LOG, CSV, MD, JSON, XML, HTML, CSS, JS, PY, etc.), **Audio/Video** (MP4, WebM, MP3, WAV, AAC, FLAC), and **PDFs**.
- **XSS & Sandbox Security**: HTML, SVG, and code files are displayed safely without executing untrusted scripts in the dashboard origin.
- **Large-File Protection**: Previews for text files exceeding **1 MB** are automatically protected with a warning notice and direct download link to keep browser memory lightweight.

### Unified Global Search
- Real-time instant search across **Files**, **Folders**, and **Clipboard history**.
- Supports case-insensitive multi-word search queries.

### Download Selected Files as ZIP
- Check individual files or entire folders, or use the "Select all" toggle.
- Click **Download selected (N)** to generate an on-the-fly streaming ZIP archive that preserves relative folder paths without consuming server RAM.

### Automatic Cleanup Improvements
- Comprehensive background and startup cleanup automatically removes expired files, expired clipboard entries, stale resumable upload sessions, and orphaned temporary files without interrupting active transfers.

---

## Networking & Connectivity (Phase 1C)

### Optional HTTPS (TLS Encryption)
- **Local-Network Encryption**: Run Pura with `--https` to encrypt all browser communications over TLS.
  ```bash
  python server.py --https
  ```
- **Custom Certificates**: Provide custom TLS certificates using `--cert <path>` and `--key <path>`. If omitted, Pura automatically generates a 2048-bit local self-signed dev certificate.
- **Browser Warning Guidance**: When using self-signed certificates on local LANs, modern browsers display a standard "Connection is not private" certificate warning. This is expected because the local certificate is self-issued and not signed by a public Certificate Authority. It provides encrypted data transfer across your local Wi-Fi.
- **Dynamic Protocol & QR Reflection**: When HTTPS is active, the dashboard, LAN URLs, and phone QR codes automatically reflect `https://` and the designated port.

### Automatic LAN Discovery
- **Zero-Config Discovery**: Pura broadcasts a lightweight announcement packet on UDP port `52002` every 4 seconds, allowing devices on the local network to automatically detect running Pura servers without typing IP addresses.
- **Privacy & Security**: Discovery packets contain **zero sensitive metadata** (only service name, hostname, protocol, and port). PIN protection, file listings, and clipboard contents are **never** broadcast.
- **Multi-Server LAN Support**: Discovers and lists other active Pura instances on the same Wi-Fi network with direct connect links in the Network Diagnostics panel.
- **Graceful Fallback**: If UDP broadcast is restricted by router/AP client isolation policies, Pura falls back seamlessly to instant QR code scanning and manual LAN URLs.

### Network Diagnostics & Connectivity Testing
- Located in the **Tools** tab under **Network Diagnostics**.
- Real-time diagnostic verification of:
  - Server operational state & active listening port
  - Protocol (`HTTP` vs `HTTPS`)
  - Multi-interface local IP addresses (filtering virtual & loopback adapters)
  - LAN Discovery status & active peer count
- Includes an interactive **[Run diagnostics]** button to inspect network reachability on demand.

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `/` | Focus global search input |
| `ArrowLeft` / `ArrowRight` | Navigate between **Files**, **Clipboard**, and **Tools** tabs |
| `Escape` | Close active preview modal or artwork dialog |
| `Ctrl+V` / `Cmd+V` | Paste text or files anywhere to upload or compose clipboard |

---

## Security & Privacy Notes

- **Private LAN Design**: Built specifically for private trusted networks and personal Wi-Fi hotspots, not for direct public internet exposure.
- **Offline Reliability**: Does not depend on external CDNs or third-party web services. Works seamlessly on offline routers and mobile hotspots.
- **Windows Device Name Protection**: Automatically sanitizes filenames against Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) and path traversal attempts.
- **Session Tokens**: Uses cryptographically secure random session tokens and constant-time string comparison (`secrets.compare_digest`) to prevent timing attacks.

---

## Troubleshooting

1. **Phone cannot reach the computer**:
   - Verify both devices are connected to the same Wi-Fi network.
   - Use the LAN URL shown in the **Tools** tab (e.g. `http://192.168.x.x:8000/`), not `127.0.0.1`.
   - Ensure the selected port (default `8000`) is allowed through Windows Defender Firewall / OS firewall.
2. **Cannot read device clipboard on mobile**:
   - Modern mobile browsers require manual paste into text fields if clipboard permissions are restricted by browser policy. Use the dedicated **Paste Device Clip** button or paste directly into the text area.
3. **Port Conflict**:
   - If port `8000` is in use by another service, specify another port:
     ```bash
     python server.py --port 8888
     ```

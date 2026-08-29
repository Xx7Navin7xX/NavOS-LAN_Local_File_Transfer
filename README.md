# Pura Services

A lightweight local-network dashboard for sharing files, clipboard text, links, and quick device tools between devices on the same Wi-Fi or LAN.

The app runs from a single Python file and opens in a browser. It is built for personal trusted-network use: move files from phone to PC, copy text between devices, scan a QR code, and manage shared files without installing a heavy stack.

## Highlights

- File sharing over your local network.
- Upload by selecting, dragging, or pasting files/images.
- Preview, download, rename, copy link, and delete shared files.
- Download all shared files as a timestamped ZIP.
- Shared clipboard inbox with one-click copy, paste-and-save, edit, delete, and clear.
- Clipboard items persist across server restarts in `shared_files/clipboard_texts/`.
- Auto-delete options for uploads and clipboard text.
- Dashboard cards for storage, latest upload, latest clipboard, and devices.
- QR code and LAN link for opening the app from a phone.
- Editable device names in the tools page.
- PIN protection enabled by default with `2002`.
- Dark mode with saved browser preference.
- Mobile-first layout: shared files and recent clipboard appear before decorative panels.
- Glossy dove-themed interface using assets from `assets/`.

## Requirements

- Python 3.10 or newer.
- Devices must be on the same Wi-Fi/LAN.
- A browser such as Chrome, Edge, or Firefox.

No Python packages are required.

## Run

```bash
py server.py
```

Then open:

- Local computer: `http://127.0.0.1:8000/`
- Phone or another device: use the LAN URL printed in the terminal or scan the QR code in the Tools page.

The default PIN is:

```text
2002
```

## Options

```bash
py server.py --port 9000
py server.py --dir C:\path\to\shared-folder
py server.py --max-upload-gb 2
py server.py --pin 2002
```

Use `--pin=` only on a trusted private network if you want to disable PIN protection for testing.

## Folder Structure

```text
.
|-- assets/
|   |-- Picture1.jpg
|   `-- Picture1_rev.jpg
|-- shared_files/
|   `-- .gitkeep
|-- .gitignore
|-- README.md
`-- server.py
```

`shared_files/` is the default runtime folder. Files uploaded through the app are ignored by Git so private/shared files are not accidentally committed.

Clipboard history is stored in:

```text
shared_files/clipboard_texts/clipboard_items.json
```

## Mobile Notes

On mobile, the layout is optimized for action first:

- Files page shows Shared files before the upload panel and artwork.
- Clipboard page shows Recent clipboard before the compose panel and artwork.
- Header/status/dashboard summary content is reduced on narrow screens to keep main work areas near the top.
- Artwork cards are smaller on mobile so they do not push the main tools down.

## Security Notes

This app is designed for trusted local networks, not public internet hosting.

- The default PIN is stored in `server.py` as `DEFAULT_PIN`.
- Browser sessions use a local cookie after successful PIN entry.
- Trusted-device mode can keep the browser unlocked for 7 days.
- Do not expose this server directly to the public internet.

## Troubleshooting

If your phone cannot open the app:

- Make sure the phone and computer are on the same Wi-Fi.
- Use the LAN URL shown in the Tools page, not `127.0.0.1`.
- Allow the selected port through Windows Firewall.
- Try another port:

```bash
py server.py --port 9000
```

If QR scanning fails, copy the LAN link from the Tools page and open it manually on the phone.

## GitHub Notes

Before committing, the project should only contain source files and assets. Runtime uploads, backups, caches, and personal files are ignored by `.gitignore`.

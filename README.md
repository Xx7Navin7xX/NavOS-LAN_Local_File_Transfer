# NavOS - LAN Local File Transfer

Smart, lightweight file transfer between devices over your local network.

NavOS is a self-hosted file transfer and device-sharing application designed to make moving files between your PC, phone, tablet, and other devices on the same network simple.

No cloud storage is required. No account is required. Your files stay on your own network.

---

# Windows Quick Start

If you are using Windows, starting NavOS is simple.

## 1. Download NavOS

Download or clone this repository to your computer.

For example:

    git clone https://github.com/Xx7Navin7xX/NavOS-LAN_Local_File_Transfer.git

Or download the repository as a ZIP file from GitHub and extract it.

---

## 2. Install Python

NavOS requires Python.

Download Python from:

https://www.python.org/downloads/

During installation, make sure Python is added to your PATH.

You can check the installation by opening Command Prompt and running:

    python --version

You should see a Python version number.

---

## 3. Start NavOS

Open the NavOS folder.

You can start the server from Command Prompt:

    python server.py

If the project includes the Windows launcher, you can also start it using:

    Start_windows.bat

---

## 4. Open NavOS

After starting the server, the console will display the address that can be opened in a browser.

It will look similar to:

    http://192.168.1.100:8000

Open that address on the computer running NavOS.

---

## 5. Connect from your phone

Make sure your phone and computer are connected to the same local network.

For example:

    Computer
       |
       | Wi-Fi / Ethernet
       |
    Router
       |
       | Wi-Fi
       |
     Phone

Then open the NavOS address shown by the server on your phone.

Example:

    http://192.168.1.100:8000

Your phone should now be able to access the NavOS interface.

---

# Easiest Way to Connect Your Phone

If QR sharing is available on the dashboard:

1. Start NavOS.
2. Open the QR code.
3. Scan it using your phone camera.
4. Tap the detected link.
5. NavOS opens in your phone browser.

No manual IP address entry is required.

---

# Using NavOS for the First Time

After opening the dashboard, you will normally see the shared files and available controls.

## Upload a file

1. Open the upload area.
2. Select one or more files.
3. Wait for the upload to finish.
4. The files will appear in the shared directory.

You can also drag files into the browser where supported.

---

## Upload a folder

1. Choose the folder upload option.
2. Select the folder.
3. Wait for the upload to complete.
4. NavOS preserves the folder structure.

---

## Download a file

Select a file and choose the download option.

The browser will download the file normally.

---

## Download a folder

Select a folder and choose the folder download option.

NavOS creates a ZIP archive containing the folder contents.

---

## Download multiple files

Select the files you want.

Use the ZIP download option to download them together as a single archive.

---

# Command-Line Options

NavOS can be configured from the command line.

The available command-line configuration includes options for:

- Server address
- Server port
- PIN configuration
- HTTPS/TLS mode
- Custom certificates
- Custom private keys
- Other server startup settings

For example:

    python server.py --https

Use:

    python server.py --help

to display the available command-line options for your version.

---

# HTTPS with a Custom Certificate

If you already have a certificate and private key, NavOS can be configured to use them.

Example:

    python server.py --https --cert path/to/certificate.pem --key path/to/private-key.pem

Keep private keys protected and never commit them to GitHub.

---

# File Sharing Directory

NavOS serves files from its configured shared directory.

Only files within the configured shared area should be considered part of the server's file-sharing environment.

Do not place sensitive personal information, private keys, passwords, or other secrets inside the shared directory unless you intentionally want them accessible to connected users.

---

# Security Model

NavOS is primarily intended for trusted local networks.

For example:

- Home network
- Personal computer network
- Office LAN
- Laboratory network
- Workshop network
- Local development environment

It is not intended to replace a professionally hardened internet-facing file server.

If you expose NavOS directly to the public internet, you are changing its threat model significantly.

For internet-facing deployment, use an appropriate reverse proxy, firewall, authentication system, TLS configuration, and network access controls.

---

# Important Security Notes

## Do not expose NavOS directly to the internet without understanding the risks.

NavOS is designed around local network sharing.

If you only need to transfer files between devices at home, keep the server accessible only from your LAN.

Use your firewall to control which devices can reach the server when necessary.

---

## Keep your PIN private

If PIN authentication is enabled, do not share your PIN with untrusted users.

Anyone who can authenticate to the server may be able to access protected functionality.

---

## Protect your configuration

The server configuration can contain security-related settings.

Protect the configuration file from unauthorized local access.

If someone already has unrestricted access to the computer running NavOS, they should be considered trusted at the operating-system level.

---

# ZIP Security

ZIP generation is protected against path traversal and unsafe symbolic-link behavior.

NavOS verifies paths before adding files to generated archives.

Symbolic links are rejected instead of being followed into other locations.

This prevents a malicious filesystem entry from causing files outside the shared directory to be unintentionally included in a downloadable ZIP archive.

---

# Upload Security

Uploaded paths are validated before files are written.

NavOS prevents uploaded paths from escaping the configured shared directory.

This protects against path traversal attempts such as trying to upload a file to a parent directory using paths like:

    ../../somewhere/file.txt

---

# Supported Workflow

A typical NavOS workflow looks like this:

    Start NavOS
        |
        v
    Connect devices
        |
        +----------------------+
        |                      |
        v                      v
      Upload                Download
        |                      |
        v                      v
    Shared Files <--------> Other Device
        |
        +---- Preview
        |
        +---- Search
        |
        +---- Rename
        |
        +---- Delete
        |
        +---- ZIP Download

Clipboard sharing, QR connection, LAN discovery, diagnostics, and activity monitoring are available alongside the main file-transfer workflow.

---

## What is NavOS?

NavOS turns your computer into a private file-sharing server that other devices can access through a web browser.

Once NavOS is running, open the displayed network address on another device and you can:

- Upload files from your phone or PC
- Download files from the server
- Upload and download entire folders
- Transfer large files with resumable uploads
- Share files using QR codes
- Search your shared files
- Preview supported files directly in the browser
- Stream supported media
- Share clipboard content between devices
- Discover other NavOS servers on your local network
- Monitor transfers and server activity
- Protect the server with PIN authentication
- Use HTTP or HTTPS/TLS networking
- Manage files and folders from the web interface

NavOS is designed primarily for trusted local networks such as your home, office, laboratory, workshop, or personal device network.

---

# Features

## File Transfer

### Upload files

Upload one or multiple files directly from the web interface.

Supported upload features include:

- Multiple-file selection
- Drag and drop
- Browser paste support
- Upload progress
- Upload speed information
- Transfer status
- Concurrent uploads
- Pause and resume
- Cancel uploads
- Resumable uploads
- SHA-256 integrity verification

### Large file uploads

NavOS supports large file transfers and resumable uploads.

Uploads can resume after an interruption instead of requiring the entire file to be transferred again.

This is useful for:

- Large videos
- Disk images
- Game files
- Backups
- Archives
- Large project files

The default maximum file size is 10 GB.

---

## Folder Uploads

Folders can be uploaded directly through the browser.

NavOS preserves the folder structure during the upload.

For example:

    Project/
    ├── README.md
    ├── src/
    │   ├── main.py
    │   └── utils.py
    └── assets/
        └── logo.png

can be uploaded as a complete folder.

---

## Downloads

Individual files can be downloaded directly.

Folders can also be downloaded as ZIP archives.

NavOS provides multiple ZIP download options, including:

- Download an entire folder
- Download all available files
- Select specific files and download them together

ZIP generation includes path-safety checks so files outside the shared directory are not unintentionally included.

Symbolic links are not followed during ZIP generation.

---

## File and Folder Management

The web interface allows you to manage files stored in the shared directory.

Available operations include:

- Rename files
- Rename folders
- Delete files
- Delete folders
- Browse directories
- Navigate through nested folders
- Search for files
- View file information

---

# File Search

NavOS includes a built-in search system for finding files in the shared directory.

Search can be used to quickly locate files without manually browsing through every folder.

This is especially useful when the shared directory contains a large number of files.

---

# File Preview

Supported files can be opened directly in the browser without downloading them first.

Depending on the file type, NavOS can provide previews for:

- Images
- Audio
- Video
- PDF documents
- Text files

Text previews are protected by a size limit to avoid loading unnecessarily large text files directly into the browser.

---

# Media Streaming

Supported audio and video files can be streamed directly from NavOS.

HTTP Range requests are supported so compatible media players and browsers can request portions of a file instead of downloading the entire file at once.

This makes browser-based playback more practical for large media files.

---

# Clipboard Sharing

NavOS includes a cross-device clipboard system.

You can use it to move text and other useful information between devices without sending yourself messages or using cloud services.

Clipboard entries can be used for things such as:

- Text
- Links
- Commands
- Notes
- OTP codes
- JSON
- Other short pieces of information

The clipboard system includes:

- Clipboard history
- Copying entries
- Editing entries
- Deleting entries
- Expiration
- System clipboard integration

For example, you can copy a command on your PC and quickly access it from your phone through NavOS.

---

# QR Code Sharing

NavOS can generate a QR code for the local sharing address.

This makes connecting a phone or tablet much easier.

Instead of manually typing an IP address and port:

1. Start NavOS on your computer.
2. Open the displayed QR code.
3. Scan it with your phone.
4. Open the displayed address.
5. Start transferring files.

QR generation is performed locally and does not require an external QR-generation service.

---

# LAN Server Discovery

NavOS can automatically discover compatible NavOS servers on the local network.

This can make it easier to find another computer running NavOS without manually entering its IP address.

The discovery system can provide information such as:

- Device/server name
- IP address
- Port
- Protocol
- Authentication state
- Server availability

Discovery uses the local network and does not require a cloud service.

---

# Network Diagnostics

NavOS includes network information and diagnostics to help troubleshoot connectivity.

The interface can provide information about detected network interfaces and the addresses that can be used to connect to the server.

This is useful when a computer has multiple network interfaces, such as:

- Wi-Fi
- Ethernet
- Virtual adapters
- VPN adapters

If another device cannot connect, the network diagnostics section can help identify which address should be used.

---

# Live Activity

NavOS provides a live activity view for monitoring server operations.

Depending on the operation, activity information can include events such as:

- File uploads
- File downloads
- File deletion
- File changes
- Connections
- Authentication events
- Server operations

This makes it easier to understand what the server is doing while multiple devices are connected.

---

# Security

NavOS is designed primarily for use on trusted local networks.

Security features include:

- PIN authentication
- Protected dashboard access
- Authentication tokens
- Login protection
- Failed-login protection
- Protected file operations
- Path traversal protection
- ZIP path validation
- Symlink protection
- Upload path validation
- Resumable-upload validation
- Security configuration protection

---

## PIN Protection

You can protect the NavOS interface with a PIN.

When authentication is enabled, users must authenticate before accessing protected functionality.

The server also protects the security configuration itself.

When security is already enabled, changing the security settings requires the current PIN.

When security is disabled, security configuration can only be bootstrapped from the local machine.

A remote device on the LAN cannot simply connect and assign itself a new PIN.

---

# HTTPS / TLS

NavOS supports HTTPS/TLS encrypted connections.

HTTPS can be enabled when starting the server.

When HTTPS is enabled, NavOS can generate and use a local TLS certificate for the server.

This allows traffic between the browser and NavOS to be encrypted.

HTTPS is particularly useful when you want encrypted traffic even on a trusted local network.

### Important

HTTPS is not enabled by default.

Start NavOS with the `--https` option when encrypted HTTPS/TLS mode is desired.

Example:

    python server.py --https

NavOS can also accept custom certificate and key configuration when required.

---

# Privacy

NavOS is designed around local, self-hosted file transfer.

Your files are served directly from your own computer.

NavOS does not require cloud storage for normal file transfer.

The normal workflow is:

    Your Device
          |
          | Local Network
          v
    NavOS Server
          |
          v
    Shared Files

Your files remain on the computer running NavOS unless you explicitly transfer them to another device.

---

# Automatic Cleanup

NavOS includes automatic cleanup functionality for temporary and expired data.

This helps prevent temporary upload data and expired clipboard information from accumulating indefinitely.

---

# Web Interface

The web interface is designed to work across different device sizes.

You can use NavOS from:

- Desktop computers
- Laptops
- Android phones
- Tablets
- Other modern web browsers

The interface includes responsive layouts and touch-friendly controls.

Dark and light interface modes are supported.

Keyboard interaction is also supported for common operations.

---

# Common Problems

## My phone cannot connect

Check the following:

1. Make sure the phone and computer are on the same network.
2. Check the IP address displayed by NavOS.
3. Make sure you are using the correct port.
4. Check Windows Firewall.
5. Make sure NavOS is still running.
6. Try the QR code if available.
7. Check the Network Diagnostics section.

---

## NavOS works on the PC but not on my phone

This is commonly caused by firewall or network isolation.

Some routers create separate networks for wireless clients or enable client isolation.

Make sure the phone is allowed to communicate with the computer on the local network.

---

## The browser says the connection is not secure

If HTTPS is enabled and NavOS is using a locally generated or self-signed certificate, your browser may display a certificate warning.

This is expected for certificates that are not issued by a public certificate authority.

Do not ignore certificate warnings on networks or devices you do not trust.

---

## Upload stopped

If a resumable upload is supported for the particular transfer, NavOS can continue the upload instead of starting over.

Check the upload status in the dashboard.

---

## A ZIP does not contain a symbolic link

This is intentional.

NavOS does not follow symbolic links when creating downloadable ZIP archives.

This prevents links from pointing outside the shared directory and exposing unintended files.

---

# Requirements

Typical requirements include:

- Windows, Linux, or another supported Python environment
- Python 3
- A modern web browser
- Local network connectivity for device-to-device access

No cloud account is required for normal operation.

---

# Project Structure

A typical NavOS installation contains the application server, web interface, browser-side resources, and optional Windows startup files.

Example:

    NavOS-LAN_Local_File_Transfer/
    ├── server.py
    ├── index.html
    ├── qrcode.min.js
    ├── Start_windows.bat
    └── README.md

Additional files may be included depending on the release.

---

# Performance

NavOS is designed to remain lightweight while supporting practical local-network transfers.

Features such as:

- Concurrent uploads
- Resumable transfers
- Streaming
- Range requests
- Temporary upload handling
- ZIP resource limits
- Cleanup tasks

help keep the server practical for everyday use.

Actual transfer speed depends on:

- Wi-Fi speed
- Ethernet speed
- Router performance
- Device hardware
- Storage speed
- Browser behavior
- Network congestion

For large transfers, wired Ethernet or a fast Wi-Fi connection will generally provide better performance.

---

# Why NavOS?

Moving a file between your own devices should not require:

- Uploading it to a cloud service
- Creating another account
- Sending yourself an email
- Connecting a USB cable
- Installing a complicated synchronization system

NavOS provides a simple alternative:

    Your computer
          |
          | Local network
          v
       NavOS
       /    \
      /      \
   Phone    Tablet
      \      /
       \    /
     Other PC

Start the server, connect your devices, and transfer what you need.

---

# Privacy Philosophy

NavOS is built around a simple idea:

> Your files should not need to leave your network just because you want to move them between your own devices.

The application is self-hosted and intended for direct local-network communication.

---

# Support the Project

If NavOS is useful to you and you would like to support its development, you can use the support options provided in the application.

Available support methods may include:

- Razorpay
- PayPal
- UPI
- GitHub Sponsors
- Ko-fi

Support is completely optional, but it helps with continued development, testing, maintenance, and future improvements.

---

# Contributing

Contributions, bug reports, suggestions, and improvements are welcome.

Before submitting a pull request:

1. Explain what the change does.
2. Keep changes focused.
3. Test the affected functionality.
4. Avoid introducing unrelated changes.
5. Do not include passwords, private keys, personal configuration, or other secrets.

---

# Reporting Security Issues

If you discover a security vulnerability, please do not publicly disclose sensitive exploit details before the issue can be investigated.

Provide enough information to reproduce the problem safely, including:

- Affected feature
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant logs
- Suggested fix, if available

---

# License

See the `LICENSE` file in this repository for the applicable license.

---

# Disclaimer

NavOS is provided as a self-hosted local-network application.

You are responsible for configuring your network, firewall, authentication, TLS certificates, shared files, and access permissions appropriately.

Do not expose the application to untrusted networks unless you understand and have appropriately addressed the additional security requirements.

---

# Quick Start

If you just want the shortest possible setup:

### Windows

    1. Install Python 3.
    2. Download NavOS.
    3. Open the NavOS folder.
    4. Run Start_windows.bat
       or:
       python server.py
    5. Open the displayed address.
    6. Scan the QR code from your phone, or enter the displayed LAN address.
    7. Start transferring files.

That's it.

---

## NavOS - LAN Local File Transfer

Smart, lightweight file transfer between devices over your local network.

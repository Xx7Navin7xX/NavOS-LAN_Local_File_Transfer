#!/usr/bin/env python3
"""Pura Services - Local-network file, clipboard, and quick-link sharing server.

A zero-dependency, private LAN sharing dashboard designed for personal trusted networks.
Supports file sharing, resumable media streaming with HTTP 206 Range requests,
persistent clipboard inbox, offline QR code generation, and multi-device synchronization.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import socket
import ssl
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


APP_TITLE = "புரா சேவைகள்"
CHUNK_SIZE = 1024 * 1024
STREAM_BUFFER_SIZE = 64 * 1024
DEFAULT_MAX_UPLOAD_GB = 10
DEFAULT_PIN = "".join(secrets.choice("0123456789") for _ in range(4))
DISCOVERY_PORT = 52002
MAX_CLIPBOARD_BYTES = 512 * 1024
MAX_CLIPBOARD_ITEMS = 30
MAX_ACTIVITY_EVENTS = 50
RESUMABLE_STALE_SECONDS = 24 * 60 * 60  # 24 hours
MAX_RESUMABLE_CHUNK_BYTES = 5 * 1024 * 1024  # 5 MB hard limit per chunk
MAX_ACTIVE_RESUMABLE_SESSIONS = 25
MAX_SSE_CLIENTS = 20
MAX_TRACKED_DEVICES = 64
DEVICE_STALE_SECONDS = 24 * 60 * 60
MAX_CONCURRENT_ZIPS = 2
MAX_ZIP_FILES = 100_000


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NavOS Local File Transfer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f1f0eb;
      --panel: #fbfaf6;
      --ink: #332c2a;
      --muted: #6f7471;
      --line: #d8d5cc;
      --accent: #7f8f66;
      --accent-strong: #556145;
      --soft: #e6e2d8;
      --hero: #dfe4dc;
      --hero-ink: #332c2a;
      --clay: #a27f6d;
      --sage: #7f8f66;
      --mist: #dce7e4;
      --dove: #f4f7f1;
      --ok: #7f8f66;
      --warn: #a27f4e;
      --danger: #a84d46;
      --glass: rgba(255, 255, 255, 0.58);
      --shine: rgba(255, 255, 255, 0.72);
      --shadow: 0 18px 45px rgba(58, 50, 47, 0.13);
      --focus: #d5e1aa;
    }

    body.dark {
      color-scheme: dark;
      --bg: #2f2927;
      --panel: #3d3633;
      --ink: #f4f1ea;
      --muted: #cbc6bd;
      --line: #5b514c;
      --accent: #a8b681;
      --accent-strong: #d5e1aa;
      --soft: #4b4640;
      --hero: #463d39;
      --hero-ink: #f4f1ea;
      --clay: #c49a83;
      --sage: #a8b681;
      --mist: #b8cac6;
      --dove: #eef3ec;
      --ok: #a8b681;
      --warn: #d3ae74;
      --danger: #e18d84;
      --glass: rgba(61, 54, 51, 0.66);
      --shine: rgba(255, 255, 255, 0.16);
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.32);
      --focus: #edf6c9;
    }

    * { box-sizing: border-box; }

    html {
      max-width: 100%;
      overflow-x: hidden;
    }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% 8%, color-mix(in srgb, var(--mist) 48%, transparent), transparent 30%),
        radial-gradient(circle at 88% 18%, color-mix(in srgb, var(--clay) 18%, transparent), transparent 28%),
        radial-gradient(circle at 74% 86%, color-mix(in srgb, var(--sage) 22%, transparent), transparent 30%),
        var(--bg);
      color: var(--ink);
      min-height: 100vh;
      min-height: 100dvh;
      max-width: 100%;
      overflow-x: hidden;
      line-height: 1.45;
      text-rendering: optimizeLegibility;
    }

    .app-shell {
      width: min(1240px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 36px;
      transition: opacity 420ms ease, transform 520ms cubic-bezier(.2, .8, .2, 1), filter 420ms ease;
      position: relative;
      isolation: isolate;
      overflow-x: hidden;
      overflow-x: clip;
    }

    body:not(.locked) .app-shell::before {
      content: "";
      position: absolute;
      z-index: -1;
      right: -70px;
      top: 210px;
      width: min(420px, 36vw);
      height: 560px;
      border-radius: 8px;
      background:
        linear-gradient(145deg, rgba(255, 255, 255, 0.22), transparent 34%),
        radial-gradient(circle at 48% 20%, color-mix(in srgb, var(--accent) 52%, transparent), transparent 48%),
        linear-gradient(180deg, color-mix(in srgb, var(--sage) 46%, transparent), transparent);
      filter: blur(22px);
      opacity: 0.62;
      pointer-events: none;
    }

    body.locked .app-shell {
      opacity: 0;
      transform: translateY(28px) scale(0.985);
      filter: blur(10px);
      pointer-events: none;
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 520px);
      gap: 16px;
      align-items: stretch;
      margin-bottom: 14px;
    }

    .brand-panel {
      min-height: 132px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(135deg, var(--shine), transparent 32%),
        linear-gradient(120deg, color-mix(in srgb, var(--mist) 58%, var(--panel)), var(--panel));
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
      gap: 18px;
      padding: 22px;
      box-shadow: var(--shadow);
      color: var(--hero-ink);
      backdrop-filter: blur(18px);
      position: relative;
      overflow: hidden;
    }

    .brand-panel::after {
      content: "";
      position: absolute;
      right: -60px;
      bottom: -80px;
      width: 260px;
      height: 180px;
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.26), transparent 36%),
        linear-gradient(135deg, color-mix(in srgb, var(--accent) 54%, transparent), transparent);
      filter: blur(2px);
      opacity: 0.72;
      pointer-events: none;
    }

    .brand-mark {
      width: 72px;
      height: 72px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background:
        linear-gradient(145deg, var(--shine), transparent 42%),
        var(--glass);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      color: var(--accent);
      backdrop-filter: blur(16px);
    }

    .brand-mark svg {
      width: 50px;
      height: 50px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    h1 {
      margin: 0 0 6px;
      font-size: clamp(30px, 4vw, 46px);
      line-height: 1;
      font-weight: 820;
      letter-spacing: 0;
    }

    h2, h3 { margin: 0; letter-spacing: 0; }
    h2 { font-size: 18px; }
    h3 { font-size: 15px; }
    p { margin: 0; color: var(--muted); line-height: 1.5; }

    .brand-panel p {
      overflow-wrap: anywhere;
    }

    .status, .panel {
      background:
        linear-gradient(145deg, var(--shine), transparent 38%),
        var(--glass);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }

    .status {
      padding: 14px;
      align-self: stretch;
      display: grid;
      align-content: center;
    }

    .status-row {
      display: grid;
      grid-template-columns: 86px 1fr auto;
      gap: 10px;
      align-items: center;
      min-height: 32px;
      font-size: 14px;
    }

    .status-row + .status-row {
      border-top: 1px solid var(--line);
      padding-top: 10px;
      margin-top: 10px;
    }

    .label {
      color: var(--muted);
      font-weight: 650;
    }

    .url, code {
      min-width: 0;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      color: var(--muted);
      max-width: 100%;
    }

    button, .button, select, input, textarea {
      border-radius: 8px;
      font: inherit;
    }

    button, .button {
      appearance: none;
      border: 1px solid transparent;
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--shine) 48%, transparent), transparent 48%),
        linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent-strong) 88%, var(--clay)));
      color: #ffffff;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 36px;
      padding: 0 13px;
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
      transition: background 150ms ease, border-color 150ms ease, color 150ms ease, transform 120ms ease, box-shadow 150ms ease;
    }

    button:hover, .button:hover {
      background: var(--accent-strong);
      transform: translateY(-1px);
    }
    button:active, .button:active { transform: translateY(0); }
    button.secondary {
      background: var(--panel);
      border-color: var(--line);
      color: var(--ink);
    }
    button.secondary:hover { background: var(--soft); }
    button.danger {
      background: var(--panel);
      border-color: #f2b8b5;
      color: var(--danger);
    }
    button.danger:hover { background: #fff4f3; }
    button:disabled { cursor: not-allowed; opacity: 0.55; }

    button:focus-visible,
    .button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    textarea:focus-visible,
    [role="button"]:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--focus) 76%, transparent);
      outline-offset: 2px;
      box-shadow: 0 0 0 1px var(--accent);
    }

    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      padding: 10px 11px;
      min-height: 40px;
      transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
    }

    select {
      padding: 6px 10px;
      cursor: pointer;
      line-height: normal;
      height: 40px;
    }

    textarea {
      min-height: 132px;
      resize: vertical;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .tabs {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 10px 14px;
    }

    .tabs-nav {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .tabs-actions {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-left: auto;
    }

    .search-box {
      min-width: min(320px, 100%);
      flex: 1;
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 10px;
      min-height: 40px;
      background: var(--bg);
      color: var(--muted);
    }

    .search-box:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 42%, transparent);
    }

    .search-box input,
    .search-box input:focus,
    .search-box input:focus-visible {
      border: 0 !important;
      outline: none !important;
      box-shadow: none !important;
      background: transparent !important;
      min-height: 36px;
      padding: 0;
    }

    .support-btn {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 0 14px;
      min-height: 40px;
      font-size: 14px;
      font-weight: 700;
      color: var(--ink);
      background: color-mix(in srgb, var(--panel) 90%, var(--line));
      border: 1px solid var(--line);
      border-radius: 8px;
      cursor: pointer;
      transition: all 160ms ease;
    }

    .support-btn:hover {
      background: color-mix(in srgb, var(--accent) 15%, var(--panel));
      border-color: color-mix(in srgb, var(--accent) 60%, var(--line));
      color: var(--accent-strong);
      transform: translateY(-1px);
    }

    .support-btn .heart-icon {
      width: 16px;
      height: 16px;
      fill: #e0245e;
      color: #e0245e;
      flex-shrink: 0;
      transition: transform 200ms cubic-bezier(.2, .8, .2, 1);
    }

    .support-btn:hover .heart-icon {
      transform: scale(1.22);
    }

    .theme-toggle {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
      user-select: none;
    }

    .support-dialog {
      width: min(560px, calc(100% - 24px));
      border-radius: 12px;
      padding: 0;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: visible !important;
      position: relative;
    }

    .support-dialog .dialog-body {
      overflow: visible;
    }

    .support-card {
      display: grid;
      gap: 16px;
      padding: 4px 4px 12px;
    }

    .support-header {
      display: grid;
      gap: 8px;
      text-align: center;
      padding: 4px 8px;
    }

    .support-heart-badge {
      width: 52px;
      height: 52px;
      margin: 0 auto;
      border-radius: 50%;
      background: color-mix(in srgb, #e0245e 12%, transparent);
      border: 1px solid color-mix(in srgb, #e0245e 32%, transparent);
      display: grid;
      place-items: center;
      color: #e0245e;
      cursor: pointer;
      user-select: none;
      position: relative;
      transition: transform 120ms cubic-bezier(.2, .8, .2, 1), background-color 150ms ease, box-shadow 150ms ease;
    }

    .support-heart-badge:hover {
      transform: scale(1.1);
      background: color-mix(in srgb, #e0245e 22%, transparent);
      box-shadow: 0 0 16px color-mix(in srgb, #e0245e 35%, transparent);
    }

    .support-heart-badge:active {
      transform: scale(0.86);
    }

    .support-heart-badge svg {
      width: 26px;
      height: 26px;
      fill: currentColor;
      pointer-events: none;
      transition: transform 120ms ease;
    }

    .floating-hearts-layer {
      position: absolute;
      inset: 0;
      pointer-events: none;
      overflow: visible;
      z-index: 10000;
    }

    .floating-heart {
      position: absolute;
      pointer-events: none;
      user-select: none;
      z-index: 10000;
      will-change: transform, opacity;
      animation: floatUpFullScreen 2.4s cubic-bezier(0.2, 0.6, 0.35, 1) forwards;
    }

    .floating-heart svg {
      display: block;
      width: 100%;
      height: 100%;
      filter: drop-shadow(0 3px 8px rgba(0, 0, 0, 0.28));
    }

    @keyframes floatUpFullScreen {
      0% {
        opacity: 1;
        transform: translate(-50%, -50%) scale(0.6) rotate(0deg);
      }
      15% {
        opacity: 1;
        transform: translate(calc(-50% + var(--sway-1, 20px)), -90px) scale(var(--scale, 1.15)) rotate(var(--rot-1, 14deg));
      }
      38% {
        opacity: 0.96;
        transform: translate(calc(-50% + var(--sway-2, -24px)), -230px) scale(var(--scale, 1.15)) rotate(var(--rot-2, -12deg));
      }
      62% {
        opacity: 0.92;
        transform: translate(calc(-50% + var(--sway-3, 18px)), -400px) scale(calc(var(--scale, 1.15) * 0.95)) rotate(var(--rot-1, 10deg));
      }
      85% {
        opacity: 0.7;
        transform: translate(calc(-50% + var(--sway-4, -14px)), -580px) scale(0.9) rotate(var(--rot-2, -15deg));
      }
      100% {
        opacity: 0;
        transform: translate(calc(-50% + var(--sway-5, 8px)), -750px) scale(0.75) rotate(var(--rot-1, 20deg));
      }
    }

    .support-header p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }

    .payment-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      width: 100%;
    }

    .payment-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      background: color-mix(in srgb, var(--panel) 75%, var(--soft));
      border: 1px solid var(--line);
      border-radius: 8px;
      text-decoration: none;
      color: var(--ink);
      transition: all 160ms ease;
      cursor: pointer;
      font-size: 14px;
    }

    .payment-link:hover {
      background: color-mix(in srgb, var(--accent) 14%, var(--panel));
      border-color: color-mix(in srgb, var(--accent) 60%, var(--line));
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }

    .payment-info {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }

    .payment-icon {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      display: grid;
      place-items: center;
      font-size: 16px;
      flex-shrink: 0;
      background: color-mix(in srgb, var(--line) 40%, transparent);
      border: 1px solid var(--line);
    }

    .payment-text {
      display: grid;
      gap: 2px;
      min-width: 0;
    }

    .payment-title {
      font-weight: 760;
      font-size: 14px;
      color: var(--ink);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .payment-subtitle {
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .payment-action {
      display: inline-flex;
      align-items: center;
      font-size: 12px;
      font-weight: 700;
      color: var(--accent-strong);
      flex-shrink: 0;
    }

    .upi-box {
      margin-top: 4px;
      padding: 10px 14px;
      background: color-mix(in srgb, var(--panel) 85%, var(--line));
      border: 1px dashed var(--line);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 13px;
    }

    button.payment-link {
      font-family: inherit;
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 75%, var(--soft));
    }

    .upi-qr-dialog {
      width: min(420px, calc(100% - 24px));
      border-radius: 12px;
      padding: 0;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      text-align: center;
    }

    .upi-qr-card {
      display: grid;
      gap: 14px;
      padding: 12px 16px 20px;
      align-items: center;
      justify-items: center;
    }

    .upi-qr-image {
      width: min(280px, 100%);
      height: auto;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 8px;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
      display: block;
      margin: 0 auto;
    }

    .upi-qr-note {
      font-size: 13px;
      color: var(--muted);
      margin: 0;
      line-height: 1.4;
    }

    .upi-id-label {
      color: var(--muted);
      font-weight: 600;
    }

    .upi-id-code {
      font-family: inherit;
      font-weight: 700;
      color: var(--ink);
      user-select: all;
    }

    .upi-copy-btn {
      padding: 4px 10px !important;
      min-height: 28px !important;
      font-size: 12px !important;
      margin: 0 !important;
    }

    .switch {
      position: relative;
      width: 52px;
      height: 30px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 82%, var(--line));
      cursor: pointer;
      padding: 0;
      min-height: 30px;
      transition: background 160ms ease, border-color 160ms ease;
    }

    .switch span {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 22px;
      height: 22px;
      border-radius: 999px;
      background: var(--muted);
      transition: transform 160ms ease;
    }

    body.dark .switch {
      background: var(--accent);
      border-color: var(--accent);
    }

    body.dark .switch span {
      transform: translateX(22px);
      background: #ffffff;
    }

    .tab.active {
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--shine) 42%, transparent), transparent 48%),
        linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: #ffffff;
      border-color: var(--accent);
      box-shadow: inset 0 1px 0 color-mix(in srgb, #ffffff 34%, transparent);
    }

    body.dark .tab.active, body.dark button:not(.secondary):not(.danger), body.dark .button {
      color: #2f2927;
    }

    .view { display: none; }
    .view.active { display: block; }

    .smart-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .metric {
      min-height: 92px;
      padding: 16px;
      display: grid;
      align-content: space-between;
      gap: 10px;
      position: relative;
      overflow: hidden;
    }

    .metric.has-action {
      padding-right: 124px;
    }

    .metric .meta {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .metric-action {
      position: absolute;
      top: 14px;
      right: 14px;
      min-width: 0;
      min-height: 32px;
      padding: 0 10px;
    }

    .metric::after {
      content: "";
      position: absolute;
      inset: auto 0 0 0;
      height: 3px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
      opacity: 0.72;
    }

    .metric strong {
      display: block;
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 24px;
      line-height: 1.1;
      letter-spacing: 0;
    }

    .metric button {
      justify-self: start;
      min-height: 32px;
    }

    .dove-card {
      min-height: 340px;
      height: 100%;
      padding: 0;
      overflow: hidden;
      cursor: pointer;
      position: relative;
      border: 1px solid color-mix(in srgb, var(--line) 70%, var(--shine));
    }

    .dove-card::after {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(130deg, rgba(255, 255, 255, 0.35), transparent 32%),
        linear-gradient(0deg, rgba(51, 44, 42, 0.36), transparent 48%);
      pointer-events: none;
    }

    .dove-art {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
      aspect-ratio: 3 / 4;
      object-position: center;
      background: #403734;
    }

    .dove-card-caption {
      position: absolute;
      left: 16px;
      right: 16px;
      bottom: 14px;
      z-index: 1;
      color: #fbfaf6;
      font-weight: 800;
      text-shadow: 0 2px 14px rgba(0, 0, 0, 0.42);
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(360px, 1fr) minmax(240px, 320px);
      gap: 16px;
      align-items: start;
    }

    .grid > .panel {
      height: clamp(450px, calc(100vh - 290px), 660px);
      min-height: 0;
      overflow: hidden;
    }

    .dropzone {
      min-height: 0;
      height: 100%;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
      text-align: center;
      outline: 2px dashed transparent;
      outline-offset: -10px;
      transition: outline-color 140ms ease, background 140ms ease;
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior-y: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }

    .dropzone.dragover {
      background: #eef8f3;
      outline-color: var(--accent);
    }

    .drop-inner {
      display: grid;
      gap: 8px;
      justify-items: center;
      width: 100%;
      max-width: 320px;
      margin: auto 0;
      padding: 4px 0;
    }

    .upload-icon {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: var(--soft);
      color: var(--accent);
    }

    .upload-icon svg {
      width: 18px;
      height: 18px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .drop-text-block {
      line-height: 1.3;
      font-size: 13.5px;
    }

    .drop-text-block #upload-note {
      font-size: 12px;
      color: var(--muted);
      display: inline-block;
      margin-top: 2px;
    }

    input[type="file"] { display: none; }

    .progress {
      width: 100%;
      display: none;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }

    .progress.active { display: grid; }
    .progress-track {
      height: 8px;
      background: #eef0f4;
      border-radius: 999px;
      overflow: hidden;
    }
    .progress-track span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--accent);
      transition: width 120ms linear;
    }

    .queue {
      width: 100%;
      display: grid;
      gap: 8px;
    }

    .queue-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      text-align: left;
      background: var(--panel);
    }

    .queue-name {
      font-weight: 700;
      overflow-wrap: anywhere;
    }

    .queue-status {
      color: var(--muted);
      font-size: 12px;
    }

    .progress-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      width: 100%;
    }

    .progress-actions button {
      min-height: 36px;
      height: 36px;
      width: 100%;
      padding-inline: 8px;
    }

    #folder-input { display: none; }

    .sha256-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--ok) 14%, transparent);
      color: var(--ok);
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      word-break: break-all;
    }
    .sha256-icon {
      font-weight: bold;
      font-size: 14px;
    }
    .sha256-badge.error {
      background: color-mix(in srgb, var(--danger) 14%, transparent);
      color: var(--danger);
    }

    .folder-group {
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 8px;
      overflow: hidden;
    }
    .folder-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      background: color-mix(in srgb, var(--accent) 8%, var(--panel));
      cursor: pointer;
      font-weight: 700;
      font-size: 14px;
    }
    .folder-header .folder-icon {
      color: var(--accent);
    }
    .folder-header .folder-actions {
      margin-left: auto;
      display: flex;
      gap: 6px;
    }
    .folder-files {
      border-top: 1px solid var(--line);
    }

    .selection-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 8px 18px;
      background: color-mix(in srgb, var(--accent) 6%, var(--panel));
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }
    .selection-bar-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .unselect-all-btn {
      min-height: 28px;
      height: 28px;
      padding: 0 10px;
      font-size: 12px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .select-all-label {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      font-weight: 600;
      user-select: none;
    }
    .file-select-checkbox {
      cursor: pointer;
      width: 17px;
      height: 17px;
      accent-color: var(--accent);
      flex-shrink: 0;
    }
    .file-row.selected {
      background: color-mix(in srgb, var(--accent) 10%, var(--panel));
    }
    .preview-audio, .preview-video {
      width: 100%;
      max-height: 70vh;
      border-radius: 8px;
      outline: none;
      background: #000;
    }
    .preview-frame {
      width: 100%;
      height: 70vh;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .tab-badge {
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 10px;
      background: color-mix(in srgb, var(--accent) 18%, transparent);
      color: var(--accent);
      margin-left: 6px;
      font-weight: bold;
    }

    .diagnostics-toolbox {
      display: grid;
      gap: 12px;
    }
    .peers-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .peer-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--accent) 8%, var(--panel));
      border: 1px solid var(--line);
      font-size: 13px;
    }
    .peer-card a {
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
      font-size: 12px;
    }
    .peer-card a:hover {
      text-decoration: underline;
    }

    .panel-head {
      min-height: 64px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      flex: 0 0 auto;
    }

    .panel-title-wrap {
      display: flex;
      align-items: baseline;
      gap: 10px;
      min-width: 0;
    }

    .panel-title-wrap h2 {
      margin: 0;
    }

    .panel-body { padding: 18px; }
    .clipboard-compose {
      display: grid;
      gap: 12px;
    }
    .list {
      display: grid;
      grid-auto-rows: max-content;
    }

    .grid .list {
      flex: 1 1 auto;
      min-height: 0;
      align-content: start;
      overflow-y: auto;
      overscroll-behavior: auto;
      overscroll-behavior-y: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }

    #files-view .grid > .panel:not(.dropzone):not(.dove-card),
    #clipboard-view .grid > .panel:not(.dove-card) {
      display: flex;
      flex-direction: column;
    }

    #clipboard-view .panel-body {
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior-y: auto;
      -webkit-overflow-scrolling: touch;
    }

    .file-row {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 10px;
      min-height: 116px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      width: 100%;
      max-width: 100%;
      overflow: hidden;
    }

    .clip-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      min-height: 76px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      position: relative;
      width: 100%;
      max-width: 100%;
      overflow: hidden;
    }

    .file-row:last-child, .clip-row:last-child { border-bottom: 0; }

    .file-row > div:first-child,
    .clip-details {
      width: 100%;
      min-width: 0;
      max-width: 100%;
      overflow: hidden;
    }

    .file-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      width: 100%;
      margin-bottom: 4px;
    }

    .file-header .file-name {
      flex: 1 1 auto;
      min-width: 0;
      margin-bottom: 0;
    }

    .file-header .file-select-checkbox {
      margin: 0;
      flex-shrink: 0;
    }

    .file-name, .clip-text {
      font-weight: 720;
      overflow-wrap: anywhere;
      word-break: break-word;
      margin-bottom: 4px;
    }

    .file-name {
      display: block;
      max-width: 100%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.25;
    }
    .clip-text {
      display: block;
      white-space: pre-wrap;
      max-height: 120px;
      overflow: auto;
      overflow-wrap: anywhere;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      line-height: 1.45;
      width: 100%;
      max-width: 100%;
      min-width: 0;
      padding-right: 0;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
    }

    .file-row .meta {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-start;
      width: 100%;
    }

    .file-row .actions,
    .clip-row .actions {
      border-top: 1px solid var(--line);
      padding-top: 10px;
      margin-top: 2px;
      flex-wrap: nowrap;
      overflow-x: auto;
      scrollbar-width: thin;
    }

    .file-row .actions {
      justify-content: flex-start;
      min-height: 34px;
    }

    .clip-row .actions {
      justify-content: flex-start;
      min-height: 34px;
      width: 100%;
      max-width: 100%;
      min-width: 0;
    }

    .actions button,
    .actions .button {
      flex: 0 0 auto;
      min-width: 0;
      padding-inline: 12px;
    }

    .file-row .actions button,
    .file-row .actions .button {
      min-height: 32px;
      padding-inline: 10px;
      font-size: 13px;
    }

    .panel-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
      margin-left: auto;
      max-width: 100%;
      overflow-x: auto;
      scrollbar-width: thin;
    }

    #clipboard-view .panel-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, auto);
      align-items: start;
    }

    #clipboard-view .panel-actions {
      margin-left: 0;
      justify-self: end;
      max-width: 100%;
    }

    .panel-actions button {
      min-width: 0;
      padding-inline: 11px;
      min-height: 34px;
    }

    .files-panel .panel-actions {
      min-width: 0;
    }

    .inline-form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: end;
    }

    .clipboard-actions-form select,
    .clipboard-actions-form button {
      min-height: 40px;
      height: 40px;
    }

    .clipboard-actions-form button {
      white-space: nowrap;
      padding-inline: 16px;
    }

    .upload-controls {
      display: grid;
      gap: 6px;
      width: 100%;
      max-width: 320px;
      margin: 0 auto;
    }

    .upload-expiry-field {
      width: 100%;
      display: grid;
      gap: 2px;
      text-align: left;
    }

    .upload-expiry-field label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
    }

    .upload-expiry-field select {
      min-height: 38px;
      height: 38px;
      padding: 6px 10px;
      line-height: normal;
      width: 100%;
    }

    .upload-buttons-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      width: 100%;
    }

    .upload-buttons-row button {
      width: 100%;
      min-height: 36px;
      height: 36px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 10px;
    }

    .field { display: grid; gap: 6px; }
    .field label { color: var(--muted); font-size: 13px; font-weight: 650; }

    .empty {
      padding: 42px 18px;
      text-align: center;
      color: var(--muted);
      font-weight: 650;
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--shine) 36%, transparent), transparent 65%),
        color-mix(in srgb, var(--panel) 74%, transparent);
    }

    .tools {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      align-items: stretch;
    }

    .tool-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 18px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: color-mix(in srgb, var(--panel) 88%, var(--soft));
      min-height: 0;
      height: 100%;
    }

    .tool-box.device-toolbox {
      grid-column: 1 / -1;
    }

    .tool-box h3 {
      font-size: 15px;
      font-weight: 700;
      margin: 0;
    }

    .tool-box:hover,
    .metric:hover,
    .file-row:hover,
    .clip-row:hover {
      background:
        linear-gradient(145deg, color-mix(in srgb, var(--shine) 30%, transparent), transparent 50%),
        color-mix(in srgb, var(--panel) 90%, var(--soft));
    }

    .tool-box code,
    .tool-box p,
    .tool-box .meta,
    .tool-box .service-list {
      width: 100%;
    }

    .tool-box button,
    .tool-box .button {
      width: 100%;
      min-width: 0;
      min-height: 38px;
      height: 38px;
      margin-top: auto;
      padding-inline: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    .tool-box .qr {
      align-self: center;
      margin: 4px auto 0;
    }

    .tool-box .meta {
      font-size: 12px;
      line-height: 1.4;
      color: var(--muted);
    }

    .tool-box code#lan-url {
      font-family: inherit;
      font-size: 13px;
      font-weight: 650;
      color: var(--ink);
      background: color-mix(in srgb, var(--panel) 65%, var(--bg));
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      word-break: break-all;
      user-select: all;
      display: block;
      margin: 2px 0 0;
    }

    .device-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 10px;
      width: 100%;
    }

    .device-row {
      display: grid;
      grid-template-columns: 10px minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--panel) 82%, var(--bg));
    }

    .device-row input {
      min-height: 36px;
      height: 36px;
      padding: 6px 10px;
      font-size: 13px;
    }

    .device-meta {
      grid-column: 2 / 4;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .tool-box .device-row button {
      min-width: 64px !important;
      width: auto !important;
      min-height: 36px !important;
      height: 36px !important;
      padding-inline: 12px !important;
      margin-top: 0 !important;
    }

    .activity-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      width: 100%;
      max-height: 125px;
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior-y: auto;
      -webkit-overflow-scrolling: touch;
      padding-right: 2px;
      margin: 0;
    }

    .activity-row {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 8px;
      align-items: baseline;
      font-size: 13px;
      line-height: 1.35;
      padding: 3px 0;
      border-bottom: 1px dashed color-mix(in srgb, var(--line) 60%, transparent);
    }

    .activity-row:last-child {
      border-bottom: none;
    }

    .activity-time {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11.5px;
      color: var(--muted);
      white-space: nowrap;
      font-weight: 600;
    }

    .activity-msg {
      color: var(--ink);
      word-break: break-word;
      font-size: 12.5px;
    }

    .activity-empty {
      color: var(--muted);
      font-size: 13px;
      font-style: italic;
      padding: 6px 0;
    }

    .service-list {
      display: grid;
      gap: 6px;
    }

    .service-row {
      display: grid;
      grid-template-columns: 10px 1fr auto;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--warn);
    }

    .dot.ok { background: var(--ok); }
    .dot.bad { background: var(--danger); }

    .qr {
      width: 112px;
      height: 112px;
      image-rendering: pixelated;
      border: 4px solid #ffffff;
      border-radius: 6px;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12), inset 0 0 0 1px var(--line);
      background: var(--panel);
    }

    dialog {
      width: min(760px, calc(100% - 28px));
      max-height: calc(100dvh - 28px);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0;
      box-shadow: var(--shadow);
      background: var(--panel);
      color: var(--ink);
      overflow: hidden;
      opacity: 0;
      transform: translateY(10px) scale(0.99);
      transition: opacity 160ms ease, transform 160ms ease;
    }
    dialog[open] {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
    dialog::backdrop {
      background:
        radial-gradient(circle at 50% 20%, rgba(168, 182, 129, 0.24), transparent 38%),
        rgba(31, 27, 25, 0.72);
      backdrop-filter: blur(12px) saturate(1.15);
    }
    .dialog-body {
      padding: 16px;
      display: grid;
      gap: 12px;
      max-height: calc(100dvh - 92px);
      overflow: auto;
      overscroll-behavior: contain;
    }
    .preview-frame {
      width: 100%;
      height: min(70dvh, 520px);
      min-height: 260px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .preview-image {
      max-width: 100%;
      max-height: min(70dvh, 620px);
      object-fit: contain;
      display: block;
      margin: 0 auto;
      border-radius: 8px;
      background: var(--soft);
    }
    .preview-text {
      white-space: pre-wrap;
      overflow: auto;
      max-height: 70vh;
      overflow-wrap: anywhere;
      word-break: break-word;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
      font-size: 13px;
      line-height: 1.5;
      max-width: 100%;
    }

    .preview-note {
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--panel) 82%, var(--soft));
      color: var(--muted);
      line-height: 1.5;
    }

    .image-dialog {
      width: auto;
      max-width: min(760px, calc(100% - 28px));
      max-height: calc(100dvh - 28px);
      overflow: hidden;
      background:
        linear-gradient(145deg, rgba(255, 255, 255, 0.18), transparent 28%),
        color-mix(in srgb, var(--panel) 76%, rgba(31, 27, 25, 0.48));
      border-color: color-mix(in srgb, var(--line) 72%, var(--shine));
      backdrop-filter: blur(24px) saturate(1.2);
    }

    .image-dialog .dove-art {
      width: auto;
      height: auto;
      margin: 0 auto;
      max-height: calc(100dvh - 190px);
      max-width: 100%;
      min-height: 0;
      object-fit: contain;
      aspect-ratio: auto;
      border-radius: 8px;
      background: #2f2927;
      box-shadow: 0 18px 55px rgba(0, 0, 0, 0.28);
    }

    .image-dialog .dialog-body {
      max-height: calc(100dvh - 92px);
      overflow: hidden;
      place-items: center;
      padding: 16px;
      gap: 14px;
    }

    .image-caption {
      width: 100%;
      max-width: 680px;
      display: flex;
      align-items: baseline;
      justify-content: center;
      gap: 10px;
      flex-wrap: wrap;
      font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
      font-size: clamp(18px, 2vw, 26px);
      font-weight: 650;
      font-style: italic;
      text-align: center;
      color: var(--ink);
      letter-spacing: 0;
      line-height: 1.18;
      padding: 4px 10px 2px;
    }

    .image-credit {
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: clamp(12px, 1.3vw, 14px);
      font-style: normal;
      font-weight: 760;
      color: var(--accent-strong);
      white-space: nowrap;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .auth {
      position: fixed;
      inset: 0;
      display: grid;
      place-items: center;
      padding: 24px;
      z-index: 20;
      pointer-events: auto;
      background:
        radial-gradient(circle at 18% 14%, rgba(98, 199, 157, 0.22), transparent 34%),
        radial-gradient(circle at 78% 76%, rgba(36, 116, 91, 0.16), transparent 32%),
        linear-gradient(135deg, var(--bg), var(--hero));
      transition: transform 700ms cubic-bezier(.2, .8, .2, 1), opacity 520ms ease;
    }
    body:not(.locked) .auth {
      pointer-events: none;
      opacity: 0;
      transform: translateY(-100%);
    }
    .auth.opening {
      transform: translateY(-100%);
      opacity: 0;
    }

    .auth .brand-mark {
      width: 84px;
      height: 84px;
    }

    .auth .brand-mark svg {
      width: 60px;
      height: 60px;
    }

    .auth-box {
      width: min(680px, 100%);
      min-height: min(700px, calc(100vh - 48px));
      background:
        radial-gradient(circle at 30% 0%, color-mix(in srgb, var(--soft) 70%, transparent), transparent 38%),
        linear-gradient(180deg, color-mix(in srgb, var(--panel) 94%, transparent), var(--panel));
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: clamp(24px, 5vw, 56px);
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 22px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }

    .auth-box::before {
      content: "";
      position: absolute;
      inset: 0;
      border: 1px solid rgba(255, 255, 255, 0.42);
      border-radius: inherit;
      pointer-events: none;
    }

    .auth-title {
      margin: 0;
      width: 100%;
      font-size: clamp(44px, 8vw, 86px);
      line-height: 1.08;
      font-weight: 900;
      color: var(--hero-ink);
      text-wrap: balance;
      overflow-wrap: anywhere;
    }

    .auth-subtitle {
      max-width: 460px;
      font-size: 16px;
    }

    .pin-panel {
      width: min(360px, 100%);
      display: grid;
      gap: 10px;
      margin-top: 8px;
    }

    .pin-field-wrapper {
      display: grid;
      gap: 10px;
      width: 100%;
      transition: opacity 200ms ease;
    }

    .pin-field-wrapper.hidden {
      display: none;
    }

    .pin-panel input {
      min-height: 52px;
      text-align: center;
      font-size: 22px;
      letter-spacing: 8px;
      font-weight: 800;
    }

    .pin-panel input::placeholder {
      font-size: 15px;
      letter-spacing: 0;
      font-weight: 700;
      color: var(--muted);
    }

    .trust-row {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }

    .trust-row input {
      width: auto;
      min-height: auto;
    }

    .pin-panel button {
      min-height: 50px;
    }

    .security-toolbox {
      gap: 14px;
      min-height: auto;
    }

    .security-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      gap: 8px;
    }

    .security-badge {
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--line) 70%, transparent);
      color: var(--muted);
      border: 1px solid var(--line);
    }

    .security-badge.active {
      background: color-mix(in srgb, var(--ok) 22%, transparent);
      color: var(--accent-strong);
      border-color: color-mix(in srgb, var(--ok) 50%, transparent);
    }

    .security-settings-box {
      width: 100%;
      display: grid;
      gap: 12px;
      background: color-mix(in srgb, var(--panel) 60%, transparent);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
    }

    .security-toggle-row {
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      font-weight: 700;
      font-size: 14px;
      user-select: none;
    }

    .security-toggle-row input {
      display: none;
    }

    .toggle-switch {
      width: 42px;
      height: 24px;
      background: var(--line);
      border-radius: 12px;
      position: relative;
      transition: background 200ms ease;
      flex-shrink: 0;
    }

    .toggle-switch::after {
      content: "";
      position: absolute;
      top: 2px;
      left: 2px;
      width: 20px;
      height: 20px;
      background: #ffffff;
      border-radius: 50%;
      transition: transform 200ms cubic-bezier(.2, .8, .2, 1);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    }

    .security-toggle-row input:checked + .toggle-switch {
      background: var(--accent);
    }

    .security-toggle-row input:checked + .toggle-switch::after {
      transform: translateX(18px);
    }

    .security-pin-form {
      display: grid;
      gap: 12px;
      padding-top: 10px;
      border-top: 1px dashed var(--line);
    }

    .pin-input-group {
      display: flex;
      gap: 8px;
      width: 100%;
      align-items: stretch;
    }

    .pin-input-group input {
      flex: 1 1 auto !important;
      min-width: 0 !important;
      width: 100% !important;
      min-height: 40px !important;
      height: 40px !important;
    }

    .pin-toggle-btn {
      flex: 0 0 74px !important;
      width: 74px !important;
      min-width: 74px !important;
      max-width: 74px !important;
      min-height: 40px !important;
      height: 40px !important;
      margin: 0 !important;
      padding-inline: 8px !important;
      font-size: 13px;
      font-weight: 600;
    }

    .security-pin-form button#save-security-btn {
      width: 100%;
      min-height: 40px;
      height: 40px;
      margin-top: 4px;
    }

    .security-bottom-actions {
      width: 100%;
      margin-top: auto;
      padding-top: 8px;
      display: flex;
      gap: 8px;
    }

    .security-bottom-actions button {
      width: 100%;
      min-height: 40px;
      height: 40px;
      margin-top: 0;
    }

    .toast {
      position: fixed;
      left: 50%;
      bottom: 22px;
      transform: translateX(-50%) translateY(14px);
      background: #101828;
      color: #ffffff;
      border-radius: 8px;
      padding: 11px 14px;
      opacity: 0;
      pointer-events: none;
      transition: opacity 160ms ease, transform 160ms ease;
      max-width: min(560px, calc(100vw - 28px));
      text-align: center;
      box-shadow: var(--shadow);
      z-index: 30;
    }
    .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

    @media (max-width: 920px) {
      .app-shell {
        width: calc(100% - 24px);
        max-width: 720px;
        padding-top: 18px;
      }
      .topbar, .grid, .tools { grid-template-columns: 1fr; }
      .smart-grid,
      .status {
        display: none;
      }
      body:not(.locked) .app-shell::before {
        right: -120px;
        top: 430px;
        width: 280px;
        height: 520px;
      }
      .brand-panel { min-height: auto; }
      .tabs {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 10px 12px;
      }
      .tabs-nav {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
        width: 100%;
      }
      .tabs-nav .tab {
        width: 100%;
        min-width: 0;
        text-align: center;
      }
      .search-box {
        width: 100%;
        min-width: 0;
        order: initial;
        flex-basis: auto;
      }
      .tabs-actions {
        display: flex;
        flex-direction: column;
        gap: 10px;
        width: 100%;
        margin-left: 0;
      }
      .support-btn {
        width: 100%;
        min-width: 0;
        min-height: 40px;
        height: 40px;
        padding: 0 14px;
        font-size: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      .theme-toggle {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: 0;
        font-size: 14px;
        font-weight: 700;
        padding: 2px 2px;
      }
      .status-row { grid-template-columns: 1fr auto; }
      .status-row .label { grid-column: 1 / -1; }
      .grid > .panel {
        height: auto;
        min-height: 260px;
      }
      #files-view .files-panel,
      #clipboard-view .grid > .panel:nth-child(2) {
        order: 1;
        height: min(62dvh, 520px);
        min-height: 320px;
        overscroll-behavior: auto;
        overscroll-behavior-y: auto;
        -webkit-overflow-scrolling: touch;
      }
      .grid .list,
      .files-panel,
      .dropzone,
      #clipboard-view .panel-body,
      .activity-list {
        overscroll-behavior: auto;
        overscroll-behavior-y: auto;
        -webkit-overflow-scrolling: touch;
      }
      .files-panel .panel-head {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
        padding: 14px 16px;
      }
      .files-panel .panel-title-wrap {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
      }
      .files-panel .panel-actions {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        width: 100%;
        margin-left: 0;
      }
      .files-panel .panel-actions button,
      .files-panel .panel-actions .button {
        width: 100%;
        max-width: none;
        min-height: 38px;
        height: 38px;
        font-size: 13px;
        padding: 0 8px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      #files-view .dropzone,
      #clipboard-view .grid > .panel:first-child {
        order: 2;
      }
      .grid > .panel.dove-card {
        order: 3;
        height: min(34dvh, 240px);
        min-height: 170px;
      }
      .actions { justify-content: flex-start; }
      .inline-form { grid-template-columns: 1fr; }
      .image-dialog .dove-art { max-height: calc(100dvh - 190px); }
      button, .button { min-height: 40px; }
    }

    @media (max-width: 640px) {
      .app-shell {
        width: calc(100% - 16px);
        max-width: 560px;
        padding-top: 12px;
      }
      .topbar {
        gap: 8px;
        margin-bottom: 8px;
      }
      .brand-panel {
        min-height: auto;
        grid-template-columns: auto minmax(0, 1fr);
        justify-items: stretch;
        gap: 12px;
        padding: 12px;
      }
      .brand-mark { width: 44px; height: 44px; }
      .brand-mark svg { width: 32px; height: 32px; }
      .brand-panel h1 {
        font-size: 24px;
        line-height: 1.05;
      }
      .brand-panel p,
      .status {
        display: none;
      }
      .tabs {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 10px 12px;
        position: sticky;
        top: 0;
        z-index: 12;
      }
      .tabs-nav {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
        width: 100%;
      }
      .tabs-nav .tab {
        width: 100%;
        min-width: 0;
        padding-inline: 4px;
        height: 38px;
        min-height: 38px;
        font-size: 13.5px;
        text-align: center;
      }
      .search-box {
        width: 100%;
        min-width: 0;
        margin: 0;
        height: 40px;
        min-height: 40px;
        order: initial;
      }
      .tabs-actions {
        display: flex;
        flex-direction: column;
        gap: 10px;
        width: 100%;
        margin: 0;
        padding-top: 2px;
      }
      .support-btn {
        width: 100%;
        min-width: 0;
        min-height: 40px;
        height: 40px;
        padding: 0 14px;
        font-size: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      .theme-toggle {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: 0;
        font-size: 14px;
        font-weight: 700;
        padding: 2px 2px;
      }
      .smart-grid {
        display: none;
      }
      .metric {
        min-height: 78px;
        padding: 12px;
      }
      .metric strong {
        font-size: 18px;
      }
      .metric.has-action {
        padding: 12px;
      }
      .metric-action {
        position: static;
        justify-self: start;
        min-height: 32px;
        padding-inline: 9px;
        font-size: 12px;
      }
      .status-row {
        grid-template-columns: 1fr;
      }
      .status-row .url {
        white-space: normal;
        word-break: break-all;
      }
      .status-row button {
        justify-self: start;
      }
      .panel-head {
        align-items: flex-start;
        gap: 12px;
      }
      .panel-actions {
        width: 100%;
        justify-content: flex-start;
        overflow-x: visible;
      }
      .files-panel .panel-head {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
        padding: 14px 16px;
      }
      .files-panel .panel-title-wrap {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
      }
      .files-panel .panel-actions {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        width: 100%;
        margin-left: 0;
      }
      .files-panel .panel-actions button,
      .files-panel .panel-actions .button {
        width: 100%;
        max-width: none;
        min-height: 38px;
        height: 38px;
        font-size: 13px;
        padding: 0 8px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      .file-row .actions {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        width: 100%;
        overflow-x: visible;
        padding-top: 12px;
        margin-top: 6px;
        border-top: 1px solid var(--line);
      }
      .file-row .actions button,
      .file-row .actions .button,
      .file-row .actions a.button {
        width: 100%;
        min-width: 0;
        height: 38px;
        min-height: 38px;
        padding: 0 8px;
        font-size: 13px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      .file-row .actions button:first-child:nth-last-child(5) {
        grid-column: 1 / -1;
      }
      #clipboard-view .panel-head {
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
        padding: 14px 16px;
      }
      #clipboard-view .panel-head h2 {
        margin: 0;
      }
      #clipboard-view .panel-head button,
      #clipboard-view .panel-actions {
        width: 100%;
        justify-self: stretch;
      }
      #clipboard-view .panel-head button {
        min-height: 38px;
        height: 38px;
      }
      .clip-row {
        padding-right: 18px;
      }
      .clip-row .actions {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        width: 100%;
        overflow-x: visible;
        padding-top: 10px;
        margin-top: 6px;
        border-top: 1px solid var(--line);
      }
      .clip-row .actions button {
        width: 100%;
        min-width: 0;
        height: 38px;
        min-height: 38px;
        padding: 0 8px;
        font-size: 13px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-sizing: border-box;
        margin: 0;
      }
      .grid > .panel.dove-card {
        height: 132px;
        min-height: 132px;
      }
      .dove-card-caption {
        font-size: 13px;
        line-height: 1.25;
      }
      .image-caption {
        font-size: 18px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        animation-duration: 0.001ms !important;
        scroll-behavior: auto !important;
        transition-duration: 0.001ms !important;
      }
    }
    .discovered-servers-panel {
      border-color: var(--accent);
      background: color-mix(in srgb, var(--panel) 94%, var(--accent));
      margin-bottom: 1.25rem;
    }
    .discovered-peers-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 12px;
      padding: 16px;
    }
    .discovered-peer-card {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 14px 16px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      transition: all 180ms ease;
    }
    .discovered-peer-card:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .discovered-peer-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .discovered-peer-name {
      font-weight: 700;
      font-size: 15px;
      color: var(--ink);
    }
    .discovered-peer-url {
      font-family: monospace;
      font-size: 13px;
      color: var(--muted);
      word-break: break-all;
    }
    .discovered-peer-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      color: var(--muted);
      margin-top: 4px;
    }
  </style>
</head>
<body class="locked">
  <main class="app-shell">
    <header class="topbar">
      <section class="brand-panel">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64">
            <path d="M16 39c10-4 18-12 22-25 5 7 7 15 4 23"></path>
            <path d="M18 44c12 4 28 0 38-10-5 13-18 22-34 20"></path>
            <path d="M31 28c-6 2-11 6-15 11"></path>
            <path d="M40 22c6 0 11 3 15 8"></path>
            <path d="M45 28h.01"></path>
            <path d="M20 48 9 55"></path>
          </svg>
        </span>
        <div>
          <h1>NavOS - Local Share</h1>
          <p>Files, clipboard, links, and device tools in one private LAN dashboard.</p>
        </div>
      </section>
      <section class="status" aria-label="Server access links">
        <div class="status-row">
          <span class="label">Share link</span>
          <span class="url" id="current-url"></span>
          <button class="secondary" id="copy-page" title="Copy share link">Copy</button>
        </div>
        <div class="status-row">
          <span class="label">Network</span>
          <span class="url" id="network-info">LAN &bull; HTTP &bull; Port 8000</span>
          <button class="secondary" id="refresh" title="Refresh network">Refresh</button>
        </div>
      </section>
    </header>

    <nav class="tabs" role="tablist" aria-label="Views">
      <div class="tabs-nav">
        <button class="secondary tab active" id="tab-files" type="button" role="tab" aria-controls="files-view" aria-selected="true" data-view="files-view">Files</button>
        <button class="secondary tab" id="tab-clipboard" type="button" role="tab" aria-controls="clipboard-view" aria-selected="false" data-view="clipboard-view">Clipboard</button>
        <button class="secondary tab" id="tab-tools" type="button" role="tab" aria-controls="tools-view" aria-selected="false" data-view="tools-view">Tools</button>
      </div>
      <label class="search-box">
        Search
        <input id="global-search" type="search" placeholder="Files, clipboard, links">
      </label>
      <div class="tabs-actions">
        <button class="secondary support-btn" id="support-btn" type="button" title="Support NavOS">
          <svg class="heart-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
          </svg>
          <span>Support</span>
        </button>
        <label class="theme-toggle">
          Dark mode
          <button class="switch" id="theme-toggle" type="button" role="switch" aria-checked="false" aria-label="Toggle dark mode"><span></span></button>
        </label>
      </div>
    </nav>

    <section class="smart-grid" aria-label="Dashboard summary">
      <section class="panel metric">
        <span class="meta">Storage</span>
        <strong id="metric-storage">--</strong>
      </section>
      <section class="panel metric has-action">
        <span class="meta">Latest upload</span>
        <strong id="metric-upload">None</strong>
        <button class="secondary metric-action" id="download-latest-upload" type="button">Download</button>
      </section>
      <section class="panel metric has-action">
        <span class="meta">Latest clipboard</span>
        <strong id="metric-clipboard">None</strong>
        <button class="secondary metric-action" id="copy-latest-clip">Copy text</button>
      </section>
      <section class="panel metric">
        <span class="meta">Recent devices</span>
        <strong id="metric-devices">0</strong>
      </section>
    </section>

    <section class="panel discovered-servers-panel" id="discovered-servers-panel" style="display:none;">
      <div class="panel-head">
        <div class="panel-title-wrap">
          <h2>Discovered LAN Servers</h2>
          <span class="meta" id="discovered-peers-count">0 servers</span>
        </div>
        <span class="security-badge active">Auto-Discovery Active</span>
      </div>
      <div class="discovered-peers-grid" id="discovered-peers-grid"></div>
    </section>

    <section class="view active" id="files-view" role="tabpanel" aria-labelledby="tab-files">
      <section class="grid">
        <section class="panel dropzone" id="dropzone">
          <input id="file-input" type="file" multiple>
          <input id="folder-input" type="file" webkitdirectory multiple>
          <div class="drop-inner">
            <span class="upload-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M12 3v12"></path><path d="m7 8 5-5 5 5"></path><path d="M5 21h14"></path></svg>
            </span>
            <div class="drop-text-block">
              <strong>Choose, drag, or paste files</strong><br>
              <span id="upload-note">Files stay on this computer.</span>
            </div>
            <div class="upload-controls">
              <div class="field upload-expiry-field">
                <label for="file-expiry">Auto-delete uploads</label>
                <select id="file-expiry">
                  <option value="0">Never</option>
                  <option value="600">After 10 minutes</option>
                  <option value="3600">After 1 hour</option>
                  <option value="86400">After 24 hours</option>
                </select>
              </div>
              <div class="upload-buttons-row">
                <button type="button" id="choose-button">Select files</button>
                <button type="button" id="choose-folder-button" class="secondary">Select folder</button>
              </div>
            </div>
            <div class="progress" id="progress">
              <div class="progress-track"><span></span></div>
              <span id="progress-text">Waiting</span>
              <div class="progress-actions">
                <button class="secondary" type="button" id="pause-upload">Pause</button>
                <button class="secondary" type="button" id="cancel-upload">Cancel</button>
              </div>
              <div id="sha256-display" class="sha256-badge" style="display:none">
                <span class="sha256-icon">✓</span>
                <span id="sha256-text"></span>
              </div>
            </div>
            <div class="queue" id="upload-queue"></div>
          </div>
        </section>


        <section class="panel files-panel">
          <div class="panel-head">
            <div class="panel-title-wrap">
              <h2>Shared files</h2>
              <span class="meta" id="file-count">Loading...</span>
            </div>
            <div class="panel-actions">
              <button class="button" id="download-selected-files" type="button" style="display:none">Download (<span id="selected-count">0</span>)</button>
              <button class="danger" id="delete-selected-files" type="button" style="display:none">Delete (<span id="delete-selected-count">0</span>)</button>
              <button class="secondary" id="download-all-files" type="button">Download all</button>
              <button class="danger" id="delete-all-files" type="button">Delete all</button>
            </div>
          </div>
          <div class="selection-bar" id="selection-bar" style="display:none">
            <div class="selection-bar-left">
              <label class="select-all-label">
                <input type="checkbox" id="select-all-checkbox" class="file-select-checkbox"> Select all
              </label>
              <button class="secondary unselect-all-btn" id="unselect-all-btn" type="button">Unselect all</button>
            </div>
            <span class="meta" id="selection-status">0 selected</span>
          </div>
          <div class="list" id="file-list"></div>
        </section>

        <section class="panel dove-card artwork-card" data-art-src="/assets/Picture1.jpg" role="button" tabindex="0" aria-label="Open dove artwork">
          <img class="dove-art" src="/assets/Picture1.jpg" alt="Dove dashboard artwork">
          <span class="dove-card-caption">Beautiful, majestic, but next level of unemployment.</span>
        </section>
      </section>
    </section>

    <section class="view" id="clipboard-view" role="tabpanel" aria-labelledby="tab-clipboard">
      <section class="grid">
        <section class="panel">
          <div class="panel-head">
            <h2>Fast clipboard</h2>
            <button class="secondary" id="read-system-clipboard">Paste from device</button>
          </div>
          <div class="panel-body clipboard-compose">
            <div class="field">
              <label for="clipboard-input">Text, link, command, note, OTP, JSON</label>
              <textarea id="clipboard-input" placeholder="Paste or type here"></textarea>
            </div>
            <div class="inline-form clipboard-actions-form">
              <div class="field">
                <label for="clipboard-expiry">Auto-delete text</label>
                <select id="clipboard-expiry">
                  <option value="0" selected>Never</option>
                  <option value="600">After 10 minutes</option>
                  <option value="3600">After 1 hour</option>
                  <option value="86400">After 24 hours</option>
                </select>
              </div>
              <button id="save-clipboard">Save clipboard</button>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>Recent clipboard</h2>
            <div class="panel-actions">
              <span class="meta" id="clip-count">Loading...</span>
              <button class="secondary" id="copy-inbox-latest" type="button">Copy text</button>
              <button class="secondary" id="paste-save-clipboard" type="button">Paste & save</button>
              <button class="danger" id="clear-clipboard" type="button">Clear</button>
            </div>
          </div>
          <div class="list" id="clip-list"></div>
        </section>

        <section class="panel dove-card artwork-card" data-art-src="/assets/Picture1_rev.jpg" role="button" tabindex="0" aria-label="Open dove artwork">
          <img class="dove-art" src="/assets/Picture1_rev.jpg" alt="Dove dashboard artwork">
          <span class="dove-card-caption">Beautiful, majestic, but next level of unemployment.</span>
        </section>
      </section>
    </section>

    <section class="view" id="tools-view" role="tabpanel" aria-labelledby="tab-tools">
      <section class="panel">
        <div class="panel-head">
          <h2>Quick tools</h2>
          <span class="meta">Open from phone, copy addresses, or share links</span>
        </div>
        <div class="panel-body tools">
          <div class="tool-box activity-toolbox">
            <h3>Live Activity</h3>
            <div class="activity-list" id="activity-list" role="log" aria-live="polite">
              <span class="activity-empty">No recent activity</span>
            </div>
          </div>
          <div class="tool-box">
            <h3>Phone QR</h3>
            <img class="qr" id="qr-image" alt="QR code for LAN link">
            <span class="meta">Scan to open this page on another device. If it does not scan, copy the LAN link.</span>
          </div>
          <div class="tool-box quick-link-toolbox">
            <h3>Quick link</h3>
            <span class="meta">Direct connection link for devices on your network:</span>
            <code id="lan-url"></code>
            <button class="secondary" id="copy-lan">Copy LAN link</button>
          </div>
          <div class="tool-box security-toolbox">
            <div class="security-card-header">
              <h3>Security &amp; Lock</h3>
              <span class="security-badge" id="security-badge">Disabled</span>
            </div>
            <p id="security-note">Checking settings...</p>
            <div class="security-settings-box">
              <label class="security-toggle-row">
                <input type="checkbox" id="security-toggle">
                <span class="toggle-switch"></span>
                <span class="toggle-label-text" id="toggle-label-text">Require PIN to open dashboard</span>
              </label>

              <div class="security-pin-form" id="security-pin-form">
                <div class="field" id="new-pin-field">
                  <label for="new-pin-input" id="new-pin-label">Set PIN / Password</label>
                  <div class="pin-input-group">
                    <input type="password" id="new-pin-input" placeholder="e.g. 1234" maxlength="32" autocomplete="new-password">
                    <button type="button" class="secondary pin-toggle-btn" id="toggle-pin-visibility" title="Show or hide PIN">Show</button>
                  </div>
                </div>
                <div class="field" id="current-pin-field" style="display: none;">
                  <label for="current-pin-input">Current PIN (to authorize change)</label>
                  <div class="pin-input-group">
                    <input type="password" id="current-pin-input" placeholder="Current PIN" maxlength="32" autocomplete="current-password">
                    <button type="button" class="secondary pin-toggle-btn" id="toggle-current-pin-visibility" title="Show or hide Current PIN">Show</button>
                  </div>
                </div>
                <button type="button" class="primary" id="save-security-btn">Save PIN Settings</button>
              </div>
            </div>
            <div class="security-bottom-actions">
              <button class="secondary" id="lock-button">Lock Dashboard</button>
            </div>
          </div>
          <div class="tool-box">
            <h3>Service check</h3>
            <div class="service-list" id="service-list">
              <div class="service-row"><span class="dot"></span><span>Server info</span><strong>Checking</strong></div>
              <div class="service-row"><span class="dot"></span><span>File service</span><strong>Checking</strong></div>
              <div class="service-row"><span class="dot"></span><span>Clipboard service</span><strong>Checking</strong></div>
              <div class="service-row"><span class="dot"></span><span>Authentication</span><strong>Checking</strong></div>
            </div>
            <button class="secondary" id="check-services">Check now</button>
          </div>
          <div class="tool-box diagnostics-toolbox">
            <div class="security-card-header">
              <h3>Network Diagnostics</h3>
              <span class="security-badge" id="net-diag-badge">Active</span>
            </div>
            <div class="service-list" id="net-diag-list">
              <div class="service-row"><span class="dot ok"></span><span>Server Status</span><strong id="diag-server-status">Running</strong></div>
              <div class="service-row"><span class="dot ok"></span><span>Protocol &amp; Port</span><strong id="diag-protocol-port">HTTP : 8000</strong></div>
              <div class="service-row"><span class="dot ok"></span><span>LAN Interface</span><strong id="diag-lan-ip">Detecting...</strong></div>
              <div class="service-row"><span class="dot ok"></span><span>LAN Discovery</span><strong id="diag-discovery-status">Active (52002)</strong></div>
            </div>
            <div class="discovered-peers-box" id="discovered-peers-box" style="display:none">
              <span class="meta">Discovered Pura servers on LAN:</span>
              <div class="peers-list" id="peers-list"></div>
            </div>
            <button class="secondary" id="run-diagnostics-btn" type="button">Run diagnostics</button>
          </div>
          <div class="tool-box device-toolbox">
            <h3>Recent devices</h3>
            <div class="device-list" id="device-list">
              <div class="service-row"><span class="dot"></span><span>No devices yet</span><strong>--</strong></div>
            </div>
          </div>
        </div>
      </section>
    </section>
  </main>

  <dialog id="preview-dialog" aria-labelledby="preview-title">
    <div class="panel-head">
      <h2 id="preview-title">Preview</h2>
      <button class="secondary" id="close-preview">Close</button>
    </div>
    <div class="dialog-body" id="preview-body"></div>
  </dialog>

  <dialog class="image-dialog" id="dove-dialog" aria-labelledby="dove-title">
    <div class="panel-head">
      <h2 id="dove-title">Dove artwork</h2>
      <button class="secondary" id="close-dove">Close</button>
    </div>
    <div class="dialog-body">
      <img class="dove-art" id="modal-artwork" src="/assets/Picture1.jpg" alt="Dove dashboard artwork">
      <div class="image-caption">Beautiful, majestic, but next level of unemployment.<span class="image-credit">-Navin</span></div>
    </div>
  </dialog>

  <dialog class="support-dialog" id="support-dialog" aria-labelledby="support-title">
    <div class="floating-hearts-layer" id="floating-hearts-layer"></div>
    <div class="panel-head">
      <h2 id="support-title">Support this project</h2>
      <button class="secondary" id="close-support">Close</button>
    </div>
    <div class="dialog-body">
      <div class="support-card">
        <div class="support-header">
          <div class="support-heart-badge" id="support-heart-badge" role="button" tabindex="0" title="Click to send love!">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
          </div>
          <p>Thanks for using this project! If you find it useful and want to support its development and future projects, every bit of support helps.</p>
        </div>

        <div class="payment-grid">
          <a class="payment-link" href="https://razorpay.me/@navin007" target="_blank" rel="noopener noreferrer">
            <div class="payment-info">
              <span class="payment-icon" aria-hidden="true">🇮🇳</span>
              <div class="payment-text">
                <span class="payment-title">Razorpay</span>
                <span class="payment-subtitle">@navin007</span>
              </div>
            </div>
            <span class="payment-action">Pay ↗</span>
          </a>

          <a class="payment-link" href="https://paypal.me/Navin007143" target="_blank" rel="noopener noreferrer">
            <div class="payment-info">
              <span class="payment-icon" aria-hidden="true">🌎</span>
              <div class="payment-text">
                <span class="payment-title">PayPal</span>
                <span class="payment-subtitle">@Navin007143</span>
              </div>
            </div>
            <span class="payment-action">Pay ↗</span>
          </a>

          <button class="payment-link payment-btn" id="upi-qr-btn" type="button" title="View Google Pay UPI QR">
            <div class="payment-info">
              <span class="payment-icon" aria-hidden="true">🇮🇳</span>
              <div class="payment-text">
                <span class="payment-title">UPI QR</span>
                <span class="payment-subtitle">Google Pay QR</span>
              </div>
            </div>
            <span class="payment-action">View QR ↗</span>
          </button>

          <a class="payment-link" href="https://github.com/sponsors/Xx7Navin7xX" target="_blank" rel="noopener noreferrer">
            <div class="payment-info">
              <span class="payment-icon" aria-hidden="true">💗</span>
              <div class="payment-text">
                <span class="payment-title">Sponsor on GitHub</span>
                <span class="payment-subtitle">@Xx7Navin7xX</span>
              </div>
            </div>
            <span class="payment-action">Sponsor ↗</span>
          </a>

          <a class="payment-link" href="https://ko-fi.com/navin007" target="_blank" rel="noopener noreferrer">
            <div class="payment-info">
              <span class="payment-icon" aria-hidden="true">☕</span>
              <div class="payment-text">
                <span class="payment-title">Support on Ko-fi</span>
                <span class="payment-subtitle">@navin007</span>
              </div>
            </div>
            <span class="payment-action">Support ↗</span>
          </a>
        </div>

        <div class="upi-box">
          <div>
            <span class="upi-id-label">UPI ID: </span>
            <code class="upi-id-code" id="upi-id-text">navinbalaji004@okhdfcbank</code>
          </div>
          <button class="secondary upi-copy-btn" id="copy-upi-btn" type="button">Copy ID</button>
        </div>
      </div>
    </div>
  </dialog>

  <dialog class="upi-qr-dialog" id="upi-qr-dialog" aria-labelledby="upi-qr-title">
    <div class="panel-head">
      <h2 id="upi-qr-title">Google Pay / UPI QR</h2>
      <button class="secondary" id="close-upi-qr">Close</button>
    </div>
    <div class="dialog-body">
      <div class="upi-qr-card">
        <img class="upi-qr-image" src="/assets/GooglePay_QR.png" alt="Google Pay UPI QR Code">
        <p class="upi-qr-note">Scan with Google Pay, PhonePe, Paytm, or any UPI app to pay</p>
        <div class="upi-box" style="width: 100%;">
          <div>
            <span class="upi-id-label">UPI ID: </span>
            <code class="upi-id-code">navinbalaji004@okhdfcbank</code>
          </div>
          <button class="secondary upi-copy-btn" id="copy-upi-modal-btn" type="button">Copy ID</button>
        </div>
      </div>
    </div>
  </dialog>

  <section class="auth" id="auth">
    <form class="auth-box" id="auth-form">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 64 64">
          <path d="M16 39c10-4 18-12 22-25 5 7 7 15 4 23"></path>
          <path d="M18 44c12 4 28 0 38-10-5 13-18 22-34 20"></path>
          <path d="M31 28c-6 2-11 6-15 11"></path>
          <path d="M40 22c6 0 11 3 15 8"></path>
          <path d="M45 28h.01"></path>
          <path d="M20 48 9 55"></path>
        </svg>
      </span>
      <h2 class="auth-title" lang="ta">புரா சேவைகள்</h2>
      <p class="auth-subtitle" id="auth-subtitle">Files, clipboard transfer, and device tools on your private network.</p>
      <div class="pin-panel" id="pin-panel">
        <div class="pin-field-wrapper" id="pin-field-wrapper">
          <input id="pin-input" type="password" inputmode="numeric" autocomplete="current-password" placeholder="PIN" aria-label="PIN">
          <label class="trust-row" id="trust-row">
            <input id="trust-device" type="checkbox">
            Trust this device for 7 days
          </label>
        </div>
        <button id="auth-submit-btn" type="submit">Open dashboard</button>
      </div>
    </form>
  </section>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
    /* qrcode-generator v1.4.4 — embedded for offline use */
    /**
 * Minified by jsDelivr using Terser v5.37.0.
 * Original file: /npm/qrcode-generator@1.4.4/qrcode.js
 *
 * Do NOT use SRI with dynamically generated files! More information: https://www.jsdelivr.com/using-sri-with-dynamic-files
 */
var qrcode=function(){var t=function(t,r){var e=t,n=g[r],o=null,i=0,a=null,u=[],f={},c=function(t,r){o=function(t){for(var r=new Array(t),e=0;e<t;e+=1){r[e]=new Array(t);for(var n=0;n<t;n+=1)r[e][n]=null}return r}(i=4*e+17),l(0,0),l(i-7,0),l(0,i-7),s(),h(),d(t,r),e>=7&&v(t),null==a&&(a=p(e,n,u)),w(a,r)},l=function(t,r){for(var e=-1;e<=7;e+=1)if(!(t+e<=-1||i<=t+e))for(var n=-1;n<=7;n+=1)r+n<=-1||i<=r+n||(o[t+e][r+n]=0<=e&&e<=6&&(0==n||6==n)||0<=n&&n<=6&&(0==e||6==e)||2<=e&&e<=4&&2<=n&&n<=4)},h=function(){for(var t=8;t<i-8;t+=1)null==o[t][6]&&(o[t][6]=t%2==0);for(var r=8;r<i-8;r+=1)null==o[6][r]&&(o[6][r]=r%2==0)},s=function(){for(var t=B.getPatternPosition(e),r=0;r<t.length;r+=1)for(var n=0;n<t.length;n+=1){var i=t[r],a=t[n];if(null==o[i][a])for(var u=-2;u<=2;u+=1)for(var f=-2;f<=2;f+=1)o[i+u][a+f]=-2==u||2==u||-2==f||2==f||0==u&&0==f}},v=function(t){for(var r=B.getBCHTypeNumber(e),n=0;n<18;n+=1){var a=!t&&1==(r>>n&1);o[Math.floor(n/3)][n%3+i-8-3]=a}for(n=0;n<18;n+=1){a=!t&&1==(r>>n&1);o[n%3+i-8-3][Math.floor(n/3)]=a}},d=function(t,r){for(var e=n<<3|r,a=B.getBCHTypeInfo(e),u=0;u<15;u+=1){var f=!t&&1==(a>>u&1);u<6?o[u][8]=f:u<8?o[u+1][8]=f:o[i-15+u][8]=f}for(u=0;u<15;u+=1){f=!t&&1==(a>>u&1);u<8?o[8][i-u-1]=f:u<9?o[8][15-u-1+1]=f:o[8][15-u-1]=f}o[i-8][8]=!t},w=function(t,r){for(var e=-1,n=i-1,a=7,u=0,f=B.getMaskFunction(r),c=i-1;c>0;c-=2)for(6==c&&(c-=1);;){for(var g=0;g<2;g+=1)if(null==o[n][c-g]){var l=!1;u<t.length&&(l=1==(t[u]>>>a&1)),f(n,c-g)&&(l=!l),o[n][c-g]=l,-1==(a-=1)&&(u+=1,a=7)}if((n+=e)<0||i<=n){n-=e,e=-e;break}}},p=function(t,r,e){for(var n=A.getRSBlocks(t,r),o=b(),i=0;i<e.length;i+=1){var a=e[i];o.put(a.getMode(),4),o.put(a.getLength(),B.getLengthInBits(a.getMode(),t)),a.write(o)}var u=0;for(i=0;i<n.length;i+=1)u+=n[i].dataCount;if(o.getLengthInBits()>8*u)throw"code length overflow. ("+o.getLengthInBits()+">"+8*u+")";for(o.getLengthInBits()+4<=8*u&&o.put(0,4);o.getLengthInBits()%8!=0;)o.putBit(!1);for(;!(o.getLengthInBits()>=8*u||(o.put(236,8),o.getLengthInBits()>=8*u));)o.put(17,8);return function(t,r){for(var e=0,n=0,o=0,i=new Array(r.length),a=new Array(r.length),u=0;u<r.length;u+=1){var f=r[u].dataCount,c=r[u].totalCount-f;n=Math.max(n,f),o=Math.max(o,c),i[u]=new Array(f);for(var g=0;g<i[u].length;g+=1)i[u][g]=255&t.getBuffer()[g+e];e+=f;var l=B.getErrorCorrectPolynomial(c),h=k(i[u],l.getLength()-1).mod(l);for(a[u]=new Array(l.getLength()-1),g=0;g<a[u].length;g+=1){var s=g+h.getLength()-a[u].length;a[u][g]=s>=0?h.getAt(s):0}}var v=0;for(g=0;g<r.length;g+=1)v+=r[g].totalCount;var d=new Array(v),w=0;for(g=0;g<n;g+=1)for(u=0;u<r.length;u+=1)g<i[u].length&&(d[w]=i[u][g],w+=1);for(g=0;g<o;g+=1)for(u=0;u<r.length;u+=1)g<a[u].length&&(d[w]=a[u][g],w+=1);return d}(o,n)};f.addData=function(t,r){var e=null;switch(r=r||"Byte"){case"Numeric":e=M(t);break;case"Alphanumeric":e=x(t);break;case"Byte":e=m(t);break;case"Kanji":e=L(t);break;default:throw"mode:"+r}u.push(e),a=null},f.isDark=function(t,r){if(t<0||i<=t||r<0||i<=r)throw t+","+r;return o[t][r]},f.getModuleCount=function(){return i},f.make=function(){if(e<1){for(var t=1;t<40;t++){for(var r=A.getRSBlocks(t,n),o=b(),i=0;i<u.length;i++){var a=u[i];o.put(a.getMode(),4),o.put(a.getLength(),B.getLengthInBits(a.getMode(),t)),a.write(o)}var g=0;for(i=0;i<r.length;i++)g+=r[i].dataCount;if(o.getLengthInBits()<=8*g)break}e=t}c(!1,function(){for(var t=0,r=0,e=0;e<8;e+=1){c(!0,e);var n=B.getLostPoint(f);(0==e||t>n)&&(t=n,r=e)}return r}())},f.createTableTag=function(t,r){t=t||2;var e="";e+='<table style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: "+(r=void 0===r?4*t:r)+"px;",e+='">',e+="<tbody>";for(var n=0;n<f.getModuleCount();n+=1){e+="<tr>";for(var o=0;o<f.getModuleCount();o+=1)e+='<td style="',e+=" border-width: 0px; border-style: none;",e+=" border-collapse: collapse;",e+=" padding: 0px; margin: 0px;",e+=" width: "+t+"px;",e+=" height: "+t+"px;",e+=" background-color: ",e+=f.isDark(n,o)?"#000000":"#ffffff",e+=";",e+='"/>';e+="</tr>"}return e+="</tbody>",e+="</table>"},f.createSvgTag=function(t,r,e,n){var o={};"object"==typeof arguments[0]&&(t=(o=arguments[0]).cellSize,r=o.margin,e=o.alt,n=o.title),t=t||2,r=void 0===r?4*t:r,(e="string"==typeof e?{text:e}:e||{}).text=e.text||null,e.id=e.text?e.id||"qrcode-description":null,(n="string"==typeof n?{text:n}:n||{}).text=n.text||null,n.id=n.text?n.id||"qrcode-title":null;var i,a,u,c,g=f.getModuleCount()*t+2*r,l="";for(c="l"+t+",0 0,"+t+" -"+t+",0 0,-"+t+"z ",l+='<svg version="1.1" xmlns="http://www.w3.org/2000/svg"',l+=o.scalable?"":' width="'+g+'px" height="'+g+'px"',l+=' viewBox="0 0 '+g+" "+g+'" ',l+=' preserveAspectRatio="xMinYMin meet"',l+=n.text||e.text?' role="img" aria-labelledby="'+y([n.id,e.id].join(" ").trim())+'"':"",l+=">",l+=n.text?'<title id="'+y(n.id)+'">'+y(n.text)+"</title>":"",l+=e.text?'<description id="'+y(e.id)+'">'+y(e.text)+"</description>":"",l+='<rect width="100%" height="100%" fill="white" cx="0" cy="0"/>',l+='<path d="',a=0;a<f.getModuleCount();a+=1)for(u=a*t+r,i=0;i<f.getModuleCount();i+=1)f.isDark(a,i)&&(l+="M"+(i*t+r)+","+u+c);return l+='" stroke="transparent" fill="black"/>',l+="</svg>"},f.createDataURL=function(t,r){t=t||2,r=void 0===r?4*t:r;var e=f.getModuleCount()*t+2*r,n=r,o=e-r;return I(e,e,(function(r,e){if(n<=r&&r<o&&n<=e&&e<o){var i=Math.floor((r-n)/t),a=Math.floor((e-n)/t);return f.isDark(a,i)?0:1}return 1}))},f.createImgTag=function(t,r,e){t=t||2,r=void 0===r?4*t:r;var n=f.getModuleCount()*t+2*r,o="";return o+="<img",o+=' src="',o+=f.createDataURL(t,r),o+='"',o+=' width="',o+=n,o+='"',o+=' height="',o+=n,o+='"',e&&(o+=' alt="',o+=y(e),o+='"'),o+="/>"};var y=function(t){for(var r="",e=0;e<t.length;e+=1){var n=t.charAt(e);switch(n){case"<":r+="&lt;";break;case">":r+="&gt;";break;case"&":r+="&amp;";break;case'"':r+="&quot;";break;default:r+=n}}return r};return f.createASCII=function(t,r){if((t=t||1)<2)return function(t){t=void 0===t?2:t;var r,e,n,o,i,a=1*f.getModuleCount()+2*t,u=t,c=a-t,g={"██":"█","█ ":"▀"," █":"▄","  ":" "},l={"██":"▀","█ ":"▀"," █":" ","  ":" "},h="";for(r=0;r<a;r+=2){for(n=Math.floor((r-u)/1),o=Math.floor((r+1-u)/1),e=0;e<a;e+=1)i="█",u<=e&&e<c&&u<=r&&r<c&&f.isDark(n,Math.floor((e-u)/1))&&(i=" "),u<=e&&e<c&&u<=r+1&&r+1<c&&f.isDark(o,Math.floor((e-u)/1))?i+=" ":i+="█",h+=t<1&&r+1>=c?l[i]:g[i];h+="\n"}return a%2&&t>0?h.substring(0,h.length-a-1)+Array(a+1).join("▀"):h.substring(0,h.length-1)}(r);t-=1,r=void 0===r?2*t:r;var e,n,o,i,a=f.getModuleCount()*t+2*r,u=r,c=a-r,g=Array(t+1).join("██"),l=Array(t+1).join("  "),h="",s="";for(e=0;e<a;e+=1){for(o=Math.floor((e-u)/t),s="",n=0;n<a;n+=1)i=1,u<=n&&n<c&&u<=e&&e<c&&f.isDark(o,Math.floor((n-u)/t))&&(i=0),s+=i?g:l;for(o=0;o<t;o+=1)h+=s+"\n"}return h.substring(0,h.length-1)},f.renderTo2dContext=function(t,r){r=r||2;for(var e=f.getModuleCount(),n=0;n<e;n++)for(var o=0;o<e;o++)t.fillStyle=f.isDark(n,o)?"black":"white",t.fillRect(n*r,o*r,r,r)},f};t.stringToBytes=(t.stringToBytesFuncs={default:function(t){for(var r=[],e=0;e<t.length;e+=1){var n=t.charCodeAt(e);r.push(255&n)}return r}}).default,t.createStringToBytes=function(t,r){var e=function(){for(var e=S(t),n=function(){var t=e.read();if(-1==t)throw"eof";return t},o=0,i={};;){var a=e.read();if(-1==a)break;var u=n(),f=n()<<8|n();i[String.fromCharCode(a<<8|u)]=f,o+=1}if(o!=r)throw o+" != "+r;return i}(),n="?".charCodeAt(0);return function(t){for(var r=[],o=0;o<t.length;o+=1){var i=t.charCodeAt(o);if(i<128)r.push(i);else{var a=e[t.charAt(o)];"number"==typeof a?(255&a)==a?r.push(a):(r.push(a>>>8),r.push(255&a)):r.push(n)}}return r}};var r,e,n,o,i,a=1,u=2,f=4,c=8,g={L:1,M:0,Q:3,H:2},l=0,h=1,s=2,v=3,d=4,w=5,p=6,y=7,B=(r=[[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],[6,26,46,66],[6,26,48,70],[6,26,50,74],[6,30,54,78],[6,30,56,82],[6,30,58,86],[6,34,62,90],[6,28,50,72,94],[6,26,50,74,98],[6,30,54,78,102],[6,28,54,80,106],[6,32,58,84,110],[6,30,58,86,114],[6,34,62,90,118],[6,26,50,74,98,122],[6,30,54,78,102,126],[6,26,52,78,104,130],[6,30,56,82,108,134],[6,34,60,86,112,138],[6,30,58,86,114,142],[6,34,62,90,118,146],[6,30,54,78,102,126,150],[6,24,50,76,102,128,154],[6,28,54,80,106,132,158],[6,32,58,84,110,136,162],[6,26,54,82,110,138,166],[6,30,58,86,114,142,170]],e=1335,n=7973,i=function(t){for(var r=0;0!=t;)r+=1,t>>>=1;return r},(o={}).getBCHTypeInfo=function(t){for(var r=t<<10;i(r)-i(e)>=0;)r^=e<<i(r)-i(e);return 21522^(t<<10|r)},o.getBCHTypeNumber=function(t){for(var r=t<<12;i(r)-i(n)>=0;)r^=n<<i(r)-i(n);return t<<12|r},o.getPatternPosition=function(t){return r[t-1]},o.getMaskFunction=function(t){switch(t){case l:return function(t,r){return(t+r)%2==0};case h:return function(t,r){return t%2==0};case s:return function(t,r){return r%3==0};case v:return function(t,r){return(t+r)%3==0};case d:return function(t,r){return(Math.floor(t/2)+Math.floor(r/3))%2==0};case w:return function(t,r){return t*r%2+t*r%3==0};case p:return function(t,r){return(t*r%2+t*r%3)%2==0};case y:return function(t,r){return(t*r%3+(t+r)%2)%2==0};default:throw"bad maskPattern:"+t}},o.getErrorCorrectPolynomial=function(t){for(var r=k([1],0),e=0;e<t;e+=1)r=r.multiply(k([1,C.gexp(e)],0));return r},o.getLengthInBits=function(t,r){if(1<=r&&r<10)switch(t){case a:return 10;case u:return 9;case f:case c:return 8;default:throw"mode:"+t}else if(r<27)switch(t){case a:return 12;case u:return 11;case f:return 16;case c:return 10;default:throw"mode:"+t}else{if(!(r<41))throw"type:"+r;switch(t){case a:return 14;case u:return 13;case f:return 16;case c:return 12;default:throw"mode:"+t}}},o.getLostPoint=function(t){for(var r=t.getModuleCount(),e=0,n=0;n<r;n+=1)for(var o=0;o<r;o+=1){for(var i=0,a=t.isDark(n,o),u=-1;u<=1;u+=1)if(!(n+u<0||r<=n+u))for(var f=-1;f<=1;f+=1)o+f<0||r<=o+f||0==u&&0==f||a==t.isDark(n+u,o+f)&&(i+=1);i>5&&(e+=3+i-5)}for(n=0;n<r-1;n+=1)for(o=0;o<r-1;o+=1){var c=0;t.isDark(n,o)&&(c+=1),t.isDark(n+1,o)&&(c+=1),t.isDark(n,o+1)&&(c+=1),t.isDark(n+1,o+1)&&(c+=1),0!=c&&4!=c||(e+=3)}for(n=0;n<r;n+=1)for(o=0;o<r-6;o+=1)t.isDark(n,o)&&!t.isDark(n,o+1)&&t.isDark(n,o+2)&&t.isDark(n,o+3)&&t.isDark(n,o+4)&&!t.isDark(n,o+5)&&t.isDark(n,o+6)&&(e+=40);for(o=0;o<r;o+=1)for(n=0;n<r-6;n+=1)t.isDark(n,o)&&!t.isDark(n+1,o)&&t.isDark(n+2,o)&&t.isDark(n+3,o)&&t.isDark(n+4,o)&&!t.isDark(n+5,o)&&t.isDark(n+6,o)&&(e+=40);var g=0;for(o=0;o<r;o+=1)for(n=0;n<r;n+=1)t.isDark(n,o)&&(g+=1);return e+=Math.abs(100*g/r/r-50)/5*10},o),C=function(){for(var t=new Array(256),r=new Array(256),e=0;e<8;e+=1)t[e]=1<<e;for(e=8;e<256;e+=1)t[e]=t[e-4]^t[e-5]^t[e-6]^t[e-8];for(e=0;e<255;e+=1)r[t[e]]=e;var n={glog:function(t){if(t<1)throw"glog("+t+")";return r[t]},gexp:function(r){for(;r<0;)r+=255;for(;r>=256;)r-=255;return t[r]}};return n}();function k(t,r){if(void 0===t.length)throw t.length+"/"+r;var e=function(){for(var e=0;e<t.length&&0==t[e];)e+=1;for(var n=new Array(t.length-e+r),o=0;o<t.length-e;o+=1)n[o]=t[o+e];return n}(),n={getAt:function(t){return e[t]},getLength:function(){return e.length},multiply:function(t){for(var r=new Array(n.getLength()+t.getLength()-1),e=0;e<n.getLength();e+=1)for(var o=0;o<t.getLength();o+=1)r[e+o]^=C.gexp(C.glog(n.getAt(e))+C.glog(t.getAt(o)));return k(r,0)},mod:function(t){if(n.getLength()-t.getLength()<0)return n;for(var r=C.glog(n.getAt(0))-C.glog(t.getAt(0)),e=new Array(n.getLength()),o=0;o<n.getLength();o+=1)e[o]=n.getAt(o);for(o=0;o<t.getLength();o+=1)e[o]^=C.gexp(C.glog(t.getAt(o))+r);return k(e,0).mod(t)}};return n}var A=function(){var t=[[1,26,19],[1,26,16],[1,26,13],[1,26,9],[1,44,34],[1,44,28],[1,44,22],[1,44,16],[1,70,55],[1,70,44],[2,35,17],[2,35,13],[1,100,80],[2,50,32],[2,50,24],[4,25,9],[1,134,108],[2,67,43],[2,33,15,2,34,16],[2,33,11,2,34,12],[2,86,68],[4,43,27],[4,43,19],[4,43,15],[2,98,78],[4,49,31],[2,32,14,4,33,15],[4,39,13,1,40,14],[2,121,97],[2,60,38,2,61,39],[4,40,18,2,41,19],[4,40,14,2,41,15],[2,146,116],[3,58,36,2,59,37],[4,36,16,4,37,17],[4,36,12,4,37,13],[2,86,68,2,87,69],[4,69,43,1,70,44],[6,43,19,2,44,20],[6,43,15,2,44,16],[4,101,81],[1,80,50,4,81,51],[4,50,22,4,51,23],[3,36,12,8,37,13],[2,116,92,2,117,93],[6,58,36,2,59,37],[4,46,20,6,47,21],[7,42,14,4,43,15],[4,133,107],[8,59,37,1,60,38],[8,44,20,4,45,21],[12,33,11,4,34,12],[3,145,115,1,146,116],[4,64,40,5,65,41],[11,36,16,5,37,17],[11,36,12,5,37,13],[5,109,87,1,110,88],[5,65,41,5,66,42],[5,54,24,7,55,25],[11,36,12,7,37,13],[5,122,98,1,123,99],[7,73,45,3,74,46],[15,43,19,2,44,20],[3,45,15,13,46,16],[1,135,107,5,136,108],[10,74,46,1,75,47],[1,50,22,15,51,23],[2,42,14,17,43,15],[5,150,120,1,151,121],[9,69,43,4,70,44],[17,50,22,1,51,23],[2,42,14,19,43,15],[3,141,113,4,142,114],[3,70,44,11,71,45],[17,47,21,4,48,22],[9,39,13,16,40,14],[3,135,107,5,136,108],[3,67,41,13,68,42],[15,54,24,5,55,25],[15,43,15,10,44,16],[4,144,116,4,145,117],[17,68,42],[17,50,22,6,51,23],[19,46,16,6,47,17],[2,139,111,7,140,112],[17,74,46],[7,54,24,16,55,25],[34,37,13],[4,151,121,5,152,122],[4,75,47,14,76,48],[11,54,24,14,55,25],[16,45,15,14,46,16],[6,147,117,4,148,118],[6,73,45,14,74,46],[11,54,24,16,55,25],[30,46,16,2,47,17],[8,132,106,4,133,107],[8,75,47,13,76,48],[7,54,24,22,55,25],[22,45,15,13,46,16],[10,142,114,2,143,115],[19,74,46,4,75,47],[28,50,22,6,51,23],[33,46,16,4,47,17],[8,152,122,4,153,123],[22,73,45,3,74,46],[8,53,23,26,54,24],[12,45,15,28,46,16],[3,147,117,10,148,118],[3,73,45,23,74,46],[4,54,24,31,55,25],[11,45,15,31,46,16],[7,146,116,7,147,117],[21,73,45,7,74,46],[1,53,23,37,54,24],[19,45,15,26,46,16],[5,145,115,10,146,116],[19,75,47,10,76,48],[15,54,24,25,55,25],[23,45,15,25,46,16],[13,145,115,3,146,116],[2,74,46,29,75,47],[42,54,24,1,55,25],[23,45,15,28,46,16],[17,145,115],[10,74,46,23,75,47],[10,54,24,35,55,25],[19,45,15,35,46,16],[17,145,115,1,146,116],[14,74,46,21,75,47],[29,54,24,19,55,25],[11,45,15,46,46,16],[13,145,115,6,146,116],[14,74,46,23,75,47],[44,54,24,7,55,25],[59,46,16,1,47,17],[12,151,121,7,152,122],[12,75,47,26,76,48],[39,54,24,14,55,25],[22,45,15,41,46,16],[6,151,121,14,152,122],[6,75,47,34,76,48],[46,54,24,10,55,25],[2,45,15,64,46,16],[17,152,122,4,153,123],[29,74,46,14,75,47],[49,54,24,10,55,25],[24,45,15,46,46,16],[4,152,122,18,153,123],[13,74,46,32,75,47],[48,54,24,14,55,25],[42,45,15,32,46,16],[20,147,117,4,148,118],[40,75,47,7,76,48],[43,54,24,22,55,25],[10,45,15,67,46,16],[19,148,118,6,149,119],[18,75,47,31,76,48],[34,54,24,34,55,25],[20,45,15,61,46,16]],r=function(t,r){var e={};return e.totalCount=t,e.dataCount=r,e},e={};return e.getRSBlocks=function(e,n){var o=function(r,e){switch(e){case g.L:return t[4*(r-1)+0];case g.M:return t[4*(r-1)+1];case g.Q:return t[4*(r-1)+2];case g.H:return t[4*(r-1)+3];default:return}}(e,n);if(void 0===o)throw"bad rs block @ typeNumber:"+e+"/errorCorrectionLevel:"+n;for(var i=o.length/3,a=[],u=0;u<i;u+=1)for(var f=o[3*u+0],c=o[3*u+1],l=o[3*u+2],h=0;h<f;h+=1)a.push(r(c,l));return a},e}(),b=function(){var t=[],r=0,e={getBuffer:function(){return t},getAt:function(r){var e=Math.floor(r/8);return 1==(t[e]>>>7-r%8&1)},put:function(t,r){for(var n=0;n<r;n+=1)e.putBit(1==(t>>>r-n-1&1))},getLengthInBits:function(){return r},putBit:function(e){var n=Math.floor(r/8);t.length<=n&&t.push(0),e&&(t[n]|=128>>>r%8),r+=1}};return e},M=function(t){var r=a,e=t,n={getMode:function(){return r},getLength:function(t){return e.length},write:function(t){for(var r=e,n=0;n+2<r.length;)t.put(o(r.substring(n,n+3)),10),n+=3;n<r.length&&(r.length-n==1?t.put(o(r.substring(n,n+1)),4):r.length-n==2&&t.put(o(r.substring(n,n+2)),7))}},o=function(t){for(var r=0,e=0;e<t.length;e+=1)r=10*r+i(t.charAt(e));return r},i=function(t){if("0"<=t&&t<="9")return t.charCodeAt(0)-"0".charCodeAt(0);throw"illegal char :"+t};return n},x=function(t){var r=u,e=t,n={getMode:function(){return r},getLength:function(t){return e.length},write:function(t){for(var r=e,n=0;n+1<r.length;)t.put(45*o(r.charAt(n))+o(r.charAt(n+1)),11),n+=2;n<r.length&&t.put(o(r.charAt(n)),6)}},o=function(t){if("0"<=t&&t<="9")return t.charCodeAt(0)-"0".charCodeAt(0);if("A"<=t&&t<="Z")return t.charCodeAt(0)-"A".charCodeAt(0)+10;switch(t){case" ":return 36;case"$":return 37;case"%":return 38;case"*":return 39;case"+":return 40;case"-":return 41;case".":return 42;case"/":return 43;case":":return 44;default:throw"illegal char :"+t}};return n},m=function(r){var e=f,n=t.stringToBytes(r),o={getMode:function(){return e},getLength:function(t){return n.length},write:function(t){for(var r=0;r<n.length;r+=1)t.put(n[r],8)}};return o},L=function(r){var e=c,n=t.stringToBytesFuncs.SJIS;if(!n)throw"sjis not supported.";!function(){var t=n("友");if(2!=t.length||38726!=(t[0]<<8|t[1]))throw"sjis not supported."}();var o=n(r),i={getMode:function(){return e},getLength:function(t){return~~(o.length/2)},write:function(t){for(var r=o,e=0;e+1<r.length;){var n=(255&r[e])<<8|255&r[e+1];if(33088<=n&&n<=40956)n-=33088;else{if(!(57408<=n&&n<=60351))throw"illegal char at "+(e+1)+"/"+n;n-=49472}n=192*(n>>>8&255)+(255&n),t.put(n,13),e+=2}if(e<r.length)throw"illegal char at "+(e+1)}};return i},D=function(){var t=[],r={writeByte:function(r){t.push(255&r)},writeShort:function(t){r.writeByte(t),r.writeByte(t>>>8)},writeBytes:function(t,e,n){e=e||0,n=n||t.length;for(var o=0;o<n;o+=1)r.writeByte(t[o+e])},writeString:function(t){for(var e=0;e<t.length;e+=1)r.writeByte(t.charCodeAt(e))},toByteArray:function(){return t},toString:function(){var r="";r+="[";for(var e=0;e<t.length;e+=1)e>0&&(r+=","),r+=t[e];return r+="]"}};return r},S=function(t){var r=t,e=0,n=0,o=0,i={read:function(){for(;o<8;){if(e>=r.length){if(0==o)return-1;throw"unexpected end of file./"+o}var t=r.charAt(e);if(e+=1,"="==t)return o=0,-1;t.match(/^\s$/)||(n=n<<6|a(t.charCodeAt(0)),o+=6)}var i=n>>>o-8&255;return o-=8,i}},a=function(t){if(65<=t&&t<=90)return t-65;if(97<=t&&t<=122)return t-97+26;if(48<=t&&t<=57)return t-48+52;if(43==t)return 62;if(47==t)return 63;throw"c:"+t};return i},I=function(t,r,e){for(var n=function(t,r){var e=t,n=r,o=new Array(t*r),i={setPixel:function(t,r,n){o[r*e+t]=n},write:function(t){t.writeString("GIF87a"),t.writeShort(e),t.writeShort(n),t.writeByte(128),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(0),t.writeByte(255),t.writeByte(255),t.writeByte(255),t.writeString(","),t.writeShort(0),t.writeShort(0),t.writeShort(e),t.writeShort(n),t.writeByte(0);var r=a(2);t.writeByte(2);for(var o=0;r.length-o>255;)t.writeByte(255),t.writeBytes(r,o,255),o+=255;t.writeByte(r.length-o),t.writeBytes(r,o,r.length-o),t.writeByte(0),t.writeString(";")}},a=function(t){for(var r=1<<t,e=1+(1<<t),n=t+1,i=u(),a=0;a<r;a+=1)i.add(String.fromCharCode(a));i.add(String.fromCharCode(r)),i.add(String.fromCharCode(e));var f,c,g,l=D(),h=(f=l,c=0,g=0,{write:function(t,r){if(t>>>r!=0)throw"length over";for(;c+r>=8;)f.writeByte(255&(t<<c|g)),r-=8-c,t>>>=8-c,g=0,c=0;g|=t<<c,c+=r},flush:function(){c>0&&f.writeByte(g)}});h.write(r,n);var s=0,v=String.fromCharCode(o[s]);for(s+=1;s<o.length;){var d=String.fromCharCode(o[s]);s+=1,i.contains(v+d)?v+=d:(h.write(i.indexOf(v),n),i.size()<4095&&(i.size()==1<<n&&(n+=1),i.add(v+d)),v=d)}return h.write(i.indexOf(v),n),h.write(e,n),h.flush(),l.toByteArray()},u=function(){var t={},r=0,e={add:function(n){if(e.contains(n))throw"dup key:"+n;t[n]=r,r+=1},size:function(){return r},indexOf:function(r){return t[r]},contains:function(r){return void 0!==t[r]}};return e};return i}(t,r),o=0;o<r;o+=1)for(var i=0;i<t;i+=1)n.setPixel(i,o,e(i,o));var a=D();n.write(a);for(var u=function(){var t=0,r=0,e=0,n="",o={},i=function(t){n+=String.fromCharCode(a(63&t))},a=function(t){if(t<0);else{if(t<26)return 65+t;if(t<52)return t-26+97;if(t<62)return t-52+48;if(62==t)return 43;if(63==t)return 47}throw"n:"+t};return o.writeByte=function(n){for(t=t<<8|255&n,r+=8,e+=1;r>=6;)i(t>>>r-6),r-=6},o.flush=function(){if(r>0&&(i(t<<6-r),t=0,r=0),e%3!=0)for(var o=3-e%3,a=0;a<o;a+=1)n+="="},o.toString=function(){return n},o}(),f=a.toByteArray(),c=0;c<f.length;c+=1)u.writeByte(f[c]);return u.flush(),"data:image/gif;base64,"+u};return t}();qrcode.stringToBytesFuncs["UTF-8"]=function(t){return function(t){for(var r=[],e=0;e<t.length;e++){var n=t.charCodeAt(e);n<128?r.push(n):n<2048?r.push(192|n>>6,128|63&n):n<55296||n>=57344?r.push(224|n>>12,128|n>>6&63,128|63&n):(e++,n=65536+((1023&n)<<10|1023&t.charCodeAt(e)),r.push(240|n>>18,128|n>>12&63,128|n>>6&63,128|63&n))}return r}(t)},function(t){"function"==typeof define&&define.amd?define([],t):"object"==typeof exports&&(module.exports=t())}((function(){return qrcode}));
//# sourceMappingURL=/sm/26b4b0d0b1e283d6b3ec9857ac597d7a60c76ac17be1ef4c965f03086de426bb.map
  </script>

  <script>
    const currentUrl = document.querySelector("#current-url");
    const networkInfo = document.querySelector("#network-info");
    const copyPage = document.querySelector("#copy-page");
    const refreshButton = document.querySelector("#refresh");
    const dropzone = document.querySelector("#dropzone");
    const fileInput = document.querySelector("#file-input");
    const folderInput = document.querySelector("#folder-input");
    const fileExpiry = document.querySelector("#file-expiry");
    const chooseButton = document.querySelector("#choose-button");
    const chooseFolderButton = document.querySelector("#choose-folder-button");
    const progress = document.querySelector("#progress");
    const progressBar = document.querySelector("#progress span");
    const progressText = document.querySelector("#progress-text");
    const pauseUpload = document.querySelector("#pause-upload");
    const cancelUpload = document.querySelector("#cancel-upload");
    const sha256Display = document.querySelector("#sha256-display");
    const sha256Text = document.querySelector("#sha256-text");
    const uploadQueue = document.querySelector("#upload-queue");
    const fileList = document.querySelector("#file-list");
    const fileCount = document.querySelector("#file-count");
    const downloadSelectedFiles = document.querySelector("#download-selected-files");
    const deleteSelectedFiles = document.querySelector("#delete-selected-files");
    const selectAllCheckbox = document.querySelector("#select-all-checkbox");
    const unselectAllBtn = document.querySelector("#unselect-all-btn");
    const selectionBar = document.querySelector("#selection-bar");
    const selectedCount = document.querySelector("#selected-count");
    const deleteSelectedCount = document.querySelector("#delete-selected-count");
    const selectionStatus = document.querySelector("#selection-status");
    const downloadLatestUpload = document.querySelector("#download-latest-upload");
    const downloadAllFiles = document.querySelector("#download-all-files");
    const deleteAllFiles = document.querySelector("#delete-all-files");
    const clipInput = document.querySelector("#clipboard-input");
    const clipExpiry = document.querySelector("#clipboard-expiry");
    const saveClipboard = document.querySelector("#save-clipboard");
    const readSystemClipboard = document.querySelector("#read-system-clipboard");
    const clipList = document.querySelector("#clip-list");
    const clipCount = document.querySelector("#clip-count");
    const toast = document.querySelector("#toast");
    const uploadNote = document.querySelector("#upload-note");
    const auth = document.querySelector("#auth");
    const authForm = document.querySelector("#auth-form");
    const authSubtitle = document.querySelector("#auth-subtitle");
    const pinFieldWrapper = document.querySelector("#pin-field-wrapper");
    const pinInput = document.querySelector("#pin-input");
    const trustDevice = document.querySelector("#trust-device");
    const authSubmitBtn = document.querySelector("#auth-submit-btn");
    const previewDialog = document.querySelector("#preview-dialog");
    const previewBody = document.querySelector("#preview-body");
    const previewTitle = document.querySelector("#preview-title");
    const closePreview = document.querySelector("#close-preview");
    const artworkCards = document.querySelectorAll(".artwork-card");
    const doveDialog = document.querySelector("#dove-dialog");
    const modalArtwork = document.querySelector("#modal-artwork");
    const closeDove = document.querySelector("#close-dove");
    const supportBtn = document.querySelector("#support-btn");
    const supportDialog = document.querySelector("#support-dialog");
    const closeSupport = document.querySelector("#close-support");
    const supportHeartBadge = document.querySelector("#support-heart-badge");
    const floatingHeartsLayer = document.querySelector("#floating-hearts-layer");
    const copyUpiBtn = document.querySelector("#copy-upi-btn");
    const upiQrBtn = document.querySelector("#upi-qr-btn");
    const upiQrDialog = document.querySelector("#upi-qr-dialog");
    const closeUpiQr = document.querySelector("#close-upi-qr");
    const copyUpiModalBtn = document.querySelector("#copy-upi-modal-btn");
    const qrImage = document.querySelector("#qr-image");
    const lanUrl = document.querySelector("#lan-url");
    const copyLan = document.querySelector("#copy-lan");
    const securityBadge = document.querySelector("#security-badge");
    const securityNote = document.querySelector("#security-note");
    const securityToggle = document.querySelector("#security-toggle");
    const toggleLabelText = document.querySelector("#toggle-label-text");
    const securityPinForm = document.querySelector("#security-pin-form");
    const newPinField = document.querySelector("#new-pin-field");
    const newPinLabel = document.querySelector("#new-pin-label");
    const newPinInput = document.querySelector("#new-pin-input");
    const currentPinField = document.querySelector("#current-pin-field");
    const currentPinInput = document.querySelector("#current-pin-input");
    const saveSecurityBtn = document.querySelector("#save-security-btn");
    const togglePinVisibility = document.querySelector("#toggle-pin-visibility");
    const toggleCurrentPinVisibility = document.querySelector("#toggle-current-pin-visibility");
    const lockButton = document.querySelector("#lock-button");
    const themeToggle = document.querySelector("#theme-toggle");
    const globalSearch = document.querySelector("#global-search");
    const serviceList = document.querySelector("#service-list");
    const checkServices = document.querySelector("#check-services");
    const netDiagBadge = document.querySelector("#net-diag-badge");
    const diagServerStatus = document.querySelector("#diag-server-status");
    const diagProtocolPort = document.querySelector("#diag-protocol-port");
    const diagLanIp = document.querySelector("#diag-lan-ip");
    const diagDiscoveryStatus = document.querySelector("#diag-discovery-status");
    const discoveredServersPanel = document.querySelector("#discovered-servers-panel");
    const discoveredPeersGrid = document.querySelector("#discovered-peers-grid");
    const discoveredPeersCount = document.querySelector("#discovered-peers-count");
    const discoveredPeersBox = document.querySelector("#discovered-peers-box");
    const peersList = document.querySelector("#peers-list");
    const runDiagnosticsBtn = document.querySelector("#run-diagnostics-btn");
    const deviceList = document.querySelector("#device-list");
    const metricStorage = document.querySelector("#metric-storage");
    const metricUpload = document.querySelector("#metric-upload");
    const metricClipboard = document.querySelector("#metric-clipboard");
    const metricDevices = document.querySelector("#metric-devices");
    const activityList = document.querySelector("#activity-list");
    const copyLatestClip = document.querySelector("#copy-latest-clip");
    const copyInboxLatest = document.querySelector("#copy-inbox-latest");
    const pasteSaveClipboard = document.querySelector("#paste-save-clipboard");
    const clearClipboard = document.querySelector("#clear-clipboard");
    let latestClipId = null;
    let infoCache = null;
    let allFiles = [];
    let allClips = [];
    let selectedFiles = new Set();
    let latestUploadUrl = "";
    let latestClipText = "";
    let uploadItems = [];
    let eventSource = null;
    let autoLockTimer = null;
    let activeUploadRequest = null;
    let uploadCanceled = false;
    let uploadPaused = false;
    const maxTextPreviewBytes = 1024 * 1024; // 1 MB preview protection limit

    currentUrl.textContent = window.location.href;
    if (networkInfo) {
      const initProto = (window.location.protocol.replace(":", "") || "HTTP").toUpperCase();
      const initPort = window.location.port || (window.location.protocol === "https:" ? "443" : "80");
      networkInfo.textContent = `LAN • ${initProto} • Port ${initPort}`;
    }
    function applyTheme(isDark) {
      document.body.classList.toggle("dark", isDark);
      themeToggle.setAttribute("aria-checked", String(isDark));
    }

    applyTheme(localStorage.getItem("pura-theme") === "dark");

    function showToast(message) {
      toast.textContent = message;
      toast.classList.add("show");
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
    }

    function showAuth() {
      auth.classList.remove("opening");
      document.body.classList.add("locked");
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      if (infoCache && infoCache.auth_enabled) {
        window.setTimeout(() => pinInput.focus(), 80);
      } else {
        window.setTimeout(() => authSubmitBtn?.focus(), 80);
      }
    }

    function unlockApp() {
      auth.classList.add("opening");
      window.setTimeout(() => {
        document.body.classList.remove("locked");
      }, 180);
      window.setTimeout(() => {
        auth.classList.remove("opening");
      }, 760);
      resetAutoLock();
    }

    function resetAutoLock() {
      window.clearTimeout(autoLockTimer);
      if (!infoCache || !infoCache.auth_enabled) return;
      if (localStorage.getItem("pura-trusted") === "true") return;
      autoLockTimer = window.setTimeout(async () => {
        await fetchJson("/api/logout", {method: "POST"}).catch(() => {});
        sessionStorage.removeItem("pura_active");
        showAuth();
        showToast("Locked after inactivity");
      }, 15 * 60 * 1000);
    }

    for (const eventName of ["click", "keydown", "pointermove", "paste", "drop"]) {
      document.addEventListener(eventName, resetAutoLock, {passive: true});
    }

    async function copyText(text, label) {
      if (navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(text);
          showToast(`${label} copied`);
          return;
        } catch (err) {
          // Fall through to execCommand if clipboard API fails (e.g., due to secure context)
        }
      }
      
      const textArea = document.createElement("textarea");
      textArea.value = text;
      
      // Avoid scrolling to bottom and keep it visually hidden
      textArea.style.top = "0";
      textArea.style.left = "0";
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      
      document.body.appendChild(textArea);
      
      // iOS specific selection
      if (navigator.userAgent.match(/ipad|iphone/i)) {
          textArea.contentEditable = true;
          textArea.readOnly = false;
          const range = document.createRange();
          range.selectNodeContents(textArea);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          textArea.setSelectionRange(0, 999999);
      } else {
          textArea.focus();
          textArea.select();
      }

      try {
        const successful = document.execCommand('copy');
        if (successful) {
           showToast(`${label} copied`);
        } else {
           prompt(`Copy failed. Select and copy manually:`, text);
        }
      } catch (err) {
        prompt(`Copy failed. Select and copy manually:`, text);
      }
      document.body.removeChild(textArea);
    }

    function formatSize(bytes) {
      const units = ["B", "KB", "MB", "GB", "TB"];
      let value = bytes;
      let index = 0;
      while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
      }
      return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function compactPreview(value, maxLength = 72) {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      if (!text) return "None";
      return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
    }

    function formatDate(value) {
      if (!value) return "Never";
      return new Date(value * 1000).toLocaleString([], {
        year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit"
      });
    }

    function formatRemaining(expiresAt) {
      if (!expiresAt) return "No expiry";
      const seconds = Math.max(0, Math.round(expiresAt - Date.now() / 1000));
      if (seconds < 60) return `${seconds}s left`;
      if (seconds < 3600) return `${Math.round(seconds / 60)}m left`;
      if (seconds < 86400) return `${Math.round(seconds / 3600)}h left`;
      return `${Math.round(seconds / 86400)}d left`;
    }

    function formatSeen(secondsAgo) {
      if (secondsAgo < 5) return "now";
      if (secondsAgo < 60) return `${secondsAgo}s ago`;
      if (secondsAgo < 3600) return `${Math.round(secondsAgo / 60)}m ago`;
      if (secondsAgo < 86400) return `${Math.round(secondsAgo / 3600)}h ago`;
      return `${Math.round(secondsAgo / 86400)}d ago`;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers: {
          ...(options.body && !(options.body instanceof FormData) ? {"Content-Type": "application/json"} : {}),
          ...(options.headers || {})
        }
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        showAuth();
        throw new Error(data.error || "PIN required");
      }
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function setView(viewId) {
      document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
      document.querySelectorAll(".tab").forEach((tab) => {
        const active = tab.dataset.view === viewId;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      });
    }

    function setServiceRows(services) {
      serviceList.innerHTML = "";
      for (const service of services) {
        const row = document.createElement("div");
        row.className = "service-row";
        const dot = document.createElement("span");
        dot.className = `dot ${service.ok ? "ok" : "bad"}`;
        const name = document.createElement("span");
        name.textContent = service.name;
        const state = document.createElement("strong");
        state.textContent = service.ok ? "OK" : "Issue";
        row.append(dot, name, state);
        serviceList.append(row);
      }
    }

    function matchesSearch(value) {
      const query = globalSearch.value.trim().toLowerCase();
      if (!query) return true;
      const terms = query.split(/\s+/);
      const target = String(value || "").toLowerCase();
      return terms.every((term) => target.includes(term));
    }

    function renderDevices(devices = []) {
      metricDevices.textContent = String(devices.length);
      deviceList.innerHTML = "";
      if (!devices.length) {
        deviceList.innerHTML = '<div class="service-row"><span class="dot"></span><span>No devices yet</span><strong>--</strong></div>';
        return;
      }
      for (const device of devices.slice(0, 6)) {
        const row = document.createElement("div");
        row.className = "device-row";
        const dot = document.createElement("span");
        dot.className = "dot ok";
        const name = document.createElement("input");
        name.value = device.name || `${device.ip} device`;
        name.maxLength = 36;
        name.setAttribute("aria-label", "Device name");
        const save = document.createElement("button");
        save.className = "secondary";
        save.type = "button";
        save.textContent = "Save";
        const meta = document.createElement("div");
        meta.className = "device-meta";
        meta.textContent = `${device.ip} | ${device.agent} | ${formatSeen(device.seen_seconds_ago)}`;
        async function saveDeviceName() {
          const nextName = name.value.trim();
          if (!nextName) {
            showToast("Device name is empty");
            return;
          }
          try {
            await fetchJson("/api/device-name", {
              method: "PATCH",
              body: JSON.stringify({id: device.id, name: nextName})
            });
            showToast("Device name saved");
            await loadDashboard();
          } catch (error) {
            showToast(error.message);
          }
        }
        save.addEventListener("click", saveDeviceName);
        name.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            saveDeviceName();
          }
        });
        row.append(dot, name, save, meta);
        deviceList.append(row);
      }
    }

    function renderDiscoveredPeers(peers) {
      if (!discoveredServersPanel || !discoveredPeersGrid) return;
      if (!peers || peers.length === 0) {
        discoveredServersPanel.style.display = "none";
        if (discoveredPeersBox) discoveredPeersBox.style.display = "none";
        return;
      }
      discoveredServersPanel.style.display = "block";
      if (discoveredPeersCount) {
        discoveredPeersCount.textContent = peers.length === 1 ? "1 server discovered" : `${peers.length} servers discovered`;
      }
      discoveredPeersGrid.innerHTML = "";
      for (const peer of peers) {
        const card = document.createElement("article");
        card.className = "discovered-peer-card";

        const header = document.createElement("div");
        header.className = "discovered-peer-header";

        const name = document.createElement("div");
        name.className = "discovered-peer-name";
        name.textContent = peer.name || "Pura Server";

        const badge = document.createElement("span");
        badge.className = "security-badge active";
        badge.textContent = (peer.protocol || "http").toUpperCase();
        header.append(name, badge);

        const url = document.createElement("div");
        url.className = "discovered-peer-url";
        url.textContent = peer.url;

        const meta = document.createElement("div");
        meta.className = "discovered-peer-meta";

        const seen = document.createElement("span");
        seen.textContent = peer.last_seen_sec <= 3 ? "Active now" : `Seen ${peer.last_seen_sec}s ago`;

        const authStatus = document.createElement("span");
        authStatus.textContent = peer.auth_enabled ? "🔒 PIN Required" : "🔓 Open Access";

        meta.append(seen, authStatus);

        const actions = document.createElement("div");
        actions.className = "actions";
        actions.style.display = "flex";
        actions.style.gap = "8px";
        actions.style.marginTop = "6px";

        const openBtn = document.createElement("a");
        openBtn.className = "button";
        openBtn.href = peer.url;
        openBtn.target = "_blank";
        openBtn.rel = "noopener noreferrer";
        openBtn.textContent = "Open Share ↗";
        openBtn.style.flex = "1";
        openBtn.style.textAlign = "center";
        openBtn.style.display = "inline-flex";
        openBtn.style.alignItems = "center";
        openBtn.style.justifyContent = "center";

        const copyBtn = document.createElement("button");
        copyBtn.className = "secondary";
        copyBtn.type = "button";
        copyBtn.textContent = "Copy Link";
        copyBtn.addEventListener("click", () => copyText(peer.url, "Server URL"));

        actions.append(openBtn, copyBtn);
        card.append(header, url, meta, actions);
        discoveredPeersGrid.append(card);
      }

      if (discoveredPeersBox && peersList) {
        discoveredPeersBox.style.display = "grid";
        peersList.innerHTML = "";
        for (const peer of peers) {
          const row = document.createElement("div");
          row.className = "peer-card";
          const info = document.createElement("span");
          info.textContent = `${peer.name} (${(peer.protocol || "http").toUpperCase()}) - ${peer.url}`;
          const link = document.createElement("a");
          link.href = peer.url;
          link.target = "_blank";
          link.rel = "noreferrer";
          link.textContent = "Open share →";
          row.append(info, link);
          peersList.append(row);
        }
      }
    }

    async function loadDashboard() {
      const data = await fetchJson("/api/dashboard");
      metricStorage.textContent = `${formatSize(data.storage_bytes)} / ${data.file_count} files`;
      const uploadName = data.latest_upload ? data.latest_upload.name : "None";
      latestUploadUrl = data.latest_upload ? data.latest_upload.url : "";
      metricUpload.textContent = compactPreview(uploadName, 48);
      metricUpload.title = uploadName;
      downloadLatestUpload.disabled = !latestUploadUrl;
      latestClipText = data.latest_clipboard ? data.latest_clipboard.text : "";
      metricClipboard.textContent = compactPreview(latestClipText, 72);
      metricClipboard.title = latestClipText || "None";
      copyLatestClip.disabled = !latestClipText;
      copyInboxLatest.disabled = !latestClipText;
      if (metricDevices) metricDevices.textContent = String((data.devices || []).length);
      renderDevices(data.devices || []);
      renderActivity(data.activity || []);
      renderDiscoveredPeers(data.peers || []);
    }

    function renderActivity(events) {
      if (!activityList) return;
      if (!events || events.length === 0) {
        activityList.innerHTML = '<span class="activity-empty">No recent activity</span>';
        return;
      }
      activityList.innerHTML = "";
      for (const ev of events) {
        const row = document.createElement("div");
        row.className = "activity-row";

        const timeSpan = document.createElement("span");
        timeSpan.className = "activity-time";
        timeSpan.textContent = ev.time || "";

        const msgSpan = document.createElement("span");
        msgSpan.className = "activity-msg";
        msgSpan.textContent = ev.message || "";

        row.appendChild(timeSpan);
        row.appendChild(msgSpan);
        activityList.appendChild(row);
      }
    }

    async function checkAllServices() {
      try {
        const health = await fetchJson("/api/health");
        setServiceRows(health.services);
      } catch {
        setServiceRows([
          {name: "Server info", ok: false},
          {name: "File service", ok: false},
          {name: "Clipboard service", ok: false},
          {name: "Authentication", ok: false}
        ]);
      }
    }

    function updateSecurityUI(info) {
      const isEnabled = Boolean(info && info.auth_enabled);
      if (securityBadge) {
        securityBadge.textContent = isEnabled ? "Enabled" : "Disabled";
        securityBadge.className = `security-badge ${isEnabled ? "active" : ""}`;
      }
      if (securityToggle) {
        securityToggle.checked = isEnabled;
      }
      if (toggleLabelText) {
        toggleLabelText.textContent = isEnabled ? "PIN Protection is Enabled" : "Require PIN to open dashboard";
      }
      if (securityNote) {
        securityNote.textContent = isEnabled
          ? "PIN protection is active. Devices must enter PIN to open the dashboard."
          : "PIN protection is OFF. Anyone on your local network can open the dashboard with one click.";
      }
      if (currentPinField) {
        currentPinField.style.display = isEnabled ? "grid" : "none";
      }
      if (newPinField) {
        newPinField.style.display = "grid";
      }
      if (newPinLabel) {
        newPinLabel.textContent = isEnabled ? "New PIN / Password" : "Set PIN / Password";
      }
      if (newPinInput) {
        newPinInput.placeholder = isEnabled ? "New PIN" : "e.g. 1234";
      }
      if (saveSecurityBtn) {
        saveSecurityBtn.textContent = isEnabled ? "Update PIN / Security" : "Enable PIN Protection";
      }
      if (lockButton) {
        lockButton.textContent = isEnabled ? "Lock Dashboard" : "Lock Dashboard (Open Gateway)";
      }
      if (pinFieldWrapper) {
        if (isEnabled) {
          pinFieldWrapper.classList.remove("hidden");
        } else {
          pinFieldWrapper.classList.add("hidden");
        }
      }
      if (authSubtitle) {
        authSubtitle.textContent = isEnabled
          ? "Enter your private PIN to open file sharing, clipboard transfer, and device tools."
          : "Instant file sharing, clipboard sync, and device tools on your private network.";
      }
    }

    async function loadNetworkDiagnostics() {
      try {
        if (runDiagnosticsBtn) runDiagnosticsBtn.textContent = "Running diagnostics...";
        const data = await fetchJson("/api/network/diagnostics");
        if (diagServerStatus) diagServerStatus.textContent = data.server_status || "Running";
        if (diagProtocolPort) diagProtocolPort.textContent = `${(data.protocol || "http").toUpperCase()} : ${data.port || 8000}`;
        if (diagLanIp) diagLanIp.textContent = data.lan_ip || "127.0.0.1";
        if (diagDiscoveryStatus) diagDiscoveryStatus.textContent = `${data.discovery_status || "Active"} (UDP ${data.discovery_port || 52002})`;
        if (netDiagBadge) {
          netDiagBadge.textContent = data.tls_enabled ? "HTTPS (Encrypted)" : "HTTP (Local LAN)";
          netDiagBadge.className = `security-badge ${data.tls_enabled ? "active" : ""}`;
        }

        if (discoveredPeersBox && peersList) {
          const peers = data.discovered_peers || [];
          if (peers.length > 0) {
            discoveredPeersBox.style.display = "grid";
            peersList.innerHTML = "";
            for (const peer of peers) {
              const row = document.createElement("div");
              row.className = "peer-card";
              const info = document.createElement("span");
              info.textContent = `${peer.name} (${peer.protocol.toUpperCase()})`;
              const link = document.createElement("a");
              link.href = peer.url;
              link.target = "_blank";
              link.rel = "noreferrer";
              link.textContent = "Open share →";
              row.append(info, link);
              peersList.append(row);
            }
          } else {
            discoveredPeersBox.style.display = "none";
          }
        }
        if (runDiagnosticsBtn) runDiagnosticsBtn.textContent = "Run diagnostics";
      } catch (err) {
        if (runDiagnosticsBtn) runDiagnosticsBtn.textContent = "Run diagnostics";
        if (netDiagBadge) netDiagBadge.textContent = "Error";
      }
    }

    async function loadInfo() {
      const info = await fetchJson("/api/info");
      infoCache = info;
      const resolvedLanUrl = info.lan_url || window.location.origin;
      if (currentUrl) {
        currentUrl.textContent = resolvedLanUrl;
        currentUrl.title = resolvedLanUrl;
      }
      if (networkInfo) {
        const proto = (info.protocol || window.location.protocol.replace(":", "") || "http").toUpperCase();
        const port = info.port || window.location.port || (proto === "HTTPS" ? "443" : "80");
        networkInfo.textContent = `LAN • ${proto} • Port ${port}`;
        networkInfo.title = `Protocol: ${proto}, Port: ${port}, Interface: LAN`;
      }
      uploadNote.textContent = `Up to ${info.max_upload_gb} GB per file. Paste images/files anywhere on the page.`;
      lanUrl.textContent = resolvedLanUrl;
      updateSecurityUI(info);
      drawQr(resolvedLanUrl);
      await checkAllServices();
      await loadNetworkDiagnostics();
    }

    async function loadFiles() {
      const data = await fetchJson("/api/files");
      allFiles = data.files;
      renderFiles();
    }

    function isTextLikeFile(file) {
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      const textExts = new Set([
        "txt", "log", "csv", "md", "json", "xml", "html", "htm", "css", "js", "ts", "tsx", "jsx",
        "py", "yaml", "yml", "sh", "bat", "ps1", "ini", "cfg", "conf", "sql", "c", "cpp", "h", "hpp",
        "rs", "go", "java", "env", "toml"
      ]);
      return (file.type && file.type.startsWith("text/")) || textExts.has(ext);
    }

    function isPreviewable(file) {
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      const type = file.type || '';
      if (type.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"].includes(ext)) return true;
      if (type.startsWith("video/") || type.startsWith("audio/") || ["mp4", "webm", "ogg", "mp3", "wav", "m4a", "aac", "flac"].includes(ext)) return true;
      if (type === "application/pdf" || ext === "pdf") return true;
      if (isTextLikeFile(file)) return true;
      return false;
    }

    function updateSelectionUI() {
      const count = selectedFiles.size;
      if (downloadSelectedFiles && selectedCount) {
        selectedCount.textContent = count;
        downloadSelectedFiles.style.display = count > 0 ? "inline-flex" : "none";
      }
      if (deleteSelectedFiles && deleteSelectedCount) {
        deleteSelectedCount.textContent = count;
        deleteSelectedFiles.style.display = count > 0 ? "inline-flex" : "none";
      }
      if (downloadAllFiles) {
        downloadAllFiles.style.display = count > 0 ? "none" : "inline-flex";
      }
      if (deleteAllFiles) {
        deleteAllFiles.style.display = count > 0 ? "none" : "inline-flex";
      }
      if (selectionBar && selectionStatus) {
        selectionBar.style.display = count > 0 ? "flex" : "none";
        selectionStatus.textContent = `${count} of ${allFiles.length} selected`;
      }
      if (selectAllCheckbox) {
        selectAllCheckbox.checked = allFiles.length > 0 && count === allFiles.length;
        selectAllCheckbox.indeterminate = count > 0 && count < allFiles.length;
      }
    }

    function renderFiles() {
      const files = allFiles.filter((file) => matchesSearch(`${file.name} ${file.path || ''} ${file.folder || ''} ${file.type || ''}`));
      fileCount.textContent = files.length === 1 ? "1 file" : `${files.length} files`;
      downloadAllFiles.disabled = !allFiles.length;
      deleteAllFiles.disabled = !allFiles.length;
      if (!files.length) {
        fileList.innerHTML = '<div class="empty">No files shared yet.</div>';
        updateSelectionUI();
        return;
      }

      fileList.innerHTML = "";
      for (const file of files) {
        const fileIdentifier = file.path || file.name;
        const isDirectory = Boolean(file.is_dir || file.type === "Folder" || file.type === "folder");
        const row = document.createElement("article");
        row.className = "file-row" + (selectedFiles.has(fileIdentifier) ? " selected" : "");

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "file-select-checkbox";
        checkbox.checked = selectedFiles.has(fileIdentifier);
        checkbox.setAttribute("aria-label", `Select ${fileIdentifier}`);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            selectedFiles.add(fileIdentifier);
            row.classList.add("selected");
          } else {
            selectedFiles.delete(fileIdentifier);
            row.classList.remove("selected");
          }
          updateSelectionUI();
        });

        const details = document.createElement("div");
        const fileHeader = document.createElement("div");
        fileHeader.className = "file-header";

        const name = document.createElement("div");
        name.className = "file-name";
        name.textContent = isDirectory ? `📁 ${file.name}` : fileIdentifier;
        name.title = fileIdentifier;

        fileHeader.append(name, checkbox);

        const meta = document.createElement("div");
        meta.className = "meta";
        if (isDirectory) {
          const countStr = typeof file.file_count === "number" ? ` | ${file.file_count} ${file.file_count === 1 ? 'file' : 'files'}` : "";
          meta.textContent = `${formatSize(file.size)}${countStr} | Folder | ${formatDate(file.modified)}`;
        } else {
          const folderTag = file.folder ? `[${file.folder}] ` : "";
          meta.textContent = `${folderTag}${formatSize(file.size)} | ${file.type} | ${formatDate(file.modified)} | ${formatRemaining(file.expires_at)}`;
        }
        meta.title = meta.textContent;
        details.append(fileHeader, meta);

        const actions = document.createElement("div");
        actions.className = "actions";

        if (!isDirectory && isPreviewable(file)) {
          const preview = document.createElement("button");
          preview.className = "secondary";
          preview.type = "button";
          preview.textContent = "Preview";
          preview.addEventListener("click", () => openPreview(file));
          actions.append(preview);
        }

        const download = document.createElement("a");
        download.className = "button";
        download.href = file.url;
        download.textContent = isDirectory ? "Download ZIP" : "Download";

        const copy = document.createElement("button");
        copy.className = "secondary";
        copy.type = "button";
        copy.textContent = "Copy link";
        copy.addEventListener("click", () => copyText(new URL(file.url, location.href).href, isDirectory ? "Folder link" : "File link"));

        const rename = document.createElement("button");
        rename.className = "secondary";
        rename.type = "button";
        rename.textContent = "Rename";
        rename.addEventListener("click", async () => {
          const nextName = prompt(isDirectory ? "New folder name" : "New file name", file.name);
          if (!nextName || nextName === file.name) return;
          await fetchJson(`/api/files/${encodeURIComponent(fileIdentifier)}`, {
            method: "PATCH",
            body: JSON.stringify({name: nextName})
          });
          showToast(isDirectory ? "Folder renamed" : "File renamed");
          await Promise.all([loadFiles(), loadDashboard()]);
        });

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Delete";
        remove.addEventListener("click", async () => {
          if (!confirm(`Delete ${fileIdentifier}?`)) return;
          await fetchJson(`/api/files/${encodeURIComponent(fileIdentifier)}`, { method: "DELETE" });
          selectedFiles.delete(fileIdentifier);
          showToast(isDirectory ? "Folder deleted" : "File deleted");
          await Promise.all([loadFiles(), loadDashboard()]);
        });

        actions.append(download, copy, rename, remove);
        row.append(details, actions);
        fileList.append(row);
      }
      updateSelectionUI();
    }

    async function openPreview(file) {
      previewTitle.textContent = file.name;
      previewBody.innerHTML = "";
      const previewUrl = `${file.url}?preview=1`;
      const ext = (file.name.split('.').pop() || '').toLowerCase();

      if (file.type.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "bmp", "ico"].includes(ext)) {
        const image = document.createElement("img");
        image.className = "preview-image";
        image.src = previewUrl;
        image.alt = file.name;
        previewBody.append(image);
      } else if (file.type === "image/svg+xml" || ext === "svg") {
        const image = document.createElement("img");
        image.className = "preview-image";
        image.src = previewUrl;
        image.alt = file.name;
        previewBody.append(image);
      } else if (file.type.startsWith("audio/") || ["mp3", "wav", "ogg", "m4a", "aac", "flac"].includes(ext)) {
        const audio = document.createElement("audio");
        audio.className = "preview-audio";
        audio.controls = true;
        audio.src = previewUrl;
        previewBody.append(audio);
      } else if (file.type.startsWith("video/") || ["mp4", "webm", "ogg"].includes(ext)) {
        const video = document.createElement("video");
        video.className = "preview-video";
        video.controls = true;
        video.src = previewUrl;
        previewBody.append(video);
      } else if (file.type === "application/pdf" || ext === "pdf") {
        const frame = document.createElement("iframe");
        frame.className = "preview-frame";
        frame.src = previewUrl;
        frame.setAttribute("sandbox", "allow-same-origin allow-scripts");
        previewBody.append(frame);
      } else if (isTextLikeFile(file)) {
        if (file.size > maxTextPreviewBytes) {
          const note = document.createElement("div");
          note.className = "preview-note";
          note.textContent = `This file is ${formatSize(file.size)}. In-app preview is disabled for files > 1 MB to keep the browser responsive. Use Download to view the full file.`;
          previewBody.append(note);
          previewDialog.showModal();
          closePreview.focus();
          return;
        }
        const text = document.createElement("pre");
        text.className = "preview-text";
        try {
          const response = await fetch(previewUrl, {credentials: "same-origin"});
          text.textContent = await response.text();
        } catch (err) {
          text.textContent = `Could not load preview: ${err.message}`;
        }
        previewBody.append(text);
      } else {
        previewBody.innerHTML = '<p class="preview-note">No browser preview available for this file type.</p>';
      }
      previewDialog.showModal();
      closePreview.focus();
    }

    const MAX_CONCURRENT_UPLOADS = 3;
    const UPLOAD_CHUNK_SIZE = 2 * 1024 * 1024; // 2 MB chunks
    const activeUploadRequests = new Set();

    async function computeSHA256(file) {
      if (!window.crypto?.subtle) return "";
      // For files > 64 MB, skip client full-buffer reading to prevent browser memory exhaustion.
      // The backend computes SHA-256 in streaming mode during chunk assembly and verifies it.
      if (file.size > 64 * 1024 * 1024) return "";
      try {
        if (file.size === 0) {
          return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
        }
        const buffer = await file.arrayBuffer();
        const digest = await crypto.subtle.digest("SHA-256", buffer);
        return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
      } catch {
        return "";
      }
    }

    function uploadFile(file, itemIndex, relativePath = "") {
      return uploadFileResumable(file, itemIndex, relativePath);
    }

    async function uploadFileResumable(file, itemIndex, relativePath = "") {
      const expires = Number(fileExpiry.value || "0");
      const isFolder = Boolean(relativePath);
      const displayName = relativePath || file.name;

      uploadItems[itemIndex].name = displayName;
      if (file.size <= 64 * 1024 * 1024) {
        uploadItems[itemIndex].status = "Calculating SHA-256...";
        renderUploadQueue();
      }

      const clientHash = await computeSHA256(file);
      uploadItems[itemIndex].status = "Initializing...";
      renderUploadQueue();

      const initResp = await fetch("/api/upload/init", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          size: file.size,
          sha256: clientHash,
          expires: expires,
          folder: isFolder,
          folder_path: relativePath
        })
      });

      if (!initResp.ok) {
        if (initResp.status === 401) {
          showAuth();
          throw new Error("PIN required");
        }
        const err = await initResp.json().catch(() => ({}));
        throw new Error(err.error || `Upload init failed: ${initResp.statusText}`);
      }

      const initData = await initResp.json();
      const uploadId = initData.upload_id;
      uploadItems[itemIndex].uploadId = uploadId;

      let offset = 0;
      const total = file.size;
      const startTime = performance.now();
      // Calibrated chunk size for smooth LAN streaming & continuous progress updates:
      const chunkSizeDynamic = file.size > 100 * 1024 * 1024 ? 4 * 1024 * 1024
        : (file.size > 10 * 1024 * 1024 ? 2 * 1024 * 1024 : 1024 * 1024);

      while (offset < total && !uploadCanceled) {
        while (uploadPaused && !uploadCanceled) {
          uploadItems[itemIndex].status = "Paused";
          scheduleQueueRender();
          await new Promise((r) => setTimeout(r, 200));
        }
        if (uploadCanceled) break;

        let chunkStart = offset;
        let chunkEnd = Math.min(chunkStart + chunkSizeDynamic, total);
        let chunkBlob = file.slice(chunkStart, chunkEnd);
        let chunkSize = chunkEnd - chunkStart;
        let chunkNumber = Math.floor(chunkStart / chunkSizeDynamic) + 1;

        let chunkSuccess = false;
        let lastError = null;
        const MAX_CHUNK_RETRIES = 12; // 12 retries for resilient LAN recovery

        for (let attempt = 0; attempt < MAX_CHUNK_RETRIES; attempt++) {
          if (uploadCanceled) break;

          // Before re-trying an interrupted chunk, query server authoritative status
          if (attempt > 0) {
            uploadItems[itemIndex].status = `Reconnecting (${attempt}/${MAX_CHUNK_RETRIES})...`;
            scheduleQueueRender();

            // Bounded exponential backoff + jitter: 400ms, 800ms, 1200ms... max 3500ms
            const backoff = Math.min(3500, Math.floor(400 * Math.pow(1.35, attempt) + Math.random() * 200));
            console.log(`[Upload ${uploadId}] Chunk #${chunkNumber} retry attempt ${attempt} waiting ${backoff}ms`);
            await new Promise((r) => setTimeout(r, backoff));

            try {
              const statusCtrl = new AbortController();
              const statusTimer = setTimeout(() => statusCtrl.abort(), 4000);
              const st = await fetch(`/api/upload/status?id=${encodeURIComponent(uploadId)}`, {
                credentials: "same-origin",
                signal: statusCtrl.signal
              });
              clearTimeout(statusTimer);
              if (st.ok) {
                const stData = await st.json();
                const serverOffset = Number(stData.received);
                console.log(`[Upload ${uploadId}] Status sync: serverOffset=${serverOffset}, expectedOffset=${chunkStart}`);
                if (!isNaN(serverOffset)) {
                  if (serverOffset > chunkStart) {
                    // Server already received this chunk (or beyond)!
                    console.log(`[Upload ${uploadId}] Ambiguous chunk recovery: server acknowledged offset ${serverOffset}`);
                    offset = serverOffset;
                    chunkSuccess = true;
                    break;
                  }
                  if (serverOffset < chunkStart) {
                    // Realign client offset to authoritative server offset
                    console.log(`[Upload ${uploadId}] Realignment: roll back chunkStart from ${chunkStart} to ${serverOffset}`);
                    offset = serverOffset;
                    chunkStart = serverOffset;
                    chunkEnd = Math.min(chunkStart + chunkSizeDynamic, total);
                    chunkBlob = file.slice(chunkStart, chunkEnd);
                    chunkSize = chunkEnd - chunkStart;
                  }
                }
              }
            } catch (syncErr) {
              console.warn(`[Upload ${uploadId}] Status sync failed on attempt ${attempt}:`, syncErr.message);
            }
          }

          console.log(`[Upload ${uploadId}] Chunk #${chunkNumber} request start: offset=${chunkStart}, size=${chunkSize}`);

          try {
            const resp = await new Promise((resolve, reject) => {
              const xhr = new XMLHttpRequest();
              activeUploadRequests.add(xhr);

              let watchdogTimer = null;
              const resetWatchdog = () => {
                if (watchdogTimer) clearTimeout(watchdogTimer);
                // Abort dead/stalled socket if no progress event for 10 seconds
                watchdogTimer = setTimeout(() => {
                  console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} stalled (no progress for 10s), aborting socket`);
                  try { xhr.abort(); } catch {}
                }, 10000);
              };

              xhr.open("POST", `/api/upload/chunk?id=${encodeURIComponent(uploadId)}&offset=${chunkStart}`);
              xhr.withCredentials = true;
              xhr.timeout = 20000; // 20s hard timeout
              xhr.setRequestHeader("Content-Type", "application/octet-stream");

              resetWatchdog();

              xhr.upload.addEventListener("progress", (e) => {
                resetWatchdog();
                const currentBytes = chunkStart + (e.lengthComputable ? e.loaded : 0);
                const percent = Math.min(100, Math.round((currentBytes / total) * 100));
                if (progressBar) progressBar.style.width = `${percent}%`;
                const elapsed = Math.max(0.1, (performance.now() - startTime) / 1000);
                const speed = currentBytes / elapsed;
                uploadItems[itemIndex].status = `${percent}% | ${formatSize(speed)}/s`;
                if (!isFolder && progressText && uploadItems.length === 1) {
                  progressText.textContent = `Uploading ${file.name} (${percent}% • ${formatSize(speed)}/s)...`;
                }
                scheduleQueueRender();
              });

              xhr.addEventListener("load", () => {
                if (watchdogTimer) clearTimeout(watchdogTimer);
                activeUploadRequests.delete(xhr);
                if (xhr.status >= 200 && xhr.status < 300) {
                  console.log(`[Upload ${uploadId}] Chunk #${chunkNumber} request completion: offset=${chunkStart}`);
                  try { resolve(JSON.parse(xhr.responseText)); } catch { resolve({}); }
                } else if (xhr.status === 409) {
                  console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} offset mismatch (HTTP 409)`);
                  reject(new Error("Offset mismatch"));
                } else {
                  let msg = xhr.statusText;
                  try { msg = JSON.parse(xhr.responseText).error || msg; } catch {}
                  console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} server error (${xhr.status}): ${msg}`);
                  reject(new Error(msg));
                }
              });

              xhr.addEventListener("error", () => {
                if (watchdogTimer) clearTimeout(watchdogTimer);
                activeUploadRequests.delete(xhr);
                console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} network error`);
                reject(new Error("Chunk upload network error"));
              });

              xhr.addEventListener("timeout", () => {
                if (watchdogTimer) clearTimeout(watchdogTimer);
                activeUploadRequests.delete(xhr);
                console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} timed out`);
                reject(new Error("Chunk upload timed out"));
              });

              xhr.addEventListener("abort", () => {
                if (watchdogTimer) clearTimeout(watchdogTimer);
                activeUploadRequests.delete(xhr);
                if (uploadCanceled) {
                  reject(new Error("Upload aborted"));
                } else {
                  reject(new Error("Connection stalled"));
                }
              });

              xhr.send(chunkBlob);
            });

            offset = (resp.offset !== undefined && typeof resp.offset === "number")
              ? resp.offset
              : (resp.received !== undefined && typeof resp.received === "number")
                ? resp.received
                : chunkEnd;
            chunkSuccess = true;
            break;
          } catch (err) {
            lastError = err;
            if (err.message === "Upload aborted" || uploadCanceled) break;
            console.warn(`[Upload ${uploadId}] Chunk #${chunkNumber} request failure: ${err.message}`);
          }
        }

        if (!chunkSuccess) {
          throw lastError || new Error(`Chunk upload failed after ${MAX_CHUNK_RETRIES} retries`);
        }
      }

      if (uploadCanceled) {
        await fetch(`/api/upload/cancel?id=${encodeURIComponent(uploadId)}`, {
          method: "DELETE",
          credentials: "same-origin"
        }).catch(() => {});
        throw new Error("Upload canceled");
      }

      uploadItems[itemIndex].status = "Verifying SHA-256...";
      scheduleQueueRender();

      const compResp = await fetch(`/api/upload/complete?id=${encodeURIComponent(uploadId)}`, {
        method: "POST",
        credentials: "same-origin"
      });

      if (!compResp.ok) {
        const err = await compResp.json().catch(() => ({}));
        throw new Error(err.error || `Finalize failed: ${compResp.statusText}`);
      }

      const compData = await compResp.json();
      uploadItems[itemIndex].status = "Done";
      if (compData.sha256) {
        uploadItems[itemIndex].sha256 = compData.sha256;
      }
      return compData;
    }

    let queueRenderRequested = false;
    function scheduleQueueRender() {
      if (queueRenderRequested) return;
      queueRenderRequested = true;
      requestAnimationFrame(() => {
        queueRenderRequested = false;
        renderUploadQueue();
      });
    }

    function renderUploadQueue() {
      uploadQueue.innerHTML = "";
      for (const item of uploadItems.slice(-6)) {
        const row = document.createElement("div");
        row.className = "queue-row";
        const details = document.createElement("div");
        const name = document.createElement("div");
        name.className = "queue-name";
        name.textContent = item.name;
        const status = document.createElement("div");
        status.className = "queue-status";
        status.textContent = item.status;
        details.append(name, status);
        const size = document.createElement("span");
        size.className = "meta";
        size.textContent = formatSize(item.size);
        row.append(details, size);
        uploadQueue.append(row);
      }
    }

    async function uploadFiles(files, isFolder = false) {
      const selected = [...files];
      if (!selected.length) return;

      uploadItems = selected.map((file) => ({
        name: file.webkitRelativePath || file.name,
        size: file.size,
        status: "Waiting",
        folderPath: file.webkitRelativePath || ""
      }));
      renderUploadQueue();
      progress.classList.add("active");
      uploadCanceled = false;
      uploadPaused = false;
      if (pauseUpload) {
        pauseUpload.textContent = "Pause";
        pauseUpload.style.display = "inline-flex";
      }
      if (sha256Display) sha256Display.style.display = "none";
      progressBar.style.width = "0%";

      const isMultiFileOrFolder = selected.length > 1 || isFolder || Boolean(selected[0]?.webkitRelativePath);
      progressText.textContent = isMultiFileOrFolder
        ? `Uploading ${isFolder ? "folder" : "files"} (0 / ${selected.length})...`
        : `Uploading ${selected[0].name}...`;

      const queue = selected.map((file, i) => ({
        file,
        index: i,
        relPath: file.webkitRelativePath || ""
      }));

      let activeCount = 0;
      let completedCount = 0;
      let hasError = false;
      let lastError = null;
      let lastCompletedHash = "";

      await new Promise((resolve) => {
        function processNext() {
          if (uploadCanceled) { resolve(); return; }
          if (queue.length === 0 && activeCount === 0) { resolve(); return; }
          while (activeCount < MAX_CONCURRENT_UPLOADS && queue.length > 0 && !uploadCanceled && !hasError) {
            const { file, index, relPath } = queue.shift();
            activeCount++;
            uploadItems[index].status = "Starting...";
            renderUploadQueue();

            uploadFileResumable(file, index, relPath).then((res) => {
              uploadItems[index].status = "Done";
              completedCount++;
              if (res?.sha256) lastCompletedHash = res.sha256;
              if (isMultiFileOrFolder) {
                progressText.textContent = `Uploading ${isFolder ? "folder" : "files"} (${completedCount} / ${selected.length}) - Current: ${file.name}`;
              }
            }).catch((err) => {
              if (!uploadCanceled) {
                hasError = true;
                lastError = err;
                uploadItems[index].status = "Error";
              }
            }).finally(() => {
              activeCount--;
              renderUploadQueue();
              processNext();
            });
          }
          if (hasError && activeCount === 0) resolve();
        }
        processNext();
      });

      try {
        if (lastError) throw lastError;
        showToast(uploadCanceled ? "Upload canceled" : "Upload complete");
        if (lastCompletedHash && sha256Display && sha256Text && !uploadCanceled) {
          sha256Text.textContent = `SHA-256 verified: ${lastCompletedHash.slice(0, 16)}...${lastCompletedHash.slice(-8)}`;
          sha256Display.className = "sha256-badge";
          sha256Display.style.display = "flex";
        }
        await Promise.all([loadFiles(), loadDashboard()]);
      } catch (error) {
        showToast(error.message);
        if (sha256Display && sha256Text) {
          sha256Text.textContent = `Upload failed: ${error.message}`;
          sha256Display.className = "sha256-badge error";
          sha256Display.style.display = "flex";
        }
      } finally {
        activeUploadRequests.clear();
        fileInput.value = "";
        if (folderInput) folderInput.value = "";
        if (uploadCanceled) {
          progress.classList.remove("active");
          progressBar.style.width = "0";
          progressText.textContent = "Waiting";
          uploadItems = [];
          renderUploadQueue();
        } else {
          window.setTimeout(() => {
            if (!uploadPaused) {
              progress.classList.remove("active");
              progressBar.style.width = "0";
              progressText.textContent = "Waiting";
              uploadItems = [];
              renderUploadQueue();
            }
          }, 3500);
        }
      }
    }

    async function saveClipboardText() {
      const text = clipInput.value;
      if (!text.trim()) {
        showToast("Clipboard text is empty");
        return;
      }
      await fetchJson("/api/clipboard", {
        method: "POST",
        body: JSON.stringify({text, expires: Number(clipExpiry.value || 0)})
      });
      clipInput.value = "";
      showToast("Clipboard saved");
      await Promise.all([loadClipboard(), loadDashboard()]);
    }

    async function pasteAndSaveClipboard() {
      try {
        const text = await navigator.clipboard.readText();
        if (!text.trim()) {
          showToast("Clipboard text is empty");
          return;
        }
        await fetchJson("/api/clipboard", {
          method: "POST",
          body: JSON.stringify({text, expires: Number(clipExpiry.value || 0)})
        });
        showToast("Clipboard inbox updated");
        await Promise.all([loadClipboard(), loadDashboard()]);
      } catch {
        showToast("Browser blocked clipboard read. Paste manually.");
      }
    }

    async function clearClipboardInbox() {
      if (!allClips.length) {
        showToast("Clipboard inbox is empty");
        return;
      }
      if (!confirm("Clear all clipboard items?")) return;
      await fetchJson("/api/clipboard", {method: "DELETE"});
      showToast("Clipboard inbox cleared");
      await Promise.all([loadClipboard(), loadDashboard()]);
    }

    function copyLatestClipboard() {
      const text = latestClipText || allClips[0]?.text || "";
      if (text) copyText(text, "Clipboard text");
    }

    function downloadLatestFile() {
      if (!latestUploadUrl) {
        showToast("No latest upload to download");
        return;
      }
      window.location.href = latestUploadUrl;
    }

    function downloadAllSharedFiles() {
      if (!allFiles.length) {
        showToast("No files to download");
        return;
      }
      window.location.href = "/api/files/download-all";
    }

    async function deleteAllSharedFiles() {
      if (!allFiles.length) {
        showToast("No files to delete");
        return;
      }
      const label = allFiles.length === 1 ? "1 shared file" : `${allFiles.length} shared files`;
      if (!confirm(`Delete ${label}?`)) return;
      const result = await fetchJson("/api/files", {method: "DELETE"});
      showToast(`${result.deleted || 0} files deleted`);
      await Promise.all([loadFiles(), loadDashboard()]);
    }

    async function loadClipboard() {
      const data = await fetchJson("/api/clipboard");
      allClips = data.items;
      renderClipboard();
    }

    function renderClipboard() {
      const items = allClips.filter((item) => matchesSearch(item.text));
      clipCount.textContent = items.length === 1 ? "1 item" : `${items.length} items`;
      copyInboxLatest.disabled = !items.length;
      clearClipboard.disabled = !allClips.length;
      if (items[0] && items[0].id !== latestClipId) {
        latestClipId = items[0].id;
      }
      if (!items.length) {
        clipList.innerHTML = '<div class="empty">No clipboard items yet.</div>';
        return;
      }
      clipList.innerHTML = "";
      for (const item of items) {
        const row = document.createElement("article");
        row.className = "clip-row";
        const details = document.createElement("div");
        details.className = "clip-details";
        const text = document.createElement("div");
        text.className = "clip-text";
        text.textContent = item.text;
        text.title = item.text;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${formatDate(item.created_at)} | ${formatRemaining(item.expires_at)}`;
        meta.title = meta.textContent;
        details.append(text, meta);

        const actions = document.createElement("div");
        actions.className = "actions";
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "secondary";
        copy.textContent = "Copy text";
        copy.addEventListener("click", () => copyText(item.text, "Clipboard text"));
        const use = document.createElement("button");
        use.type = "button";
        use.className = "secondary";
        use.textContent = "Edit";
        use.addEventListener("click", () => {
          clipInput.value = item.text;
          setView("clipboard-view");
          clipInput.focus();
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger";
        remove.textContent = "Delete";
        remove.addEventListener("click", async () => {
          await fetchJson(`/api/clipboard/${item.id}`, {method: "DELETE"});
          showToast("Clipboard deleted");
          await Promise.all([loadClipboard(), loadDashboard()]);
        });
        actions.append(copy, use, remove);
        row.append(details, actions);
        clipList.append(row);
      }
    }

    function drawQr(text) {
      try {
        const qr = qrcode(0, 'L');
        qr.addData(text);
        qr.make();
        qrImage.src = qr.createDataURL(4, 0);
      } catch (e) {
        showToast("QR Code generation failed");
      }
    }

    async function downloadSelectedZip() {
      if (!selectedFiles.size) {
        showToast("No files selected");
        return;
      }
      try {
        const response = await fetch("/api/files/download-zip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ files: Array.from(selectedFiles) })
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.error || `Download failed (${response.status})`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const disposition = response.headers.get("Content-Disposition");
        let filename = "Selected_Files.zip";
        if (disposition && disposition.includes('filename="')) {
          filename = disposition.split('filename="')[1].split('"')[0];
        }
        a.download = filename;
        document.body.append(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast("ZIP download started");
      } catch (err) {
        showToast(`Download failed: ${err.message}`);
      }
    }

    async function deleteSelectedSharedFiles() {
      const count = selectedFiles.size;
      if (!count) {
        showToast("No files selected");
        return;
      }
      const label = count === 1 ? "1 selected item" : `${count} selected items`;
      if (!confirm(`Delete ${label}?`)) return;
      try {
        const toDelete = [...selectedFiles];
        await Promise.all(
          toDelete.map((id) => fetchJson(`/api/files/${encodeURIComponent(id)}`, { method: "DELETE" }))
        );
        selectedFiles.clear();
        showToast(`${toDelete.length} item(s) deleted`);
        await Promise.all([loadFiles(), loadDashboard()]);
      } catch (err) {
        showToast(`Delete failed: ${err.message}`);
        await Promise.all([loadFiles(), loadDashboard()]);
      }
    }

    document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
    globalSearch.addEventListener("input", () => {
      renderFiles();
      renderClipboard();
    });
    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener("change", () => {
        if (selectAllCheckbox.checked) {
          for (const f of allFiles) {
            selectedFiles.add(f.path || f.name);
          }
        } else {
          selectedFiles.clear();
        }
        renderFiles();
      });
    }
    if (unselectAllBtn) {
      unselectAllBtn.addEventListener("click", () => {
        selectedFiles.clear();
        renderFiles();
      });
    }
    if (downloadSelectedFiles) {
      downloadSelectedFiles.addEventListener("click", downloadSelectedZip);
    }
    if (deleteSelectedFiles) {
      deleteSelectedFiles.addEventListener("click", deleteSelectedSharedFiles);
    }
    themeToggle.addEventListener("click", () => {
      const isDark = !document.body.classList.contains("dark");
      applyTheme(isDark);
      localStorage.setItem("pura-theme", isDark ? "dark" : "light");
    });
    checkServices.addEventListener("click", async () => {
      await checkAllServices();
      await loadDashboard();
      showToast("Service check complete");
    });
    if (runDiagnosticsBtn) {
      runDiagnosticsBtn.addEventListener("click", async () => {
        await loadNetworkDiagnostics();
        showToast("Diagnostics updated");
      });
    }
    copyLatestClip.addEventListener("click", copyLatestClipboard);
    copyInboxLatest.addEventListener("click", copyLatestClipboard);
    pasteSaveClipboard.addEventListener("click", pasteAndSaveClipboard);
    clearClipboard.addEventListener("click", clearClipboardInbox);
    downloadLatestUpload.addEventListener("click", downloadLatestFile);
    downloadAllFiles.addEventListener("click", downloadAllSharedFiles);
    deleteAllFiles.addEventListener("click", deleteAllSharedFiles);
    copyPage.addEventListener("click", () => {
      const urlToCopy = (infoCache && infoCache.lan_url) || currentUrl.textContent || window.location.href;
      copyText(urlToCopy, "Share link");
    });
    copyLan.addEventListener("click", () => copyText(infoCache?.lan_url || window.location.href, "LAN link"));
    refreshButton.addEventListener("click", async () => {
      await Promise.all([loadInfo(), loadFiles(), loadClipboard(), loadDashboard()]);
      showToast("Refreshed");
    });
    chooseButton.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => uploadFiles(fileInput.files));
    if (chooseFolderButton && folderInput) {
      chooseFolderButton.addEventListener("click", () => folderInput.click());
      folderInput.addEventListener("change", () => uploadFiles(folderInput.files, true));
    }
    if (pauseUpload) {
      pauseUpload.addEventListener("click", () => {
        uploadPaused = !uploadPaused;
        if (uploadPaused) {
          pauseUpload.textContent = "Resume";
          progressText.textContent = "Upload paused";
        } else {
          pauseUpload.textContent = "Pause";
          progressText.textContent = "Resuming upload...";
        }
      });
    }
    cancelUpload.addEventListener("click", () => {
      uploadCanceled = true;
      uploadPaused = false;
      if (pauseUpload) pauseUpload.textContent = "Pause";
      for (const req of activeUploadRequests) req.abort();
      activeUploadRequests.clear();
      progress.classList.remove("active");
      progressBar.style.width = "0";
      progressText.textContent = "Waiting";
      uploadItems = [];
      renderUploadQueue();
      showToast("Upload canceled");
    });
    saveClipboard.addEventListener("click", saveClipboardText);
    closePreview.addEventListener("click", () => previewDialog.close());
    function openArtwork(card) {
      modalArtwork.src = card.dataset.artSrc;
      modalArtwork.alt = card.querySelector("img")?.alt || "Dove dashboard artwork";
      doveDialog.showModal();
      closeDove.focus();
    }

    artworkCards.forEach((card) => {
      card.addEventListener("click", () => openArtwork(card));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openArtwork(card);
        }
      });
    });
    closeDove.addEventListener("click", () => doveDialog.close());
    supportBtn?.addEventListener("click", () => {
      supportDialog?.showModal();
      closeSupport?.focus();
    });
    closeSupport?.addEventListener("click", () => supportDialog?.close());

    const heartColors = [
      "#ff2d55", "#e0245e", "#ff375f", "#ff6482", "#ff4b72",
      "#ff7597", "#f43f5e", "#ec4899", "#f59e0b", "#a855f7",
      "#38bdf8", "#8b5cf6", "#10b981", "#fbbf24"
    ];

    function spawnFloatingHeart(customX, customY) {
      if (!supportHeartBadge) return;
      const container = floatingHeartsLayer || supportDialog || document.body;
      const heart = document.createElement("div");
      heart.className = "floating-heart";

      const dialogRect = supportDialog?.getBoundingClientRect() || { left: 0, top: 0 };
      const badgeRect = supportHeartBadge.getBoundingClientRect();

      let startX = (badgeRect.left - dialogRect.left) + badgeRect.width / 2;
      let startY = (badgeRect.top - dialogRect.top) + badgeRect.height / 2;

      if (customX !== undefined && customY !== undefined && supportDialog) {
        startX = customX - dialogRect.left;
        startY = customY - dialogRect.top;
      }

      // Add slight jitter around center
      startX += Math.floor(Math.random() * 20 - 10);
      startY += Math.floor(Math.random() * 16 - 8);

      const color = heartColors[Math.floor(Math.random() * heartColors.length)];
      const size = Math.floor(Math.random() * 14) + 24;
      const scale = (Math.random() * 0.4 + 0.95).toFixed(2);
      const sway1 = (Math.random() * 50 - 25).toFixed(0) + "px";
      const sway2 = (Math.random() * 70 - 35).toFixed(0) + "px";
      const sway3 = (Math.random() * 60 - 30).toFixed(0) + "px";
      const sway4 = (Math.random() * 50 - 25).toFixed(0) + "px";
      const sway5 = (Math.random() * 40 - 20).toFixed(0) + "px";
      const rot1 = (Math.random() * 32 - 16).toFixed(0) + "deg";
      const rot2 = (Math.random() * 38 - 19).toFixed(0) + "deg";
      const duration = (Math.random() * 0.5 + 2.0).toFixed(2) + "s";

      heart.style.left = `${startX}px`;
      heart.style.top = `${startY}px`;
      heart.style.width = `${size}px`;
      heart.style.height = `${size}px`;
      heart.style.color = color;
      heart.style.animationDuration = duration;
      heart.style.setProperty("--scale", scale);
      heart.style.setProperty("--sway-1", sway1);
      heart.style.setProperty("--sway-2", sway2);
      heart.style.setProperty("--sway-3", sway3);
      heart.style.setProperty("--sway-4", sway4);
      heart.style.setProperty("--sway-5", sway5);
      heart.style.setProperty("--rot-1", rot1);
      heart.style.setProperty("--rot-2", rot2);

      heart.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';

      container.appendChild(heart);
      heart.addEventListener("animationend", () => heart.remove());
    }

    supportHeartBadge?.addEventListener("click", (event) => {
      event.stopPropagation();
      const x = event.clientX;
      const y = event.clientY;
      spawnFloatingHeart(x, y);
      if (Math.random() > 0.4) setTimeout(() => spawnFloatingHeart(x, y), 60);
      if (Math.random() > 0.7) setTimeout(() => spawnFloatingHeart(x, y), 120);
    });

    supportHeartBadge?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        spawnFloatingHeart();
      }
    });
    copyUpiBtn?.addEventListener("click", () => {
      copyText("navinbalaji004@okhdfcbank", "UPI ID");
    });
    upiQrBtn?.addEventListener("click", () => {
      upiQrDialog?.showModal();
      closeUpiQr?.focus();
    });
    closeUpiQr?.addEventListener("click", () => upiQrDialog?.close());
    copyUpiModalBtn?.addEventListener("click", () => {
      copyText("navinbalaji004@okhdfcbank", "UPI ID");
    });

    [previewDialog, doveDialog, supportDialog, upiQrDialog].forEach((dlg) => {
      dlg?.addEventListener("click", (event) => {
        if (event.target === dlg) {
          dlg.close();
        }
      });
    });
    lockButton.addEventListener("click", async () => {
      await fetchJson("/api/logout", {method: "POST"}).catch(() => {});
      localStorage.removeItem("pura-trusted");
      sessionStorage.removeItem("pura_active");
      showAuth();
      showToast("Dashboard locked");
    });
    if (securityToggle) {
      securityToggle.addEventListener("change", () => {
        const willEnable = securityToggle.checked;
        const currentlyEnabled = Boolean(infoCache && infoCache.auth_enabled);
        if (toggleLabelText) {
          toggleLabelText.textContent = willEnable ? "PIN Protection is Enabled" : "Require PIN to open dashboard";
        }
        if (newPinField) {
          newPinField.style.display = willEnable ? "grid" : (currentlyEnabled ? "none" : "grid");
        }
        if (newPinLabel) {
          newPinLabel.textContent = willEnable && currentlyEnabled ? "New PIN / Password" : "Set PIN / Password";
        }
        if (saveSecurityBtn) {
          saveSecurityBtn.textContent = willEnable ? (currentlyEnabled ? "Update PIN / Security" : "Save & Enable PIN") : "Save & Disable PIN";
        }
      });
    }

    if (togglePinVisibility) {
      togglePinVisibility.addEventListener("click", () => {
        const isPassword = newPinInput.type === "password";
        newPinInput.type = isPassword ? "text" : "password";
        togglePinVisibility.textContent = isPassword ? "Hide" : "Show";
      });
    }

    if (toggleCurrentPinVisibility) {
      toggleCurrentPinVisibility.addEventListener("click", () => {
        const isPassword = currentPinInput.type === "password";
        currentPinInput.type = isPassword ? "text" : "password";
        toggleCurrentPinVisibility.textContent = isPassword ? "Hide" : "Show";
      });
    }

    [newPinInput, currentPinInput].forEach((input) => {
      input?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          saveSecurityBtn?.click();
        }
      });
    });

    if (saveSecurityBtn) {
      saveSecurityBtn.addEventListener("click", async () => {
        const enableAuth = securityToggle.checked;
        let newPin = newPinInput.value.trim();
        const currentPin = currentPinInput.value.trim();
        const currentlyEnabled = Boolean(infoCache && infoCache.auth_enabled);

        // If PIN protection is currently active, require current PIN
        if (currentlyEnabled) {
          if (!currentPin) {
            showToast("Please enter your current PIN to authorize this change");
            currentPinInput.focus();
            return;
          }
          if (enableAuth && !newPin) {
            showToast("Please enter a new PIN (or uncheck toggle to disable)");
            newPinInput.focus();
            return;
          }
        } else {
          if (enableAuth && !newPin) {
            showToast("Please enter a PIN to enable protection");
            newPinInput.focus();
            return;
          }
        }

        try {
          const payload = {
            auth_enabled: enableAuth,
            pin: newPin || undefined,
            current_pin: currentPin || undefined
          };
          const res = await fetchJson("/api/security", {
            method: "POST",
            body: JSON.stringify(payload)
          });
          if (res.auth_enabled) {
            showToast(newPin ? "PIN updated and active" : "PIN protection enabled");
          } else {
            showToast("PIN protection disabled");
          }
          newPinInput.value = "";
          currentPinInput.value = "";
          await loadInfo();
        } catch (error) {
          showToast(error.message);
        }
      });
    }
    readSystemClipboard.addEventListener("click", async () => {
      try {
        clipInput.value = await navigator.clipboard.readText();
        clipInput.focus();
      } catch {
        showToast("Browser blocked clipboard read. Paste manually.");
      }
    });

    authForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        if (infoCache && infoCache.auth_enabled) {
          await fetchJson("/api/login", {
            method: "POST",
            body: JSON.stringify({pin: pinInput.value, trusted: trustDevice.checked})
          });
          localStorage.setItem("pura-trusted", trustDevice.checked ? "true" : "false");
          pinInput.value = "";
        }
        sessionStorage.setItem("pura_active", "true");
        await start();
      } catch (error) {
        showToast(error.message);
      }
    });

    for (const eventName of ["dragenter", "dragover"]) {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("dragover");
      });
    }
    for (const eventName of ["dragleave", "drop"]) {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.remove("dragover");
      });
    }
    dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));

    document.addEventListener("paste", (event) => {
      const files = [...(event.clipboardData?.files || [])];
      if (files.length) {
        uploadFiles(files);
        return;
      }
      const text = event.clipboardData?.getData("text");
      if (text && document.activeElement !== clipInput) {
        clipInput.value = text;
        setView("clipboard-view");
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
        event.preventDefault();
        globalSearch.focus();
      }
      if (event.key === "Escape" && previewDialog.open) previewDialog.close();
      if (event.key === "Escape" && doveDialog.open) doveDialog.close();
      if (event.key === "Escape" && supportDialog?.open) supportDialog.close();
      if (event.key === "Escape" && upiQrDialog?.open) upiQrDialog.close();
    });

    // Android / touch device scroll chaining:
    // When an inner dashboard container (files list, clipboard list, etc.) reaches its end,
    // continue scrolling smoothly in the main page during touch drag gestures.
    (function initAndroidScrollChaining() {
      let activeScroller = null;
      let lastClientY = 0;
      let lastClientX = 0;
      let startedAtBottom = false;
      let startedAtTop = false;

      function getDashboardScroller(el) {
        if (!el || (el.closest && el.closest("dialog, .modal"))) return null;
        let curr = el;
        while (curr && curr !== document.body && curr !== document.documentElement) {
          if (curr.classList && (
            curr.classList.contains("list") ||
            curr.classList.contains("panel-body") ||
            curr.classList.contains("dropzone") ||
            curr.classList.contains("activity-list")
          )) {
            if (curr.scrollHeight > curr.clientHeight + 1) {
              const style = window.getComputedStyle(curr);
              if (style.overflowY === "auto" || style.overflowY === "scroll") {
                return curr;
              }
            }
          }
          curr = curr.parentElement;
        }
        return null;
      }

      document.addEventListener("touchstart", (e) => {
        if (e.touches.length !== 1) {
          activeScroller = null;
          return;
        }
        const touch = e.touches[0];
        activeScroller = getDashboardScroller(e.target);
        if (!activeScroller) return;

        lastClientY = touch.clientY;
        lastClientX = touch.clientX;
        startedAtTop = activeScroller.scrollTop <= 1;
        startedAtBottom = activeScroller.scrollTop + activeScroller.clientHeight >= activeScroller.scrollHeight - 1;
      }, { passive: true });

      document.addEventListener("touchmove", (e) => {
        if (!activeScroller || e.touches.length !== 1) return;
        const touch = e.touches[0];
        const deltaY = lastClientY - touch.clientY; // > 0: finger moving UP (scrolling DOWN)
        const deltaX = lastClientX - touch.clientX;
        lastClientY = touch.clientY;
        lastClientX = touch.clientX;

        // Ignore predominantly horizontal swipes
        if (Math.abs(deltaY) <= Math.abs(deltaX) || Math.abs(deltaY) < 0.5) return;

        const scroller = activeScroller;
        const maxScroll = scroller.scrollHeight - scroller.clientHeight;
        const atBottom = scroller.scrollTop >= maxScroll - 1;
        const atTop = scroller.scrollTop <= 1;

        // If user scrolls inside the container, reset initial boundary lock
        if (scroller.scrollTop > 8) startedAtTop = false;
        if (scroller.scrollTop < maxScroll - 8) startedAtBottom = false;

        if (deltaY > 0 && atBottom) {
          // Scrolling down and inner container is at bottom -> continue scrolling in main page!
          if (!startedAtBottom) {
            window.scrollBy({ top: deltaY, left: 0, behavior: "instant" });
          }
        } else if (deltaY < 0 && atTop) {
          // Scrolling up and inner container is at top -> continue scrolling in main page!
          if (!startedAtTop) {
            window.scrollBy({ top: deltaY, left: 0, behavior: "instant" });
          }
        }
      }, { passive: true });

      function endTouch() {
        activeScroller = null;
      }
      document.addEventListener("touchend", endTouch, { passive: true });
      document.addEventListener("touchcancel", endTouch, { passive: true });
    })();

    async function start() {
      await loadInfo();
      await Promise.all([loadFiles(), loadClipboard(), loadDashboard()]);
      connectEvents();
      unlockApp();
    }

    function connectEvents() {
      if (eventSource) return;
      eventSource = new EventSource("/api/events");
      eventSource.addEventListener("update", async () => {
        await Promise.all([loadInfo(), loadFiles(), loadClipboard(), loadDashboard()]).catch(() => {});
      });
      eventSource.addEventListener("error", () => {
        eventSource.close();
        eventSource = null;
        window.setTimeout(() => {
          if (!document.body.classList.contains("locked")) connectEvents();
        }, 3000);
      });
    }

    loadInfo().then(() => {
      if (!infoCache || !infoCache.auth_enabled || infoCache.is_authenticated || sessionStorage.getItem("pura_active") === "true") {
        start().catch((error) => {
          if (error.message !== "PIN required") showToast(error.message);
        });
      }
    }).catch((error) => {
      if (error.message !== "PIN required") showToast(error.message);
    });
    window.setInterval(() => {
      if (!eventSource && !document.body.classList.contains("locked")) {
        loadFiles().catch(() => {});
        loadClipboard().catch(() => {});
        loadDashboard().catch(() => {});
      }
    }, 30000);
  </script>
</body>
</html>
"""


WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def sanitize_filename(name: str) -> str:
    cleaned = Path(name).name.strip()
    cleaned = re.sub(r"[^\w .()@+-]", "_", cleaned, flags=re.ASCII)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return f"upload-{int(time.time())}"
    stem = Path(cleaned).stem
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def sanitize_folder_path(relative_path: str) -> str | None:
    """Sanitize a browser-provided relative folder path.

    Returns a safe relative path string (using '/' separators) or None if the
    path is malicious/invalid. Each component is run through sanitize_filename()
    and checked against directory-traversal, absolute-path, drive-letter, and
    UNC-path attacks.
    """
    if not relative_path or not str(relative_path).strip():
        return None

    raw = str(relative_path).strip().replace("\\", "/")

    # Reject absolute paths, UNC paths, drive-letter paths
    if raw.startswith("/") or raw.startswith("\\"):
        return None
    if len(raw) >= 2 and raw[1] == ":":
        return None
    if raw.startswith("//") or raw.startswith("\\\\"):
        return None

    parts = raw.split("/")
    safe_parts: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            return None  # reject traversal
        cleaned = sanitize_filename(part)
        if not cleaned:
            return None
        safe_parts.append(cleaned)

    if not safe_parts:
        return None

    return "/".join(safe_parts)


def unique_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.exists():
        return path

    stem = path.stem or "file"
    suffix = path.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def get_all_lan_ips() -> list[str]:
    ips = set()
    primary = get_lan_ip()
    if primary and not primary.startswith("127."):
        ips.add(primary)
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.add(ip)
    except Exception:
        pass
    return sorted(list(ips)) if ips else ["127.0.0.1"]


def cert_matches_lan_ips(cert_path: Path, expected_ips: list[str], expected_dns: list[str] | None = None) -> bool:
    """Check if an existing certificate file contains all expected IP and DNS Subject Alternative Names."""
    if not cert_path.exists():
        return False
    try:
        raw_pem = cert_path.read_bytes()
        import base64
        b64 = b"".join(line.strip() for line in raw_pem.splitlines() if line and not line.startswith(b"-----"))
        der = base64.b64decode(b64)

        # Check for SAN OID 2.5.29.17 (\x55\x1d\x11)
        if b"\x55\x1d\x11" not in der:
            return False

        # Verify all expected IPs are present as \x87\x04<raw_ip>
        for ip in expected_ips:
            try:
                raw_ip = socket.inet_aton(ip)
                if b"\x87\x04" + raw_ip not in der:
                    return False
            except Exception:
                return False

        # Verify expected DNS
        expected_dns = expected_dns or ["localhost"]
        for dns in expected_dns:
            d_bytes = dns.encode("ascii", errors="ignore")
            if d_bytes not in der:
                return False

        return True
    except Exception:
        return False


def generate_self_signed_cert(
    cert_path: Path,
    key_path: Path,
    san_ips: list[str] | str | None = None,
    san_dns: list[str] | None = None
) -> bool:
    """Generate a 2048-bit self-signed certificate with IP/DNS SANs.

    Uses the OpenSSL command-line tool when available and falls back to the
    built-in Python implementation when OpenSSL is unavailable.
    """
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize SAN IPs
    if isinstance(san_ips, str):
        raw_ip_list = [san_ips]
    elif san_ips is None:
        raw_ip_list = get_all_lan_ips()
    else:
        raw_ip_list = list(san_ips)

    unique_ips: list[str] = []
    for ip in raw_ip_list + ["127.0.0.1"]:
        if ip and ip not in unique_ips:
            try:
                socket.inet_aton(ip)
                unique_ips.append(ip)
            except Exception:
                pass

    unique_dns: list[str] = ["localhost"]
    if san_dns:
        for d in san_dns:
            if d and d not in unique_dns:
                unique_dns.append(d)

    # Strategy 1: Use OpenSSL CLI with SAN config when available; fall back to pure Python below.
    if shutil.which("openssl"):
        cnf_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".cnf", encoding="utf-8") as cnf:
                cnf_path = Path(cnf.name)
                cnf.write("[req]\n")
                cnf.write("distinguished_name = req_distinguished_name\n")
                cnf.write("x509_extensions = v3_req\n")
                cnf.write("prompt = no\n\n")
                cnf.write("[req_distinguished_name]\n")
                cnf.write("CN = Pura Server\n\n")
                cnf.write("[v3_req]\n")
                cnf.write("subjectAltName = @alt_names\n\n")
                cnf.write("[alt_names]\n")
                for i, d in enumerate(unique_dns, 1):
                    cnf.write(f"DNS.{i} = {d}\n")
                for i, ip in enumerate(unique_ips, 1):
                    cnf.write(f"IP.{i} = {ip}\n")

            cmd = [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key_path), "-out", str(cert_path),
                "-days", "365", "-nodes",
                "-config", str(cnf_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cnf_path.unlink(missing_ok=True)
            return True
        except Exception:
            if cnf_path and cnf_path.exists():
                cnf_path.unlink(missing_ok=True)

    # Strategy 2: Pure-Python standard-library RSA 2048 & ASN.1 DER fallback with SAN extension
    try:
        def is_prime(n, k=30):
            if n < 2: return False
            if n in (2, 3): return True
            if n % 2 == 0: return False
            r, s = 0, n - 1
            while s % 2 == 0:
                r += 1
                s //= 2
            for _ in range(k):
                a = secrets.randbelow(n - 4) + 2
                x = pow(a, s, n)
                if x == 1 or x == n - 1:
                    continue
                for _ in range(r - 1):
                    x = pow(x, 2, n)
                    if x == n - 1:
                        break
                else:
                    return False
            return True

        def get_prime(bits=1024):
            while True:
                p = secrets.randbits(bits) | (1 << (bits - 1)) | 1
                if is_prime(p):
                    return p

        def der_len(length):
            if length < 128:
                return bytes([length])
            len_bytes = []
            while length > 0:
                len_bytes.append(length & 0xFF)
                length >>= 8
            len_bytes.reverse()
            return bytes([0x80 | len(len_bytes)]) + bytes(len_bytes)

        def der_seq(*items):
            payload = b''.join(items)
            return b'\x30' + der_len(len(payload)) + payload

        def der_int(val):
            b = []
            while val > 0:
                b.append(val & 0xFF)
                val >>= 8
            if not b:
                b = [0]
            b.reverse()
            if b[0] & 0x80:
                b.insert(0, 0)
            payload = bytes(b)
            return b'\x02' + der_len(len(payload)) + payload

        def der_bit_string(data):
            payload = b'\x00' + data
            return b'\x03' + der_len(len(payload)) + payload

        def der_printable_string(s):
            payload = s.encode('ascii', errors='ignore')
            return b'\x13' + der_len(len(payload)) + payload

        def der_utc_time(dt):
            payload = dt.strftime('%y%m%d%H%M%SZ').encode('ascii')
            return b'\x17' + der_len(len(payload)) + payload

        def b64_wrap(tag, data):
            import base64
            b64 = base64.b64encode(data).decode('ascii')
            lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
            return f"-----BEGIN {tag}-----\n" + "\n".join(lines) + f"\n-----END {tag}-----\n"

        e = 65537
        p = get_prime(1024)
        q = get_prime(1024)
        while p == q:
            q = get_prime(1024)
        n = p * q
        phi = (p - 1) * (q - 1)
        d = pow(e, -1, phi)
        dp = d % (p - 1)
        dq = d % (q - 1)
        qinv = pow(q, -1, p)

        rsa_key_der = der_seq(
            der_int(0), der_int(n), der_int(e), der_int(d),
            der_int(p), der_int(q), der_int(dp), der_int(dq), der_int(qinv)
        )
        alg_id = der_seq(b'\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01', b'\x05\x00')
        priv_key_info = der_seq(
            der_int(0), alg_id, b'\x04' + der_len(len(rsa_key_der)) + rsa_key_der
        )
        pub_key_bitstr = der_bit_string(der_seq(der_int(n), der_int(e)))
        spki = der_seq(alg_id, pub_key_bitstr)
        serial = secrets.randbits(64)
        cn_str = "Pura Server"
        cn_atv = der_seq(b'\x06\x03\x55\x04\x03', der_printable_string(cn_str[:64]))
        rdn = b'\x31' + der_len(len(cn_atv)) + cn_atv
        name = der_seq(rdn)

        # Validity: UTC time backdated 1 day for client skew, valid 1 year
        now_utc = datetime.now(timezone.utc)
        validity = der_seq(
            der_utc_time(now_utc - timedelta(days=1)),
            der_utc_time(now_utc + timedelta(days=365))
        )
        sig_alg = der_seq(b'\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x0b', b'\x05\x00')

        # Build Subject Alternative Name (SAN) entries
        san_entries = []
        for dns in unique_dns:
            d_bytes = dns.encode('ascii', errors='ignore')
            san_entries.append(b'\x82' + der_len(len(d_bytes)) + d_bytes)
        for ip in unique_ips:
            try:
                raw_ip = socket.inet_aton(ip)
                san_entries.append(b'\x87\x04' + raw_ip)
            except Exception:
                pass

        san_gen_names = der_seq(*san_entries)
        # OID 2.5.29.17 (\x55\x1d\x11) + OCTET STRING containing GeneralNames sequence
        san_ext = der_seq(b'\x06\x03\x55\x1d\x11', b'\x04' + der_len(len(san_gen_names)) + san_gen_names)
        exts_seq = der_seq(san_ext)
        exts_explicit = b'\xa3' + der_len(len(exts_seq)) + exts_seq

        tbs_cert = der_seq(
            b'\xa0\x03\x02\x01\x02',
            der_int(serial),
            sig_alg,
            name,
            validity,
            name,
            spki,
            exts_explicit
        )
        h = hashlib.sha256(tbs_cert).digest()
        digest_info = b'\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20' + h
        mod_len = (n.bit_length() + 7) // 8
        pad_len = mod_len - 3 - len(digest_info)
        em = b'\x00\x01' + (b'\xff' * pad_len) + b'\x00' + digest_info
        em_int = int.from_bytes(em, 'big')
        sig_int = pow(em_int, d, n)
        sig_bytes = sig_int.to_bytes(mod_len, 'big')
        cert_der = der_seq(tbs_cert, sig_alg, der_bit_string(sig_bytes))

        key_path.write_text(b64_wrap("PRIVATE KEY", priv_key_info), encoding="utf-8")
        cert_path.write_text(b64_wrap("CERTIFICATE", cert_der), encoding="utf-8")
        return True
    except Exception as exc:
        print(f"Warning: Failed to generate self-signed certificate: {exc}")
        return False


def get_broadcast_targets() -> list[str]:
    """Calculate all subnet-directed broadcast addresses and loopback/global fallbacks for active interfaces."""
    targets = set()
    targets.add("127.0.0.1")
    targets.add("255.255.255.255")

    all_ips = get_all_lan_ips()
    for ip in all_ips:
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        parts = ip.split(".")
        if len(parts) == 4:
            targets.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
            if parts[0] == "10":
                targets.add(f"{parts[0]}.{parts[1]}.255.255")
                targets.add(f"{parts[0]}.255.255.255")
            elif parts[0] == "172" and 16 <= int(parts[1]) <= 31:
                targets.add(f"{parts[0]}.{parts[1]}.255.255")

    return sorted(list(targets))


class LanDiscoveryService:
    def __init__(
        self,
        server_id: str,
        server_name: str,
        protocol: str,
        port: int,
        lan_url: str,
        auth_enabled: bool = False,
        on_peers_changed: Any | None = None,
        debug: bool = False,
    ):
        self.server_id = server_id
        self.server_name = server_name
        self.protocol = protocol
        self.port = port
        self.lan_url = lan_url
        self.auth_enabled = auth_enabled
        self.on_peers_changed = on_peers_changed
        self.debug = debug
        self.discovered_peers: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.running = False
        self.broadcast_thread: threading.Thread | None = None
        self.listen_thread: threading.Thread | None = None
        self.status = "Initializing"
        self.packets_sent = 0
        self.packets_received = 0
        self.last_broadcast_time: float | None = None
        self.last_received_time: float | None = None
        self.broadcast_targets: list[str] = []

    def start(self) -> None:
        self.running = True
        self.status = "Active"
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True, name="Pura-Discovery-Broadcast")
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True, name="Pura-Discovery-Listen")
        self.broadcast_thread.start()
        self.listen_thread.start()
        if self.debug:
            print(f"[DISCOVERY] Service started (Server ID: {self.server_id}, Port: {self.port}, UDP Port: {DISCOVERY_PORT})")

    def stop(self) -> None:
        self.running = False
        self.status = "Stopped"
        if self.debug:
            print("[DISCOVERY] Service stopped")

    def _broadcast_loop(self) -> None:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
        except Exception as e:
            self.status = f"Broadcast unavailable ({e})"
            if self.debug:
                print(f"[DISCOVERY] Error creating broadcast socket: {e}")
            return

        while self.running:
            try:
                lan_ip = get_lan_ip()
                packet = {
                    "service": "pura",
                    "version": "1.0",
                    "server_id": self.server_id,
                    "name": self.server_name,
                    "protocol": self.protocol,
                    "host": lan_ip,
                    "port": self.port,
                    "url": f"{self.protocol}://{lan_ip}:{self.port}/",
                    "auth_enabled": self.auth_enabled,
                }
                data = json.dumps(packet).encode("utf-8")
                targets = get_broadcast_targets()
                self.broadcast_targets = targets

                sent_count = 0
                for target_ip in targets:
                    try:
                        sock.sendto(data, (target_ip, DISCOVERY_PORT))
                        sent_count += 1
                    except OSError:
                        pass

                self.packets_sent += sent_count
                self.last_broadcast_time = time.time()
                if self.debug:
                    print(f"[DISCOVERY] Sent announcement packet to {sent_count}/{len(targets)} targets ({', '.join(targets)}) from {lan_ip}:{self.port}")
            except Exception as exc:
                if self.debug:
                    print(f"[DISCOVERY] Error during broadcast send: {exc}")

            # Clean up stale peers (> 15 seconds without packet)
            now = time.time()
            expired_any = False
            with self.lock:
                stale = [pid for pid, p in self.discovered_peers.items() if now - p.get("last_seen", 0) > 15]
                for pid in stale:
                    p_info = self.discovered_peers.pop(pid, None)
                    expired_any = True
                    if self.debug and p_info:
                        print(f"[DISCOVERY] Peer expired (timeout): {pid} ({p_info.get('url')})")

            if expired_any and self.on_peers_changed:
                try:
                    self.on_peers_changed()
                except Exception:
                    pass

            for _ in range(30):
                if not self.running:
                    break
                time.sleep(0.1)

        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def _listen_loop(self) -> None:
        recv_sock = None
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            recv_sock.bind(("", DISCOVERY_PORT))
            recv_sock.settimeout(1.0)
        except Exception as e:
            self.status = f"Listen unavailable ({e})"
            if self.debug:
                print(f"[DISCOVERY] Error binding UDP listen socket: {e}")
            return

        while self.running:
            try:
                data, addr = recv_sock.recvfrom(4096)
                if not data:
                    continue
                self.packets_received += 1
                self.last_received_time = time.time()

                try:
                    packet = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception:
                    continue

                if not isinstance(packet, dict):
                    continue
                if packet.get("service") != "pura":
                    continue

                peer_id = str(packet.get("server_id", "")).strip()
                if not peer_id or peer_id == self.server_id:
                    continue

                # Strict validation of received untrusted metadata
                peer_protocol = str(packet.get("protocol", "http")).lower().strip()
                if peer_protocol not in ("http", "https"):
                    continue

                try:
                    peer_port = int(packet.get("port", 8000))
                    if not (1 <= peer_port <= 65535):
                        continue
                except (ValueError, TypeError):
                    continue

                peer_name = str(packet.get("name", "Pura Server"))[:60].strip() or "Pura Server"
                # Never trust host/url advertised by an unauthenticated UDP peer.
                # The packet sender address is the authoritative LAN host.
                peer_host = addr[0]
                peer_url = f"{peer_protocol}://{peer_host}:{peer_port}/"

                peer_auth = bool(packet.get("auth_enabled", False))

                is_new_or_changed = False
                with self.lock:
                    existing = self.discovered_peers.get(peer_id)
                    if not existing or existing.get("url") != peer_url or existing.get("name") != peer_name:
                        is_new_or_changed = True

                    # Limit tracked peers to prevent memory exhaustion
                    if len(self.discovered_peers) >= 50 and peer_id not in self.discovered_peers:
                        oldest_k = min(self.discovered_peers.keys(), key=lambda k: self.discovered_peers[k].get("last_seen", 0))
                        del self.discovered_peers[oldest_k]

                    self.discovered_peers[peer_id] = {
                        "server_id": peer_id,
                        "name": peer_name,
                        "protocol": peer_protocol,
                        "host": peer_host,
                        "port": peer_port,
                        "url": peer_url,
                        "auth_enabled": peer_auth,
                        "last_seen": time.time(),
                    }

                if self.debug and is_new_or_changed:
                    print(f"[DISCOVERY] Peer registered/updated: {peer_name} ({peer_id}) -> {peer_url} (Auth: {peer_auth})")

                if is_new_or_changed and self.on_peers_changed:
                    try:
                        self.on_peers_changed()
                    except Exception:
                        pass
            except (socket.timeout, OSError):
                continue
            except Exception as exc:
                if self.debug:
                    print(f"[DISCOVERY] Error processing packet: {exc}")
                continue

        if recv_sock:
            try:
                recv_sock.close()
            except Exception:
                pass

    def get_peers(self) -> list[dict]:
        now = time.time()
        with self.lock:
            stale = [pid for pid, p in self.discovered_peers.items() if now - p.get("last_seen", 0) > 15]
            for pid in stale:
                self.discovered_peers.pop(pid, None)
            return [
                {
                    "server_id": pid,
                    "name": p["name"],
                    "protocol": p["protocol"],
                    "host": p["host"],
                    "port": p["port"],
                    "url": p["url"],
                    "auth_enabled": p["auth_enabled"],
                    "last_seen_sec": int(max(0, now - p["last_seen"])),
                }
                for pid, p in sorted(self.discovered_peers.items(), key=lambda item: item[1].get("last_seen", 0), reverse=True)
            ]


def parse_json_body(handler: BaseHTTPRequestHandler, limit: int = 1024 * 1024) -> dict:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except ValueError:
        raise ValueError("Invalid Content-Length header")
    if length > limit:
        raise ValueError("Request body is too large")
    if length <= 0:
        return {}
    body = handler.rfile.read(length)
    return json.loads(body.decode("utf-8"))


def load_device_names(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value)[:36] for key, value in data.items() if str(value).strip()}


def save_device_names(path: Path, names: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def load_server_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_server_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def load_file_expiry(path: Path, share_dir: Path) -> dict[str, float]:
    """Load persisted file expiry map, pruning stale/expired entries."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    result: dict[str, float] = {}
    share_root = share_dir.resolve()
    for rel_key, expires_at in data.items():
        try:
            ts = float(expires_at)
        except (TypeError, ValueError):
            continue
        try:
            file_path = (share_dir / str(rel_key).replace("/", os.sep)).resolve()
            file_path.relative_to(share_root)
        except (OSError, ValueError):
            continue
        if not file_path.is_file():
            continue
        if ts <= now:
            try:
                file_path.unlink()
            except OSError:
                pass
            continue
        result[str(rel_key).replace("\\", "/")] = ts
    return result


def save_file_expiry(path: Path, expiry: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(expiry, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a Range header like 'bytes=start-end'. Returns (start, end) inclusive or None."""
    if not range_header.startswith("bytes="):
        return None
    range_spec = range_header[6:].strip()
    if "," in range_spec:
        return None  # multi-range not supported
    if range_spec.startswith("-"):
        try:
            suffix_len = int(range_spec[1:])
        except ValueError:
            return None
        if suffix_len <= 0:
            return None
        start = max(0, file_size - suffix_len)
        return (start, file_size - 1)
    parts = range_spec.split("-", 1)
    try:
        start = int(parts[0])
    except ValueError:
        return None
    if parts[1]:
        try:
            end = int(parts[1])
        except ValueError:
            return None
    else:
        end = file_size - 1
    if start < 0 or start >= file_size:
        return None
    end = min(end, file_size - 1)
    if start > end:
        return None
    return (start, end)


def parse_timestamp(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        timestamp = float(value)
    else:
        raw = str(value).strip()
        if not raw:
            return default
        lowered = raw.lower()
        if lowered in {"none", "null", "never", "no expiry", "no_expiry", "no-expiry"}:
            return None if default is None else default
        try:
            timestamp = float(raw)
        except ValueError:
            try:
                timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return default
    if timestamp > 10_000_000_000:
        timestamp /= 1000.0
    if timestamp < 0:
        return default
    return timestamp


def load_clipboard_items(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = None
        for key in ("items", "clipboard_items", "clipboard", "texts", "data"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                raw_items = candidate
                break
        if raw_items is None:
            raw_items = next((value for value in data.values() if isinstance(value, list)), [])
    else:
        raw_items = []
    if not isinstance(raw_items, list):
        return []

    now = time.time()
    items = []
    used_ids: set[int] = set()
    next_id = 1
    for raw in raw_items:
        if isinstance(raw, dict):
            raw_id = raw.get("id", raw.get("item_id"))
            text = str(raw.get("text", raw.get("value", raw.get("content", ""))))
            created_at = parse_timestamp(
                raw.get("created_at", raw.get("created", raw.get("timestamp"))),
                default=now,
            )
            expires_at = parse_timestamp(
                raw.get("expires_at", raw.get("expires", raw.get("expire_at", raw.get("expiry")))),
                default=None,
            )
        elif isinstance(raw, str):
            raw_id = None
            text = raw
            created_at = now
            expires_at = None
        else:
            continue
        text = text.strip()
        if not text or len(text.encode("utf-8")) > MAX_CLIPBOARD_BYTES:
            continue
        # Keep persisted clipboard entries visible after restart even when
        # the old expiry timestamp is already in the past.
        if expires_at is not None and expires_at <= now:
            expires_at = None
        if created_at is None:
            created_at = now
        item_id = None
        if raw_id is not None:
            try:
                item_id = int(str(raw_id).strip())
            except (TypeError, ValueError):
                item_id = None
        if item_id is None or item_id <= 0 or item_id in used_ids:
            while next_id in used_ids:
                next_id += 1
            item_id = next_id
        used_ids.add(item_id)
        if next_id <= item_id:
            next_id = item_id + 1
        items.append({"id": item_id, "text": text, "created_at": created_at, "expires_at": expires_at})

    return sorted(items, key=lambda item: item["created_at"], reverse=True)[:MAX_CLIPBOARD_ITEMS]


def save_clipboard_items(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


class PuraHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True
    ssl_context: ssl.SSLContext | None = None

    def finish_request(self, request, client_address):
        if self.ssl_context:
            try:
                request = self.ssl_context.wrap_socket(
                    request,
                    server_side=True,
                    do_handshake_on_connect=True,
                )
            except ssl.SSLError:
                try:
                    request.close()
                except Exception:
                    pass
                return
            except Exception:
                try:
                    request.close()
                except Exception:
                    pass
                return
        super().finish_request(request, client_address)


class FileShareHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PuraLocalShare/2.0"
    share_dir: Path
    max_upload_bytes: int
    max_upload_gb: int
    asset_dir: Path
    lan_url: str
    auth_enabled: bool
    pin: str | None
    auth_token: str | None
    config_path: Path
    config_lock: threading.Lock
    clipboard_items: list[dict]
    clipboard_counter: int
    clipboard_lock: threading.Lock
    clipboard_store_path: Path
    file_expiry: dict[str, float]
    file_expiry_lock: threading.Lock
    file_expiry_path: Path
    devices: dict[str, dict]
    device_names: dict[str, str]
    device_names_path: Path
    devices_lock: threading.Lock
    event_condition: threading.Condition
    event_version: int
    resumable_uploads: dict[str, dict]
    resumable_uploads_lock: threading.Lock
    active_sse_clients: int = 0
    sse_lock: threading.Lock = threading.Lock()
    zip_semaphore: threading.Semaphore = threading.Semaphore(MAX_CONCURRENT_ZIPS)
    activity_events: list[dict]
    activity_lock: threading.Lock

    def add_activity(self, message: str) -> None:
        cls = self.__class__
        timestamp = datetime.now().strftime("%H:%M:%S")
        with cls.activity_lock:
            cls.activity_events.insert(0, {"message": message, "time": timestamp})
            if len(cls.activity_events) > MAX_ACTIVITY_EVENTS:
                cls.activity_events.pop()
        self.notify_update()

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(INDEX_HTML)
            return
        if parsed.path.startswith("/files/"):
            if not self.require_auth():
                return
            self.mark_device()
            self.send_file(parsed.path.removeprefix("/files/"), parse_qs(parsed.query).get("preview", ["0"])[0] == "1")
            return
        if parsed.path.startswith("/assets/"):
            self.send_asset(parsed.path.removeprefix("/assets/"))
            return
        if parsed.path == "/api/info":
            self.send_json(
                {
                    "share_dir": self.share_dir.name,
                    "max_upload_gb": self.max_upload_gb,
                    "lan_url": self.lan_url,
                    "protocol": getattr(self.__class__, "protocol", "http"),
                    "port": getattr(self.__class__, "port", 8000),
                    "auth_enabled": bool(self.auth_enabled),
                    "has_pin": bool(self.pin),
                    "is_authenticated": self.is_authorized(),
                }
            )
            return
        if parsed.path in ("/api/security", "/api/auth/security"):
            self.send_json(
                {
                    "auth_enabled": bool(self.auth_enabled),
                    "has_pin": bool(self.pin),
                }
            )
            return
        if not self.require_auth():
            return
        if parsed.path == "/api/network/diagnostics":
            self.send_network_diagnostics()
            return
        if parsed.path == "/api/network/peers":
            discovery_svc = getattr(self.__class__, "discovery_service", None)
            peers = discovery_svc.get_peers() if discovery_svc else []
            self.send_json({"peers": peers})
            return
        self.mark_device()
        if parsed.path == "/api/files/download-all":
            self.send_all_files_zip(parse_qs(parsed.query))
        elif parsed.path == "/api/files/download-zip":
            self.handle_download_selected_zip()
        elif parsed.path.startswith("/api/files/download-folder/"):
            self.send_folder_zip(parsed.path.removeprefix("/api/files/download-folder/"))
        elif parsed.path == "/api/files":
            self.send_files()
        elif parsed.path == "/api/upload/status":
            self.handle_upload_status(parsed)
        elif parsed.path == "/api/clipboard":
            self.send_clipboard()
        elif parsed.path == "/api/health":
            self.send_health()
        elif parsed.path == "/api/dashboard":
            self.send_dashboard()
        elif parsed.path == "/api/events":
            self.send_events()
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")

    def notify_update(self) -> None:
        with self.event_condition:
            self.__class__.event_version += 1
            self.event_condition.notify_all()

    def mark_device(self) -> None:
        agent = self.headers.get("User-Agent", "Unknown")
        short_agent = agent.split(")")[0].replace("Mozilla/5.0 (", "")[:42] or "Browser"
        key = f"{self.client_address[0]}|{short_agent}"
        now = time.time()
        cls = self.__class__
        with cls.devices_lock:
            existing = cls.devices.get(key)
            if existing is None and len(cls.devices) >= MAX_TRACKED_DEVICES:
                stale_keys = [k for k, d in cls.devices.items() if now - d.get("last_seen", 0) > 3600]
                for k in stale_keys:
                    cls.devices.pop(k, None)
                while len(cls.devices) >= MAX_TRACKED_DEVICES:
                    oldest_key = min(cls.devices.keys(), key=lambda k: cls.devices[k].get("last_seen", 0))
                    cls.devices.pop(oldest_key, None)

            saved_name = cls.device_names.get(key, "")
            device_name = existing.get("name") if existing else (saved_name or self.default_device_name(short_agent))

            is_new_connection = False
            if not existing or (now - existing.get("last_seen", 0) > 300):
                is_new_connection = True

            cls.devices[key] = {
                "id": key,
                "ip": self.client_address[0],
                "agent": short_agent,
                "name": device_name,
                "last_seen": now,
            }

        if is_new_connection:
            self.add_activity(f"{device_name} connected")

    def default_device_name(self, agent: str) -> str:
        agent_lower = agent.lower()
        if "iphone" in agent_lower:
            return "iPhone"
        if "android" in agent_lower:
            return "Android phone"
        if "windows" in agent_lower:
            return "Windows PC"
        if "mac" in agent_lower:
            return "Mac"
        return "Browser device"

    def recent_devices(self) -> list[dict]:
        now = time.time()
        cls = self.__class__
        with cls.devices_lock:
            stale_keys = [k for k, d in cls.devices.items() if now - d.get("last_seen", 0) > DEVICE_STALE_SECONDS]
            for k in stale_keys:
                cls.devices.pop(k, None)
            devices = sorted(cls.devices.values(), key=lambda item: item["last_seen"], reverse=True)
        return [
            {
                "id": item.get("id", f'{item["ip"]}|{item["agent"]}'),
                "ip": item["ip"],
                "agent": item["agent"],
                "name": item.get("name") or self.default_device_name(item["agent"]),
                "seen_seconds_ago": max(0, int(now - item["last_seen"])),
            }
            for item in devices[:8]
        ]

    def send_health(self) -> None:
        self.cleanup_expired_files()
        cls = self.__class__
        with cls.clipboard_lock:
            if self.cleanup_clipboard_locked():
                self.persist_clipboard_locked()
            clipboard_ok = isinstance(cls.clipboard_items, list)
        files_ok = self.share_dir.exists() and os.access(self.share_dir, os.R_OK | os.W_OK)
        self.send_json(
            {
                "ok": True,
                "checked_at": time.time(),
                "services": [
                    {"name": "Server info", "ok": True},
                    {"name": "File service", "ok": bool(files_ok)},
                    {"name": "Clipboard service", "ok": bool(clipboard_ok)},
                    {"name": "Authentication", "ok": self.is_authorized()},
                ],
            }
        )

    def send_dashboard(self) -> None:
        self.cleanup_expired_files()
        files = [path for path in self.share_dir.iterdir() if path.is_file() and not path.name.startswith(".")]
        storage_bytes = sum(path.stat().st_size for path in files)
        latest_file = max(files, key=lambda path: path.stat().st_mtime, default=None)
        cls = self.__class__
        with cls.clipboard_lock:
            if self.cleanup_clipboard_locked():
                self.persist_clipboard_locked()
            latest_clipboard = cls.clipboard_items[0] if cls.clipboard_items else None
        latest_upload = None
        if latest_file:
            stat = latest_file.stat()
            latest_upload = {
                "name": latest_file.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "url": f"/files/{quote(latest_file.name)}",
            }
        with cls.activity_lock:
            recent_activities = list(cls.activity_events)
        discovery_svc = getattr(cls, "discovery_service", None)
        peers = discovery_svc.get_peers() if discovery_svc else []

        self.send_json(
            {
                "storage_bytes": storage_bytes,
                "file_count": len(files),
                "latest_upload": latest_upload,
                "latest_clipboard": latest_clipboard,
                "devices": self.recent_devices(),
                "activity": recent_activities,
                "peers": peers,
            }
        )

    def send_network_diagnostics(self) -> None:
        cls = self.__class__
        lan_ip = get_lan_ip()
        all_ips = get_all_lan_ips()
        discovery_svc = getattr(cls, "discovery_service", None)
        peers = discovery_svc.get_peers() if discovery_svc else []
        disc_status = discovery_svc.status if discovery_svc else "Disabled"
        uptime = int(time.time() - getattr(cls, "start_time", time.time()))
        protocol = getattr(cls, "protocol", "http")
        port = getattr(cls, "port", 8000)
        bind_host = getattr(cls, "bind_host", "0.0.0.0")

        data = {
            "server_status": "Running",
            "protocol": protocol,
            "bind_host": bind_host,
            "port": port,
            "lan_ip": lan_ip,
            "all_interfaces": all_ips,
            "lan_url": self.lan_url,
            "qr_url_valid": True,
            "tls_enabled": (protocol == "https"),
            "auth_enabled": bool(self.auth_enabled),
            "discovery_status": disc_status,
            "discovery_port": DISCOVERY_PORT,
            "discovery_packets_sent": discovery_svc.packets_sent if discovery_svc else 0,
            "discovery_packets_received": discovery_svc.packets_received if discovery_svc else 0,
            "discovery_broadcast_targets": discovery_svc.broadcast_targets if discovery_svc else [],
            "discovery_last_broadcast": discovery_svc.last_broadcast_time if discovery_svc else None,
            "discovery_last_received": discovery_svc.last_received_time if discovery_svc else None,
            "discovered_peers": peers,
            "client_ip": self.client_address[0] if getattr(self, "client_address", None) else "127.0.0.1",
            "uptime_seconds": uptime,
        }
        self.send_json(data)

    def send_events(self) -> None:
        cls = self.__class__
        with cls.sse_lock:
            if cls.active_sse_clients >= MAX_SSE_CLIENTS:
                self.send_error_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    f"Maximum concurrent event streams ({MAX_SSE_CLIENTS}) reached",
                )
                return
            cls.active_sse_clients += 1

        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            last_seen = cls.event_version
            self.wfile.write(f"event: update\ndata: {last_seen}\n\n".encode("utf-8"))
            self.wfile.flush()

            deadline = time.time() + 300  # 5 minutes bounded thread lifetime
            while time.time() < deadline:
                with cls.event_condition:
                    cls.event_condition.wait(timeout=15)
                    version = cls.event_version
                if version != last_seen:
                    last_seen = version
                    payload = f"event: update\ndata: {version}\n\n"
                else:
                    payload = ": keep-alive\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError, OSError):
            pass
        finally:
            with cls.sse_lock:
                cls.active_sse_clients = max(0, cls.active_sse_clients - 1)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/api/login", "/api/auth/login"):
            self.handle_login()
            return
        if parsed.path in ("/api/logout", "/api/auth/logout"):
            self.handle_logout()
            return
        if parsed.path in ("/api/security", "/api/auth/security"):
            self.handle_security_update()
            return
        if not self.require_auth():
            return
        if parsed.path == "/api/network/diagnostics":
            self.send_network_diagnostics()
            return
        self.mark_device()
        if parsed.path == "/api/upload":
            self.handle_upload(parsed)
        elif parsed.path == "/api/upload/init":
            self.handle_upload_init(parsed)
        elif parsed.path == "/api/upload/chunk":
            self.handle_upload_chunk(parsed)
        elif parsed.path == "/api/upload/complete":
            self.handle_upload_complete(parsed)
        elif parsed.path == "/api/files/download-zip":
            self.handle_download_selected_zip()
        elif parsed.path == "/api/clipboard":
            self.create_clipboard()
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not self.require_auth():
            return
        self.mark_device()
        if parsed.path == "/api/device-name":
            self.update_device_name()
            return
        if not parsed.path.startswith("/api/files/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        path = self.resolve_shared_path(parsed.path.removeprefix("/api/files/"))
        if path is None or not (path.is_file() or path.is_dir()):
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
            return
        try:
            payload = parse_json_body(self)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        new_name = sanitize_filename(str(payload.get("name", "")))
        if not new_name:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Missing new file name")
            return
        # Rename in place: preserve the file/folder's existing parent directory.
        # The resolved source path has already been constrained to share_dir.
        destination = path.parent / new_name
        if destination.exists() and destination.resolve() != path.resolve():
            destination = unique_path(path.parent, new_name)
        try:
            path.rename(destination)
        except OSError as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Rename failed")
            return
        with self.file_expiry_lock:
            old_rel = str(path.relative_to(self.share_dir)).replace(os.sep, "/")
            new_rel = str(destination.relative_to(self.share_dir)).replace(os.sep, "/")
            expires_at = self.file_expiry.pop(old_rel, self.file_expiry.pop(path.name, None))
            if expires_at:
                self.file_expiry[new_rel] = expires_at
                save_file_expiry(self.file_expiry_path, self.file_expiry)
        self.send_json({"ok": True, "name": destination.name, "url": f"/files/{quote(destination.name)}"})
        self.notify_update()

    def update_device_name(self) -> None:
        try:
            payload = parse_json_body(self, limit=4096)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        device_id = str(payload.get("id", "")).strip()
        name = re.sub(r"\s+", " ", str(payload.get("name", "")).strip())[:36]
        if not device_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Missing device id")
            return
        if not name:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Device name is empty")
            return
        cls = self.__class__
        with cls.devices_lock:
            device = cls.devices.get(device_id)
            if not device:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Device not found")
                return
            device["name"] = name
            cls.device_names[device_id] = name
            try:
                save_device_names(cls.device_names_path, cls.device_names)
            except OSError as exc:
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not save device name")
                return
        self.send_json({"ok": True, "name": name})
        self.notify_update()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not self.require_auth():
            return
        self.mark_device()
        if parsed.path == "/api/files":
            self.delete_all_files()
        elif parsed.path.startswith("/api/files/"):
            encoded_name = parsed.path.removeprefix("/api/files/")
            path = self.resolve_shared_path(encoded_name)
            if path is None:
                self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
                return
            share_root = self.share_dir.resolve()
            if path.is_dir():
                rel_dir = str(path.resolve().relative_to(share_root)).replace(os.sep, "/")
                try:
                    shutil.rmtree(path)
                except OSError as exc:
                    self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Delete failed")
                    return
                with self.file_expiry_lock:
                    prefix = f"{rel_dir}/"
                    stale = [k for k in self.file_expiry if k == rel_dir or k.startswith(prefix)]
                    for k in stale:
                        self.file_expiry.pop(k, None)
                    if stale:
                        save_file_expiry(self.file_expiry_path, self.file_expiry)
                self.send_json({"ok": True})
                self.add_activity(f"{path.name} deleted")
            elif path.is_file():
                rel_key = str(path.resolve().relative_to(share_root)).replace(os.sep, "/")
                path.unlink()
                with self.file_expiry_lock:
                    removed = self.file_expiry.pop(rel_key, self.file_expiry.pop(path.name, None))
                    if removed is not None:
                        save_file_expiry(self.file_expiry_path, self.file_expiry)
                self.send_json({"ok": True})
                self.add_activity(f"{path.name} deleted")
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
        elif parsed.path == "/api/upload/cancel":
            self.handle_upload_cancel(parsed)
        elif parsed.path.startswith("/api/clipboard/"):
            item_id = parsed.path.removeprefix("/api/clipboard/")
            cls = self.__class__
            with cls.clipboard_lock:
                cls.clipboard_items[:] = [item for item in cls.clipboard_items if str(item["id"]) != item_id]
                self.persist_clipboard_locked()
            self.send_json({"ok": True})
            self.notify_update()
        elif parsed.path == "/api/clipboard":
            cls = self.__class__
            with cls.clipboard_lock:
                cls.clipboard_items.clear()
                self.persist_clipboard_locked()
            self.send_json({"ok": True})
            self.notify_update()
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")

    def _auth_cookie(self, max_age: int | None = None, clear: bool = False) -> str:
        cls = self.__class__
        parts = ["pura_share=", "Path=/", "HttpOnly", "SameSite=Lax"]
        if cls.protocol == "https":
            parts.insert(2, "Secure")
        if clear:
            parts[0] = "pura_share="
            parts.insert(1, "Max-Age=0")
        elif max_age is not None:
            parts.insert(1, f"Max-Age={max_age}")
        value = cls.auth_token or ""
        parts[0] = f"pura_share={value}"
        if clear:
            parts[0] = "pura_share="
        return "; ".join(parts)

    def handle_security_update(self) -> None:
        try:
            payload = parse_json_body(self, limit=4096)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return

        cls = self.__class__
        with cls.config_lock:
            current_enabled = cls.auth_enabled
            current_pin = cls.pin

            # Security changes are privileged operations. If security is already
            # enabled, the current PIN authorizes the change. If security is
            # disabled, only a request originating from this machine may bootstrap
            # the security settings; a LAN client must not be able to choose the
            # initial PIN or toggle authentication on/off.
            if current_enabled:
                given_current = str(payload.get("current_pin", "")).strip()
                if not given_current:
                    self.send_error_json(HTTPStatus.UNAUTHORIZED, "Current PIN is required to authorize change")
                    return
                if not current_pin or not secrets.compare_digest(given_current, current_pin):
                    self.send_error_json(HTTPStatus.UNAUTHORIZED, "Current PIN is incorrect")
                    return
            else:
                try:
                    peer_ip = ipaddress.ip_address(self.client_address[0])
                    if not peer_ip.is_loopback:
                        self.send_error_json(HTTPStatus.FORBIDDEN, "Security settings can only be initialized locally")
                        return
                except (ValueError, IndexError):
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Security settings can only be initialized locally")
                    return

            enable_target = bool(payload.get("auth_enabled"))
            new_pin = payload.get("pin")
            if new_pin is not None:
                new_pin = str(new_pin).strip()

            if enable_target:
                if new_pin:
                    cls.pin = new_pin
                elif not cls.pin:
                    cls.pin = DEFAULT_PIN
                cls.auth_enabled = True
                cls.auth_token = secrets.token_urlsafe(32)
            else:
                cls.auth_enabled = False
                if new_pin:
                    cls.pin = new_pin

            config_data = {
                "auth_enabled": cls.auth_enabled,
                "pin": cls.pin or DEFAULT_PIN,
            }
            try:
                save_server_config(cls.config_path, config_data)
            except OSError as exc:
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not save security settings")
                return

        self.add_activity("Security settings updated")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cls.auth_enabled and cls.auth_token:
            self.send_header("Set-Cookie", self._auth_cookie())
        else:
            self.send_header("Set-Cookie", self._auth_cookie(clear=True))
        body = json.dumps({"ok": True, "auth_enabled": cls.auth_enabled, "has_pin": bool(cls.pin)}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def handle_login(self) -> None:
        cls = self.__class__
        if not cls.auth_enabled or not cls.pin:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", self._auth_cookie())
            body = b'{"ok": true}'
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            payload = parse_json_body(self, limit=4096)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        client_key = self.client_address[0] if self.client_address else "unknown"
        now = time.monotonic()
        with cls.login_attempts_lock:
            if len(cls.login_attempts) > 512:
                cutoff = now - 300.0
                for key, value in list(cls.login_attempts.items()):
                    if value.get("blocked_until", 0.0) < now and value.get("last_seen", cutoff) < cutoff:
                        cls.login_attempts.pop(key, None)
            attempt = cls.login_attempts.get(client_key, {"failures": 0, "blocked_until": 0.0, "last_seen": now})
            attempt["last_seen"] = now
            if attempt.get("blocked_until", 0.0) > now:
                retry_after = max(1, int(attempt["blocked_until"] - now))
                self.close_connection = True
                self.send_error_json(HTTPStatus.TOO_MANY_REQUESTS, "Too many failed PIN attempts; try again later")
                return

        if secrets.compare_digest(str(payload.get("pin", "")), cls.pin):
            with cls.login_attempts_lock:
                cls.login_attempts.pop(client_key, None)
            trusted = bool(payload.get("trusted"))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            max_age = "; Max-Age=604800" if trusted else ""
            self.send_header("Set-Cookie", self._auth_cookie(604800 if trusted else None))
            body = b'{"ok": true}'
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            self.add_activity("Device authenticated")
        else:
            with cls.login_attempts_lock:
                attempt = cls.login_attempts.setdefault(client_key, {"failures": 0, "blocked_until": 0.0})
                attempt["failures"] = min(attempt.get("failures", 0) + 1, 10)
                if attempt["failures"] >= cls.login_max_failures:
                    delay = min(cls.login_base_delay * (2 ** (attempt["failures"] - cls.login_max_failures)), cls.login_max_delay)
                    attempt["blocked_until"] = time.monotonic() + delay
            self.close_connection = True
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Wrong PIN")

    def handle_logout(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", self._auth_cookie(clear=True))
        body = b'{"ok": true}'
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def handle_upload(self, parsed) -> None:
        query = parse_qs(parsed.query)
        original_name = query.get("name", [""])[0]
        content_length = self.headers.get("Content-Length")
        if not content_length:
            self.send_error_json(HTTPStatus.LENGTH_REQUIRED, "Missing Content-Length header")
            return

        try:
            remaining = int(content_length)
            expires = int(query.get("expires", ["0"])[0] or "0")
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid upload metadata")
            return

        if remaining < 0:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid upload size")
            return
        if remaining > self.max_upload_bytes:
            self.send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"File is larger than the {self.max_upload_gb} GB limit",
            )
            return

        # Folder upload support: ?folder=1 with name containing relative path
        is_folder_upload = query.get("folder", ["0"])[0] == "1"
        decoded_name = unquote(original_name)

        if is_folder_upload:
            safe_path = sanitize_folder_path(decoded_name)
            if safe_path is None:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid folder path")
                return
            target = self.share_dir / safe_path.replace("/", os.sep)
            # Verify the resolved path is strictly under share_dir
            try:
                target.resolve().relative_to(self.share_dir.resolve())
            except ValueError:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Path traversal detected")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            destination = target
            filename = target.name
        else:
            filename = sanitize_filename(decoded_name)
            destination = unique_path(self.share_dir, filename)

        temp_name = f".upload-{time.time_ns()}-{threading.get_ident()}.tmp"
        temp_path = self.share_dir / temp_name

        sha256_hash = hashlib.sha256()
        try:
            with temp_path.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(STREAM_BUFFER_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("Upload ended early")
                    handle.write(chunk)
                    sha256_hash.update(chunk)
                    remaining -= len(chunk)
            os.replace(temp_path, destination)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Upload failed")
            return

        server_sha256 = sha256_hash.hexdigest()

        rel_path = str(destination.resolve().relative_to(self.share_dir.resolve())).replace(os.sep, "/")

        if expires > 0:
            with self.file_expiry_lock:
                self.file_expiry[rel_path] = time.time() + expires
                save_file_expiry(self.file_expiry_path, self.file_expiry)

        self.send_json(
            {"ok": True, "name": destination.name, "path": rel_path,
             "url": f"/files/{quote(rel_path)}", "sha256": server_sha256},
            HTTPStatus.CREATED,
        )
        self.add_activity(f"{destination.name} uploaded")

    # ── Resumable upload handlers ────────────────────────────────────

    def cleanup_stale_resumable(self) -> None:
        """Remove resumable upload sessions older than RESUMABLE_STALE_SECONDS."""
        now = time.time()
        cls = self.__class__
        stale_ids: list[str] = []
        with cls.resumable_uploads_lock:
            for uid, session in list(cls.resumable_uploads.items()):
                if now - session.get("last_activity", session["created_at"]) > RESUMABLE_STALE_SECONDS:
                    stale_ids.append(uid)
            for uid in stale_ids:
                session = cls.resumable_uploads.pop(uid, None)
                if session:
                    handle = session.get("temp_handle")
                    if handle:
                        try:
                            handle.close()
                        except Exception:
                            pass
                    temp_path = session.get("temp_path")
                    if temp_path:
                        try:
                            Path(temp_path).unlink(missing_ok=True)
                        except Exception:
                            pass

    def handle_upload_init(self, parsed) -> None:
        """POST /api/upload/init — Create a resumable upload session."""
        try:
            payload = parse_json_body(self, limit=8192)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return

        cls = self.__class__
        # Clean stale sessions before checking capacity
        self.cleanup_stale_resumable()

        with cls.resumable_uploads_lock:
            if len(cls.resumable_uploads) >= MAX_ACTIVE_RESUMABLE_SESSIONS:
                self.send_error_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    f"Maximum active upload sessions ({MAX_ACTIVE_RESUMABLE_SESSIONS}) reached. Please complete or cancel existing uploads.",
                )
                return

        original_name = str(payload.get("filename") or payload.get("name") or "")
        total_size = payload.get("size", 0)
        sha256_expected = str(payload.get("sha256", "")).strip().lower()
        expires = int(payload.get("expires", 0) or 0)
        is_folder = bool(payload.get("folder", False))
        folder_path = str(payload.get("folder_path", ""))

        if not original_name:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Missing filename")
            return

        try:
            total_size = int(total_size)
        except (ValueError, TypeError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid size")
            return

        if total_size < 0:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid size")
            return
        if total_size > self.max_upload_bytes:
            self.send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"File is larger than the {self.max_upload_gb} GB limit",
            )
            return

        if is_folder and folder_path:
            safe_path = sanitize_folder_path(folder_path)
            if safe_path is None:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid folder path")
                return
            filename = safe_path
        else:
            filename = sanitize_filename(original_name)

        upload_id = secrets.token_urlsafe(32)
        temp_name = f".resumable-{upload_id}.tmp"
        temp_path = self.share_dir / temp_name

        try:
            temp_handle = temp_path.open("wb")
        except OSError as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not initialize upload temp file")
            return

        session = {
            "upload_id": upload_id,
            "filename": filename,
            "total_size": total_size,
            "received": 0,
            "sha256_expected": sha256_expected,
            "sha256_hash": hashlib.sha256(),
            "temp_path": str(temp_path),
            "temp_handle": temp_handle,
            "write_lock": threading.Lock(),
            "created_at": time.time(),
            "last_activity": time.time(),
            "expires": expires,
            "is_folder": is_folder,
        }

        with cls.resumable_uploads_lock:
            cls.resumable_uploads[upload_id] = session

        self.send_json(
            {"ok": True, "upload_id": upload_id, "filename": filename, "offset": 0},
            HTTPStatus.CREATED,
        )

    def handle_upload_chunk(self, parsed) -> None:
        """POST /api/upload/chunk?id=<upload_id>&offset=<N> — Upload a chunk."""
        query = parse_qs(parsed.query)
        upload_id = query.get("id", [""])[0]
        try:
            client_offset = int(query.get("offset", ["0"])[0])
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid offset")
            return

        content_length = self.headers.get("Content-Length")
        if not content_length:
            self.send_error_json(HTTPStatus.LENGTH_REQUIRED, "Missing Content-Length header")
            return
        try:
            chunk_size = int(content_length)
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return

        if chunk_size <= 0:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid chunk size")
            return

        if chunk_size > MAX_RESUMABLE_CHUNK_BYTES:
            self.send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"Chunk exceeds maximum size of {MAX_RESUMABLE_CHUNK_BYTES} bytes",
            )
            return

        cls = self.__class__
        with cls.resumable_uploads_lock:
            session = cls.resumable_uploads.get(upload_id)
            if not session:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
                return

        write_lock = session["write_lock"]
        with write_lock:
            with cls.resumable_uploads_lock:
                if upload_id not in cls.resumable_uploads:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
                    return

            server_offset = session["received"]

            # Duplicate / stale retry
            if client_offset < server_offset:
                remaining = chunk_size
                while remaining > 0:
                    discard = self.rfile.read(min(STREAM_BUFFER_SIZE, remaining))
                    if not discard:
                        break
                    remaining -= len(discard)
                self.send_json({"ok": True, "offset": server_offset, "received": server_offset})
                return

            # Out-of-order chunk
            if client_offset > server_offset:
                remaining = chunk_size
                while remaining > 0:
                    discard = self.rfile.read(min(STREAM_BUFFER_SIZE, remaining))
                    if not discard:
                        break
                    remaining -= len(discard)
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    f"Offset mismatch: client={client_offset}, server={server_offset}",
                )
                return

            # Chunk would exceed total size
            if server_offset + chunk_size > session["total_size"]:
                remaining = chunk_size
                while remaining > 0:
                    discard = self.rfile.read(min(STREAM_BUFFER_SIZE, remaining))
                    if not discard:
                        break
                    remaining -= len(discard)
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Chunk would exceed total file size")
                return

            temp_handle = session["temp_handle"]
            sha256_hash = session["sha256_hash"]

            chunk_data = bytearray()
            remaining = chunk_size
            try:
                while remaining > 0:
                    data = self.rfile.read(min(STREAM_BUFFER_SIZE, remaining))
                    if not data:
                        raise ConnectionError("Chunk upload ended early")
                    chunk_data.extend(data)
                    remaining -= len(data)
            except Exception:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Chunk read interrupted")
                return

            try:
                temp_handle.seek(server_offset)
                temp_handle.write(chunk_data)
                temp_handle.flush()
                sha256_hash.update(chunk_data)
            except Exception:
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Chunk write failed")
                return

            session["received"] = server_offset + len(chunk_data)
            session["last_activity"] = time.time()
            new_offset = session["received"]

        self.send_json({"ok": True, "offset": new_offset, "received": new_offset})

    def handle_upload_complete(self, parsed) -> None:
        query = parse_qs(parsed.query)
        upload_id = query.get("id", [""])[0]
        cls = self.__class__
        with cls.resumable_uploads_lock:
            session = cls.resumable_uploads.get(upload_id)
        if not session:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
            return
        with session["write_lock"]:
            self._handle_upload_complete_locked(parsed)

    def _handle_upload_complete_locked(self, parsed) -> None:
        """Internal completion implementation; caller holds the per-upload lock."""
        query = parse_qs(parsed.query)
        upload_id = query.get("id", [""])[0]

        cls = self.__class__
        with cls.resumable_uploads_lock:
            session = cls.resumable_uploads.get(upload_id)
            if not session:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
                return

        # Validate completion
        if session["received"] != session["total_size"]:
            self.send_error_json(
                HTTPStatus.BAD_REQUEST,
                f"Upload incomplete: received {session['received']}/{session['total_size']} bytes",
            )
            return

        # Close persistent handle before renaming
        temp_handle = session.get("temp_handle")
        if temp_handle:
            try:
                temp_handle.flush()
                temp_handle.close()
            except Exception:
                pass

        temp_path = Path(session["temp_path"])
        server_sha256 = session["sha256_hash"].hexdigest()
        expected_sha256 = session["sha256_expected"]

        # SHA-256 verification
        if expected_sha256 and expected_sha256 != server_sha256:
            temp_path.unlink(missing_ok=True)
            with cls.resumable_uploads_lock:
                cls.resumable_uploads.pop(upload_id, None)
            self.send_error_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                f"SHA-256 mismatch: expected {expected_sha256}, got {server_sha256}",
            )
            return

        # Determine destination path
        if session.get("is_folder") and "/" in session["filename"]:
            target = self.share_dir / session["filename"].replace("/", os.sep)
            try:
                resolved_target = target.resolve(strict=False)
                resolved_target.relative_to(self.share_dir.resolve())
                resolved_parent = resolved_target.parent
                resolved_parent.relative_to(self.share_dir.resolve())
            except (OSError, ValueError):
                temp_path.unlink(missing_ok=True)
                with cls.resumable_uploads_lock:
                    cls.resumable_uploads.pop(upload_id, None)
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Path traversal detected")
                return
            destination = resolved_target
        else:
            destination = unique_path(self.share_dir, session["filename"])

        try:
            os.replace(temp_path, destination)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            with cls.resumable_uploads_lock:
                cls.resumable_uploads.pop(upload_id, None)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Finalize failed")
            return

        rel_path = str(destination.resolve().relative_to(self.share_dir.resolve())).replace(os.sep, "/")

        # Set expiry using relative path
        expires = session.get("expires", 0)
        if expires and expires > 0:
            with self.file_expiry_lock:
                self.file_expiry[rel_path] = time.time() + expires
                save_file_expiry(self.file_expiry_path, self.file_expiry)

        # Clean up session
        with cls.resumable_uploads_lock:
            cls.resumable_uploads.pop(upload_id, None)

        self.send_json(
            {"ok": True, "name": destination.name, "path": rel_path,
             "url": f"/files/{quote(rel_path)}", "sha256": server_sha256,
             "verified": bool(expected_sha256)},
            HTTPStatus.CREATED,
        )
        self.add_activity(f"{destination.name} uploaded")

    def handle_upload_status(self, parsed) -> None:
        """GET /api/upload/status?id=<upload_id> — Query resumable upload state."""
        query = parse_qs(parsed.query)
        upload_id = query.get("id", [""])[0]

        cls = self.__class__
        with cls.resumable_uploads_lock:
            session = cls.resumable_uploads.get(upload_id)

        if not session:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
            return

        self.send_json({
            "upload_id": session["upload_id"],
            "filename": session["filename"],
            "total_size": session["total_size"],
            "received": session["received"],
            "offset": session["received"],
            "status": "complete" if session["received"] == session["total_size"] else "uploading",
        })

    def handle_upload_cancel(self, parsed) -> None:
        """DELETE /api/upload/cancel?id=<upload_id> — Cancel and clean up."""
        query = parse_qs(parsed.query)
        upload_id = query.get("id", [""])[0]

        cls = self.__class__
        with cls.resumable_uploads_lock:
            session = cls.resumable_uploads.get(upload_id)

        if not session:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
            return

        with session["write_lock"]:
            with cls.resumable_uploads_lock:
                session = cls.resumable_uploads.pop(upload_id, None)
            if not session:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Upload session not found")
                return

            temp_handle = session.get("temp_handle")
            if temp_handle:
                try:
                    temp_handle.close()
                except Exception:
                    pass

            temp_path = Path(session["temp_path"])
            temp_path.unlink(missing_ok=True)
            self.send_json({"ok": True})


    def create_clipboard(self) -> None:
        try:
            payload = parse_json_body(self, limit=MAX_CLIPBOARD_BYTES + 4096)
        except (json.JSONDecodeError, ValueError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        text = str(payload.get("text", ""))
        if not text.strip():
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Clipboard text is empty")
            return
        if len(text.encode("utf-8")) > MAX_CLIPBOARD_BYTES:
            self.send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Clipboard text is too large")
            return
        try:
            expires = int(payload.get("expires", 0) or 0)
        except ValueError:
            expires = 0
        now = time.time()
        cls = self.__class__
        with cls.clipboard_lock:
            cls.clipboard_counter += 1
            item = {
                "id": cls.clipboard_counter,
                "text": text,
                "created_at": now,
                "expires_at": now + expires if expires > 0 else None,
            }
            cls.clipboard_items.insert(0, item)
            self.cleanup_clipboard_locked()
            del cls.clipboard_items[MAX_CLIPBOARD_ITEMS:]
            self.persist_clipboard_locked()
        self.send_json({"ok": True, "item": item}, HTTPStatus.CREATED)
        self.add_activity("Clipboard updated")

    def send_clipboard(self) -> None:
        cls = self.__class__
        with cls.clipboard_lock:
            if self.cleanup_clipboard_locked():
                self.persist_clipboard_locked()
            items = list(cls.clipboard_items)
        self.send_json({"items": items})

    def send_files(self) -> None:
        self.cleanup_expired_files()
        items = []
        share_root = self.share_dir.resolve()
        folders = set()

        try:
            entries = sorted(self.share_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            entries = []

        for path in entries:
            if path.name.startswith("."):
                continue
            try:
                path.resolve().relative_to(share_root)
            except (ValueError, OSError):
                continue

            if path.is_dir():
                sub_files = [
                    f for f in path.rglob("*")
                    if f.is_file() and not any(p.startswith(".") for p in f.relative_to(path).parts)
                ]
                total_size = sum(f.stat().st_size for f in sub_files)
                latest_mtime = max((f.stat().st_mtime for f in sub_files), default=path.stat().st_mtime)
                folders.add(path.name)
                items.append({
                    "name": path.name,
                    "path": path.name,
                    "is_dir": True,
                    "size": total_size,
                    "file_count": len(sub_files),
                    "modified": latest_mtime,
                    "type": "Folder",
                    "expires_at": None,
                    "url": f"/api/files/download-folder/{quote(path.name)}",
                    "folder": None,
                })
            elif path.is_file():
                stat = path.stat()
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                with self.file_expiry_lock:
                    rel_key = str(path.relative_to(self.share_dir)).replace(os.sep, "/")
                    expires_at = self.file_expiry.get(rel_key, self.file_expiry.get(path.name))
                items.append({
                    "name": path.name,
                    "path": path.name,
                    "is_dir": False,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "type": content_type,
                    "expires_at": expires_at,
                    "url": f"/files/{quote(path.name)}",
                    "folder": None,
                })

        self.send_json({"files": items, "folders": sorted(folders)})

    def send_all_files_zip(self, query: dict | None = None) -> None:
        self.cleanup_expired_files()
        share_root = self.share_dir.resolve()

        all_files: list[Path] = []
        for path in self.share_dir.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if any(part.startswith(".") for part in path.relative_to(self.share_dir).parts):
                continue
            try:
                resolved_path = path.resolve()
                resolved_path.relative_to(share_root)
            except (OSError, ValueError):
                continue
            all_files.append(resolved_path)
            if len(all_files) > MAX_ZIP_FILES:
                self.send_error_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    f"Too many files to include in one ZIP archive (maximum {MAX_ZIP_FILES:,}).",
                )
                return

        if not all_files:
            self.send_error_json(HTTPStatus.NOT_FOUND, "No files to download")
            return

        cls = self.__class__
        if not cls.zip_semaphore.acquire(blocking=False):
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Another ZIP archive is currently being assembled. Please retry in a few moments.",
            )
            return

        try:
            total_bytes = sum(p.stat().st_size for p in all_files)
            free_disk = shutil.disk_usage(tempfile.gettempdir()).free
            required_disk = int(total_bytes * 1.1) + 100 * 1024 * 1024
            if free_disk < required_disk:
                self.send_error_json(
                    HTTPStatus.INSUFFICIENT_STORAGE,
                    "Insufficient temporary disk space to assemble ZIP archive.",
                )
                cls.zip_semaphore.release()
                return
        except (OSError, ValueError) as exc:
            cls.zip_semaphore.release()
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Unable to safely verify temporary disk space for ZIP archive.",
            )
            return

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = Path(temp_file.name)
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in all_files:
                    try:
                        safe_path = path.resolve()
                        safe_path.relative_to(share_root)
                    except (OSError, ValueError) as exc:
                        raise ValueError("ZIP source escaped the shared folder") from exc
                    if not safe_path.is_file() or safe_path.name.startswith("."):
                        raise ValueError("ZIP source is no longer a regular shared file")
                    arcname = str(safe_path.relative_to(share_root)).replace(os.sep, "/")
                    archive.write(safe_path, arcname=arcname)
            stat = temp_path.stat()
        except (OSError, ValueError) as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()
            message = "Download all failed" if isinstance(exc, OSError) else "ZIP source escaped the shared folder"
            status = HTTPStatus.INTERNAL_SERVER_ERROR if isinstance(exc, OSError) else HTTPStatus.BAD_REQUEST
            self.send_error_json(status, message)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        zip_name = f"Files_{datetime.now().strftime('%H_%M_%d_%m_%y')}.zip"
        self.send_header("Content-Disposition", f'attachment; filename="{zip_name}"')
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with temp_path.open("rb") as handle:
                while True:
                    chunk = handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError:
            pass
        else:
            self.add_activity("ZIP downloaded")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()

    def send_folder_zip(self, encoded_folder: str) -> None:
        """Download a specific folder as a ZIP archive."""
        folder_name = unquote(encoded_folder)
        folder_path = self.share_dir / folder_name
        share_root = self.share_dir.resolve()

        try:
            resolved = folder_path.resolve()
            resolved.relative_to(share_root)
        except (OSError, ValueError):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Folder not found")
            return

        if not folder_path.is_dir():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Folder not found")
            return

        all_files: list[Path] = []
        for path in folder_path.rglob("*"):
            if path.is_symlink() or not path.is_file() or any(p.startswith(".") for p in path.relative_to(folder_path).parts):
                continue
            try:
                resolved_path = path.resolve()
                resolved_path.relative_to(share_root)
            except (OSError, ValueError):
                # Never include symlinks or paths that resolve outside the shared root.
                continue
            all_files.append(resolved_path)
            if len(all_files) > MAX_ZIP_FILES:
                self.send_error_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    f"Too many files to include in one ZIP archive (maximum {MAX_ZIP_FILES:,}).",
                )
                return

        if not all_files:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Folder is empty")
            return

        cls = self.__class__
        if not cls.zip_semaphore.acquire(blocking=False):
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Another ZIP archive is currently being assembled. Please retry in a few moments.",
            )
            return

        try:
            total_bytes = sum(p.stat().st_size for p in all_files)
            free_disk = shutil.disk_usage(tempfile.gettempdir()).free
            required_disk = int(total_bytes * 1.1) + 100 * 1024 * 1024
            if free_disk < required_disk:
                self.send_error_json(
                    HTTPStatus.INSUFFICIENT_STORAGE,
                    "Insufficient temporary disk space to assemble ZIP archive.",
                )
                cls.zip_semaphore.release()
                return
        except (OSError, ValueError) as exc:
            cls.zip_semaphore.release()
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Unable to safely verify temporary disk space for ZIP archive.",
            )
            return

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = Path(temp_file.name)
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in all_files:
                    try:
                        safe_path = path.resolve()
                        safe_path.relative_to(share_root)
                    except (OSError, ValueError) as exc:
                        raise ValueError("ZIP source escaped the shared folder") from exc
                    if not safe_path.is_file() or safe_path.name.startswith("."):
                        raise ValueError("ZIP source is no longer a regular shared file")
                    arcname = str(safe_path.relative_to(share_root)).replace(os.sep, "/")
                    archive.write(safe_path, arcname=arcname)
            stat = temp_path.stat()
        except (OSError, ValueError) as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()
            message = "Folder download failed" if isinstance(exc, OSError) else "ZIP source escaped the shared folder"
            status = HTTPStatus.INTERNAL_SERVER_ERROR if isinstance(exc, OSError) else HTTPStatus.BAD_REQUEST
            self.send_error_json(status, message)
            return

        safe_name = sanitize_filename(folder_name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}.zip"')
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with temp_path.open("rb") as handle:
                while True:
                    chunk = handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError:
            pass
        else:
            self.add_activity("ZIP downloaded")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()

    def handle_download_selected_zip(self) -> None:
        """Download arbitrary selected files and folders as a streamed ZIP archive."""
        self.cleanup_expired_files()
        share_root = self.share_dir.resolve()

        file_list: list[str] = []
        if self.command == "POST":
            try:
                payload = parse_json_body(self, limit=128 * 1024)
                file_list = payload.get("files", [])
            except (json.JSONDecodeError, ValueError):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid request body")
                return
        else:
            query = parse_qs(urlparse(self.path).query)
            file_list = query.get("files", [])

        if not isinstance(file_list, list) or not file_list:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "No files selected")
            return

        resolved_files: list[tuple[Path, str]] = []
        seen_paths: set[Path] = set()

        for raw_name in file_list:
            if not isinstance(raw_name, str):
                continue
            name = raw_name.strip()
            if not name:
                continue

            # Reject traversal or dangerous prefixes
            if ".." in name or name.startswith("/") or name.startswith("\\"):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid path in selection")
                return

            raw_path = self.share_dir / name
            try:
                if raw_path.is_symlink():
                    continue
            except OSError:
                continue

            path = self.resolve_shared_path(name)
            if path is None or not path.exists():
                continue

            try:
                resolved = path.resolve()
                resolved.relative_to(share_root)
            except (OSError, ValueError):
                continue

            if resolved.is_file() and not resolved.name.startswith("."):
                if resolved not in seen_paths:
                    seen_paths.add(resolved)
                    arcname = str(resolved.relative_to(share_root)).replace(os.sep, "/")
                    resolved_files.append((resolved, arcname))
                    if len(resolved_files) > MAX_ZIP_FILES:
                        self.send_error_json(
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            f"Too many files to include in one ZIP archive (maximum {MAX_ZIP_FILES:,}).",
                        )
                        return
            elif resolved.is_dir() and not resolved.name.startswith("."):
                for sub_item in resolved.rglob("*"):
                    if sub_item.is_symlink() or not sub_item.is_file() or any(p.startswith(".") for p in sub_item.relative_to(share_root).parts):
                        continue
                    try:
                        safe_item = sub_item.resolve()
                        safe_item.relative_to(share_root)
                    except (OSError, ValueError):
                        continue
                    if safe_item in seen_paths:
                        continue
                    seen_paths.add(safe_item)
                    arcname = str(safe_item.relative_to(share_root)).replace(os.sep, "/")
                    resolved_files.append((safe_item, arcname))
                    if len(resolved_files) > MAX_ZIP_FILES:
                        self.send_error_json(
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            f"Too many files to include in one ZIP archive (maximum {MAX_ZIP_FILES:,}).",
                        )
                        return

        if not resolved_files:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Selected files not found")
            return

        cls = self.__class__
        if not cls.zip_semaphore.acquire(blocking=False):
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Another ZIP archive is currently being assembled. Please retry in a few moments.",
            )
            return

        try:
            total_bytes = sum(abs_path.stat().st_size for abs_path, _ in resolved_files)
            free_disk = shutil.disk_usage(tempfile.gettempdir()).free
            required_disk = int(total_bytes * 1.1) + 100 * 1024 * 1024
            if free_disk < required_disk:
                self.send_error_json(
                    HTTPStatus.INSUFFICIENT_STORAGE,
                    "Insufficient temporary disk space to assemble ZIP archive.",
                )
                cls.zip_semaphore.release()
                return
        except (OSError, ValueError) as exc:
            cls.zip_semaphore.release()
            self.send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Unable to safely verify temporary disk space for ZIP archive.",
            )
            return

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = Path(temp_file.name)
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for abs_path, arcname in resolved_files:
                    try:
                        safe_path = abs_path.resolve()
                        safe_path.relative_to(share_root)
                    except (OSError, ValueError) as exc:
                        raise ValueError("ZIP source escaped the shared folder") from exc
                    if not safe_path.is_file() or safe_path.name.startswith("."):
                        raise ValueError("ZIP source is no longer a regular shared file")
                    archive.write(safe_path, arcname=arcname)
            stat = temp_path.stat()
        except (OSError, ValueError) as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()
            message = "Download selected failed" if isinstance(exc, OSError) else "ZIP source escaped the shared folder"
            status = HTTPStatus.INTERNAL_SERVER_ERROR if isinstance(exc, OSError) else HTTPStatus.BAD_REQUEST
            self.send_error_json(status, message)
            return

        zip_name = f"Selected_{datetime.now().strftime('%H_%M_%d_%m_%y')}.zip"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{zip_name}"')
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with temp_path.open("rb") as handle:
                while True:
                    chunk = handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError:
            pass
        else:
            self.add_activity("ZIP downloaded")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            cls.zip_semaphore.release()

    def delete_all_files(self) -> None:
        self.cleanup_expired_files()
        protected_exts = {".py", ".bat", ".sh", ".git", ".toml"}
        protected_names = {"README.md", "LICENSE", "index.html", "qrcode.min.js"}
        files = [
            path for path in self.share_dir.iterdir()
            if path.is_file() and not path.name.startswith(".")
            and path.suffix.lower() not in protected_exts
            and path.name not in protected_names
        ]
        dirs = [
            path for path in self.share_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
            and path.name not in ("assets", "cert", "scratch", "__pycache__", ".git")
        ]
        deleted = 0
        failed: list[str] = []
        for path in files:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                failed.append(path.name)
        for path in dirs:
            try:
                shutil.rmtree(path)
                deleted += 1
            except OSError:
                failed.append(path.name)
        with self.file_expiry_lock:
            if self.file_expiry:
                self.file_expiry.clear()
                save_file_expiry(self.file_expiry_path, self.file_expiry)
        if failed:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not delete: {', '.join(failed[:3])}")
            return
        self.send_json({"ok": True, "deleted": deleted})
        self.add_activity("All files deleted")

    def send_file(self, encoded_name: str, preview: bool) -> None:
        self.cleanup_expired_files()
        path = self.resolve_shared_path(encoded_name)
        if path is None or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if preview and self.is_text_preview_file(path, content_type):
            content_type = "text/plain; charset=utf-8"
        stat = path.stat()
        file_size = stat.st_size

        range_header = self.headers.get("Range")
        range_spec = None
        if range_header:
            range_spec = parse_range_header(range_header, file_size)

        if range_header and not range_spec:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if range_spec:
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            start, end = range_spec
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            content_length = end - start + 1
        else:
            self.send_response(HTTPStatus.OK)
            start, end = 0, file_size - 1
            content_length = file_size

        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        disposition = "inline" if preview else "attachment"
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(path.name)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        if preview:
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        if content_length <= 0:
            return

        try:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = handle.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        else:
            if not range_spec or start == 0:
                self.add_activity(f"{path.name} downloaded")

    def is_text_preview_file(self, path: Path, content_type: str) -> bool:
        return content_type.startswith("text/") or path.suffix.lower() in {
            ".json",
            ".csv",
            ".md",
            ".log",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".css",
            ".html",
            ".htm",
            ".xml",
            ".txt",
            ".yaml",
            ".yml",
            ".sh",
            ".bat",
            ".ps1",
            ".ini",
            ".cfg",
            ".conf",
            ".sql",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".rs",
            ".go",
            ".java",
            ".env",
            ".toml",
        }

    def send_asset(self, encoded_name: str) -> None:
        name = unquote(encoded_name)
        try:
            path = (self.asset_dir / name).resolve()
            path.relative_to(self.asset_dir.resolve())
        except (OSError, ValueError):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        if not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def cleanup_expired_files(self) -> None:
        now = time.time()
        expired = []
        share_root = self.share_dir.resolve()
        with self.file_expiry_lock:
            for rel_key, expires_at in list(self.file_expiry.items()):
                if expires_at <= now:
                    expired.append(rel_key)
                    self.file_expiry.pop(rel_key, None)
            if expired:
                save_file_expiry(self.file_expiry_path, self.file_expiry)
        for rel_key in expired:
            try:
                target = (self.share_dir / rel_key.replace("/", os.sep)).resolve()
                target.relative_to(share_root)
                if target.is_file():
                    target.unlink()
                    self.add_activity(f"{target.name} expired")
            except (OSError, ValueError):
                pass
        self.cleanup_stale_resumable()

    def cleanup_clipboard_locked(self) -> bool:
        now = time.time()
        cls = self.__class__
        original_count = len(cls.clipboard_items)
        cls.clipboard_items[:] = [
            item for item in cls.clipboard_items if not item.get("expires_at") or item["expires_at"] > now
        ]
        return len(cls.clipboard_items) != original_count

    def persist_clipboard_locked(self) -> None:
        try:
            save_clipboard_items(self.__class__.clipboard_store_path, self.__class__.clipboard_items)
        except OSError as exc:
            print(f"Could not save clipboard items: {exc}")

    def resolve_shared_path(self, encoded_name: str) -> Path | None:
        name = unquote(encoded_name)
        try:
            path = (self.share_dir / name).resolve()
            share_root = self.share_dir.resolve()
            rel = path.relative_to(share_root)
            if any(part.startswith(".") for part in rel.parts):
                return None
            if path.suffix.lower() in {".key", ".pem", ".pfx", ".p12"}:
                return None
            return path
        except (OSError, ValueError):
            return None

    def is_authorized(self) -> bool:
        cls = self.__class__
        if not cls.auth_enabled or not cls.pin:
            return True
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        token = cookie.get("pura_share")
        return bool(token and cls.auth_token and secrets.compare_digest(token.value, cls.auth_token))

    def require_auth(self) -> bool:
        if self.is_authorized():
            return True
        if self.command in ("POST", "PUT", "PATCH"):
            self.close_connection = True
        self.send_error_json(HTTPStatus.UNAUTHORIZED, "PIN required")
        return False

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        if self.command in ("POST", "PUT", "PATCH") or status >= 400:
            self.close_connection = True
        self.send_json({"error": message}, status)


def build_handler(
    share_dir: Path,
    asset_dir: Path,
    max_upload_gb: int,
    lan_url: str,
    pin: str | None,
    protocol: str = "http",
    bind_host: str = "0.0.0.0",
    port: int = 8000,
    discovery_service: LanDiscoveryService | None = None,
) -> type[FileShareHandler]:
    share_dir = Path(share_dir).resolve()
    asset_dir = Path(asset_dir).resolve()

    class ConfiguredFileShareHandler(FileShareHandler):
        pass

    for tmp_file in share_dir.glob(".upload-*.tmp"):
        try:
            tmp_file.unlink()
        except OSError:
            pass
    for tmp_file in share_dir.glob(".resumable-*.tmp"):
        try:
            tmp_file.unlink()
        except OSError:
            pass

    config_path = share_dir / ".pura_config.json"
    saved_config = load_server_config(config_path)

    if pin == "":
        auth_enabled = False
        resolved_pin = None
    elif pin != DEFAULT_PIN and pin is not None:
        auth_enabled = True
        resolved_pin = pin
    elif saved_config and "auth_enabled" in saved_config:
        auth_enabled = bool(saved_config.get("auth_enabled", False))
        resolved_pin = str(saved_config.get("pin", DEFAULT_PIN))
    else:
        auth_enabled = False
        resolved_pin = DEFAULT_PIN

    ConfiguredFileShareHandler.share_dir = share_dir
    ConfiguredFileShareHandler.asset_dir = asset_dir
    ConfiguredFileShareHandler.max_upload_gb = max_upload_gb
    ConfiguredFileShareHandler.max_upload_bytes = max_upload_gb * 1024 * 1024 * 1024
    ConfiguredFileShareHandler.lan_url = lan_url
    ConfiguredFileShareHandler.protocol = protocol
    ConfiguredFileShareHandler.bind_host = bind_host
    ConfiguredFileShareHandler.port = port
    ConfiguredFileShareHandler.discovery_service = discovery_service
    ConfiguredFileShareHandler.start_time = time.time()
    ConfiguredFileShareHandler.auth_enabled = auth_enabled
    ConfiguredFileShareHandler.pin = resolved_pin
    ConfiguredFileShareHandler.auth_token = secrets.token_urlsafe(32)
    ConfiguredFileShareHandler.login_attempts = {}
    ConfiguredFileShareHandler.login_attempts_lock = threading.Lock()
    ConfiguredFileShareHandler.login_max_failures = 5
    ConfiguredFileShareHandler.login_base_delay = 1.0
    ConfiguredFileShareHandler.login_max_delay = 30.0
    ConfiguredFileShareHandler.config_path = config_path
    ConfiguredFileShareHandler.config_lock = threading.Lock()
    ConfiguredFileShareHandler.clipboard_store_path = share_dir / "clipboard_texts" / "clipboard_items.json"
    ConfiguredFileShareHandler.clipboard_store_path.parent.mkdir(parents=True, exist_ok=True)
    ConfiguredFileShareHandler.clipboard_items = load_clipboard_items(ConfiguredFileShareHandler.clipboard_store_path)
    ConfiguredFileShareHandler.clipboard_counter = max(
        (int(item["id"]) for item in ConfiguredFileShareHandler.clipboard_items),
        default=0,
    )
    ConfiguredFileShareHandler.clipboard_lock = threading.Lock()
    ConfiguredFileShareHandler.file_expiry_path = share_dir / ".pura_file_expiry.json"
    ConfiguredFileShareHandler.file_expiry = load_file_expiry(ConfiguredFileShareHandler.file_expiry_path, share_dir)
    ConfiguredFileShareHandler.file_expiry_lock = threading.Lock()
    ConfiguredFileShareHandler.devices = {}
    ConfiguredFileShareHandler.device_names_path = share_dir / ".pura_device_names.json"
    ConfiguredFileShareHandler.device_names = load_device_names(ConfiguredFileShareHandler.device_names_path)
    ConfiguredFileShareHandler.devices_lock = threading.Lock()
    ConfiguredFileShareHandler.event_condition = threading.Condition()
    ConfiguredFileShareHandler.event_version = 0
    if discovery_service:
        def trigger_discovery_update():
            with ConfiguredFileShareHandler.event_condition:
                ConfiguredFileShareHandler.event_version += 1
                ConfiguredFileShareHandler.event_condition.notify_all()
        discovery_service.on_peers_changed = trigger_discovery_update

    ConfiguredFileShareHandler.resumable_uploads = {}
    ConfiguredFileShareHandler.resumable_uploads_lock = threading.Lock()
    ConfiguredFileShareHandler.active_sse_clients = 0
    ConfiguredFileShareHandler.sse_lock = threading.Lock()
    ConfiguredFileShareHandler.zip_semaphore = threading.Semaphore(MAX_CONCURRENT_ZIPS)
    ConfiguredFileShareHandler.activity_events = [{"message": "Server started", "time": datetime.now().strftime("%H:%M:%S")}]
    ConfiguredFileShareHandler.activity_lock = threading.Lock()

    def cleanup_on_shutdown():
        try:
            with ConfiguredFileShareHandler.resumable_uploads_lock:
                for session in list(ConfiguredFileShareHandler.resumable_uploads.values()):
                    handle = session.get("temp_handle")
                    if handle:
                        try:
                            handle.close()
                        except Exception:
                            pass
                    tpath = session.get("temp_path")
                    if tpath:
                        try:
                            Path(tpath).unlink(missing_ok=True)
                        except Exception:
                            pass
                ConfiguredFileShareHandler.resumable_uploads.clear()
        except Exception:
            pass

    atexit.register(cleanup_on_shutdown)
    return ConfiguredFileShareHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Share files and clipboard text with devices on the same local network.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind. Default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on. Default: 8000")
    parser.add_argument("--dir", default="shared_files", help="Directory containing files to share. Default: shared_files")
    parser.add_argument(
        "--max-upload-gb",
        type=int,
        default=DEFAULT_MAX_UPLOAD_GB,
        help=f"Maximum size per uploaded file. Default: {DEFAULT_MAX_UPLOAD_GB}",
    )
    parser.add_argument(
        "--pin",
        default=DEFAULT_PIN,
        help=f"PIN required before using the share. Default: {DEFAULT_PIN}",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="Enable HTTPS (TLS) encrypted mode. Default: False",
    )
    parser.add_argument(
        "--cert",
        default="",
        help="Path to custom TLS certificate (.crt or .pem). Default: cert/server.crt",
    )
    parser.add_argument(
        "--key",
        default="",
        help="Path to custom TLS private key (.key or .pem). Default: cert/server.key",
    )
    parser.add_argument(
        "--auto-cert",
        action="store_true",
        help="Automatically generate self-signed dev certificate if cert is missing.",
    )
    parser.add_argument(
        "--no-discovery",
        action="store_true",
        help="Disable automatic local network UDP discovery announcements.",
    )
    parser.add_argument(
        "--debug-discovery",
        action="store_true",
        help="Print real-time UDP discovery diagnostic logs.",
    )
    return parser.parse_args()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    if args.port < 1 or args.port > 65535:
        print(f"Error: Invalid port number {args.port}. Port must be between 1 and 65535.", file=sys.stderr)
        sys.exit(1)
    if args.max_upload_gb <= 0:
        print(f"Error: Invalid max upload size {args.max_upload_gb}. Must be greater than 0.", file=sys.stderr)
        sys.exit(1)

    try:
        share_dir = Path(args.dir).expanduser().resolve()
        share_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        print(f"Error: Cannot access or create share directory '{args.dir}': {err.strerror or err}", file=sys.stderr)
        sys.exit(1)

    protocol = "https" if args.https else "http"
    lan_ip = get_lan_ip()
    local_url = f"{protocol}://127.0.0.1:{args.port}/"
    lan_url = f"{protocol}://{lan_ip}:{args.port}/"

    # TLS Configuration if HTTPS enabled
    ssl_context = None
    if args.https:
        cert_path = Path(args.cert).expanduser().resolve() if args.cert else (Path(__file__).resolve().parent / "cert" / "server.crt")
        key_path = Path(args.key).expanduser().resolve() if args.key else (Path(__file__).resolve().parent / "cert" / "server.key")

        all_detected_ips = get_all_lan_ips()
        required_ips = list(dict.fromkeys(all_detected_ips + ["127.0.0.1", lan_ip]))

        if (args.cert or args.key) and not args.auto_cert:
            if not cert_path.exists() or not key_path.exists():
                print(f"Error: Specified TLS certificate ({cert_path}) or key ({key_path}) not found.", file=sys.stderr)
                sys.exit(1)
        else:
            needs_gen = not cert_path.exists() or not key_path.exists() or not cert_matches_lan_ips(cert_path, required_ips)
            if needs_gen:
                print(f"Generating self-signed certificate for {', '.join(required_ips)} at {cert_path.parent}...")
                cert_path.parent.mkdir(parents=True, exist_ok=True)
                if not generate_self_signed_cert(cert_path, key_path, required_ips):
                    print("Error: Could not generate self-signed certificate. Starting in HTTP mode.", file=sys.stderr)
                    protocol = "http"
                    local_url = f"http://127.0.0.1:{args.port}/"
                    lan_url = f"http://{lan_ip}:{args.port}/"
                else:
                    print(f"Generated self-signed certificate with SANs {required_ips}: {cert_path}")

        if protocol == "https":
            try:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
            except Exception as e:
                print(f"Error loading TLS certificates: {e}", file=sys.stderr)
                sys.exit(1)

    # Initialize LAN Discovery
    discovery_service = None
    if not args.no_discovery:
        server_id = f"pura-{secrets.token_hex(4)}"
        server_name = "Pura Server"
        discovery_service = LanDiscoveryService(
            server_id=server_id,
            server_name=server_name,
            protocol=protocol,
            port=args.port,
            lan_url=lan_url,
            auth_enabled=bool(args.pin),
            debug=args.debug_discovery,
        )
        discovery_service.start()

    asset_dir = (Path(__file__).resolve().parent / "assets").resolve()
    handler = build_handler(
        share_dir=share_dir,
        asset_dir=asset_dir,
        max_upload_gb=args.max_upload_gb,
        lan_url=lan_url,
        pin=args.pin,
        protocol=protocol,
        bind_host=args.host,
        port=args.port,
        discovery_service=discovery_service,
    )
    # Discovery must advertise the handler's actual authentication state.
    if discovery_service is not None:
        discovery_service.auth_enabled = bool(handler.auth_enabled)
    try:
        server = PuraHTTPServer((args.host, args.port), handler)
    except OSError as err:
        if discovery_service:
            discovery_service.stop()
        print(f"Error: Could not bind to {args.host}:{args.port} - {err.strerror or err}", file=sys.stderr)
        print(f"Tip: Port {args.port} may already be in use. Try specifying another port with --port <number>.", file=sys.stderr)
        sys.exit(1)
    if ssl_context:
        server.ssl_context = ssl_context

    print(f"{APP_TITLE} is running ({protocol.upper()})")
    print(f"Sharing folder: {share_dir}")
    print(f"On this computer: {local_url}")
    print(f"On the same Wi-Fi/LAN: {lan_url}")
    if protocol == "https":
        print("Note: Using local TLS certificate. Browsers may show a standard self-signed security warning.")
    if discovery_service and discovery_service.status == "Active":
        print(f"Automatic LAN discovery: Active (broadcasting on UDP {DISCOVERY_PORT})")
    if handler.auth_enabled:
        print(f"PIN protection: enabled (PIN: {handler.pin})")
    else:
        print("PIN protection: disabled (can be enabled in Security tab)")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        if discovery_service:
            discovery_service.stop()
        server.server_close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Local-network file, clipboard, and quick-link sharing server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


APP_TITLE = "புரா சேவைகள்"
CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_UPLOAD_GB = 10
DEFAULT_PIN = "2002"
MAX_CLIPBOARD_BYTES = 512 * 1024
MAX_CLIPBOARD_ITEMS = 30


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>புரா சேவைகள்</title>
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

    textarea {
      min-height: 132px;
      resize: vertical;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 10px;
    }

    .search-box {
      min-width: min(360px, 100%);
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

    .search-box input {
      border: 0;
      background: transparent;
      min-height: 36px;
      padding: 0;
    }

    .theme-toggle {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
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
      height: clamp(380px, calc(100vh - 330px), 560px);
      min-height: 0;
      overflow: hidden;
    }

    .dropzone {
      min-height: 340px;
      padding: 22px;
      display: grid;
      place-items: center;
      text-align: center;
      outline: 2px dashed transparent;
      outline-offset: -10px;
      transition: outline-color 140ms ease, background 140ms ease;
    }

    .dropzone.dragover {
      background: #eef8f3;
      outline-color: var(--accent);
    }

    .drop-inner {
      display: grid;
      gap: 14px;
      justify-items: center;
    }

    .upload-icon {
      width: 58px;
      height: 58px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: var(--soft);
      color: var(--accent);
    }

    .upload-icon svg {
      width: 24px;
      height: 24px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    input[type="file"] { display: none; }

    .progress {
      width: 100%;
      display: none;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }

    .progress.active { display: grid; }
    .progress-track {
      height: 10px;
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
      overscroll-behavior: contain;
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
      grid-template-columns: minmax(0, 1fr) 140px;
      gap: 10px;
      align-items: end;
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
      gap: 12px;
      align-items: stretch;
      grid-auto-rows: 1fr;
    }

    .tool-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      display: grid;
      gap: 10px;
      grid-template-rows: auto;
      align-content: start;
      justify-items: start;
      background: color-mix(in srgb, var(--panel) 88%, var(--soft));
      min-height: 210px;
    }

    .tool-box h3 {
      font-size: 16px;
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
      justify-self: start;
      width: auto;
      min-width: 148px;
      margin-top: 4px;
    }

    .tool-box .qr {
      justify-self: center;
    }

    .device-list {
      display: grid;
      gap: 10px;
      width: 100%;
    }

    .device-row {
      display: grid;
      grid-template-columns: 10px minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      width: 100%;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--panel) 82%, var(--bg));
    }

    .device-row input {
      min-height: 34px;
      padding: 7px 9px;
    }

    .device-meta {
      grid-column: 2 / 4;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .tool-box .device-row button {
      min-width: 58px;
      min-height: 34px;
      padding-inline: 10px;
      margin-top: 0;
    }

    .service-list {
      display: grid;
      gap: 8px;
    }

    .service-row {
      display: grid;
      grid-template-columns: 12px 1fr auto;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--warn);
    }

    .dot.ok { background: var(--ok); }
    .dot.bad { background: var(--danger); }

    .qr {
      width: 164px;
      height: 164px;
      image-rendering: pixelated;
      border: 8px solid #ffffff;
      box-shadow: inset 0 0 0 1px var(--line);
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
      .theme-toggle { margin-left: 0; }
      .search-box { order: 5; flex-basis: 100%; }
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
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
        padding: 8px;
        position: sticky;
        top: 0;
        z-index: 12;
      }
      .tab {
        width: 100%;
        min-width: 0;
        padding-inline: 4px;
      }
      .search-box {
        grid-column: 1 / -1;
        min-width: 0;
        width: 100%;
        order: initial;
      }
      .theme-toggle {
        grid-column: 1 / -1;
        width: 100%;
        justify-content: space-between;
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
        gap: 10px;
      }
      .panel-actions {
        width: 100%;
        justify-content: flex-start;
        overflow-x: visible;
      }
      .files-panel .panel-head {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        align-items: start;
      }
      .files-panel .panel-head h2 {
        min-width: 0;
      }
      .files-panel .panel-actions {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
        margin-left: 0;
      }
      .files-panel .panel-actions .meta {
        flex: 1 1 72px;
        min-width: 64px;
      }
      .files-panel .panel-actions button {
        flex: 1 1 126px;
        max-width: 180px;
      }
      .file-row .actions {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        flex-wrap: initial;
        overflow-x: visible;
      }
      .file-row .actions button,
      .file-row .actions .button {
        width: 100%;
        min-width: 0;
        padding-inline: 8px;
      }
      #clipboard-view .panel-head {
        grid-template-columns: minmax(0, 1fr);
      }
      #clipboard-view .panel-actions {
        justify-self: start;
      }
      .clip-row {
        padding-right: 18px;
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
          <h1>Local Share</h1>
          <p>Files, clipboard, links, and device tools in one private LAN dashboard.</p>
        </div>
      </section>
      <section class="status" aria-label="Server access links">
        <div class="status-row">
          <span class="label">This page</span>
          <span class="url" id="current-url"></span>
          <button class="secondary" id="copy-page" title="Copy page link">Copy</button>
        </div>
        <div class="status-row">
          <span class="label">Folder</span>
          <span class="url" id="folder-path"></span>
          <button class="secondary" id="refresh" title="Refresh">Refresh</button>
        </div>
      </section>
    </header>

    <nav class="tabs" role="tablist" aria-label="Views">
      <button class="secondary tab active" id="tab-files" type="button" role="tab" aria-controls="files-view" aria-selected="true" data-view="files-view">Files</button>
      <button class="secondary tab" id="tab-clipboard" type="button" role="tab" aria-controls="clipboard-view" aria-selected="false" data-view="clipboard-view">Clipboard</button>
      <button class="secondary tab" id="tab-tools" type="button" role="tab" aria-controls="tools-view" aria-selected="false" data-view="tools-view">Tools</button>
      <label class="search-box">
        Search
        <input id="global-search" type="search" placeholder="Files, clipboard, links">
      </label>
      <label class="theme-toggle">
        Dark mode
        <button class="switch" id="theme-toggle" type="button" role="switch" aria-checked="false" aria-label="Toggle dark mode"><span></span></button>
      </label>
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

    <section class="view active" id="files-view" role="tabpanel" aria-labelledby="tab-files">
      <section class="grid">
        <section class="panel dropzone" id="dropzone">
          <input id="file-input" type="file" multiple>
          <div class="drop-inner">
            <span class="upload-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M12 3v12"></path><path d="m7 8 5-5 5 5"></path><path d="M5 21h14"></path></svg>
            </span>
            <span>
              <strong>Choose, drag, or paste files</strong><br>
              <span id="upload-note">Files stay on this computer.</span>
            </span>
            <div class="inline-form">
              <div class="field">
                <label for="file-expiry">Auto-delete uploads</label>
                <select id="file-expiry">
                  <option value="0">Never</option>
                  <option value="600">After 10 minutes</option>
                  <option value="3600">After 1 hour</option>
                  <option value="86400">After 24 hours</option>
                </select>
              </div>
              <button type="button" id="choose-button">Select files</button>
            </div>
            <div class="progress" id="progress">
              <div class="progress-track"><span></span></div>
              <span id="progress-text">Waiting</span>
              <button class="secondary" type="button" id="cancel-upload">Cancel upload</button>
            </div>
            <div class="queue" id="upload-queue"></div>
          </div>
        </section>

        <section class="panel files-panel">
          <div class="panel-head">
            <h2>Shared files</h2>
            <div class="panel-actions">
              <span class="meta" id="file-count">Loading...</span>
              <button class="secondary" id="download-all-files" type="button">Download all</button>
              <button class="danger" id="delete-all-files" type="button">Delete all</button>
            </div>
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
            <div class="inline-form">
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
          <div class="tool-box">
            <h3>Dashboard summary</h3>
            <div class="service-list">
              <div class="service-row"><span class="dot ok"></span><span>Storage</span><strong id="quick-storage">--</strong></div>
              <div class="service-row"><span class="dot ok"></span><span>Latest upload</span><strong id="quick-upload">None</strong></div>
              <div class="service-row"><span class="dot ok"></span><span>Devices</span><strong id="quick-devices">0</strong></div>
            </div>
          </div>
          <div class="tool-box">
            <h3>Phone QR</h3>
            <img class="qr" id="qr-image" alt="QR code for LAN link">
            <span class="meta">Scan to open this page on another device. If it does not scan, copy the LAN link.</span>
          </div>
          <div class="tool-box">
            <h3>Quick link</h3>
            <code id="lan-url"></code>
            <button class="secondary" id="copy-lan">Copy LAN link</button>
          </div>
          <div class="tool-box">
            <h3>Security</h3>
            <p id="security-note">Checking settings...</p>
            <button class="secondary" id="lock-button">Lock this browser</button>
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
          <div class="tool-box">
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
      <p class="auth-subtitle">Enter your private PIN to open file sharing, clipboard transfer, and device tools.</p>
      <div class="pin-panel">
        <input id="pin-input" type="password" inputmode="numeric" autocomplete="current-password" placeholder="PIN" aria-label="PIN">
        <label class="trust-row">
          <input id="trust-device" type="checkbox">
          Trust this device for 7 days
        </label>
        <button>Open dashboard</button>
      </div>
    </form>
  </section>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
    const currentUrl = document.querySelector("#current-url");
    const folderPath = document.querySelector("#folder-path");
    const copyPage = document.querySelector("#copy-page");
    const refreshButton = document.querySelector("#refresh");
    const dropzone = document.querySelector("#dropzone");
    const fileInput = document.querySelector("#file-input");
    const fileExpiry = document.querySelector("#file-expiry");
    const chooseButton = document.querySelector("#choose-button");
    const progress = document.querySelector("#progress");
    const progressBar = document.querySelector("#progress span");
    const progressText = document.querySelector("#progress-text");
    const cancelUpload = document.querySelector("#cancel-upload");
    const uploadQueue = document.querySelector("#upload-queue");
    const fileList = document.querySelector("#file-list");
    const fileCount = document.querySelector("#file-count");
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
    const pinInput = document.querySelector("#pin-input");
    const trustDevice = document.querySelector("#trust-device");
    const previewDialog = document.querySelector("#preview-dialog");
    const previewBody = document.querySelector("#preview-body");
    const previewTitle = document.querySelector("#preview-title");
    const closePreview = document.querySelector("#close-preview");
    const artworkCards = document.querySelectorAll(".artwork-card");
    const doveDialog = document.querySelector("#dove-dialog");
    const modalArtwork = document.querySelector("#modal-artwork");
    const closeDove = document.querySelector("#close-dove");
    const qrImage = document.querySelector("#qr-image");
    const lanUrl = document.querySelector("#lan-url");
    const copyLan = document.querySelector("#copy-lan");
    const securityNote = document.querySelector("#security-note");
    const lockButton = document.querySelector("#lock-button");
    const themeToggle = document.querySelector("#theme-toggle");
    const globalSearch = document.querySelector("#global-search");
    const serviceList = document.querySelector("#service-list");
    const checkServices = document.querySelector("#check-services");
    const deviceList = document.querySelector("#device-list");
    const metricStorage = document.querySelector("#metric-storage");
    const metricUpload = document.querySelector("#metric-upload");
    const metricClipboard = document.querySelector("#metric-clipboard");
    const metricDevices = document.querySelector("#metric-devices");
    const quickStorage = document.querySelector("#quick-storage");
    const quickUpload = document.querySelector("#quick-upload");
    const quickDevices = document.querySelector("#quick-devices");
    const copyLatestClip = document.querySelector("#copy-latest-clip");
    const copyInboxLatest = document.querySelector("#copy-inbox-latest");
    const pasteSaveClipboard = document.querySelector("#paste-save-clipboard");
    const clearClipboard = document.querySelector("#clear-clipboard");
    let latestClipId = null;
    let infoCache = null;
    let allFiles = [];
    let allClips = [];
    let latestUploadUrl = "";
    let latestClipText = "";
    let uploadItems = [];
    let eventSource = null;
    let autoLockTimer = null;
    let activeUploadRequest = null;
    let uploadCanceled = false;
    const maxTextPreviewBytes = 256 * 1024;

    currentUrl.textContent = window.location.href;
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
      window.setTimeout(() => pinInput.focus(), 80);
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
      if (localStorage.getItem("pura-trusted") === "true") return;
      autoLockTimer = window.setTimeout(async () => {
        await fetchJson("/api/logout", {method: "POST"}).catch(() => {});
        showAuth();
        showToast("Locked after inactivity");
      }, 15 * 60 * 1000);
    }

    for (const eventName of ["click", "keydown", "pointermove", "paste", "drop"]) {
      document.addEventListener(eventName, resetAutoLock, {passive: true});
    }

    async function copyText(text, label) {
      try {
        await navigator.clipboard.writeText(text);
        showToast(`${label} copied`);
      } catch {
        showToast("Copy failed. Select the text manually.");
      }
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
      return !query || value.toLowerCase().includes(query);
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

    async function loadDashboard() {
      const data = await fetchJson("/api/dashboard");
      metricStorage.textContent = `${formatSize(data.storage_bytes)} / ${data.file_count} files`;
      const uploadName = data.latest_upload ? data.latest_upload.name : "None";
      latestUploadUrl = data.latest_upload ? data.latest_upload.url : "";
      metricUpload.textContent = compactPreview(uploadName, 48);
      metricUpload.title = uploadName;
      downloadLatestUpload.disabled = !latestUploadUrl;
      quickStorage.textContent = formatSize(data.storage_bytes);
      quickUpload.textContent = data.latest_upload ? data.latest_upload.name.slice(0, 18) : "None";
      quickUpload.title = data.latest_upload ? data.latest_upload.name : "None";
      latestClipText = data.latest_clipboard ? data.latest_clipboard.text : "";
      metricClipboard.textContent = compactPreview(latestClipText, 72);
      metricClipboard.title = latestClipText || "None";
      copyLatestClip.disabled = !latestClipText;
      copyInboxLatest.disabled = !latestClipText;
      quickDevices.textContent = String((data.devices || []).length);
      renderDevices(data.devices || []);
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

    async function loadInfo() {
      const info = await fetchJson("/api/info");
      infoCache = info;
      folderPath.textContent = info.share_dir;
      uploadNote.textContent = `Up to ${info.max_upload_gb} GB per file. Paste images/files anywhere on the page.`;
      lanUrl.textContent = info.lan_url;
      securityNote.textContent = info.auth_enabled ? "PIN protection is enabled." : "No PIN is set. Use --pin 2002 when starting for trusted access control.";
      lockButton.disabled = !info.auth_enabled;
      qrImage.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=12&data=${encodeURIComponent(info.lan_url)}`;
      await checkAllServices();
    }

    async function loadFiles() {
      const data = await fetchJson("/api/files");
      allFiles = data.files;
      renderFiles();
    }

    function isTextLikeFile(file) {
      return file.type.startsWith("text/") || /\.(json|csv|md|log|py|js|css|html|htm|xml|txt)$/i.test(file.name);
    }

    function renderFiles() {
      const files = allFiles.filter((file) => matchesSearch(`${file.name} ${file.type}`));
      fileCount.textContent = files.length === 1 ? "1 file" : `${files.length} files`;
      downloadAllFiles.disabled = !allFiles.length;
      deleteAllFiles.disabled = !allFiles.length;
      if (!files.length) {
        fileList.innerHTML = '<div class="empty">No files shared yet.</div>';
        return;
      }

      fileList.innerHTML = "";
      for (const file of files) {
        const row = document.createElement("article");
        row.className = "file-row";

        const details = document.createElement("div");
        const name = document.createElement("div");
        name.className = "file-name";
        name.textContent = file.name;
        name.title = file.name;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${formatSize(file.size)} | ${file.type} | ${formatDate(file.modified)} | ${formatRemaining(file.expires_at)}`;
        meta.title = meta.textContent;
        details.append(name, meta);

        const actions = document.createElement("div");
        actions.className = "actions";

        const preview = document.createElement("button");
        preview.className = "secondary";
        preview.type = "button";
        preview.textContent = "Preview";
        preview.addEventListener("click", () => openPreview(file));

        const download = document.createElement("a");
        download.className = "button";
        download.href = file.url;
        download.textContent = "Download";

        const copy = document.createElement("button");
        copy.className = "secondary";
        copy.type = "button";
        copy.textContent = "Copy link";
        copy.addEventListener("click", () => copyText(new URL(file.url, location.href).href, "File link"));

        const rename = document.createElement("button");
        rename.className = "secondary";
        rename.type = "button";
        rename.textContent = "Rename";
        rename.addEventListener("click", async () => {
          const nextName = prompt("New file name", file.name);
          if (!nextName || nextName === file.name) return;
          await fetchJson(`/api/files/${encodeURIComponent(file.name)}`, {
            method: "PATCH",
            body: JSON.stringify({name: nextName})
          });
          showToast("File renamed");
          await Promise.all([loadFiles(), loadDashboard()]);
        });

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Delete";
        remove.addEventListener("click", async () => {
          if (!confirm(`Delete ${file.name}?`)) return;
          await fetchJson(`/api/files/${encodeURIComponent(file.name)}`, { method: "DELETE" });
          showToast("File deleted");
          await Promise.all([loadFiles(), loadDashboard()]);
        });

        actions.append(preview, download, copy, rename, remove);
        row.append(details, actions);
        fileList.append(row);
      }
    }

    async function openPreview(file) {
      previewTitle.textContent = file.name;
      previewBody.innerHTML = "";
      const previewUrl = `${file.url}?preview=1`;
      if (file.type.startsWith("image/")) {
        const image = document.createElement("img");
        image.className = "preview-image";
        image.src = previewUrl;
        previewBody.append(image);
      } else if (file.type === "application/pdf" || file.type.startsWith("video/") || file.type.startsWith("audio/")) {
        const frame = document.createElement("iframe");
        frame.className = "preview-frame";
        frame.src = previewUrl;
        previewBody.append(frame);
      } else if (isTextLikeFile(file)) {
        if (file.size > maxTextPreviewBytes) {
          const note = document.createElement("div");
          note.className = "preview-note";
          note.textContent = `This text file is ${formatSize(file.size)}, so the in-app preview is disabled to keep the dashboard stable. Use Download to open the full file.`;
          previewBody.append(note);
          previewDialog.showModal();
          closePreview.focus();
          return;
        }
        const text = document.createElement("pre");
        text.className = "preview-text";
        const response = await fetch(previewUrl, {credentials: "same-origin"});
        text.textContent = await response.text();
        previewBody.append(text);
      } else {
        previewBody.innerHTML = '<p>No browser preview for this file type.</p>';
      }
      previewDialog.showModal();
      closePreview.focus();
    }

    function uploadFile(file) {
      return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        activeUploadRequest = request;
        const expires = encodeURIComponent(fileExpiry.value || "0");
        request.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}&expires=${expires}`);
        request.withCredentials = true;
        const start = performance.now();
        request.upload.addEventListener("progress", (event) => {
          if (!event.lengthComputable) return;
          const percent = Math.round((event.loaded / event.total) * 100);
          const elapsed = Math.max(0.1, (performance.now() - start) / 1000);
          const speed = event.loaded / elapsed;
          progressBar.style.width = `${percent}%`;
          progressText.textContent = `${percent}% | ${formatSize(speed)}/s`;
        });
        request.addEventListener("load", () => {
          let body = {};
          try { body = JSON.parse(request.responseText || "{}"); } catch {}
          if (request.status === 401) {
            showAuth();
            reject(new Error("PIN required"));
          } else if (request.status >= 200 && request.status < 300) {
            resolve(body);
          } else {
            reject(new Error(body.error || request.statusText));
          }
        });
        request.addEventListener("error", () => reject(new Error("Upload failed")));
        request.addEventListener("abort", () => reject(new Error("Upload canceled")));
        request.send(file);
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

    async function uploadFiles(files) {
      const selected = [...files];
      if (!selected.length) return;
      uploadItems = selected.map((file) => ({name: file.name, size: file.size, status: "Waiting"}));
      renderUploadQueue();
      progress.classList.add("active");
      uploadCanceled = false;
      progressBar.style.width = "0";
      try {
        for (let index = 0; index < selected.length; index += 1) {
          if (uploadCanceled) break;
          uploadItems[index].status = "Uploading";
          renderUploadQueue();
          progressText.textContent = `Uploading ${index + 1} of ${selected.length}: ${selected[index].name}`;
          await uploadFile(selected[index]);
          uploadItems[index].status = "Done";
          renderUploadQueue();
        }
        showToast(uploadCanceled ? "Upload canceled" : "Upload complete");
        await Promise.all([loadFiles(), loadDashboard()]);
      } catch (error) {
        showToast(error.message);
      } finally {
        activeUploadRequest = null;
        progress.classList.remove("active");
        progressBar.style.width = "0";
        progressText.textContent = "Waiting";
        fileInput.value = "";
        window.setTimeout(() => {
          if (!progress.classList.contains("active")) {
            uploadItems = uploadItems.filter((item) => item.status !== "Done");
            renderUploadQueue();
          }
        }, 2500);
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
      const qrCanvas = document.createElement("canvas");
      qrCanvas.width = 220;
      qrCanvas.height = 220;
      const version = 4;
      const size = 17 + version * 4;
      const dataCodewords = 80;
      const eccCodewords = 20;
      const modules = Array.from({length: size}, () => Array(size).fill(false));
      const reserved = Array.from({length: size}, () => Array(size).fill(false));

      function setFunc(row, col, dark) {
        if (row < 0 || col < 0 || row >= size || col >= size) return;
        modules[row][col] = dark;
        reserved[row][col] = true;
      }

      function finder(row, col) {
        for (let y = -1; y <= 7; y += 1) {
          for (let x = -1; x <= 7; x += 1) {
            const rr = row + y;
            const cc = col + x;
            if (rr < 0 || cc < 0 || rr >= size || cc >= size) continue;
            const dark = x >= 0 && x <= 6 && y >= 0 && y <= 6 &&
              (x === 0 || x === 6 || y === 0 || y === 6 || (x >= 2 && x <= 4 && y >= 2 && y <= 4));
            setFunc(rr, cc, dark);
          }
        }
      }

      finder(0, 0);
      finder(0, size - 7);
      finder(size - 7, 0);
      for (let i = 8; i < size - 8; i += 1) {
        setFunc(6, i, i % 2 === 0);
        setFunc(i, 6, i % 2 === 0);
      }
      for (const center of [6, 26]) {
        if (center === 6) continue;
        for (const rowCenter of [6, 26]) {
          if ((center === 26 && rowCenter === 6) || (center === 6 && rowCenter === 26)) continue;
          for (let y = -2; y <= 2; y += 1) {
            for (let x = -2; x <= 2; x += 1) {
              const dark = Math.max(Math.abs(x), Math.abs(y)) === 2 || (x === 0 && y === 0);
              setFunc(rowCenter + y, center + x, dark);
            }
          }
        }
      }
      setFunc(4 * version + 9, 8, true);

      const bytes = new TextEncoder().encode(text);
      if (bytes.length > 72) {
        showToast("LAN URL is too long for the built-in QR");
        return;
      }
      const bits = [];
      function pushBits(value, count) {
        for (let i = count - 1; i >= 0; i -= 1) bits.push((value >>> i) & 1);
      }
      pushBits(0b0100, 4);
      pushBits(bytes.length, 8);
      for (const byte of bytes) pushBits(byte, 8);
      pushBits(0, Math.min(4, dataCodewords * 8 - bits.length));
      while (bits.length % 8) bits.push(0);
      const data = [];
      for (let i = 0; i < bits.length; i += 8) {
        data.push(bits.slice(i, i + 8).reduce((acc, bit) => (acc << 1) | bit, 0));
      }
      for (let pad = 0xec; data.length < dataCodewords; pad ^= 0xfd) data.push(pad);

      const exp = Array(512).fill(0);
      const log = Array(256).fill(0);
      let value = 1;
      for (let i = 0; i < 255; i += 1) {
        exp[i] = value;
        log[value] = i;
        value <<= 1;
        if (value & 0x100) value ^= 0x11d;
      }
      for (let i = 255; i < 512; i += 1) exp[i] = exp[i - 255];
      function mul(a, b) {
        return a && b ? exp[log[a] + log[b]] : 0;
      }
      let generator = [1];
      for (let i = 0; i < eccCodewords; i += 1) {
        const next = Array(generator.length + 1).fill(0);
        for (let j = 0; j < generator.length; j += 1) {
          next[j] ^= generator[j];
          next[j + 1] ^= mul(generator[j], exp[i]);
        }
        generator = next;
      }
      const ecc = Array(eccCodewords).fill(0);
      for (const byte of data) {
        const factor = byte ^ ecc.shift();
        ecc.push(0);
        for (let i = 0; i < eccCodewords; i += 1) ecc[i] ^= mul(generator[i + 1], factor);
      }
      const allCodewords = data.concat(ecc);
      const codeBits = [];
      for (const byte of allCodewords) pushCodeBits(byte, 8);
      function pushCodeBits(value, count) {
        for (let i = count - 1; i >= 0; i -= 1) codeBits.push((value >>> i) & 1);
      }

      let bitIndex = 0;
      let upward = true;
      for (let right = size - 1; right >= 1; right -= 2) {
        if (right === 6) right -= 1;
        for (let vert = 0; vert < size; vert += 1) {
          const row = upward ? size - 1 - vert : vert;
          for (let j = 0; j < 2; j += 1) {
            const col = right - j;
            if (reserved[row][col]) continue;
            let bit = bitIndex < codeBits.length ? codeBits[bitIndex] : 0;
            bitIndex += 1;
            if ((row + col) % 2 === 0) bit ^= 1;
            modules[row][col] = Boolean(bit);
          }
        }
        upward = !upward;
      }

      const formatData = (1 << 3) | 0;
      let rem = formatData << 10;
      for (let i = 14; i >= 10; i -= 1) {
        if ((rem >>> i) & 1) rem ^= 0x537 << (i - 10);
      }
      const format = ((formatData << 10) | rem) ^ 0x5412;
      function formatBit(i) { return Boolean((format >>> i) & 1); }
      for (let i = 0; i <= 5; i += 1) setFunc(8, i, formatBit(i));
      setFunc(8, 7, formatBit(6));
      setFunc(8, 8, formatBit(7));
      setFunc(7, 8, formatBit(8));
      for (let i = 9; i < 15; i += 1) setFunc(14 - i, 8, formatBit(i));
      for (let i = 0; i < 8; i += 1) setFunc(size - 1 - i, 8, formatBit(i));
      for (let i = 8; i < 15; i += 1) setFunc(8, size - 15 + i, formatBit(i));

      const ctx = qrCanvas.getContext("2d");
      const pixels = qrCanvas.width;
      const quiet = 4;
      const cell = Math.floor(pixels / (size + quiet * 2));
      const offset = Math.floor((pixels - (size + quiet * 2) * cell) / 2) + quiet * cell;
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, pixels, pixels);
      ctx.fillStyle = "#111827";
      for (let row = 0; row < size; row += 1) {
        for (let col = 0; col < size; col += 1) {
          if (modules[row][col]) ctx.fillRect(offset + col * cell, offset + row * cell, cell, cell);
        }
      }
      qrImage.src = qrCanvas.toDataURL("image/png");
    }

    document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
    globalSearch.addEventListener("input", () => {
      renderFiles();
      renderClipboard();
    });
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
    copyLatestClip.addEventListener("click", copyLatestClipboard);
    copyInboxLatest.addEventListener("click", copyLatestClipboard);
    pasteSaveClipboard.addEventListener("click", pasteAndSaveClipboard);
    clearClipboard.addEventListener("click", clearClipboardInbox);
    downloadLatestUpload.addEventListener("click", downloadLatestFile);
    downloadAllFiles.addEventListener("click", downloadAllSharedFiles);
    deleteAllFiles.addEventListener("click", deleteAllSharedFiles);
    copyPage.addEventListener("click", () => copyText(window.location.href, "Page link"));
    copyLan.addEventListener("click", () => copyText(infoCache?.lan_url || window.location.href, "LAN link"));
    refreshButton.addEventListener("click", async () => { await Promise.all([loadFiles(), loadClipboard(), loadDashboard()]); showToast("Refreshed"); });
    chooseButton.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => uploadFiles(fileInput.files));
    cancelUpload.addEventListener("click", () => {
      uploadCanceled = true;
      if (activeUploadRequest) activeUploadRequest.abort();
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
    lockButton.addEventListener("click", async () => {
      await fetchJson("/api/logout", {method: "POST"});
      localStorage.removeItem("pura-trusted");
      showAuth();
    });
    readSystemClipboard.addEventListener("click", async () => {
      try {
        clipInput.value = await navigator.clipboard.readText();
        clipInput.focus();
      } catch {
        showToast("Browser blocked clipboard read. Paste manually.");
      }
    });
    qrImage.addEventListener("error", () => {
      qrImage.alt = "QR code could not load. Copy the LAN link instead.";
      showToast("QR failed. Copy the LAN link.");
    });

    authForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await fetchJson("/api/login", {method: "POST", body: JSON.stringify({pin: pinInput.value, trusted: trustDevice.checked})});
        localStorage.setItem("pura-trusted", trustDevice.checked ? "true" : "false");
        pinInput.value = "";
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
    });

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
        await Promise.all([loadFiles(), loadClipboard(), loadDashboard()]).catch(() => {});
      });
      eventSource.addEventListener("error", () => {
        eventSource.close();
        eventSource = null;
        window.setTimeout(() => {
          if (!document.body.classList.contains("locked")) connectEvents();
        }, 3000);
      });
    }

    start().catch((error) => {
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


def sanitize_filename(name: str) -> str:
    cleaned = Path(name).name.strip()
    cleaned = re.sub(r"[^\w .()@+-]", "_", cleaned, flags=re.ASCII)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .")
    return cleaned or f"upload-{int(time.time())}"


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


class FileShareHandler(BaseHTTPRequestHandler):
    server_version = "PuraLocalShare/2.0"
    share_dir: Path
    max_upload_bytes: int
    max_upload_gb: int
    asset_dir: Path
    lan_url: str
    pin: str | None
    auth_token: str | None
    clipboard_items: list[dict]
    clipboard_counter: int
    clipboard_lock: threading.Lock
    clipboard_store_path: Path
    file_expiry: dict[str, float]
    file_expiry_lock: threading.Lock
    devices: dict[str, dict]
    device_names: dict[str, str]
    device_names_path: Path
    devices_lock: threading.Lock
    event_condition: threading.Condition
    event_version: int

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
        if not self.require_auth():
            return
        self.mark_device()
        if parsed.path == "/api/files/download-all":
            self.send_all_files_zip()
        elif parsed.path == "/api/files":
            self.send_files()
        elif parsed.path == "/api/clipboard":
            self.send_clipboard()
        elif parsed.path == "/api/health":
            self.send_health()
        elif parsed.path == "/api/dashboard":
            self.send_dashboard()
        elif parsed.path == "/api/events":
            self.send_events()
        elif parsed.path == "/api/info":
            self.send_json(
                {
                    "share_dir": str(self.share_dir),
                    "max_upload_gb": self.max_upload_gb,
                    "lan_url": self.lan_url,
                    "auth_enabled": bool(self.pin),
                }
            )
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
        cls = self.__class__
        with cls.devices_lock:
            existing = cls.devices.get(key, {})
            saved_name = cls.device_names.get(key, "")
            cls.devices[key] = {
                "id": key,
                "ip": self.client_address[0],
                "agent": short_agent,
                "name": existing.get("name") or saved_name or self.default_device_name(short_agent),
                "last_seen": time.time(),
            }

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
        self.send_json(
            {
                "storage_bytes": storage_bytes,
                "file_count": len(files),
                "latest_upload": latest_upload,
                "latest_clipboard": latest_clipboard,
                "devices": self.recent_devices(),
            }
        )

    def send_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_seen = self.event_version
        try:
            self.wfile.write(f"event: update\ndata: {last_seen}\n\n".encode("utf-8"))
            self.wfile.flush()
            deadline = time.time() + 60 * 60
            while time.time() < deadline:
                with self.event_condition:
                    self.event_condition.wait(timeout=25)
                    version = self.event_version
                if version != last_seen:
                    last_seen = version
                    payload = f"event: update\ndata: {version}\n\n"
                else:
                    payload = ": keep-alive\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            self.handle_login()
            return
        if parsed.path == "/api/logout":
            self.handle_logout()
            return
        if not self.require_auth():
            return
        self.mark_device()
        if parsed.path == "/api/upload":
            self.handle_upload(parsed)
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
        if path is None or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
            return
        try:
            payload = parse_json_body(self)
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        new_name = sanitize_filename(str(payload.get("name", "")))
        if not new_name:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Missing new file name")
            return
        destination = self.share_dir / new_name
        if destination.exists() and destination.resolve() != path.resolve():
            destination = unique_path(self.share_dir, new_name)
        try:
            path.rename(destination)
        except OSError as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Rename failed: {exc}")
            return
        with self.file_expiry_lock:
            expires_at = self.file_expiry.pop(path.name, None)
            if expires_at:
                self.file_expiry[destination.name] = expires_at
        self.send_json({"ok": True, "name": destination.name, "url": f"/files/{quote(destination.name)}"})
        self.notify_update()

    def update_device_name(self) -> None:
        try:
            payload = parse_json_body(self, limit=4096)
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
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
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not save device name: {exc}")
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
            path = self.resolve_shared_path(parsed.path.removeprefix("/api/files/"))
            if path is None or not path.is_file():
                self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
                return
            path.unlink()
            with self.file_expiry_lock:
                self.file_expiry.pop(path.name, None)
            self.send_json({"ok": True})
            self.notify_update()
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

    def handle_login(self) -> None:
        if not self.pin or not self.auth_token:
            self.send_json({"ok": True})
            return
        try:
            payload = parse_json_body(self, limit=4096)
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if secrets.compare_digest(str(payload.get("pin", "")), self.pin):
            trusted = bool(payload.get("trusted"))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            max_age = "; Max-Age=604800" if trusted else ""
            self.send_header("Set-Cookie", f"pura_share={self.auth_token}; Path=/{max_age}; SameSite=Lax")
            body = b'{"ok": true}'
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Wrong PIN")

    def handle_logout(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", "pura_share=; Path=/; Max-Age=0; SameSite=Lax")
        body = b'{"ok": true}'
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def handle_upload(self, parsed) -> None:
        query = parse_qs(parsed.query)
        original_name = query.get("name", [""])[0]
        filename = sanitize_filename(unquote(original_name))
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

        destination = unique_path(self.share_dir, filename)
        temp_name = f".upload-{time.time_ns()}-{threading.get_ident()}.tmp"
        temp_path = self.share_dir / temp_name

        try:
            with temp_path.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("Upload ended early")
                    handle.write(chunk)
                    remaining -= len(chunk)
            os.replace(temp_path, destination)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Upload failed: {exc}")
            return

        if expires > 0:
            with self.file_expiry_lock:
                self.file_expiry[destination.name] = time.time() + expires
        self.send_json(
            {"ok": True, "name": destination.name, "url": f"/files/{quote(destination.name)}"},
            HTTPStatus.CREATED,
        )
        self.notify_update()

    def create_clipboard(self) -> None:
        try:
            payload = parse_json_body(self, limit=MAX_CLIPBOARD_BYTES + 4096)
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
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
        self.notify_update()

    def send_clipboard(self) -> None:
        cls = self.__class__
        with cls.clipboard_lock:
            if self.cleanup_clipboard_locked():
                self.persist_clipboard_locked()
            items = list(cls.clipboard_items)
        self.send_json({"items": items})

    def send_files(self) -> None:
        self.cleanup_expired_files()
        files = []
        for path in sorted(self.share_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_file() or path.name.startswith("."):
                continue
            stat = path.stat()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            with self.file_expiry_lock:
                expires_at = self.file_expiry.get(path.name)
            files.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "type": content_type,
                    "expires_at": expires_at,
                    "url": f"/files/{quote(path.name)}",
                }
            )
        self.send_json({"files": files})

    def send_all_files_zip(self) -> None:
        self.cleanup_expired_files()
        files = [
            path
            for path in sorted(self.share_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
            if path.is_file() and not path.name.startswith(".")
        ]
        if not files:
            self.send_error_json(HTTPStatus.NOT_FOUND, "No files to download")
            return

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
                temp_path = Path(temp_file.name)
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in files:
                    archive.write(path, arcname=path.name)
            stat = temp_path.stat()
        except OSError as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Download all failed: {exc}")
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
        finally:
            temp_path.unlink(missing_ok=True)

    def delete_all_files(self) -> None:
        self.cleanup_expired_files()
        files = [path for path in self.share_dir.iterdir() if path.is_file() and not path.name.startswith(".")]
        deleted = 0
        failed: list[str] = []
        for path in files:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                failed.append(path.name)
        with self.file_expiry_lock:
            for path in files:
                self.file_expiry.pop(path.name, None)
        if failed:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not delete: {', '.join(failed[:3])}")
            return
        self.send_json({"ok": True, "deleted": deleted})
        self.notify_update()

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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stat.st_size))
        disposition = "inline" if preview else "attachment"
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(path.name)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        with path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def is_text_preview_file(self, path: Path, content_type: str) -> bool:
        return content_type.startswith("text/") or path.suffix.lower() in {
            ".json",
            ".csv",
            ".md",
            ".log",
            ".py",
            ".js",
            ".css",
            ".html",
            ".htm",
            ".xml",
            ".txt",
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
        with self.file_expiry_lock:
            for name, expires_at in list(self.file_expiry.items()):
                if expires_at <= now:
                    expired.append(name)
                    self.file_expiry.pop(name, None)
        for name in expired:
            path = self.share_dir / name
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

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
            path.relative_to(share_root)
            return path
        except (OSError, ValueError):
            return None

    def is_authorized(self) -> bool:
        if not self.pin:
            return True
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        token = cookie.get("pura_share")
        return bool(token and self.auth_token and secrets.compare_digest(token.value, self.auth_token))

    def require_auth(self) -> bool:
        if self.is_authorized():
            return True
        self.send_error_json(HTTPStatus.UNAUTHORIZED, "PIN required")
        return False

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)


def build_handler(share_dir: Path, asset_dir: Path, max_upload_gb: int, lan_url: str, pin: str | None) -> type[FileShareHandler]:
    class ConfiguredFileShareHandler(FileShareHandler):
        pass

    ConfiguredFileShareHandler.share_dir = share_dir
    ConfiguredFileShareHandler.asset_dir = asset_dir
    ConfiguredFileShareHandler.max_upload_gb = max_upload_gb
    ConfiguredFileShareHandler.max_upload_bytes = max_upload_gb * 1024 * 1024 * 1024
    ConfiguredFileShareHandler.lan_url = lan_url
    ConfiguredFileShareHandler.pin = pin
    ConfiguredFileShareHandler.auth_token = secrets.token_urlsafe(32) if pin else None
    ConfiguredFileShareHandler.clipboard_store_path = share_dir / "clipboard_texts" / "clipboard_items.json"
    ConfiguredFileShareHandler.clipboard_store_path.parent.mkdir(parents=True, exist_ok=True)
    ConfiguredFileShareHandler.clipboard_items = load_clipboard_items(ConfiguredFileShareHandler.clipboard_store_path)
    ConfiguredFileShareHandler.clipboard_counter = max(
        (int(item["id"]) for item in ConfiguredFileShareHandler.clipboard_items),
        default=0,
    )
    ConfiguredFileShareHandler.clipboard_lock = threading.Lock()
    ConfiguredFileShareHandler.file_expiry = {}
    ConfiguredFileShareHandler.file_expiry_lock = threading.Lock()
    ConfiguredFileShareHandler.devices = {}
    ConfiguredFileShareHandler.device_names_path = share_dir / ".pura_device_names.json"
    ConfiguredFileShareHandler.device_names = load_device_names(ConfiguredFileShareHandler.device_names_path)
    ConfiguredFileShareHandler.devices_lock = threading.Lock()
    ConfiguredFileShareHandler.event_condition = threading.Condition()
    ConfiguredFileShareHandler.event_version = 0
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
    return parser.parse_args()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    share_dir = Path(args.dir).expanduser().resolve()
    share_dir.mkdir(parents=True, exist_ok=True)

    lan_ip = get_lan_ip()
    local_url = f"http://127.0.0.1:{args.port}/"
    lan_url = f"http://{lan_ip}:{args.port}/"

    asset_dir = (Path(__file__).resolve().parent / "assets").resolve()
    handler = build_handler(share_dir, asset_dir, args.max_upload_gb, lan_url, args.pin)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"{APP_TITLE} is running")
    print(f"Sharing folder: {share_dir}")
    print(f"On this computer: {local_url}")
    print(f"On the same Wi-Fi/LAN: {lan_url}")
    if args.pin:
        print("PIN protection: enabled")
    else:
        print("PIN protection: disabled. Add --pin 1234 to require a PIN.")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

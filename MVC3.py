# Multi AI Chat Desktop Client
# PyQt6-based application for managing multiple AI chat sessions simultaneously

import sys
import os

# Performance: Set Chromium-specific optimization flags before any Qt imports
# --enable-gpu-rasterization: Uses GPU for drawing, faster than CPU
# --enable-zero-copy: Reduces memory copies for textures
# --ignore-gpu-blocklist: Forces hardware acceleration on older/unsupported GPUs
# --enable-parallel-downloading: Speeds up loading of JS/CSS assets
os.environ["QTWEBENGINE_CHROME_FLAGS"] = (
    "--enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist "
    "--enable-features=ParallelDownloading,CanvasOoopRasterization "
    "--disable-background-networking --disable-sync --metrics-recording-only "
    "--wasm-tier-up --enable-webgl-draft-extensions"
)

import argparse
import subprocess
import shutil
import webbrowser
import json
import base64
import mimetypes
from urllib.parse import quote_plus
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QLineEdit,
                             QPushButton, QFrame, QSplitter, QComboBox, QStackedLayout,
                             QFileDialog, QSizePolicy)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QPoint, QUrl, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QGuiApplication, QKeyEvent, QColor,
                         QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent)
from PyQt6.QtTest import QTest
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineScript, QWebEngineUrlRequestInterceptor

# Pre-computed header bytes for performance (avoid repeated encoding)
_HEADER_ACCEPT_LANG = b"en-US,en;q=0.9"
_HEADER_SEC_CH_UA = b'"Not A(Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"'
_HEADER_SEC_CH_MOBILE = b"?0"
_HEADER_SEC_CH_PLATFORM = b'"Windows"'

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Lightweight request interceptor - filters tracking and sets essential headers for speed"""
    # Common tracking/telemetry domains to block for faster load
    _BLOCK_LIST = {
        b"google-analytics.com", b"analytics.google.com", b"sentry.io", 
        b"intercom.io", b"intercomcdn.com", b"segment.io", b"facebook.net",
        b"hotjar.com", b"mixpanel.com"
    }

    def interceptRequest(self, info):
        # Block telemetry/tracking to speed up page logic
        url_host = info.requestUrl().host().lower().encode()
        for block_domain in self._BLOCK_LIST:
            if block_domain in url_host:
                info.block(True)
                return

        # Only set critical headers that affect site behavior
        info.setHttpHeader(b"Accept-Language", _HEADER_ACCEPT_LANG)
        info.setHttpHeader(b"sec-ch-ua", _HEADER_SEC_CH_UA)
        info.setHttpHeader(b"sec-ch-ua-mobile", _HEADER_SEC_CH_MOBILE)
        info.setHttpHeader(b"sec-ch-ua-platform", _HEADER_SEC_CH_PLATFORM)

# Class-level user agent to avoid repeated string creation
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

class CustomWebEnginePage(QWebEnginePage):
    fileUploadAccepted = pyqtSignal(int, int, int)

    # Track if user agent was set on this profile to avoid redundant calls
    _ua_set_profiles = set()
    
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        # Only set user agent once per profile
        profile_id = id(profile)
        if profile_id not in CustomWebEnginePage._ua_set_profiles:
            profile.setHttpUserAgent(_USER_AGENT)
            CustomWebEnginePage._ua_set_profiles.add(profile_id)
        self._popup_windows = []
        self._upload_token = 0
        self._queued_upload_files = []

    def queue_file_upload(self, file_paths):
        """Provide files to the next file chooser opened by this page."""
        self._upload_token += 1
        self._queued_upload_files = list(file_paths)
        return self._upload_token

    def cancel_queued_file_upload(self, token):
        if token == self._upload_token:
            self._queued_upload_files = []

    def chooseFiles(self, mode, old_files, accepted_mime_types):
        """Answer a website's file chooser with files dropped on the main input."""
        if self._queued_upload_files:
            token = self._upload_token
            is_multiple = mode == QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
            if is_multiple:
                selected = self._queued_upload_files
                self._queued_upload_files = []
            else:
                selected = self._queued_upload_files[:1]
                self._queued_upload_files = self._queued_upload_files[1:]

            remaining = len(self._queued_upload_files)
            # Defer the signal so the chooser can finish before another file is queued.
            QTimer.singleShot(
                0,
                lambda t=token, count=len(selected), left=remaining:
                    self.fileUploadAccepted.emit(t, count, left)
            )
            return selected

        return super().chooseFiles(mode, old_files, accepted_mime_types)
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Silence console messages entirely for performance
        # Prevents expensive string passing between processes
        pass
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # Allow all navigation including popups
        return True
    
    def createWindow(self, window_type):
        """Handle popup windows for OAuth flows"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton
        from PyQt6.QtCore import QTimer
        
        # Create independent popup dialog
        popup = QDialog()
        popup.setWindowTitle("Sign in - Pop-up")
        popup.setGeometry(100, 100, 600, 700)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create new web view for popup
        popup_view = CustomWebEngineView()
        popup_page = CustomWebEnginePage(self.profile(), popup_view)
        popup_view.setPage(popup_page)
        
        layout.addWidget(popup_view)
        
        # Add a close button at the bottom
        close_btn = QPushButton("Close Pop-up")
        close_btn.clicked.connect(popup.close)
        layout.addWidget(close_btn)
        
        popup.setLayout(layout)
        
        # Keep reference to prevent garbage collection
        self._popup_windows.append(popup)
        
        # Display popup
        popup.show()
        
        # Auto-close on auth completion
        def check_auth_complete():
            try:
                url = popup_page.url().toString()
                # Detect OAuth callback completion
                if url and url != "about:blank":
                    if any(pattern in url for pattern in [
                        'oauth/authorized',
                        'oauth2/authorized', 
                        'oauth_callback',
                        'auth/callback',
                        '/close',
                        'success=true'
                    ]):
                        QTimer.singleShot(1500, popup.close)
            except:
                pass
        
        popup_page.urlChanged.connect(lambda: check_auth_complete())
        
        # Cleanup when closed
        popup.finished.connect(lambda: self._cleanup_popup(popup))
        
        return popup_page
    
    def _cleanup_popup(self, popup):
        """Clean up popup window reference"""
        if popup in self._popup_windows:
            self._popup_windows.remove(popup)

class CustomWebEngineView(QWebEngineView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dev_tools_view = None

    def wheelEvent(self, event):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle > 0: self.setZoomFactor(self.zoomFactor() + 0.1)
            elif angle < 0: self.setZoomFactor(self.zoomFactor() - 0.1)
        else: super().wheelEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        if self.hasSelection():
            selected_text = self.selectedText()
            search_action = QAction("Search on Google", self)
            search_action.triggered.connect(lambda: self._open_google_search(selected_text))
            menu.addSeparator()
            menu.addAction(search_action)
        inspect_action = QAction("Inspect Element", self)
        inspect_action.triggered.connect(lambda: self.open_dev_tools())
        menu.addSeparator()
        menu.addAction(inspect_action)
        menu.exec(event.globalPos())

    def _open_google_search(self, text):
        query = quote_plus(text)
        url = f"https://www.google.com/search?q={query}"
        webbrowser.open(url)

    def open_dev_tools(self):
        if self.dev_tools_view is None:
            self.dev_tools_view = QWebEngineView()
            self.dev_tools_view.setWindowTitle("Developer Tools")
            self.dev_tools_view.setGeometry(100, 100, 800, 600)
        self.page().setDevToolsPage(self.dev_tools_view.page())
        self.dev_tools_view.show()

class DropableFrame(QFrame):
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _extract_local_files(self, event):
        files = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    files.append(url.toLocalFile())
                elif url.path() and os.path.exists(url.path()):
                    files.append(url.path())
        return files

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._extract_local_files(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._extract_local_files(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        files = self._extract_local_files(event)
        if files:
            event.acceptProposedAction()
            self.filesDropped.emit(files)
        else:
            super().dropEvent(event)

class PromptTextEdit(QTextEdit):
    ctrlEnterPressed = pyqtSignal()
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_active = False
        self._default_style = """
            QTextEdit {
                border: 1px solid #555555;
                border-radius: 5px;
                padding: 4px;
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QTextEdit:focus {
                border: 1px solid #2196F3;
            }
        """
        self._drag_style = """
            QTextEdit {
                border: 2px dashed #4CAF50;
                border-radius: 5px;
                padding: 4px;
                background-color: #1b3320;
                color: #ffffff;
            }
        """
        self.setStyleSheet(self._default_style)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.ctrlEnterPressed.emit()
        else:
            super().keyPressEvent(event)
        
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())

    def _extract_local_files(self, event):
        files = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    files.append(url.toLocalFile())
                else:
                    path = url.path()
                    if path and os.path.exists(path):
                        files.append(path)
        return files

    def dragEnterEvent(self, event: QDragEnterEvent):
        files = self._extract_local_files(event)
        if files:
            self._drag_active = True
            self.setStyleSheet(self._drag_style)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        files = self._extract_local_files(event)
        if files:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        if self._drag_active:
            self._drag_active = False
            self.setStyleSheet(self._default_style)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if self._drag_active:
            self._drag_active = False
            self.setStyleSheet(self._default_style)
            
        files = self._extract_local_files(event)
        if files:
            event.acceptProposedAction()
            self.filesDropped.emit(files)
        else:
            super().dropEvent(event)

class MultiVibeChat(QMainWindow):
    # Pre-computed list of domains for preconnect (speeds up initial connections)
    _PRECONNECT_DOMAINS = [
        'chatgpt.com', 'claude.ai', 'grok.com', 'aistudio.google.com', 'kimi.com',
        'meta.ai',
        'chat.qwen.ai', 'chat.z.ai',
        'cdn.oaistatic.com', 'cdn.openai.com'  # Common CDNs
    ]
    
    def __init__(self, profile_name='default'):
        super().__init__()
        self.profile_name = profile_name
        self.browsers = [] 
        self.is_grid_layout = False  # Default to Nx1 horizontal layout
        self.url_bars_visible = False  # Track URL bar visibility for Alt toggle
        self.broadcast_enabled = True  # Toggle for unified prompt delivery
        self._pending_loads = {}  # Track deferred browser loads
        self._attachment_batch_id = 0
        self._attachment_progress = {}
        self.all_targets = {
            'ChatGPT': 'https://chatgpt.com/', 
            'Claude': 'https://claude.ai/new',
            'Grok': 'https://grok.com/', 
            'AI Studio': 'https://aistudio.google.com/prompts/new_chat',
            'Kimi K2': 'https://www.kimi.com/en',
            'Meta AI': 'https://www.meta.ai/',
            'Qwen': 'https://chat.qwen.ai/',
            'Z AI': 'https://chat.z.ai/',
            'Gemini': 'https://gemini.google.com/app',
            'DeepSeek': 'https://chat.deepseek.com/'
        }
        self.enabled_ais = self.load_enabled_ais()  # Load saved AI selection (list of dicts)
        self.rebuild_targets_from_enabled()
        self.prompt_templates = {
            'ChatGPT': """var input = document.querySelector('div#prompt-textarea[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[data-testid="send-button"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Claude': """var input = document.querySelector('div.ProseMirror[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[aria-label="Send message"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Grok': """var input = document.querySelector('textarea[placeholder="Ask anything"]') || document.querySelector('textarea'); if (input) {{ input.focus(); document.execCommand('insertText', false, `{prompt}`); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[data-testid="chat-submit"]') || document.querySelector('button[aria-label="Submit"]') || document.querySelector('button[aria-label="Grok something"]') || document.querySelector('button[aria-label="Send message"]') || document.querySelector('button[aria-label*="send" i]'); if (btn && !btn.disabled && window.getComputedStyle(btn).display !== 'none') {{ btn.click(); clearInterval(interval); }} else if (attempts > 30) {{ input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }})); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'AI Studio': """
            var input = document.querySelector('ms-autosize-textarea textarea') ||
                       document.querySelector('textarea[placeholder*="Type something"]') ||
                       document.querySelector('textarea[aria-label*="prompt"]') ||
                       document.querySelector('.text-input-field textarea') ||
                       document.querySelector('textarea');

            if (input) {{
                input.focus();
                input.value = `{prompt}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));

                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('ms-run-button button') ||
                             document.querySelector('button[aria-label*="Run"]') ||
                             document.querySelector('button[aria-label*="Send"]') ||
                             document.querySelector('.run-button button') ||
                             document.querySelector('button.send-button');

                    if (btn && !btn.disabled) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 20) {{
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keypress', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'Kimi K2': """
            var input = document.querySelector('#chat-container > div.layout-content-main > div > div.chat-editor > div.chat-input > div.chat-input-editor-container > div.chat-input-editor') ||
                       document.querySelector('div.chat-input-editor[contenteditable="true"]') ||
                       document.querySelector('div[data-lexical-editor="true"]') ||
                       document.querySelector('.chat-input-editor');

            if (input) {{
                input.focus();
                var sel = window.getSelection();
                var range = document.createRange();
                range.selectNodeContents(input);
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('insertText', false, `{prompt}`);

                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('.send-button-container:not(.disabled)');
                    if (btn && !btn.classList.contains('disabled')) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 30) {{
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'Meta AI': """
            var input = document.querySelector('div[data-testid="composer-input"][contenteditable="true"]') ||
                        document.querySelector('textarea[data-testid="composer-input"]') ||
                        document.querySelector('[data-testid="composer-input"]');

            if (input) {{
                input.focus();

                if (input.isContentEditable) {{
                    var sel = window.getSelection();
                    var range = document.createRange();
                    range.selectNodeContents(input);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    document.execCommand('insertText', false, `{prompt}`);
                }} else {{
                    input.value = `{prompt}`;
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}

                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('button[data-testid="composer-send-button"]') ||
                              document.querySelector('button[aria-label*="Send" i]');
                    if (btn && !btn.disabled) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 30) {{
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'Qwen': """
            var input = document.querySelector('textarea.message-input-textarea') || document.querySelector('textarea');
            if (input) {{
                input.focus();
                let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                if (nativeInputValueSetter) {{
                    nativeInputValueSetter.call(input, `{prompt}`);
                }} else {{
                    input.value = `{prompt}`;
                }}
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('.message-input-right-button-send .ant-dropdown-trigger') ||
                              document.querySelector('.message-input-right-button-send > div > div') ||
                              document.querySelector('button[aria-label*="send"]') ||
                              document.querySelector('button[class*="send"]');
                    if (btn && window.getComputedStyle(btn).display !== 'none') {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 30) {{
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'Z AI': """
            var input = document.querySelector('textarea');
            if (input) {{
                input.focus();
                input.value = `{prompt}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('button[aria-label*="send"]') || document.querySelector('button[class*="send"]');
                    if (btn && !btn.disabled) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 30) {{
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'Gemini': """
            var input = document.querySelector('.ql-editor[contenteditable="true"]') ||
                        document.querySelector('rich-textarea div[contenteditable="true"]') ||
                        document.querySelector('div[aria-label="Enter a prompt for Gemini"]');

            if (input) {{
                input.focus();
                var sel = window.getSelection();
                var range = document.createRange();
                range.selectNodeContents(input);
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('insertText', false, `{prompt}`);

                let attempts = 0;
                const interval = setInterval(() => {{
                    var btn = document.querySelector('button.send-button') ||
                              document.querySelector('button[aria-label="Send message"]');
                    if (btn && btn.getAttribute('aria-disabled') !== 'true' && !btn.disabled) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 30) {{
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """,
            'DeepSeek': """
            var input = document.querySelector('textarea.ds-scroll-area') || document.querySelector('textarea[placeholder*="DeepSeek"]') || document.querySelector('textarea');
            if (input) {{
                input.focus();
                let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                if (nativeInputValueSetter) {{ nativeInputValueSetter.call(input, `{prompt}`); }}
                else {{ input.value = `{prompt}`; }}
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                let attempts = 0;
                const interval = setInterval(() => {{
                    var btns = Array.from(document.querySelectorAll('div.ds-icon-button[role="button"]:not(.ds-icon-button--disabled)'));
                    var sendBtn = btns.find(b => b.querySelector('svg') && b.parentNode && b.parentNode.style.width === 'fit-content');
                    if (sendBtn) {{ sendBtn.click(); clearInterval(interval); }}
                    else if (attempts > 30) {{
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        clearInterval(interval);
                    }}
                    attempts++;
                }}, 100);
            }}
            """
        }
        self.init_ui()

    def rebuild_targets_from_enabled(self):
        """Update active targets dictionary from enabled settings"""
        self.targets = {}
        self.target_bases = {}
        for inst in self.enabled_ais:
            if inst == 'Extra Duplicate':
                base = getattr(self, 'extra_ai_choice', 'ChatGPT')
                target_key = f"Extra Duplicate: {base}"
                self.targets[target_key] = self.all_targets[base]
                self.target_bases[target_key] = base
            elif inst in self.all_targets:
                self.targets[inst] = self.all_targets[inst]
                self.target_bases[inst] = inst

    def init_ui(self):
        self.setWindowTitle(f"Multi Vibe Chat - Profile: {self.profile_name}")
        self.setGeometry(100, 100, 1600, 1000)

        self.main_container = QWidget()
        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.main_container)

        self.handle_profile_logic()
        
        # Trigger preconnect to AI domains for faster initial load
        self._preconnect_domains()

        # Create browser container that will be rebuilt when AI selection changes
        self.browser_container = QWidget()
        self.browser_layout = QVBoxLayout(self.browser_container)
        self.browser_layout.setContentsMargins(0, 0, 0, 0)
        
        self.view_stack = QStackedLayout()
        self.browser_layout.addLayout(self.view_stack)
        
        # Build the initial browser panes
        self.rebuild_browser_panes()

        self.main_layout.addWidget(self.browser_container, 1)

        control_panel = DropableFrame()
        control_panel.setFrameShape(QFrame.Shape.NoFrame)
        control_panel.filesDropped.connect(self.handle_files_dropped)

        control_vbox = QVBoxLayout(control_panel)
        control_vbox.setSpacing(4)
        control_vbox.setContentsMargins(4, 4, 4, 4)

        # Status notification banner for file attachments
        self.attachment_status_label = QLabel()
        self.attachment_status_label.setStyleSheet(
            "QLabel { background-color: #1e3d2f; color: #a5d6a7; border: 1px solid #2e7d32; "
            "border-radius: 4px; padding: 4px 8px; font-weight: bold; font-size: 12px; }"
        )
        self.attachment_status_label.setWordWrap(True)
        self.attachment_status_label.hide()
        control_vbox.addWidget(self.attachment_status_label)

        main_control_layout = QHBoxLayout()
        main_control_layout.setSpacing(6)
        main_control_layout.setContentsMargins(0, 0, 0, 0)

        # Attach file button
        attach_btn = QPushButton("📎")
        attach_btn.setToolTip("Attach file(s) to all opened AI chatbots (or drag & drop files here)")
        attach_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        attach_btn.setMinimumHeight(45)
        attach_btn.setFixedWidth(42)
        attach_btn.setStyleSheet(
            "QPushButton { font-size: 16px; background-color: #37474f; color: white; font-weight: bold; border-radius: 5px; } "
            "QPushButton:hover { background-color: #455a64; } "
            "QPushButton:pressed { background-color: #263238; }"
        )
        attach_btn.clicked.connect(self.open_file_dialog)
        main_control_layout.addWidget(attach_btn)

        self.prompt_text = PromptTextEdit()
        self.prompt_text.setPlaceholderText("Enter prompt for all AIs (Ctrl+Enter to send) or drag & drop files here...")
        self.prompt_text.filesDropped.connect(self.handle_files_dropped)
        
        # --- FIX: Replaced fixed pixel height with dynamic, font-based height ---
        font_metrics = self.prompt_text.fontMetrics()
        # Set height to be roughly 4.5 lines of text plus a small margin for padding
        line_height = font_metrics.height()
        self.prompt_text.setFixedHeight(int(line_height * 4.5) + 6)

        main_control_layout.addWidget(self.prompt_text, 1)
        control_vbox.addLayout(main_control_layout)

        right_panel = QWidget()
        right_panel_layout = QHBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(4) 

        send_btn = QPushButton("Send to All")
        send_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        send_btn.setMinimumHeight(50)
        font = send_btn.font()
        font.setBold(True)
        send_btn.setFont(font)
        
        right_panel_layout.addWidget(send_btn)

        right_panel_vbox = QVBoxLayout()
        right_panel_vbox.setSpacing(4)

        from PyQt6.QtWidgets import QGridLayout
        top_button_layout = QGridLayout()
        refresh_btn = QPushButton("Refresh All")
        
        self.layout_switch_btn = QPushButton("Switch to Grid")
        self.focus_mode_btn = QPushButton("LOG IN MODE: OFF")
        self.focus_mode_btn.setCheckable(True)
        self.focus_mode_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; } QPushButton:checked { background-color: #4CAF50; color: white; }")
        google_signin_btn = QPushButton("🔐 Google Login (legacy)")
        google_signin_btn.setStyleSheet("background-color: #808080; color: white; font-weight: bold;")
        ai_select_btn = QPushButton("🤖 Select AIs")
        ai_select_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        
        # Row 0
        top_button_layout.addWidget(self.layout_switch_btn, 0, 0)
        top_button_layout.addWidget(self.focus_mode_btn, 0, 1)
        top_button_layout.addWidget(ai_select_btn, 0, 2)
        # Row 1
        top_button_layout.addWidget(refresh_btn, 1, 0)
        top_button_layout.addWidget(google_signin_btn, 1, 1, 1, 2)

        profile_bar_layout = QHBoxLayout()
        profile_bar_layout.addStretch()  # Add stretch before elements to push them to the right

        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.setPlaceholderText("Type new name to create...")
        
        existing_profiles = self.find_existing_profiles()
        self.profile_combo.addItems(existing_profiles)
        if self.profile_name in existing_profiles:
            self.profile_combo.setCurrentText(self.profile_name)

        switch_profile_btn = QPushButton("Switch / Create")
        profile_label = QLabel("Profile:")
        profile_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        profile_bar_layout.addWidget(profile_label)
        profile_bar_layout.addWidget(self.profile_combo)
        profile_bar_layout.addWidget(switch_profile_btn)
        
        right_panel_vbox.addLayout(top_button_layout)
        right_panel_vbox.addLayout(profile_bar_layout)
        right_panel_layout.addLayout(right_panel_vbox)
        main_control_layout.addWidget(right_panel)

        send_btn.clicked.connect(self.broadcast_prompts)
        self.prompt_text.ctrlEnterPressed.connect(self.broadcast_prompts)
        refresh_btn.clicked.connect(self.refresh_all)
        self.layout_switch_btn.clicked.connect(self.switch_layout)
        self.focus_mode_btn.toggled.connect(self.toggle_focus_mode)
        google_signin_btn.clicked.connect(self.open_google_signin)
        switch_profile_btn.clicked.connect(self.switch_profile)
        ai_select_btn.clicked.connect(self.open_ai_selection)
        
        self.main_layout.addWidget(control_panel)

    def keyPressEvent(self, event: QKeyEvent):
        # Toggle URL bar visibility on Alt key press (not hold)
        if event.key() == Qt.Key.Key_Alt and not event.isAutoRepeat():
            self.url_bars_visible = not self.url_bars_visible
            for browser in self.browsers:
                try:
                    if browser.get('url_bar'):
                        if self.url_bars_visible:
                            browser['url_bar'].show()
                        else:
                            browser['url_bar'].hide()
                except (RuntimeError, KeyError):
                    # URL bar has been deleted or doesn't exist, skip it
                    continue
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        # Do nothing on Alt release - we toggle on press now
        super().keyReleaseEvent(event)

    def create_browser_pane(self, name, delay_ms=0):
        """Create a browser pane, optionally with delayed load for staggered initialization"""
        from PyQt6.QtCore import QTimer
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        url_bar = QLineEdit()
        url_bar.setReadOnly(False)  # Make URL bar editable
        url_bar.setPlaceholderText("Enter URL and press Enter to navigate...")
        url_bar.hide()

        browser = CustomWebEngineView()
        page = CustomWebEnginePage(self.profile, browser)
        browser.setPage(page)
        page.fileUploadAccepted.connect(
            lambda token, count, remaining, ai_name=name, web_page=page:
                self._on_file_upload_accepted(
                    ai_name, web_page, token, count, remaining
                )
        )
        
        # Set black background to avoid white flash during page load
        page.setBackgroundColor(QColor(0, 0, 0))
        browser.setStyleSheet("background-color: #000000;")
        
        # Stagger page loads to avoid overwhelming the system
        target_url = self.targets[name]
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, lambda: browser.load(QUrl(target_url)))
        else:
            browser.load(QUrl(target_url))
        
        # Update URL bar when page URL changes
        browser.urlChanged.connect(lambda url, bar=url_bar: bar.setText(url.toString()))
        
        # Navigate when user presses Enter in URL bar
        url_bar.returnPressed.connect(lambda b=browser, bar=url_bar: self.navigate_to_url(b, bar))

        layout.addWidget(url_bar)
        layout.addWidget(browser)
        
        browser_info = {'name': name, 'browser': browser, 'url_bar': url_bar, 'container': container}
        self.browsers.append(browser_info)
        return container
    
    def _preconnect_domains(self):
        """Warm up connections to AI domains for faster page loads"""
        from PyQt6.QtCore import QTimer
        # Use a hidden browser to trigger DNS prefetch and connection warmup
        preconnect_html = '<html><head>'
        for domain in self._PRECONNECT_DOMAINS:
            preconnect_html += f'<link rel="preconnect" href="https://{domain}" crossorigin>'
            preconnect_html += f'<link rel="dns-prefetch" href="https://{domain}">'
        preconnect_html += '</head><body></body></html>'
        
        # Create a temporary hidden view to execute preconnect
        self._preconnect_view = QWebEngineView()
        self._preconnect_view.setHtml(preconnect_html)
        # Clean up after a short delay
        QTimer.singleShot(3000, self._cleanup_preconnect)
    
    def _cleanup_preconnect(self):
        """Clean up preconnect resources"""
        if hasattr(self, '_preconnect_view'):
            try:
                self._preconnect_view.deleteLater()
            except RuntimeError:
                pass
            del self._preconnect_view
    
    def navigate_to_url(self, browser, url_bar):
        """Navigate browser to URL entered in the URL bar"""
        url_text = url_bar.text().strip()
        if url_text:
            # Add https:// if no protocol specified
            if not url_text.startswith('http://') and not url_text.startswith('https://'):
                url_text = 'https://' + url_text
            browser.load(QUrl(url_text))

    def switch_layout(self):
        if self.is_grid_layout:
            # Switch to horizontal layout
            self.move_containers_to_horizontal()
            self.view_stack.setCurrentIndex(1)
            self.layout_switch_btn.setText("Switch to Grid")
        else:
            # Switch to grid layout
            self.move_containers_to_grid()
            self.view_stack.setCurrentIndex(0)
            self.layout_switch_btn.setText("Switch to Nx1")
        self.is_grid_layout = not self.is_grid_layout

    def rebuild_browser_panes(self):
        """Rebuild browser panes based on currently enabled AIs, preserving existing browsers"""
        # Get current and new AI names
        current_ai_names = {browser_info['name'] for browser_info in self.browsers if browser_info.get('browser')}
        new_ai_names = set(self.targets.keys())
        
        # Find AIs to add and remove
        ais_to_add = new_ai_names - current_ai_names
        ais_to_remove = current_ai_names - new_ai_names
        
        # Remove browsers for deselected AIs
        browsers_to_keep = []
        for browser_info in self.browsers:
            if browser_info.get('name') in ais_to_remove:
                # Remove from layout and dispose
                try:
                    # Try stored container reference first
                    container = browser_info.get('container')
                    if not container and browser_info.get('browser'):
                        container = browser_info['browser'].parent()
                    
                    if container:
                        container.setParent(None)
                        container.deleteLater()
                    
                    browser = browser_info.get('browser')
                    if browser:
                        browser.setParent(None)
                        browser.deleteLater()
                except RuntimeError:
                    # Object already deleted, ignore
                    pass
            elif browser_info.get('browser') and browser_info.get('name'):
                browsers_to_keep.append(browser_info)
        
        self.browsers = browsers_to_keep
        
        # Add browsers for newly selected AIs with staggered loading
        # Delay each subsequent browser by 150ms to avoid network/CPU contention
        delay_increment = 150
        for idx, ai_name in enumerate(ais_to_add):
            if ai_name in self.targets:
                # Create new browser pane with staggered delay
                self.create_browser_pane(ai_name, delay_ms=idx * delay_increment)
                # Note: create_browser_pane already appends to self.browsers
        
        # Clear view stack
        while self.view_stack.count() > 0:
            item = self.view_stack.itemAt(0)
            widget = item.widget() if item else None
            if widget:
                self.view_stack.removeWidget(widget)
                widget.deleteLater()
            else:
                break
        
        ai_names = list(self.targets.keys())
        num_ais = len(ai_names)
        
        if num_ais == 0:
            # Show placeholder if no AIs selected
            placeholder = QLabel("No AIs selected. Click '🤖 Select AIs' to add AI assistants.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("font-size: 16px; color: #666;")
            self.view_stack.addWidget(placeholder)
            self.view_stack.addWidget(QWidget())  # Empty widget for horizontal layout
            return
        
        # Create both layouts using the existing containers (if any)
        self.create_layouts_with_existing_containers(ai_names)
        
        # Apply URL bar visibility state
        for browser_info in self.browsers:
            try:
                if browser_info.get('url_bar') and hasattr(self, 'url_bars_visible'):
                    if self.url_bars_visible:
                        browser_info['url_bar'].show()
                    else:
                        browser_info['url_bar'].hide()
            except RuntimeError:
                # URL bar has been deleted, skip it
                continue

    def create_layouts_with_existing_containers(self, ai_names):
        """Create both grid and horizontal layouts, containers will be moved between them as needed"""
        # Create a mapping of AI names to their browser containers
        browser_containers = {}
        for browser_info in self.browsers:
            if browser_info.get('name'):
                try:
                    # First try to get the stored container reference
                    container = browser_info.get('container')
                    if not container and browser_info.get('browser'):
                        # Fallback to getting parent from browser
                        container = browser_info['browser'].parent()
                    
                    if container:
                        browser_containers[browser_info['name']] = container
                except RuntimeError:
                    # Browser object has been deleted, skip it
                    continue
        
        num_ais = len(ai_names)
        
        # Create grid layout (2xN grid)
        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        grid_layout.addWidget(main_splitter)
        
        # Create horizontal layout (Nx1)
        horizontal_container = QWidget()
        horizontal_layout = QHBoxLayout(horizontal_container)
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        horizontal_layout.addWidget(horizontal_splitter)
        
        # Add containers to the appropriate initial layout based on is_grid_layout
        if self.is_grid_layout:
            # Add to grid layout
            if num_ais == 1:
                row_splitter = QSplitter(Qt.Orientation.Horizontal)
                if ai_names[0] in browser_containers:
                    row_splitter.addWidget(browser_containers[ai_names[0]])
                main_splitter.addWidget(row_splitter)
            else:
                rows_needed = (num_ais + 1) // 2  # Ceiling division
                idx = 0
                for row in range(rows_needed):
                    row_splitter = QSplitter(Qt.Orientation.Horizontal)
                    added_widgets = 0
                    for col in range(2):
                        if idx < num_ais and ai_names[idx] in browser_containers:
                            row_splitter.addWidget(browser_containers[ai_names[idx]])
                            added_widgets += 1
                            idx += 1
                        elif idx < num_ais:
                            idx += 1
                    if added_widgets > 0:  # Only add if it has widgets
                        main_splitter.addWidget(row_splitter)
        else:
            # Add to horizontal layout
            for name in ai_names:
                if name in browser_containers:
                    horizontal_splitter.addWidget(browser_containers[name])
            
            # Set equal sizes for all widgets in horizontal layout
            if horizontal_splitter.count() > 0:
                equal_size = 100 // horizontal_splitter.count()
                sizes = [equal_size] * horizontal_splitter.count()
                remainder = 100 - (equal_size * horizontal_splitter.count())
                if remainder > 0:
                    sizes[-1] += remainder
                horizontal_splitter.setSizes(sizes)
        
        # Store references to both layouts so switch_layout can move containers
        self.grid_splitter = main_splitter
        self.horizontal_splitter = horizontal_splitter
        self.browser_containers = browser_containers
        self.ai_names = ai_names
        
        self.view_stack.addWidget(grid_container)
        self.view_stack.addWidget(horizontal_container)
        
        # Show the correct layout based on current state
        if self.is_grid_layout:
            self.view_stack.setCurrentIndex(0)
        else:
            self.view_stack.setCurrentIndex(1)
    
    def move_containers_to_horizontal(self):
        """Move all browser containers to the horizontal layout"""
        if hasattr(self, 'browser_containers') and hasattr(self, 'horizontal_splitter') and hasattr(self, 'ai_names'):
            # Process containers safely
            containers_to_move = []
            for name in self.ai_names:
                if name in self.browser_containers:
                    container = self.browser_containers[name]
                    try:
                        if container and not container.isHidden():
                            containers_to_move.append(container)
                    except RuntimeError:
                        # Container has been deleted, skip it
                        continue
            
            # Move containers one by one with safety checks
            for container in containers_to_move:
                try:
                    # Remove from current parent safely
                    if container and container.parent():
                        container.setParent(None)
                    if container:
                        self.horizontal_splitter.addWidget(container)
                except RuntimeError:
                    # Container has been deleted during move, skip it
                    continue
            
            # Set equal sizes for all widgets in horizontal layout
            if self.horizontal_splitter.count() > 0:
                # Use QTimer to set sizes after layout is settled
                from PyQt6.QtCore import QTimer
                def set_equal_sizes():
                    try:
                        if self.horizontal_splitter.count() > 0:
                            equal_size = 100 // self.horizontal_splitter.count()
                            sizes = [equal_size] * self.horizontal_splitter.count()
                            remainder = 100 - (equal_size * self.horizontal_splitter.count())
                            if remainder > 0:
                                sizes[-1] += remainder
                            self.horizontal_splitter.setSizes(sizes)
                    except (RuntimeError, AttributeError):
                        pass
                
                QTimer.singleShot(100, set_equal_sizes)
    
    def move_containers_to_grid(self):
        """Move all browser containers back to the grid layout"""
        if hasattr(self, 'browser_containers') and hasattr(self, 'grid_splitter') and hasattr(self, 'ai_names'):
            # Safely collect containers to move
            containers_to_move = []
            while self.horizontal_splitter.count() > 0:
                widget = self.horizontal_splitter.widget(0)
                if widget:
                    try:
                        widget.setParent(None)
                        containers_to_move.append(widget)
                    except RuntimeError:
                        break
                else:
                    break
            
            # Clear existing grid structure safely
            while self.grid_splitter.count() > 0:
                row_widget = self.grid_splitter.widget(0)
                if row_widget:
                    try:
                        # Remove containers from this row splitter first
                        if hasattr(row_widget, 'count'):  # It's a splitter
                            while row_widget.count() > 0:
                                container = row_widget.widget(0)
                                if container:
                                    container.setParent(None)
                        # Now it's safe to delete the empty row splitter
                        row_widget.setParent(None)
                        row_widget.deleteLater()
                    except RuntimeError:
                        break
                else:
                    break
            
            # Rebuild grid with the preserved containers
            num_ais = len(self.ai_names)
            
            if num_ais == 1:
                row_splitter = QSplitter(Qt.Orientation.Horizontal)
                if self.ai_names[0] in self.browser_containers:
                    try:
                        container = self.browser_containers[self.ai_names[0]]
                        if container and container in containers_to_move:
                            row_splitter.addWidget(container)
                    except RuntimeError:
                        pass
                if row_splitter.count() > 0:
                    self.grid_splitter.addWidget(row_splitter)
            else:
                rows_needed = (num_ais + 1) // 2
                idx = 0
                for row in range(rows_needed):
                    row_splitter = QSplitter(Qt.Orientation.Horizontal)
                    added_widgets = 0
                    for col in range(2):
                        if idx < num_ais and self.ai_names[idx] in self.browser_containers:
                            try:
                                container = self.browser_containers[self.ai_names[idx]]
                                if container and container in containers_to_move:
                                    row_splitter.addWidget(container)
                                    added_widgets += 1
                            except RuntimeError:
                                pass
                            idx += 1
                        elif idx < num_ais:
                            idx += 1
                    if added_widgets > 0:  # Only add if it has widgets
                        self.grid_splitter.addWidget(row_splitter)

    def open_ai_selection(self):
        """Open dialog to select which AIs to display"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel, QHBoxLayout, QComboBox
        from PyQt6.QtWidgets import QMessageBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Select AI Assistants")
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Choose which AI assistants to display:")
        info_label.setStyleSheet("padding: 10px; font-weight: bold;")
        layout.addWidget(info_label)
        
        # Create checkboxes for each AI
        checkboxes = {}
        for ai_name in self.all_targets.keys():
            checkbox = QCheckBox(ai_name)
            checkbox.setChecked(ai_name in self.enabled_ais)
            checkbox.setStyleSheet("padding: 5px; font-size: 14px;")
            checkboxes[ai_name] = checkbox
            layout.addWidget(checkbox)
            
        # Extra duplicate layout
        extra_layout = QHBoxLayout()
        extra_checkbox = QCheckBox("Extra Duplicate:")
        extra_checkbox.setStyleSheet("padding: 5px; font-size: 14px;")
        extra_checkbox.setChecked('Extra Duplicate' in self.enabled_ais)
        
        extra_combo = QComboBox()
        extra_combo.addItems(list(self.all_targets.keys()))
        if hasattr(self, 'extra_ai_choice') and self.extra_ai_choice in self.all_targets:
            extra_combo.setCurrentText(self.extra_ai_choice)
            
        extra_layout.addWidget(extra_checkbox)
        extra_layout.addWidget(extra_combo)
        layout.addLayout(extra_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        cancel_btn = QPushButton("Cancel")
        
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        # Button actions
        def select_all():
            for cb in checkboxes.values(): cb.setChecked(True)
            extra_checkbox.setChecked(True)
            
        def deselect_all():
            for cb in checkboxes.values(): cb.setChecked(False)
            extra_checkbox.setChecked(False)
            
        select_all_btn.clicked.connect(select_all)
        deselect_all_btn.clicked.connect(deselect_all)
        cancel_btn.clicked.connect(dialog.reject)
        
        def apply_selection():
            selected = [name for name, cb in checkboxes.items() if cb.isChecked()]
            if extra_checkbox.isChecked():
                selected.append('Extra Duplicate')
                
            if not selected:
                QMessageBox.warning(dialog, "Warning", "Please select at least one AI assistant.")
                return
            
            self.enabled_ais = selected
            self.extra_ai_choice = extra_combo.currentText()
            self.save_enabled_ais()
            self.rebuild_targets_from_enabled()
            self.rebuild_browser_panes()
            dialog.accept()
        
        apply_btn.clicked.connect(apply_selection)
        
        dialog.setLayout(layout)
        dialog.exec()

    def load_enabled_ais(self):
        """Load the enabled AI list from config file."""
        try:
            config_path = self.get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.extra_ai_choice = config.get('extra_ai_choice', 'ChatGPT')
                    enabled = config.get('enabled_ais', None)
                    if enabled:
                        valid_names = list(self.all_targets.keys()) + ['Extra Duplicate']
                        migrated_list = []
                        for item in enabled:
                            if isinstance(item, str) and item in valid_names:
                                migrated_list.append(item)
                            elif isinstance(item, dict) and "base" in item:
                                if item["base"] in self.all_targets and item["base"] not in migrated_list:
                                    migrated_list.append(item["base"])
                        if migrated_list:
                            return migrated_list
        except Exception as e:
            print(f"Error loading enabled AIs: {e}")
        
        self.extra_ai_choice = 'ChatGPT'
        return ['ChatGPT', 'Claude', 'Gemini']

    def save_enabled_ais(self):
        """Save the enabled AI list to config file."""
        try:
            config_path = self.get_config_path()
            config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                except json.JSONDecodeError:
                    pass
            config['enabled_ais'] = self.enabled_ais
            if hasattr(self, 'extra_ai_choice'):
                config['extra_ai_choice'] = self.extra_ai_choice
            with open(config_path, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Error saving enabled AIs: {e}")

    def toggle_focus_mode(self, enabled):
        """Pause automatic broadcasting when focus mode is enabled"""
        self.broadcast_enabled = not enabled
        if enabled:
            self.focus_mode_btn.setText("LOG IN MODE: ON")
            self.prompt_text.setPlaceholderText("Log in mode active...")
            self.prompt_text.setEnabled(False)
        else:
            self.focus_mode_btn.setText("LOG IN MODE: OFF")
            self.prompt_text.setPlaceholderText("Enter prompt for all AIs (Ctrl+Enter to send)...")
            self.prompt_text.setEnabled(True)

    def open_file_dialog(self):
        """Select files and attach them to every currently open AI pane."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach files to all AI chatbots"
        )
        if file_paths:
            self.handle_files_dropped(file_paths)

    def handle_files_dropped(self, file_paths):
        """Queue dropped files for every browser and open each site's picker."""
        valid_files = []
        seen = set()
        for path in file_paths:
            normalized = os.path.abspath(os.path.normpath(path))
            key = os.path.normcase(normalized)
            if key not in seen and os.path.isfile(normalized):
                seen.add(key)
                valid_files.append(normalized)

        if not valid_files:
            self._show_attachment_status(
                "No valid local files were dropped.", "error"
            )
            return

        if not self.browsers:
            self._show_attachment_status(
                "No AI chatbot windows are open.", "error"
            )
            return

        try:
            web_file_payload = []
            for path in valid_files:
                stat = os.stat(path)
                mime_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                with open(path, 'rb') as file_handle:
                    encoded_data = base64.b64encode(file_handle.read()).decode('ascii')
                web_file_payload.append({
                    'name': os.path.basename(path),
                    'type': mime_type,
                    'lastModified': int(stat.st_mtime * 1000),
                    'data': encoded_data
                })
        except (OSError, ValueError) as error:
            self._show_attachment_status(
                f"Could not read the dropped file: {error}", "error"
            )
            return

        self._attachment_batch_id += 1
        batch_id = self._attachment_batch_id
        for old_progress in self._attachment_progress.values():
            self._restore_attachment_zoom(old_progress)
        self._attachment_progress = {}

        for ai_info in self.browsers:
            name = ai_info['name']
            page = ai_info['browser'].page()
            if not isinstance(page, CustomWebEnginePage):
                self._attachment_progress[name] = {
                    'state': 'failed', 'selected': 0,
                    'total': len(valid_files), 'token': None, 'page': page
                }
                continue

            token = page.queue_file_upload(valid_files)
            self._attachment_progress[name] = {
                'state': 'waiting', 'selected': 0,
                'total': len(valid_files), 'token': token, 'page': page,
                'browser': ai_info['browser'], 'payload': web_file_payload,
                'diagnostic': '', 'native_attempted': False
            }
            self._trigger_file_picker(name, page, token, batch_id)

            timeout_ms = 12000 + max(0, len(valid_files) - 1) * 5000
            QTimer.singleShot(
                timeout_ms,
                lambda ai_name=name, web_page=page, upload_token=token,
                       current_batch=batch_id:
                    self._file_upload_timed_out(
                        ai_name, web_page, upload_token, current_batch
                    )
            )

        file_word = "file" if len(valid_files) == 1 else "files"
        self._show_attachment_status(
            f"Attaching {len(valid_files)} {file_word} to "
            f"{len(self.browsers)} open chatbot(s)...",
            "working"
        )

    def _try_native_upload_menu(self, name, page, token, batch_id, provider):
        """Locate a provider's upload launcher before clicking it through Qt."""
        provider_json = json.dumps(provider)
        script = r"""
        (() => {
            const provider = __PROVIDER__;
            const selectors = {
                'ChatGPT': ['button[data-testid="composer-plus-btn"]'],
                'Gemini': [
                    'button[aria-label="Upload & tools"]',
                    '.upload-card-button',
                    'button[aria-label="Open upload file menu"]',
                    'button[aria-label*="upload file" i]'
                ],
                'Qwen': [
                    '.mode-select-open',
                    '.mode-select .ant-dropdown-trigger',
                    '.message-input-action-button',
                    '.message-input-action-item'
                ]
            };
            const visible = element => {
                if (!element) return false;
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 &&
                       style.display !== 'none' && style.visibility !== 'hidden';
            };
            const element = (selectors[provider] || [])
                .map(selector => document.querySelector(selector))
                .find(visible);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
                tag: element.tagName,
                label: element.getAttribute('aria-label') || element.textContent || ''
            };
        })();
        """.replace('__PROVIDER__', provider_json)
        try:
            page.runJavaScript(
                script,
                QWebEngineScript.ScriptWorldId.ApplicationWorld.value,
                lambda result, ai_name=name, web_page=page,
                       upload_token=token, current_batch=batch_id,
                       ai_provider=provider:
                    self._on_native_launcher_location(
                        ai_name, web_page, upload_token, current_batch,
                        ai_provider, result
                    )
            )
        except RuntimeError:
            pass

    def _on_native_launcher_location(self, name, page, token, batch_id,
                                     provider, result):
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached' or
                not isinstance(result, dict)):
            return

        if not self._qt_click_browser_point(progress.get('browser'), result):
            return

        debug_log(
            f"Clicked native upload launcher for {name}: "
            f"{result.get('tag')} {result.get('label', '')[:100]}"
        )
        QTimer.singleShot(
            550,
            lambda ai_name=name, web_page=page, upload_token=token,
                   current_batch=batch_id, ai_provider=provider:
                self._find_native_upload_menu_item(
                    ai_name, web_page, upload_token, current_batch, ai_provider
                )
        )

    def _find_native_upload_menu_item(self, name, page, token, batch_id,
                                      provider, attempt=0):
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached'):
            return

        provider_json = json.dumps(provider)
        script = r"""
        (() => {
            const provider = __PROVIDER__;
            const visible = element => {
                if (!element) return false;
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 &&
                       style.display !== 'none' && style.visibility !== 'hidden';
            };
            const textOf = element => (
                element.getAttribute('aria-label') || element.textContent || ''
            ).replace(/\s+/g, ' ').trim().toLowerCase();

            let element = null;
            if (provider === 'Qwen') {
                const qwenItems = Array.from(document.querySelectorAll(
                    '.qwen-chat-v2-dropdown-menu-item, .ant-dropdown-menu-item, '
                    + '[class*="dropdown-menu-item" i], [class*="menu-item" i], '
                    + '[role="menuitem"], [role="option"]'
                )).filter(visible);
                const isUploadItem = candidate => {
                    const label = textOf(candidate);
                    return /^upload attachment\b/i.test(label) ||
                           /^upload files?\b/i.test(label) ||
                           /\bupload\b.*\b(?:attachment|file)s?\b/i.test(label);
                };
                element = qwenItems.find(isUploadItem) || null;

                if (!element) {
                    const uploadLabel = Array.from(
                        document.querySelectorAll('body *')
                    ).filter(candidate =>
                        visible(candidate) && candidate.children.length === 0 &&
                        isUploadItem(candidate)
                    ).sort((left, right) =>
                        left.getBoundingClientRect().width -
                        right.getBoundingClientRect().width
                    )[0] || null;
                    if (uploadLabel) {
                        element = uploadLabel.closest(
                            '.qwen-chat-v2-dropdown-menu-item, '
                            + '.ant-dropdown-menu-item, '
                            + '[class*="dropdown-menu-item" i], '
                            + '[class*="menu-item" i], '
                            + '[role="menuitem"], [role="option"], '
                            + 'button, [role="button"]'
                        ) || uploadLabel;
                    }
                }
            } else if (provider === 'Gemini') {
                const directSelectors = [
                    'button[data-test-id="local-images-files-uploader-button"]',
                    'images-files-uploader[data-test-id="uploader-images-files-button-advanced"] '
                        + 'button:not(.hidden-local-file-image-selector-button)',
                    'button[aria-label^="Upload files."]'
                ];
                element = directSelectors
                    .map(selector => document.querySelector(selector))
                    .find(visible) || null;
                if (!element) {
                    const candidates = Array.from(document.querySelectorAll(
                        '[role="menuitem"], [role="option"], [role="menu"] button, '
                        + '[class*="menu" i] button'
                    )).filter(visible);
                    element = candidates.find(candidate => {
                        const label = textOf(candidate);
                        return /^upload files?(?:\.|$)/i.test(label) ||
                               /\u4e0a\u4f20\u6587\u4ef6/.test(label);
                    }) || null;
                }
            } else {
                const candidates = Array.from(document.querySelectorAll(
                    '[role="menuitem"], [role="option"], [role="menu"] button, '
                    + '[class*="menu" i] button'
                )).filter(visible);
                element = candidates.find(candidate => {
                    const label = textOf(candidate);
                    if (provider === 'ChatGPT') {
                        return /add photos?\s*(?:&|and)\s*files?/i.test(label);
                    }
                    return false;
                }) || null;
            }
            if (!element) {
                const labels = Array.from(document.querySelectorAll(
                    'button, [role="button"], [role="menuitem"], [role="option"], '
                    + '.qwen-chat-v2-dropdown-menu-item, [class*="menu-item" i]'
                )).filter(visible).map(textOf).filter(label =>
                    /upload|attach|file/i.test(label)
                ).slice(0, 12);
                return { found: false, labels: labels };
            }
            const rect = element.getBoundingClientRect();
            return {
                found: true,
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
                tag: element.tagName,
                label: textOf(element)
            };
        })();
        """.replace('__PROVIDER__', provider_json)
        try:
            page.runJavaScript(
                script,
                QWebEngineScript.ScriptWorldId.ApplicationWorld.value,
                lambda result, ai_name=name, web_page=page,
                       upload_token=token, current_batch=batch_id,
                       ai_provider=provider, current_attempt=attempt:
                    self._on_native_menu_item_location(
                        ai_name, web_page, upload_token, current_batch,
                        ai_provider, current_attempt, result
                    )
            )
        except RuntimeError:
            pass

    def _on_native_menu_item_location(self, name, page, token, batch_id,
                                      provider, attempt, result):
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached'):
            return

        if not isinstance(result, dict) or not result.get('found'):
            if attempt < 10:
                QTimer.singleShot(
                    300,
                    lambda ai_name=name, web_page=page, upload_token=token,
                           current_batch=batch_id, ai_provider=provider,
                           next_attempt=attempt + 1:
                        self._find_native_upload_menu_item(
                            ai_name, web_page, upload_token, current_batch,
                            ai_provider, next_attempt
                        )
                )
            else:
                labels = result.get('labels', []) if isinstance(result, dict) else []
                debug_log(
                    f"Native upload menu item not found for {name}; "
                    f"visible upload labels={labels}"
                )
                if provider == 'Qwen':
                    self._qt_activate_first_upload_menu_item(
                        progress.get('browser')
                    )
            return

        if self._qt_click_browser_point(progress.get('browser'), result):
            debug_log(
                f"Clicked native upload menu item for {name}: "
                f"{result.get('tag')} {result.get('label', '')[:100]}"
            )
            QTimer.singleShot(
                500,
                lambda current_progress=progress:
                    self._restore_attachment_zoom(current_progress)
            )
        elif provider == 'Qwen':
            debug_log(
                f"Qwen upload row was found but its coordinates were outside "
                f"the browser: {result}"
            )
            self._qt_activate_first_upload_menu_item(progress.get('browser'))

    def _qt_activate_first_upload_menu_item(self, browser):
        """Use Qwen's accessible menu keyboard flow if its DOM is in flux."""
        if browser is None:
            return False
        try:
            browser.setFocus(Qt.FocusReason.OtherFocusReason)
            target = browser.focusProxy() or browser
            QTest.keyClick(
                target,
                Qt.Key.Key_Down,
                Qt.KeyboardModifier.NoModifier,
                20
            )
            QTest.keyClick(
                target,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier,
                20
            )
            debug_log("Activated Qwen's first upload menu item with the keyboard")
            return True
        except RuntimeError:
            return False

    def _prepare_gemini_upload_layout(self, progress):
        """Temporarily expose Gemini's upload controls in narrow panes."""
        browser = progress.get('browser')
        if browser is None:
            return 0
        try:
            original_zoom = float(browser.zoomFactor())
            progress.setdefault('original_zoom', original_zoom)
            css_width = browser.width() / max(original_zoom, 0.01)
            if css_width >= 800:
                return 0

            target_zoom = max(
                0.25,
                min(original_zoom, browser.width() / 960.0)
            )
            if target_zoom >= original_zoom:
                return 0
            browser.setZoomFactor(target_zoom)
            progress['temporary_zoom'] = True
            debug_log(
                f"Temporarily set Gemini upload zoom to {target_zoom:.3f} "
                f"for a {browser.width()}px pane"
            )
            return 500
        except (TypeError, ValueError, RuntimeError):
            return 0

    def _restore_attachment_zoom(self, progress):
        if not progress or not progress.pop('temporary_zoom', False):
            return
        browser = progress.get('browser')
        original_zoom = progress.get('original_zoom')
        if browser is None or original_zoom is None:
            return
        try:
            browser.setZoomFactor(float(original_zoom))
        except (TypeError, ValueError, RuntimeError):
            pass

    def _qt_click_browser_point(self, browser, location):
        """Deliver a Chromium-recognized mouse click at a DOM client point."""
        if browser is None:
            return False
        try:
            browser.setFocus(Qt.FocusReason.OtherFocusReason)
            zoom = float(browser.zoomFactor())
            point = QPoint(
                round(float(location['x']) * zoom),
                round(float(location['y']) * zoom)
            )
            target = browser.focusProxy() or browser
            if target is not browser:
                point = target.mapFrom(browser, point)
            if not target.rect().contains(point):
                return False
            QTest.mouseClick(
                target,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
                10
            )
            return True
        except (KeyError, TypeError, ValueError, RuntimeError):
            return False

    def _trigger_file_picker(self, name, page, token, batch_id):
        """Inject browser File objects, with the native chooser as a fallback."""
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('token') != token or
                progress.get('state') not in ('waiting', 'uploading')):
            return

        provider = self.target_bases.get(name, name)
        if provider in ('ChatGPT', 'Gemini', 'Qwen') and not progress.get('native_attempted'):
            progress['native_attempted'] = True
            native_delay = 0
            if provider == 'Gemini':
                native_delay = self._prepare_gemini_upload_layout(progress)
            QTimer.singleShot(
                native_delay,
                lambda ai_name=name, web_page=page, upload_token=token,
                       current_batch=batch_id, ai_provider=provider:
                    self._try_native_upload_menu(
                        ai_name, web_page, upload_token, current_batch,
                        ai_provider
                    )
            )
            fallback_delay = 5200 if provider == 'Qwen' else 2600
            QTimer.singleShot(
                fallback_delay,
                lambda ai_name=name, web_page=page, upload_token=token,
                       current_batch=batch_id:
                    self._trigger_file_picker(
                        ai_name, web_page, upload_token, current_batch
                    )
            )
            return

        already_selected = progress.get('selected', 0)
        payload_json = json.dumps(
            progress.get('payload', [])[already_selected:]
        )
        provider_json = json.dumps(provider)
        script = r"""
        (() => {
            if (window.__multiVibeFileAttachTimer) {
                clearInterval(window.__multiVibeFileAttachTimer);
            }
            window.__multiVibeFileAttachResult = { status: 'starting' };

            const nativeFileChange = event => {
                const target = event.target;
                if (target && target.matches && target.matches('input[type="file"]') &&
                        target.files && target.files.length) {
                    document.removeEventListener('change', nativeFileChange, true);
                    if (window.__multiVibeFileAttachTimer) {
                        clearInterval(window.__multiVibeFileAttachTimer);
                        window.__multiVibeFileAttachTimer = null;
                    }
                    window.__multiVibeFileAttachResult = {
                        status: 'native-chosen', count: target.files.length,
                        id: target.id || '', provider: __MULTI_VIBE_PROVIDER__
                    };
                }
            };
            document.addEventListener('change', nativeFileChange, true);

            const payload = __MULTI_VIBE_FILE_PAYLOAD__;
            const provider = __MULTI_VIBE_PROVIDER__;
            let files;
            try {
                files = payload.map(item => {
                    const binary = atob(item.data);
                    const bytes = new Uint8Array(binary.length);
                    for (let index = 0; index < binary.length; index += 1) {
                        bytes[index] = binary.charCodeAt(index);
                    }
                    return new File([bytes], item.name, {
                        type: item.type,
                        lastModified: item.lastModified
                    });
                });
            } catch (error) {
                window.__multiVibeFileAttachResult = {
                    status: 'failed', detail: 'Could not create browser File objects: ' + error
                };
                return false;
            }

            const makeTransfer = () => {
                const transfer = new DataTransfer();
                files.forEach(file => transfer.items.add(file));
                return transfer;
            };

            const textOf = (element) => [
                element.getAttribute('aria-label') || '',
                element.getAttribute('title') || '',
                element.getAttribute('data-testid') || '',
                element.innerText || '',
                element.textContent || ''
            ].join(' ').replace(/\s+/g, ' ').trim().toLowerCase();

            const usableInputs = allowGeneric => {
                const providerSelectors = {
                    'ChatGPT': ['input#upload-files'],
                    'Claude': ['input[type="file"]'],
                    'Qwen': ['input#filesUpload'],
                    'Gemini': []
                };
                const targeted = (providerSelectors[provider] || [])
                    .flatMap(selector => Array.from(document.querySelectorAll(selector)))
                    .filter(input => !input.disabled);
                if (targeted.length || !allowGeneric) {
                    return Array.from(new Set(targeted));
                }

                const inputs = Array.from(
                    document.querySelectorAll('input[type="file"]:not([disabled])')
                );
                return inputs.sort((left, right) => {
                    const score = input =>
                        (input.multiple ? 4 : 0) +
                        (!input.accept ? 2 : 0) +
                        (!/image\//i.test(input.accept || '') ? 1 : 0);
                    return score(right) - score(left);
                });
            };

            const injectIntoInput = input => {
                const transfer = makeTransfer();
                try {
                    input.files = transfer.files;
                } catch (_error) {
                    Object.defineProperty(input, 'files', {
                        configurable: true,
                        value: transfer.files
                    });
                }
                if (input.files.length !== transfer.files.length) {
                    Object.defineProperty(input, 'files', {
                        configurable: true,
                        value: transfer.files
                    });
                }
                input.dispatchEvent(new Event('input', {
                    bubbles: true, composed: true
                }));
                input.dispatchEvent(new Event('change', {
                    bubbles: true, composed: true
                }));
                window.__multiVibeFileAttachResult = {
                    status: 'injected', count: input.files.length,
                    payloadCount: files.length, provider: provider,
                    id: input.id || '', name: input.name || '',
                    accept: input.accept || '', multiple: !!input.multiple
                };
            };

            const makeDragEvent = (type, transfer) => {
                try {
                    return new DragEvent(type, {
                        bubbles: true, cancelable: true, dataTransfer: transfer
                    });
                } catch (_error) {
                    const event = new Event(type, { bubbles: true, cancelable: true });
                    Object.defineProperty(event, 'dataTransfer', { value: transfer });
                    return event;
                }
            };

            const dispatchDrop = () => {
                const composer =
                    document.querySelector('#prompt-textarea') ||
                    document.querySelector('div.ProseMirror[contenteditable="true"]') ||
                    document.querySelector('rich-textarea div[contenteditable="true"]') ||
                    document.querySelector('.ql-editor[contenteditable="true"]') ||
                    document.querySelector('[data-lexical-editor="true"]') ||
                    document.querySelector('[contenteditable="true"]') ||
                    document.querySelector('textarea') ||
                    document.body;
                const initialTarget = composer.closest('form') || composer;
                const transfer = makeTransfer();
                initialTarget.dispatchEvent(makeDragEvent('dragenter', transfer));
                initialTarget.dispatchEvent(makeDragEvent('dragover', transfer));

                setTimeout(() => {
                    const dropTarget =
                        document.querySelector('[data-testid*="drop" i]') ||
                        document.querySelector('[class*="dropzone" i]') ||
                        document.querySelector('[class*="drop-zone" i]') ||
                        initialTarget;
                    dropTarget.dispatchEvent(makeDragEvent('dragover', transfer));
                    dropTarget.dispatchEvent(makeDragEvent('drop', transfer));
                    window.__multiVibeFileAttachResult = {
                        status: 'drop-dispatched', count: transfer.files.length,
                        target: dropTarget.tagName
                    };
                }, 350);
            };

            let launcherClicked = false;
            let launcherElement = null;
            let menuChoiceClicked = false;
            let ticks = 0;

            const tick = () => {
                ticks += 1;
                const allowGeneric = provider === 'Claude' || menuChoiceClicked ||
                    !['ChatGPT', 'Claude', 'Qwen', 'Gemini'].includes(provider);
                const inputs = usableInputs(allowGeneric);
                if (inputs.length) {
                    try {
                        injectIntoInput(inputs[0]);
                    } catch (error) {
                        window.__multiVibeFileAttachResult = {
                            status: 'input-failed', detail: String(error)
                        };
                    }
                    clearInterval(window.__multiVibeFileAttachTimer);
                    window.__multiVibeFileAttachTimer = null;
                    return;
                }

                const elements = Array.from(document.querySelectorAll(
                    'button:not([disabled]), [role="button"], [role="menuitem"]'
                ));

                if (!launcherClicked) {
                    const providerLauncherSelectors = {
                        'ChatGPT': ['button[data-testid="composer-plus-btn"]'],
                        'Gemini': [
                            'button[aria-label="Upload & tools"]',
                            '.upload-card-button',
                            'button[aria-label="Open upload file menu"]'
                        ],
                        'Qwen': [
                            '.mode-select-open',
                            '.mode-select .ant-dropdown-trigger'
                        ]
                    };
                    const knownSelector = [
                        ...(providerLauncherSelectors[provider] || []),
                        'button[data-testid="composer-plus-btn"]',
                        'button[data-testid="input-menu-trigger"]',
                        '[data-test-id="upload-files-button"]',
                        'button[aria-label*="attach" i]',
                        'button[aria-label*="add content" i]',
                        'button[aria-label*="add file" i]',
                        'button[aria-label*="upload file" i]',
                        'button[title*="attach" i]',
                        'button[title*="upload" i]'
                    ].map(selector => document.querySelector(selector)).find(Boolean);

                    const labelledLauncher = elements.find(element => {
                        const label = textOf(element);
                        return /(^|\b)(attach|attachment|add files?|upload files?)(\b|$)/i.test(label) ||
                               /add files? and more/i.test(label) ||
                               /open upload file menu/i.test(label);
                    });

                    const launcher = knownSelector || labelledLauncher;
                    if (launcher) {
                        launcher.click();
                        launcherElement = launcher;
                        launcherClicked = true;
                    }
                } else if (!menuChoiceClicked) {
                    const menuElements = Array.from(document.querySelectorAll(
                        '[role="menuitem"], [role="option"], [role="menu"] button, '
                        + '[role="listbox"] button, [class*="menu" i] button, '
                        + '.ant-dropdown-menu-item'
                    ));
                    let menuChoice = null;
                    if (provider === 'Qwen') {
                        menuChoice = Array.from(document.querySelectorAll(
                            '.qwen-chat-v2-dropdown-menu-item, .ant-dropdown-menu-item'
                        )).find(element =>
                            /^upload attachment\b/i.test(textOf(element)) ||
                            /^upload files?\b/i.test(textOf(element))
                        ) || null;
                    }
                    menuChoice = menuChoice || menuElements.find(element => {
                        if (element === launcherElement) return false;
                        const label = textOf(element);
                        if (provider === 'ChatGPT') {
                            return /add photos?\s*(?:&|and)\s*files?/i.test(label);
                        }
                        if (provider === 'Gemini') {
                            return /^upload files?$/i.test(label) ||
                                   /\u4e0a\u4f20\u6587\u4ef6/.test(label);
                        }
                        return /upload from (computer|device)/i.test(label) ||
                               /upload files?/i.test(label) ||
                               /add (a )?file/i.test(label);
                    });
                    if (menuChoice) {
                        menuChoice.click();
                        menuChoiceClicked = true;
                    }
                }

                if (ticks >= 20) {
                    clearInterval(window.__multiVibeFileAttachTimer);
                    window.__multiVibeFileAttachTimer = null;
                    try {
                        dispatchDrop();
                    } catch (error) {
                        const labels = elements
                            .map(textOf)
                            .filter(label => /attach|upload|add file/i.test(label))
                            .slice(0, 8);
                        window.__multiVibeFileAttachResult = {
                            status: 'failed', detail: String(error), labels: labels
                        };
                    }
                }
            };

            window.__multiVibeFileAttachTimer = setInterval(tick, 250);
            tick();
            return true;
        })();
        """
        script = script.replace('__MULTI_VIBE_FILE_PAYLOAD__', payload_json)
        script = script.replace('__MULTI_VIBE_PROVIDER__', provider_json)
        try:
            page.runJavaScript(
                script,
                QWebEngineScript.ScriptWorldId.ApplicationWorld.value
            )
            QTimer.singleShot(
                6500,
                lambda ai_name=name, web_page=page, upload_token=token,
                       current_batch=batch_id:
                    self._poll_file_injection_result(
                        ai_name, web_page, upload_token, current_batch
                    )
            )
        except RuntimeError:
            self._restore_attachment_zoom(progress)
            progress['state'] = 'failed'
            page.cancel_queued_file_upload(token)
            self._update_attachment_status()

    def _poll_file_injection_result(self, name, page, token, batch_id):
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached'):
            return

        try:
            page.runJavaScript(
                "window.__multiVibeFileAttachResult || null",
                QWebEngineScript.ScriptWorldId.ApplicationWorld.value,
                lambda result, ai_name=name, web_page=page,
                       upload_token=token, current_batch=batch_id:
                    self._on_file_injection_result(
                        ai_name, web_page, upload_token, current_batch, result
                    )
            )
        except RuntimeError:
            self._restore_attachment_zoom(progress)
            progress['state'] = 'failed'
            page.cancel_queued_file_upload(token)
            self._update_attachment_status()

    def _on_file_injection_result(self, name, page, token, batch_id, result):
        progress = self._attachment_progress.get(name)
        if (batch_id != self._attachment_batch_id or not progress or
                progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached'):
            return

        if not isinstance(result, dict):
            self._restore_attachment_zoom(progress)
            progress['diagnostic'] = 'The page did not return an upload result.'
            return

        self._restore_attachment_zoom(progress)
        status = result.get('status', '')
        try:
            debug_log(
                f"Attachment result for {name} at {page.url().toString()}: {result}"
            )
        except RuntimeError:
            pass
        if status in ('injected', 'native-chosen', 'drop-dispatched'):
            progress['selected'] = progress.get('total', 0)
            progress['state'] = 'attached'
            progress['diagnostic'] = status
            page.cancel_queued_file_upload(token)
            self._update_attachment_status()
        elif status in ('failed', 'input-failed'):
            progress['diagnostic'] = result.get('detail', status)

    def _on_file_upload_accepted(self, name, page, token, count, remaining):
        progress = self._attachment_progress.get(name)
        if (not progress or progress.get('page') is not page or
                progress.get('token') != token):
            return

        try:
            debug_log(
                f"Native chooser accepted for {name}: "
                f"count={count}, remaining={remaining}"
            )
        except RuntimeError:
            pass
        self._restore_attachment_zoom(progress)
        progress['selected'] += count
        if remaining:
            progress['state'] = 'uploading'
            self._update_attachment_status()
            QTimer.singleShot(
                1200,
                lambda ai_name=name, web_page=page, upload_token=token,
                       batch_id=self._attachment_batch_id:
                    self._trigger_file_picker(
                        ai_name, web_page, upload_token, batch_id
                    )
            )
        else:
            progress['state'] = 'attached'
            self._update_attachment_status()

    def _file_upload_timed_out(self, name, page, token, batch_id):
        if batch_id != self._attachment_batch_id:
            return
        progress = self._attachment_progress.get(name)
        if (not progress or progress.get('page') is not page or
                progress.get('token') != token or
                progress.get('state') == 'attached'):
            return
        self._restore_attachment_zoom(progress)
        progress['state'] = 'failed'
        page.cancel_queued_file_upload(token)
        try:
            debug_log(
                f"Attachment failed for {name} at {page.url().toString()}: "
                f"{progress.get('diagnostic') or 'no result from page'}"
            )
        except RuntimeError:
            pass
        self._update_attachment_status()

    def _update_attachment_status(self):
        if not self._attachment_progress:
            return

        attached = []
        failed = []
        pending = []
        for name, progress in self._attachment_progress.items():
            state = progress.get('state')
            if state == 'attached':
                attached.append(name)
            elif state == 'failed':
                failed.append(name)
            else:
                selected = progress.get('selected', 0)
                total = progress.get('total', 0)
                suffix = f" ({selected}/{total})" if selected else ""
                pending.append(f"{name}{suffix}")

        if pending:
            message = f"Attaching to: {', '.join(pending)}"
            if attached:
                message += f" | Attached: {', '.join(attached)}"
            self._show_attachment_status(message, "working")
            return

        if failed:
            message = "Could not attach automatically to: " + ", ".join(failed)
            if attached:
                message += " | Attached to: " + ", ".join(attached)
            self._show_attachment_status(message, "warning")
        else:
            self._show_attachment_status(
                "Attached to all open chatbots: " + ", ".join(attached),
                "success"
            )

    def _show_attachment_status(self, message, kind):
        colors = {
            'working': ('#263238', '#bbdefb', '#1976d2'),
            'success': ('#1e3d2f', '#a5d6a7', '#2e7d32'),
            'warning': ('#4a3b16', '#ffe082', '#f9a825'),
            'error': ('#4a2020', '#ef9a9a', '#c62828')
        }
        background, foreground, border = colors.get(kind, colors['working'])
        self.attachment_status_label.setStyleSheet(
            "QLabel { "
            f"background-color: {background}; color: {foreground}; "
            f"border: 1px solid {border}; border-radius: 4px; "
            "padding: 4px 8px; font-weight: bold; font-size: 12px; }"
        )
        self.attachment_status_label.setText(message)
        self.attachment_status_label.show()

    def broadcast_prompts(self):
        if not self.broadcast_enabled:
            return
        
        prompt = self.prompt_text.toPlainText().strip()
        if not prompt: return
        js_safe_prompt = prompt.replace('\\', '\\\\').replace('`', '\\`').replace('\n', '\\n').replace("'", "\\'")
        
        for ai_info in self.browsers:
            name = ai_info['name']
            base = self.target_bases.get(name, name)
            browser = ai_info['browser']
            if base in self.prompt_templates:
                browser.page().runJavaScript(self.prompt_templates[base].format(prompt=js_safe_prompt))
                
        self.prompt_text.clear()

    def refresh_all(self):
        for ai_info in self.browsers:
            ai_info['browser'].reload()
    
    def open_google_signin(self):
        """Open a dedicated Google sign-in dialog"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from PyQt6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Sign in with Google")
        dialog.setGeometry(200, 200, 600, 800)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Sign in to your Google account. This window uses the same profile as your browsers.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # Web view for Google sign-in
        signin_browser = CustomWebEngineView()
        page = CustomWebEnginePage(self.profile, signin_browser)
        signin_browser.setPage(page)
        signin_browser.load(QUrl("https://accounts.google.com/"))
        layout.addWidget(signin_browser)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.setLayout(layout)
        dialog.exec()

    def find_existing_profiles(self):
        app_data_dir = self.get_app_data_dir()
        prefix = ".multi_vibe_chat_profile_"
        try:
            profiles = [
                item[len(prefix):]
                for item in os.listdir(app_data_dir)
                if os.path.isdir(os.path.join(app_data_dir, item)) and item.startswith(prefix)
            ]
        except FileNotFoundError:
            profiles = []
        return sorted(profiles) if profiles else ['default']

    def switch_profile(self):
        new_profile_name = self.profile_combo.currentText().strip()
        if not new_profile_name or new_profile_name == self.profile_name:
            return

        debug_log(f"=== Switching Profile (In-Process) ===")
        debug_log(f"Current profile: {self.profile_name}")
        debug_log(f"New profile: {new_profile_name}")

        # Save the new profile as the last used
        self.save_last_profile(new_profile_name)

        # Apply the switch without restarting the app (avoids PyInstaller temp conflicts)
        self.apply_profile_switch(new_profile_name)

    def apply_profile_switch(self, new_profile_name):
        """Switch profiles in-process by rebuilding all browsers with a new QWebEngineProfile."""
        debug_log("Applying profile switch in-process")

        # Update profile name and window title
        self.profile_name = new_profile_name
        self.setWindowTitle(f"Multi Vibe Chat - Profile: {self.profile_name}")

        # Clear existing browsers and containers
        for browser_info in list(self.browsers):
            try:
                container = browser_info.get('container')
                if container:
                    container.setParent(None)
                    container.deleteLater()
                browser = browser_info.get('browser')
                if browser:
                    browser.setParent(None)
                    browser.deleteLater()
            except RuntimeError:
                pass

        self.browsers = []

        # Clear view stack widgets
        while self.view_stack.count() > 0:
            item = self.view_stack.itemAt(0)
            widget = item.widget() if item else None
            if widget:
                self.view_stack.removeWidget(widget)
                widget.deleteLater()
            else:
                break

        # Dispose old profile and create a new one
        try:
            if hasattr(self, 'profile') and self.profile:
                self.profile.deleteLater()
        except RuntimeError:
            pass

        self.handle_profile_logic()

        # Rebuild browsers with the new profile
        self.rebuild_browser_panes()

        # Update profile combo list if needed
        existing_profiles = self.find_existing_profiles()
        if new_profile_name not in existing_profiles:
            self.profile_combo.addItem(new_profile_name)
        self.profile_combo.setCurrentText(new_profile_name)

    def get_app_data_dir(self):
        """Get the application data directory for storing profiles and configs."""
        return os.path.join(os.path.expanduser("~"), ".MultiVibeChat")

    def get_config_path(self):
        """Get path to the config file that stores the last profile."""
        app_data_dir = self.get_app_data_dir()
        os.makedirs(app_data_dir, exist_ok=True)
        return os.path.join(app_data_dir, ".multi_vibe_chat_config.json")

    def load_last_profile(self):
        """Load the last used profile from config file."""
        try:
            config_path = self.get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get('last_profile', 'default')
        except Exception as e:
            print(f"Error loading last profile: {e}")
        return 'default'

    def save_last_profile(self, profile_name):
        """Save the current profile as the last used."""
        try:
            config_path = self.get_config_path()
            config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                except json.JSONDecodeError:
                    pass
            config['last_profile'] = profile_name
            with open(config_path, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Error saving last profile: {e}")

    def setup_download_handling(self):
        """Set up download handling to save files to user's Downloads folder"""
        from PyQt6.QtCore import QStandardPaths
        
        # Get the user's default Downloads folder
        downloads_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if downloads_path:
            self.profile.setDownloadPath(downloads_path)
        
        # Connect to download requests
        self.profile.downloadRequested.connect(self.handle_download)
    
    def handle_download(self, download):
        """Handle file download requests"""
        from PyQt6.QtCore import QStandardPaths
        from PyQt6.QtWidgets import QMessageBox
        
        # Get suggested filename
        suggested_filename = download.downloadFileName()
        
        # Get downloads path
        downloads_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        
        if downloads_path:
            # Set download directory and accept the download
            download.setDownloadDirectory(downloads_path)
            download.accept()
            
            # Show notification
            print(f"Downloading: {suggested_filename} to {downloads_path}")
            
            # Connect to track download progress/completion
            download.isFinishedChanged.connect(
                lambda: self.on_download_finished(download) if download.isFinished() else None
            )
        else:
            print(f"Could not determine downloads folder for: {suggested_filename}")
            download.cancel()
    
    def on_download_finished(self, download):
        """Called when a download is finished"""
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
        
        if download.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            filename = download.downloadFileName()
            directory = download.downloadDirectory()
            print(f"Download completed: {filename}")
            # Optional: Show a message box notification
            # QMessageBox.information(self, "Download Complete", f"Downloaded: {filename}\\nSaved to: {directory}")
        elif download.state() == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            print(f"Download failed: {download.downloadFileName()}")

    def handle_profile_logic(self):
        # Use consistent app data directory for persistent storage
        # This ensures profiles work in both development and packaged versions
        app_data_dir = self.get_app_data_dir()
        os.makedirs(app_data_dir, exist_ok=True)
        
        legacy_path = os.path.join(app_data_dir, ".multi_ai_browser_profile")
        default_path = os.path.join(app_data_dir, ".multi_vibe_chat_profile_default")
        current_path = os.path.join(app_data_dir, f".multi_vibe_chat_profile_{self.profile_name}")

        if not os.path.exists(default_path) and os.path.exists(legacy_path):
            try:
                os.rename(legacy_path, default_path)
            except Exception as e:
                print(f"Migration failed: {e}")

        if self.profile_name != 'default' and not os.path.exists(current_path):
            if os.path.exists(default_path):
                try:
                    shutil.copytree(default_path, current_path)
                except Exception as e:
                    print(f"Cloning failed: {e}")
        
        self.profile = QWebEngineProfile(f"persistent-profile-{self.profile_name}", self)
        self.profile.setPersistentStoragePath(current_path)
        # Enable and tune disk cache for faster page loads
        cache_path = os.path.join(current_path, "Cache")
        self.profile.setCachePath(cache_path)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        # 512 MB cache (in bytes)
        self.profile.setHttpCacheMaximumSize(512 * 1024 * 1024)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile.setSpellCheckEnabled(False)
        
        # Language settings
        self.profile.setHttpAcceptLanguage("en-US,en;q=0.9")
        
        # HTTP header interceptor
        self.interceptor = RequestInterceptor(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        
        # Set up download handling to save files to user's Downloads folder
        self.setup_download_handling()
        
        # Web features configuration
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.XSSAuditingEnabled, False)  # Disable for speed
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)  # Faster error handling
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, False)  # Reduce focus overhead
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, False)  # Not needed
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)  # Prevent autoplay load
        settings.setAttribute(QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, False)  # Disable PING requests
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, False)  # Not needed for chat
        
        # Minimized environment script - only essential properties for AI sites
        # Reduces JS parsing overhead on every page load
        environment_alignment_script = """(function(){
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8});
Object.defineProperty(navigator,'deviceMemory',{get:()=>8});
Object.defineProperty(navigator,'platform',{get:()=>'Win32'});
Object.defineProperty(navigator,'vendor',{get:()=>'Google Inc.'});
window.chrome={app:{isInstalled:false},runtime:{},csi:function(){},loadTimes:function(){}};
try{delete navigator.__proto__.webdriver}catch(e){}
})();"""
        
        user_script = QWebEngineScript()
        user_script.setSourceCode(environment_alignment_script)
        user_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        user_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        # Inject only into main frames to reduce per-frame overhead
        user_script.setRunsOnSubFrames(False)
        self.profile.scripts().insert(user_script)

def debug_log(message):
    """Write debug messages to a log file in user's home directory"""
    try:
        log_path = os.path.join(os.path.expanduser("~"), ".MultiVibeChat", "debug.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a') as f:
            from datetime import datetime
            f.write(f"{datetime.now()}: {message}\n")
    except:
        pass

def main():
    debug_log(f"=== App Starting ===")
    debug_log(f"sys.executable: {sys.executable}")
    debug_log(f"sys.argv: {sys.argv}")
    debug_log(f"Has _MEIPASS: {hasattr(sys, '_MEIPASS')}")
    if hasattr(sys, '_MEIPASS'):
        debug_log(f"_MEIPASS: {sys._MEIPASS}")
    
    parser = argparse.ArgumentParser(description="Multi Vibe Chat")
    parser.add_argument('--profile', type=str, default=None, help='Profile name to use.')
    args = parser.parse_args()
    
    debug_log(f"Parsed args.profile: {args.profile}")
    
    app = QApplication(sys.argv)
    
    # If no profile specified via command line, load the last used profile
    if args.profile is None:
        # Get app data directory consistently matching MultiVibeChat class
        app_data_dir = os.path.join(os.path.expanduser("~"), ".MultiVibeChat")
        
        os.makedirs(app_data_dir, exist_ok=True)
        config_path = os.path.join(app_data_dir, ".multi_vibe_chat_config.json")
        debug_log(f"Config path: {config_path}")
        profile_name = 'default'
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    profile_name = config.get('last_profile', 'default')
                    debug_log(f"Loaded profile from config: {profile_name}")
        except Exception as e:
            debug_log(f"Error loading last profile: {e}")
            print(f"Error loading last profile: {e}")
    else:
        profile_name = args.profile
        debug_log(f"Using profile from args: {profile_name}")
    
    debug_log(f"Final profile_name: {profile_name}")
    
    try:
        browser_app = MultiVibeChat(profile_name=profile_name)
        # Save this profile as the last used
        browser_app.save_last_profile(profile_name)
        browser_app.show()
        debug_log("App window shown successfully")
        sys.exit(app.exec())
    except Exception as e:
        debug_log(f"FATAL ERROR: {e}")
        import traceback
        debug_log(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()

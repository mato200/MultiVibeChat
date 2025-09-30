#  MultiVibeChat 2 - Multi AI Chat Desktop Client
# A PyQt6-based application for managing multiple AI chat sessions

import sys
import os
import argparse
import subprocess
import shutil
import webbrowser
import json
from urllib.parse import quote_plus
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QLineEdit,
                             QPushButton, QFrame, QSplitter, QComboBox, QStackedLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QKeyEvent
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineScript, QWebEngineUrlRequestInterceptor

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Adds standard browser headers to requests for compatibility"""
    def interceptRequest(self, info):
        # Standard Chrome browser headers
        info.setHttpHeader(b"Accept-Language", b"en-US,en;q=0.9")
        info.setHttpHeader(b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7")
        info.setHttpHeader(b"Upgrade-Insecure-Requests", b"1")
        info.setHttpHeader(b"Sec-Fetch-Site", b"none")
        info.setHttpHeader(b"Sec-Fetch-Mode", b"navigate")
        info.setHttpHeader(b"Sec-Fetch-User", b"?1")
        info.setHttpHeader(b"Sec-Fetch-Dest", b"document")
        info.setHttpHeader(b"sec-ch-ua", b'"Not A(Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"')
        info.setHttpHeader(b"sec-ch-ua-mobile", b"?0")
        info.setHttpHeader(b"sec-ch-ua-platform", b'"Windows"')

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        # Set user agent to match current Chrome version
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        self.profile().setHttpUserAgent(user_agent)
        self._popup_windows = []
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Filter out verbose console messages
        if message and ('webdriver' in message.lower() or 'automation' in message.lower()):
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # Allow navigation for popups and redirects
        return True
    
    def createWindow(self, window_type):
        """Handle popup windows for OAuth and other authentication flows"""
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
        
        # Store reference to prevent garbage collection
        self._popup_windows.append(popup)
        
        # Show popup window
        popup.show()
        
        # Auto-close when authentication flow completes
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

class PromptTextEdit(QTextEdit):
    ctrlEnterPressed = pyqtSignal()
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.ctrlEnterPressed.emit()
        else: super().keyPressEvent(event)

class MultiVibeChat(QMainWindow):
    def __init__(self, profile_name='default'):
        super().__init__()
        self.profile_name = profile_name
        self.browsers = [] 
        self.is_grid_layout = True
        self.auto_inject_enabled = True  # Toggle for auto-injection
        self.targets = {
            'ChatGPT': 'https://chatgpt.com/', 'Claude': 'https://claude.ai/new',
            'Grok': 'https://x.com/i/grok', 'AI Studio': 'https://aistudio.google.com/prompts/new_chat'
        }
        self.prompt_injection_js = {
            'ChatGPT': """var input = document.querySelector('div#prompt-textarea[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[data-testid="send-button"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Claude': """var input = document.querySelector('div.ProseMirror[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[aria-label="Send message"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Grok': """var input = document.querySelector('textarea[placeholder="Ask anything"]'); if (input) {{ input.focus(); document.execCommand('insertText', false, `{prompt}`); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[aria-label="Grok something"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'AI Studio': """var input = document.querySelector('ms-autosize-textarea textarea'); if (input) {{ input.value = `{prompt}`; input.dispatchEvent(new Event('input', {{ bubbles: true }})); setTimeout(() => {{ var btn = document.querySelector('ms-run-button button'); if (btn && !btn.disabled) btn.click(); }}, 500); }}"""
        }
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"Multi Vibe Chat - Profile: {self.profile_name}")
        self.setGeometry(100, 100, 1600, 1000)

        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(main_container)

        self.handle_profile_logic()

        self.view_stack = QStackedLayout()
        
        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(bottom_splitter)
        grid_layout.addWidget(main_splitter)
        
        horizontal_container = QWidget()
        horizontal_layout = QHBoxLayout(horizontal_container)
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        horizontal_layout.addWidget(horizontal_splitter)

        ai_names = list(self.targets.keys())

        top_splitter.addWidget(self.create_browser_pane(ai_names[0]))
        top_splitter.addWidget(self.create_browser_pane(ai_names[1]))
        bottom_splitter.addWidget(self.create_browser_pane(ai_names[2]))
        bottom_splitter.addWidget(self.create_browser_pane(ai_names[3]))

        horizontal_splitter.addWidget(self.create_browser_pane(ai_names[0]))
        horizontal_splitter.addWidget(self.create_browser_pane(ai_names[1]))
        horizontal_splitter.addWidget(self.create_browser_pane(ai_names[2]))
        horizontal_splitter.addWidget(self.create_browser_pane(ai_names[3]))
        
        self.view_stack.addWidget(grid_container)
        self.view_stack.addWidget(horizontal_container)

        main_layout.addLayout(self.view_stack, 1)

        control_panel = QFrame()
        control_panel.setFrameShape(QFrame.Shape.NoFrame)
        main_control_layout = QHBoxLayout(control_panel)
        main_control_layout.setSpacing(6)
        main_control_layout.setContentsMargins(2, 2, 2, 2)

        self.prompt_text = PromptTextEdit()
        self.prompt_text.setPlaceholderText("Enter prompt for all AIs (Ctrl+Enter to send)...")
        
        # --- FIX: Replaced fixed pixel height with dynamic, font-based height ---
        font_metrics = self.prompt_text.fontMetrics()
        # Set height to be roughly 2.5 lines of text plus a small margin for padding
        line_height = font_metrics.height()
        self.prompt_text.setFixedHeight(int(line_height * 2.5) + 6)

        main_control_layout.addWidget(self.prompt_text, 1)

        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(4) 

        top_button_layout = QHBoxLayout()
        send_btn, refresh_btn = QPushButton("Send to All"), QPushButton("Refresh All")
        self.layout_switch_btn = QPushButton("Switch to 4x1")
        self.login_mode_btn = QPushButton("Login Mode: OFF")
        self.login_mode_btn.setCheckable(True)
        self.login_mode_btn.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; }")
        google_signin_btn = QPushButton("🔐 Sign in with Google")
        google_signin_btn.setStyleSheet("background-color: #4285F4; color: white; font-weight: bold;")
        top_button_layout.addWidget(send_btn)
        top_button_layout.addWidget(refresh_btn)
        top_button_layout.addWidget(self.layout_switch_btn)
        top_button_layout.addWidget(self.login_mode_btn)
        top_button_layout.addWidget(google_signin_btn)

        profile_bar_layout = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.setPlaceholderText("Type new name to create...")
        
        existing_profiles = self.find_existing_profiles()
        self.profile_combo.addItems(existing_profiles)
        if self.profile_name in existing_profiles:
            self.profile_combo.setCurrentText(self.profile_name)

        switch_profile_btn = QPushButton("Switch / Create")
        profile_bar_layout.addWidget(QLabel("Profile:"))
        profile_bar_layout.addWidget(self.profile_combo)
        profile_bar_layout.addWidget(switch_profile_btn)
        
        right_panel_layout.addLayout(top_button_layout)
        right_panel_layout.addLayout(profile_bar_layout)
        main_control_layout.addWidget(right_panel)

        send_btn.clicked.connect(self.send_to_all_ais)
        self.prompt_text.ctrlEnterPressed.connect(self.send_to_all_ais)
        refresh_btn.clicked.connect(self.refresh_all)
        self.layout_switch_btn.clicked.connect(self.switch_layout)
        self.login_mode_btn.toggled.connect(self.toggle_login_mode)
        google_signin_btn.clicked.connect(self.open_google_signin)
        switch_profile_btn.clicked.connect(self.switch_profile)
        
        main_layout.addWidget(control_panel)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Alt and not event.isAutoRepeat():
            for browser in self.browsers:
                browser['url_bar'].show()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Alt and not event.isAutoRepeat():
            for browser in self.browsers:
                browser['url_bar'].hide()
        super().keyReleaseEvent(event)

    def create_browser_pane(self, name):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        url_bar = QLineEdit()
        url_bar.setReadOnly(True)
        url_bar.hide()

        browser = CustomWebEngineView()
        page = CustomWebEnginePage(self.profile, browser)
        browser.setPage(page)
        browser.load(QUrl(self.targets[name]))
        
        browser.urlChanged.connect(lambda url, bar=url_bar: bar.setText(url.toString()))

        layout.addWidget(url_bar)
        layout.addWidget(browser)
        
        browser_info = {'name': name, 'browser': browser, 'url_bar': url_bar}
        self.browsers.append(browser_info)
        return container

    def switch_layout(self):
        if self.is_grid_layout:
            self.view_stack.setCurrentIndex(1)
            self.layout_switch_btn.setText("Switch to 2x2")
        else:
            self.view_stack.setCurrentIndex(0)
            self.layout_switch_btn.setText("Switch to 4x1")
        self.is_grid_layout = not self.is_grid_layout

    def toggle_login_mode(self, enabled):
        """Toggle manual interaction mode for authentication"""
        self.auto_inject_enabled = not enabled
        if enabled:
            self.login_mode_btn.setText("Login Mode: ON")
            self.prompt_text.setPlaceholderText("Login Mode - Manual interaction enabled...")
            self.prompt_text.setEnabled(False)
        else:
            self.login_mode_btn.setText("Login Mode: OFF")
            self.prompt_text.setPlaceholderText("Enter prompt for all AIs (Ctrl+Enter to send)...")
            self.prompt_text.setEnabled(True)

    def send_to_all_ais(self):
        if not self.auto_inject_enabled:
            return
        
        prompt = self.prompt_text.toPlainText().strip()
        if not prompt: return
        js_safe_prompt = prompt.replace('\\', '\\\\').replace('`', '\\`').replace('\n', '\\n').replace("'", "\\'")
        
        for ai_info in self.browsers:
            name = ai_info['name']
            browser = ai_info['browser']
            if name in self.prompt_injection_js:
                browser.page().runJavaScript(self.prompt_injection_js[name].format(prompt=js_safe_prompt))
                
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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        prefix = ".multi_vibe_chat_profile_"
        profiles = [item[len(prefix):] for item in os.listdir(script_dir) if os.path.isdir(os.path.join(script_dir, item)) and item.startswith(prefix)]
        return sorted(profiles) if profiles else ['default']

    def switch_profile(self):
        new_profile_name = self.profile_combo.currentText().strip()
        if not new_profile_name or new_profile_name == self.profile_name:
            return
        # Save the new profile as the last used
        self.save_last_profile(new_profile_name)
        args = [sys.executable, sys.argv[0], '--profile', new_profile_name]
        subprocess.Popen(args)
        self.close()

    def get_config_path(self):
        """Get path to the config file that stores the last profile."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, ".multi_vibe_chat_config.json")

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
            config = {'last_profile': profile_name}
            with open(config_path, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Error saving last profile: {e}")

    def handle_profile_logic(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        legacy_path = os.path.join(script_dir, ".multi_ai_browser_profile")
        default_path = os.path.join(script_dir, ".multi_vibe_chat_profile_default")
        current_path = os.path.join(script_dir, f".multi_vibe_chat_profile_{self.profile_name}")

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
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        
        # Set browser language preferences
        self.profile.setHttpAcceptLanguage("en-US,en;q=0.9")
        
        # Add request interceptor for standard headers
        self.interceptor = RequestInterceptor(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        
        # Enable standard web features
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.XSSAuditingEnabled, True)
        
        # Browser compatibility enhancements
        browser_compat_script = """
        // Standard browser compatibility setup
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Plugin information for compatibility
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                return [
                    {
                        0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: Plugin},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    },
                    {
                        0: {type: "application/pdf", suffixes: "pdf", description: "", enabledPlugin: Plugin},
                        description: "",
                        filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                        length: 1,
                        name: "Chrome PDF Viewer"
                    },
                    {
                        0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable", enabledPlugin: Plugin},
                        1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable", enabledPlugin: Plugin},
                        description: "",
                        filename: "internal-nacl-plugin",
                        length: 2,
                        name: "Native Client"
                    }
                ];
            }
        });
        
        // Language preferences
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Chrome API compatibility layer
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: {
                    DISABLED: 'disabled',
                    INSTALLED: 'installed',
                    NOT_INSTALLED: 'not_installed'
                },
                RunningState: {
                    CANNOT_RUN: 'cannot_run',
                    READY_TO_RUN: 'ready_to_run',
                    RUNNING: 'running'
                }
            },
            runtime: {
                OnInstalledReason: {
                    CHROME_UPDATE: 'chrome_update',
                    INSTALL: 'install',
                    SHARED_MODULE_UPDATE: 'shared_module_update',
                    UPDATE: 'update'
                },
                OnRestartRequiredReason: {
                    APP_UPDATE: 'app_update',
                    OS_UPDATE: 'os_update',
                    PERIODIC: 'periodic'
                },
                PlatformArch: {
                    ARM: 'arm',
                    ARM64: 'arm64',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64'
                },
                PlatformNaclArch: {
                    ARM: 'arm',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64'
                },
                PlatformOs: {
                    ANDROID: 'android',
                    CROS: 'cros',
                    LINUX: 'linux',
                    MAC: 'mac',
                    OPENBSD: 'openbsd',
                    WIN: 'win'
                },
                RequestUpdateCheckStatus: {
                    NO_UPDATE: 'no_update',
                    THROTTLED: 'throttled',
                    UPDATE_AVAILABLE: 'update_available'
                }
            },
            csi: function() {},
            loadTimes: function() {}
        };
        
        // Permissions API compatibility
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Hardware specifications
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        // Device memory information
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        // Platform information
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Vendor information
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.'
        });
        
        // Network connection information
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false
            })
        });
        
        // Battery API compatibility
        if (navigator.getBattery) {
            const originalGetBattery = navigator.getBattery;
            navigator.getBattery = function() {
                return Promise.resolve({
                    charging: true,
                    chargingTime: 0,
                    dischargingTime: Infinity,
                    level: 1
                });
            };
        }
        
        });
        
        // Function toString compatibility
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === navigator.getBattery) {
                return 'function getBattery() { [native code] }';
            }
            return originalToString.call(this);
        };
        
        // WebGL renderer information
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel(R) UHD Graphics 630';
            }
            return getParameter.call(this, parameter);
        };
        
        // Screen dimensions
        Object.defineProperty(screen, 'availWidth', {
            get: () => screen.width
        });
        Object.defineProperty(screen, 'availHeight', {
            get: () => screen.height - 40
        });
        
        // User agent client hints
        if (navigator.userAgentData) {
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => ({
                    brands: [
                        { brand: "Not A(Brand", version: "8" },
                        { brand: "Chromium", version: "131" },
                        { brand: "Google Chrome", version: "131" }
                    ],
                    mobile: false,
                    platform: "Windows"
                })
            });
        }
        
        // Cleanup prototype chain
        delete navigator.__proto__.webdriver;
        
        // Console output filtering
        const originalLog = console.log;
        console.log = function(...args) {
            if (args.length > 0 && typeof args[0] === 'string' && args[0].includes('webdriver')) {
                return;
            }
            return originalLog.apply(console, args);
        };
        """
        
        user_script = QWebEngineScript()
        user_script.setSourceCode(browser_compat_script)
        user_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        user_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        user_script.setRunsOnSubFrames(True)
        self.profile.scripts().insert(user_script)

def main():
    parser = argparse.ArgumentParser(description="Multi Vibe Chat")
    parser.add_argument('--profile', type=str, default=None, help='Profile name to use.')
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # If no profile specified via command line, load the last used profile
    if args.profile is None:
        # Create a temporary instance just to load the last profile
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, ".multi_vibe_chat_config.json")
        profile_name = 'default'
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    profile_name = config.get('last_profile', 'default')
        except Exception as e:
            print(f"Error loading last profile: {e}")
    else:
        profile_name = args.profile
    
    browser_app = MultiVibeChat(profile_name=profile_name)
    # Save this profile as the last used
    browser_app.save_last_profile(profile_name)
    browser_app.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

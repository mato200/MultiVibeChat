# Multi AI Chat Desktop Client
# PyQt6-based application for managing multiple AI chat sessions simultaneously

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
    """Custom request interceptor for adding HTTP headers"""
    def interceptRequest(self, info):
        # Modern browser headers
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
        # Current Chrome user agent string
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        self.profile().setHttpUserAgent(user_agent)
        self._popup_windows = []
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Reduce console noise
        if message and ('webdriver' in message.lower() or 'automation' in message.lower()):
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
    
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
        self.is_grid_layout = False  # Default to Nx1 horizontal layout
        self.url_bars_visible = False  # Track URL bar visibility for Alt toggle
        self.broadcast_enabled = True  # Toggle for unified prompt delivery
        self.all_targets = {
            'ChatGPT': 'https://chatgpt.com/', 
            'Claude': 'https://claude.ai/new',
            'Grok': 'https://x.com/i/grok', 
            'AI Studio': 'https://aistudio.google.com/prompts/new_chat',
            'Kimi K2': 'https://www.kimi.com/en'
        }
        self.enabled_ais = self.load_enabled_ais()  # Load saved AI selection
        self.targets = {k: v for k, v in self.all_targets.items() if k in self.enabled_ais}
        self.prompt_templates = {
            'ChatGPT': """var input = document.querySelector('div#prompt-textarea[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[data-testid="send-button"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Claude': """var input = document.querySelector('div.ProseMirror[contenteditable="true"]'); if (input) {{ input.innerHTML = '<p>{prompt}</p>'; input.dispatchEvent(new Event('input', {{ bubbles: true }})); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[aria-label="Send message"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'Grok': """var input = document.querySelector('textarea[placeholder="Ask anything"]'); if (input) {{ input.focus(); document.execCommand('insertText', false, `{prompt}`); let attempts = 0; const interval = setInterval(() => {{ const btn = document.querySelector('button[aria-label="Grok something"]'); if ((btn && !btn.disabled) || attempts > 30) {{ if (btn && !btn.disabled) btn.click(); clearInterval(interval); }} attempts++; }}, 100); }}""",
            'AI Studio': """
            // Try multiple selectors for Google AI Studio input field
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
                
                // Wait and try multiple methods to submit
                let attempts = 0;
                const interval = setInterval(() => {{
                    // Try to find the run/send button
                    var btn = document.querySelector('ms-run-button button') ||
                             document.querySelector('button[aria-label*="Run"]') ||
                             document.querySelector('button[aria-label*="Send"]') ||
                             document.querySelector('.run-button button') ||
                             document.querySelector('button.send-button');
                    
                    if (btn && !btn.disabled) {{
                        btn.click();
                        clearInterval(interval);
                    }} else if (attempts > 20) {{
                        // Fallback: simulate Enter key press on the textarea
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
            // Kimi K2 uses a contenteditable div with Lexical editor
            var input = document.querySelector('#chat-container > div.layout-content-main > div > div.chat-editor > div.chat-input > div.chat-input-editor-container > div.chat-input-editor') ||
                       document.querySelector('div.chat-input-editor[contenteditable="true"]') ||
                       document.querySelector('div[data-lexical-editor="true"]') ||
                       document.querySelector('.chat-input-editor');
            
            if (input) {{
                input.focus();
                
                // Select all existing content and replace with new text using execCommand
                // This is the most reliable way to work with Lexical editor
                var sel = window.getSelection();
                var range = document.createRange();
                range.selectNodeContents(input);
                sel.removeAllRanges();
                sel.addRange(range);
                
                // Insert text using execCommand (replaces selected content)
                document.execCommand('insertText', false, `{prompt}`);
                
                // Wait for the send button to become active and click it
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
            """
        }
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"Multi Vibe Chat - Profile: {self.profile_name}")
        self.setGeometry(100, 100, 1600, 1000)

        self.main_container = QWidget()
        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.main_container)

        self.handle_profile_logic()

        # Create browser container that will be rebuilt when AI selection changes
        self.browser_container = QWidget()
        self.browser_layout = QVBoxLayout(self.browser_container)
        self.browser_layout.setContentsMargins(0, 0, 0, 0)
        
        self.view_stack = QStackedLayout()
        self.browser_layout.addLayout(self.view_stack)
        
        # Build the initial browser panes
        self.rebuild_browser_panes()

        self.main_layout.addWidget(self.browser_container, 1)

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
        self.layout_switch_btn = QPushButton("Switch to Grid")
        self.focus_mode_btn = QPushButton("LOG IN MODE: OFF")
        self.focus_mode_btn.setCheckable(True)
        self.focus_mode_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; } QPushButton:checked { background-color: #4CAF50; color: white; }")
        google_signin_btn = QPushButton("🔐 Google Login (legacy)")
        google_signin_btn.setStyleSheet("background-color: #808080; color: white; font-weight: bold;")
        ai_select_btn = QPushButton("🤖 Select AIs")
        ai_select_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        top_button_layout.addWidget(send_btn)
        top_button_layout.addWidget(refresh_btn)
        top_button_layout.addWidget(self.layout_switch_btn)
        top_button_layout.addWidget(self.focus_mode_btn)
        top_button_layout.addWidget(ai_select_btn)
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

    def create_browser_pane(self, name):
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
        browser.load(QUrl(self.targets[name]))
        
        # Update URL bar when page URL changes
        browser.urlChanged.connect(lambda url, bar=url_bar: bar.setText(url.toString()))
        
        # Navigate when user presses Enter in URL bar
        url_bar.returnPressed.connect(lambda b=browser, bar=url_bar: self.navigate_to_url(b, bar))

        layout.addWidget(url_bar)
        layout.addWidget(browser)
        
        browser_info = {'name': name, 'browser': browser, 'url_bar': url_bar, 'container': container}
        self.browsers.append(browser_info)
        return container
    
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
        
        # Add browsers for newly selected AIs
        for ai_name in ais_to_add:
            if ai_name in self.targets:
                # Create new browser pane
                self.create_browser_pane(ai_name)
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
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel, QHBoxLayout
        
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
        select_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes.values()])
        deselect_all_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes.values()])
        cancel_btn.clicked.connect(dialog.reject)
        
        def apply_selection():
            selected = [name for name, cb in checkboxes.items() if cb.isChecked()]
            if not selected:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(dialog, "Warning", "Please select at least one AI assistant.")
                return
            
            self.enabled_ais = selected
            self.save_enabled_ais()
            self.targets = {k: v for k, v in self.all_targets.items() if k in self.enabled_ais}
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
                    enabled = config.get('enabled_ais', None)
                    if enabled:
                        # Filter to only include valid AI names
                        return [ai for ai in enabled if ai in self.all_targets]
        except Exception as e:
            print(f"Error loading enabled AIs: {e}")
        # Default: all AIs enabled
        return list(self.all_targets.keys())

    def save_enabled_ais(self):
        """Save the enabled AI list to config file."""
        try:
            config_path = self.get_config_path()
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
            config['enabled_ais'] = self.enabled_ais
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

    def broadcast_prompts(self):
        if not self.broadcast_enabled:
            return
        
        prompt = self.prompt_text.toPlainText().strip()
        if not prompt: return
        js_safe_prompt = prompt.replace('\\', '\\\\').replace('`', '\\`').replace('\n', '\\n').replace("'", "\\'")
        
        for ai_info in self.browsers:
            name = ai_info['name']
            browser = ai_info['browser']
            if name in self.prompt_templates:
                browser.page().runJavaScript(self.prompt_templates[name].format(prompt=js_safe_prompt))
                
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
            config = {'last_profile': profile_name}
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
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        
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
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.XSSAuditingEnabled, True)
        
        # Align browser runtime configuration with desktop defaults
        environment_alignment_script = """
        // Normalize browser API surface
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Provide expected plugin descriptors
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
        
        // Language configuration
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Populate chrome.runtime namespace with standard values
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
        
        // Permissions API behavior
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Hardware profile
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        // Memory profile
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        // Platform identifier
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Vendor metadata
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.'
        });
        
        // Network information
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false
            })
        });
        
        // Battery API shim
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
        
        // Preserve native function signatures
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === navigator.getBattery) {
                return 'function getBattery() { [native code] }';
            }
            return originalToString.call(this);
        };
        
        // WebGL rendering info
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
        
        // Screen metrics
        Object.defineProperty(screen, 'availWidth', {
            get: () => screen.width
        });
        Object.defineProperty(screen, 'availHeight', {
            get: () => screen.height - 40
        });
        
        // User-Agent Client Hints
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
        
        // Navigator prototype adjustments
        delete navigator.__proto__.webdriver;
        
        // Console logging guard
        const originalLog = console.log;
        console.log = function(...args) {
            if (args.length > 0 && typeof args[0] === 'string' && args[0].includes('webdriver')) {
                return;
            }
            return originalLog.apply(console, args);
        };
        """
        
        user_script = QWebEngineScript()
        user_script.setSourceCode(environment_alignment_script)
        user_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        user_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        user_script.setRunsOnSubFrames(True)
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
        # Get app data directory consistently
        if hasattr(sys, '_MEIPASS'):
            # Running from PyInstaller bundle
            app_data_dir = os.path.join(os.path.expanduser("~"), ".MultiVibeChat")
        else:
            # Running from source - keep data in script directory
            app_data_dir = os.path.dirname(os.path.abspath(__file__))
        
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

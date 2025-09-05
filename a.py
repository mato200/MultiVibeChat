# --- START OF FILE a.py ---

import sys
import os
import argparse
import subprocess
import shutil
import webbrowser
from urllib.parse import quote_plus
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QLineEdit,
                             QPushButton, QFrame, QSplitter, QComboBox, QStackedLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QKeyEvent

os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '8888'

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.profile().setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

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
        top_button_layout.addWidget(send_btn)
        top_button_layout.addWidget(refresh_btn)
        top_button_layout.addWidget(self.layout_switch_btn)

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

    def send_to_all_ais(self):
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

    def find_existing_profiles(self):
        home_dir = os.path.expanduser("~")
        prefix = ".multi_vibe_chat_profile_"
        profiles = [item[len(prefix):] for item in os.listdir(home_dir) if os.path.isdir(os.path.join(home_dir, item)) and item.startswith(prefix)]
        return sorted(profiles) if profiles else ['default']

    def switch_profile(self):
        new_profile_name = self.profile_combo.currentText().strip()
        if not new_profile_name or new_profile_name == self.profile_name:
            return
        args = [sys.executable, sys.argv[0], '--profile', new_profile_name]
        subprocess.Popen(args)
        self.close()

    def handle_profile_logic(self):
        home_dir = os.path.expanduser("~")
        legacy_path = os.path.join(home_dir, ".multi_ai_browser_profile")
        default_path = os.path.join(home_dir, ".multi_vibe_chat_profile_default")
        current_path = os.path.join(home_dir, f".multi_vibe_chat_profile_{self.profile_name}")

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

def main():
    parser = argparse.ArgumentParser(description="Multi Vibe Chat")
    parser.add_argument('--profile', type=str, default='default', help='Profile name to use.')
    args = parser.parse_args()
    app = QApplication(sys.argv)
    browser_app = MultiVibeChat(profile_name=args.profile)
    browser_app.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
import sys
import pathlib
import textwrap
import datetime
import json
import os

import google.generativeai as genai
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

# --- Constants ---
DEFAULT_API_KEY_PLACEHOLDER = "YOUR_GEMINI_API_KEY"
SETTINGS_FILE = "pyroai_settings.json"  # Use a separate file for settings
DEFAULT_SETTINGS = {
    "apiKey": DEFAULT_API_KEY_PLACEHOLDER,
    "theme": "dark",  # "light" or "dark"
    "fontSize": 12,
    "fontFamily": "Courier New",
    "autoSave": False,
    "autoSaveInterval": 5  # in minutes
}

# --- Utility Functions ---

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
        # Apply any missing default settings
        for key, value in DEFAULT_SETTINGS.items():
            if key not in settings:
                settings[key] = value
        return settings
    except FileNotFoundError:
        return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

# --- Worker Thread --- 
class Worker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)  # Signal to update progress bar

    def __init__(self, message, image_path=None, api_key=None):
        super().__init__()
        self.message = message
        self.image_path = image_path
        self.api_key = api_key
        self.chat = None  

    def run(self):
        try:
            if self.api_key and self.api_key != DEFAULT_API_KEY_PLACEHOLDER:
                genai.configure(api_key=self.api_key)
            else:
                self.error.emit("API key not set. Please configure in Settings.")
                return

            if self.chat is None:
                self.chat = genai.GenerativeModel('gemini-1.5-flash').start_chat(history=[])

            if self.image_path:
                img = pathlib.Path(self.image_path).read_bytes()
                response = self.chat.send_message([self.message, img], stream=True)
            else:
                response = self.chat.send_message(self.message, stream=True)

            total_tokens = 0 
            for i, chunk in enumerate(response):  # Use enumerate to get chunk index
                self.progress.emit(i + 1)  # Update progress
                total_tokens += 1
            self.finished.emit(response.text)

        except Exception as e:
            self.error.emit(str(e))

# --- Settings Dialog ---
class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyroAI Settings")
        self.settings = settings

        self.api_key_label = QLabel("Gemini API Key:")
        self.api_key_input = QLineEdit(self.settings.get("apiKey", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)

        self.theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        current_theme = self.settings.get("theme", "light")
        self.theme_combo.setCurrentText(current_theme.capitalize())

        self.auto_save_label = QLabel("Auto Save:")
        self.auto_save_combo = QComboBox()
        self.auto_save_combo.addItems(["Enabled", "Disabled"])
        auto_save_status = "Enabled" if self.settings.get("autoSave", False) else "Disabled"
        self.auto_save_combo.setCurrentText(auto_save_status)

        self.auto_save_interval_label = QLabel("Auto Save Interval (minutes):")
        self.auto_save_interval_input = QLineEdit(str(self.settings.get("autoSaveInterval", 5)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QGridLayout(self)
        layout.addWidget(self.api_key_label, 0, 0)
        layout.addWidget(self.api_key_input, 0, 1)
        layout.addWidget(self.theme_label, 1, 0)
        layout.addWidget(self.theme_combo, 1, 1)
        layout.addWidget(self.auto_save_label, 2, 0)
        layout.addWidget(self.auto_save_combo, 2, 1)
        layout.addWidget(self.auto_save_interval_label, 3, 0)
        layout.addWidget(self.auto_save_interval_input, 3, 1)
        layout.addWidget(buttons, 4, 0, 1, 2) # Span 2 columns

    def accept(self):
        self.settings["apiKey"] = self.api_key_input.text()
        self.settings["theme"] = self.theme_combo.currentText().lower()
        self.settings["autoSave"] = self.auto_save_combo.currentText() == "Enabled"
        self.settings["autoSaveInterval"] = int(self.auto_save_interval_input.text())
        save_settings(self.settings)  # Save settings to file
        super().accept()


# --- Main Application Window ---
class PyroAI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.initUI()
        self.worker = None
        self.apply_theme(self.settings.get("theme", "light"))

        if self.settings.get("autoSave", False):
            self.start_auto_save_timer()

    def initUI(self):
        self.setWindowTitle("PyroAI Chatbot")
        self.setGeometry(100, 100, 800, 600)

        # --- UI Elements --- 
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.send_button = QPushButton("Send")
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)  # Initially hide the progress bar

        # --- Layout ---
        main_layout = QVBoxLayout()
        input_layout = QHBoxLayout()

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)
        main_layout.addWidget(self.output_area)
        main_layout.addWidget(self.progress_bar)  # Add progress bar to layout

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- Menubar ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        settings_menu = menubar.addMenu("&Settings")
        view_menu = menubar.addMenu("&View")

        # File Menu Actions
        save_chat_action = QAction("&Save Chat", self)
        save_chat_action.triggered.connect(self.save_chat)
        file_menu.addAction(save_chat_action)

        clear_chat_action = QAction("&Clear Chat", self)
        clear_chat_action.triggered.connect(self.clear_chat)
        file_menu.addAction(clear_chat_action)

        # Settings Menu Actions
        api_settings_action = QAction("&API Key", self)
        api_settings_action.triggered.connect(self.open_api_settings)
        settings_menu.addAction(api_settings_action)

        # View Menu Actions
        font_action = QAction('&Font...', self)
        font_action.triggered.connect(self.change_font)
        view_menu.addAction(font_action)

        color_action = QAction('&Background Color...', self)
        color_action.triggered.connect(self.change_background_color)
        view_menu.addAction(color_action)

        # --- System Tray ---
        self.tray_icon = QSystemTrayIcon(QIcon("icon.png"), self)
        tray_menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # --- Connections ---
        self.send_button.clicked.connect(self.send_message)

        self.apply_settings() 

    # --- Slots/Methods ---

    def send_message(self):
        user_input = self.input_field.text()
        self.input_field.clear()

        if user_input.lower() in ("quit", "exit"):
            QApplication.quit()

        self.display_message("You: " + user_input)

        api_key = self.settings.get("apiKey", DEFAULT_API_KEY_PLACEHOLDER)
        self.worker = Worker(user_input, api_key=api_key)
        self.worker.finished.connect(self.display_bot_reply)
        self.worker.error.connect(self.display_error)
        self.worker.progress.connect(self.update_progress) 
        self.worker.start()

        self.progress_bar.setVisible(True)  # Show progress bar
        self.progress_bar.setMaximum(0)  # Set to indeterminate state

    def display_bot_reply(self, reply_text):
        self.display_message("PyroAI: " + reply_text)
        self.progress_bar.setVisible(False)  # Hide when done
        self.progress_bar.setMaximum(100) # Reset to determinate

    def display_message(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.output_area.append(f"[{timestamp}] {message}")
        self.output_area.verticalScrollBar().setValue(
            self.output_area.verticalScrollBar().maximum()
        )

    def clear_chat(self):
        self.output_area.clear()
        if self.worker:
            self.worker.chat = None

    def save_chat(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Chat As", "",
                                                  "Text Files (*.txt);;All Files (*)", options=options)
        if file_path:
            try:
                with open(file_path, "w") as f:
                    f.write(self.output_area.toPlainText())
                QMessageBox.information(self, "Success", "Chat saved successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save chat: {e}")

    def open_api_settings(self):
        dialog = SettingsDialog(self.settings, self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.apply_settings()  # Reapply settings if changed

    def change_font(self):
        font, ok = QFontDialog.getFont(self.output_area.font(), self)
        if ok:
            self.output_area.setFont(font)
            self.settings["fontFamily"] = font.family()
            self.settings["fontSize"] = font.pointSize()
            save_settings(self.settings)

    def change_background_color(self):
        color = QColorDialog.getColor(self.palette().color(QPalette.Background), self)
        if color.isValid():
            self.apply_theme("light", color)  # Apply as light theme with custom color

    def apply_settings(self):
        font_family = self.settings.get("fontFamily", "Courier New")
        font_size = self.settings.get("fontSize", 12)
        self.output_area.setFont(QFont(font_family, font_size))
        self.apply_theme(self.settings.get("theme", "light"))

    def apply_theme(self, theme, bg_color=None):
        if theme == "dark":
            self.setStyleSheet("""
                QMainWindow { background-color: #333; color: #eee; }
                QLineEdit { background-color: #444; color: #eee; border: 1px solid #555; }
                QPushButton { background-color: #007bff; color: #fff; }
                QTextEdit { background-color: #222; color: #eee; }
            """)
        else:  # "light" or any other theme
            self.setStyleSheet("""
                QMainWindow { background-color: #f2f2f2; color: #333; }
                QLineEdit { background-color: #fff; color: #333; border: 1px solid #ccc; }
                QPushButton { background-color: #008CBA; color: white; }
                QTextEdit { background-color: #fff; color: #333; }
            """)
            if bg_color is not None:
                palette = self.palette()
                palette.setColor(QPalette.Background, bg_color)
                self.setPalette(palette)

    def display_error(self, error_message):
        QMessageBox.critical(self, "Error", error_message)
        self.progress_bar.setVisible(False) # Hide progress bar on error
        self.progress_bar.setMaximum(100) # Reset to determinate

    def update_progress(self, value):
        # For now, just treat as indeterminate. 
        # In the future, you'll get token counts from the API
        # and can make this a more accurate progress bar. 
        pass

    def start_auto_save_timer(self):
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save_chat)
        interval = self.settings.get("autoSaveInterval", 5) * 60 * 1000  # Convert minutes to milliseconds
        self.auto_save_timer.start(interval)

    def auto_save_chat(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"chat_auto_save_{timestamp}.txt"
        try:
            with open(file_path, "w") as f:
                f.write(self.output_area.toPlainText())
            self.tray_icon.showMessage("Auto Save", f"Chat auto-saved to {file_path}", QSystemTrayIcon.Information)
        except Exception as e:
            self.tray_icon.showMessage("Auto Save Error", f"Failed to auto-save chat: {e}", QSystemTrayIcon.Critical)

# --- Splash Screen ---
class SplashScreen(QSplashScreen):
    def __init__(self):
        super().__init__()
        pixmap = QPixmap("splash.png")  # Replace with your splash image
        self.setPixmap(pixmap.scaled(QSize(400, 300)))  # Adjust size as needed

# --- Application Entry Point ---
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Splash Screen 
    splash = SplashScreen()
    splash.show()
    app.processEvents()  # Process events to show the splash screen

    # Load settings before creating the main window
    settings = load_settings()

    pyro_ai = PyroAI()

    # Simulate loading delay (replace with actual loading if needed)
    for i in range(1, 101):
        splash.showMessage(f"Loading... {i}%", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()
        QThread.msleep(10)  # Simulate loading delay 

    pyro_ai.show()
    splash.finish(pyro_ai) 
    sys.exit(app.exec_())
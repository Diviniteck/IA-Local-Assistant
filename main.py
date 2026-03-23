#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from GUI.main_window import UnityAIAssistant


def main():
    print("=" * 60)
    print("🤖 UNITY AI ASSISTANT - Votre Bezi Personnel")
    print("=" * 60)
    print("Initialisation...\n")

    app = QApplication(sys.argv)

    app.setStyleSheet("""
    QMainWindow {
        background-color: #1e1e1e;
    }

    QLabel {
        color: #e6e6e6;
    }

    QListWidget {
        background-color: #2b2b2b;
        color: #e6e6e6;
        border: 1px solid #3c3c3c;
        border-radius: 6px;
        padding: 4px;
    }

    QTextEdit {
        background-color: #2b2b2b;
        color: #e6e6e6;
        border: 1px solid #3c3c3c;
        border-radius: 6px;
    }

    QPushButton {
        background-color: #3c3c3c;
        color: #e6e6e6;
        border-radius: 5px;
        padding: 6px;
    }

    QPushButton:hover {
        background-color: #4a4a4a;
    }

    QStatusBar {
        background-color: #1e1e1e;
        color: #cccccc;
    }

    QProgressBar {
        background-color: #2b2b2b;
        border: 1px solid #3c3c3c;
        color: white;
    }
""")

    window = UnityAIAssistant()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
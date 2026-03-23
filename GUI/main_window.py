import os
import json
import threading

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QSplitter, QListWidget, QListWidgetItem,
    QStatusBar, QProgressBar, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QFont

from Core.ai_connector import LMStudioConnector
from Core.project_scanner import UnityProjectScanner
from Core.conversation_manager import ConversationManager
from Core.unity_bridge_server import UnityBridgeServer
from Core.project_context import ProjectContext


class UnityAIAssistant(QMainWindow):
    """Fenêtre principale de l'application."""

    answer_received = pyqtSignal(str)
    file_changed_signal = pyqtSignal(str, str)
    unity_state_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        self.config_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "config.json")
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.project_context = ProjectContext(self.config_path)
        
        self.ai_connector = LMStudioConnector(
            self.config_path,
            project_context=self.project_context
        )
        self.scanner = UnityProjectScanner(
        self.config_path,
        project_context=self.project_context
        )

        self.conversation_manager = ConversationManager(self.config_path)

        self.bridge_server = UnityBridgeServer(
            host="127.0.0.1",
            port=8765,
            on_state_changed=lambda state: self.unity_state_signal.emit(state)
        )

        self.init_ui()
        self.setup_connections()
        self.load_conversations_list()
        self.ensure_startup_conversation()
        self.bridge_server.start()

    def init_ui(self):
        self.setWindowTitle("🤖 Unity AI Assistant - Votre Bezi Personnel")
        self.setGeometry(100, 100, 1500, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==================== PANNEAU GAUCHE ====================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_title = QLabel("📁 PROJET UNITY")
        left_title.setStyleSheet("color: #ffffff;")
        left_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        left_layout.addWidget(left_title)

        btn_row = QHBoxLayout()
        self.btn_scan = QPushButton("🔍 Scanner le Projet")
        self.btn_monitor = QPushButton("👁️ Activer Surveillance")
        self.btn_monitor.setCheckable(True)
        self.btn_config = QPushButton("⚙️ Configuration")
        btn_row.addWidget(self.btn_scan)
        btn_row.addWidget(self.btn_monitor)
        btn_row.addWidget(self.btn_config)
        left_layout.addLayout(btn_row)

        self.project_status = QLabel("📊 Statut: En attente...")
        self.project_status.setStyleSheet("color: #aaaaaa; font-style: italic;")
        left_layout.addWidget(self.project_status)

        self.project_path_label = QLabel(f"📂 Projet : {self.config['unity_project_path']}")
        self.project_path_label.setWordWrap(True)
        left_layout.addWidget(self.project_path_label)

        # ===== Bridge Unity =====
        bridge_title = QLabel("🌉 UNITY BRIDGE")
        bridge_title.setStyleSheet("color: #ffffff;")
        bridge_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        left_layout.addWidget(bridge_title)

        self.unity_connection_label = QLabel("🔴 Unity : Déconnecté")
        self.unity_connection_label.setStyleSheet("color: #ff6b6b;")
        left_layout.addWidget(self.unity_connection_label)

        self.unity_project_label = QLabel("📦 Projet Unity connecté : -")
        self.unity_project_label.setWordWrap(True)
        left_layout.addWidget(self.unity_project_label)

        self.unity_scene_label = QLabel("🗺️ Scène active : -")
        self.unity_scene_label.setWordWrap(True)
        left_layout.addWidget(self.unity_scene_label)

        self.unity_selection_label = QLabel("🎯 Sélection : -")
        self.unity_selection_label.setWordWrap(True)
        left_layout.addWidget(self.unity_selection_label)

        self.unity_mode_label = QLabel("▶️ Mode : -")
        self.unity_mode_label.setWordWrap(True)
        left_layout.addWidget(self.unity_mode_label)

        conv_title = QLabel("🕘 HISTORIQUE DES CONVERSATIONS")
        conv_title.setStyleSheet("color: #ffffff;")
        conv_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        left_layout.addWidget(conv_title)

        conv_btn_row = QHBoxLayout()
        self.btn_new_chat = QPushButton("🆕 Nouvelle conversation")
        conv_btn_row.addWidget(self.btn_new_chat)
        left_layout.addLayout(conv_btn_row)

        self.conversations_list = QListWidget()
        self.conversations_list.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.conversations_list, stretch=1)

        files_title = QLabel("📄 FICHIERS DU PROJET")
        files_title.setStyleSheet("color: #ffffff;")
        files_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        left_layout.addWidget(files_title)

        self.files_list = QListWidget()
        self.files_list.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.files_list, stretch=2)

        splitter.addWidget(left_panel)

        # ==================== PANNEAU DROIT ====================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)

        right_title = QLabel("💬 ASSISTANT IA")
        right_title.setStyleSheet("color: #ffffff;")
        right_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        right_layout.addWidget(right_title)

        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #e6e6e6;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 13px;
            }
        """)
        self.response_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        right_layout.addWidget(self.response_area)

        input_row = QHBoxLayout()

        self.question_input = QTextEdit()
        self.question_input.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #e6e6e6;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        self.question_input.setMaximumHeight(120)
        self.question_input.setFont(QFont("Consolas", 10))
        self.question_input.setPlaceholderText(
            "Posez votre question sur le projet Unity..."
        )
        input_row.addWidget(self.question_input, stretch=1)

        btn_col = QVBoxLayout()

        self.btn_send = QPushButton("🚀 Envoyer")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        self.btn_clear_input = QPushButton("🧹 Vider la saisie")
        self.btn_clear_input.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)

        btn_col.addWidget(self.btn_send)
        btn_col.addWidget(self.btn_clear_input)
        input_row.addLayout(btn_col)

        right_layout.addLayout(input_row)

        self.progress_label = QLabel("🤔 L'IA réfléchit...")
        self.progress_label.setVisible(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)

        right_layout.addWidget(self.progress_label)
        right_layout.addWidget(self.progress_bar)

        splitter.addWidget(right_panel)
        splitter.setSizes([470, 1030])

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt. Bridge Unity actif sur le port 8765.")

    def setup_connections(self):
        self.btn_scan.clicked.connect(self.scan_project)
        self.btn_monitor.toggled.connect(self.toggle_monitoring)
        self.btn_send.clicked.connect(self.send_question)
        self.btn_clear_input.clicked.connect(self.clear_input_only)
        self.btn_config.clicked.connect(self.show_config_dialog)
        self.btn_new_chat.clicked.connect(self.create_new_conversation)

        self.answer_received.connect(self.on_answer_received)
        self.file_changed_signal.connect(self.on_file_changed)
        self.unity_state_signal.connect(self.on_unity_state_changed)

        self.conversations_list.itemClicked.connect(self.on_conversation_selected)
        self.question_input.installEventFilter(self)

    def ensure_startup_conversation(self):
        conversations = self.conversation_manager.list_conversations()

        if conversations:
            first_id = conversations[0]["id"]
            self.conversation_manager.load_conversation(first_id)
        else:
            self.conversation_manager.create_new_conversation()

        self.refresh_chat_display()
        self.load_conversations_list()

    def load_conversations_list(self):
        self.conversations_list.clear()

        for conv in self.conversation_manager.list_conversations():
            title = conv["title"]
            updated = conv.get("updated_at", "")
            item = QListWidgetItem(f"💬 {title}\n🕒 {updated}")
            item.setData(Qt.ItemDataRole.UserRole, conv["id"])
            self.conversations_list.addItem(item)

    def create_new_conversation(self):
        self.conversation_manager.create_new_conversation()
        self.load_conversations_list()
        self.refresh_chat_display()
        self.status_bar.showMessage("🆕 Nouvelle conversation créée")

    def on_conversation_selected(self, item: QListWidgetItem):
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        self.conversation_manager.load_conversation(conversation_id)
        self.refresh_chat_display()
        self.status_bar.showMessage("📂 Conversation chargée")

    def refresh_chat_display(self):
        messages = self.conversation_manager.get_current_messages()

        if not messages:
            self.response_area.setPlainText("Aucun message dans cette conversation.")
            return

        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")

            if role == "user":
                lines.append(f"👤 VOUS [{timestamp}]\n{'-' * 70}\n{content}\n")
            elif role == "assistant":
                lines.append(f"🤖 ASSISTANT [{timestamp}]\n{'-' * 70}\n{content}\n")
            else:
                lines.append(f"ℹ️ {role.upper()} [{timestamp}]\n{'-' * 70}\n{content}\n")

        self.response_area.setPlainText("\n".join(lines))
        self.response_area.verticalScrollBar().setValue(
            self.response_area.verticalScrollBar().maximum()
        )

    def scan_project(self):
        self.status_bar.showMessage("🔍 Scan en cours...")
        file_count = self.scanner.scan_all()

        self.files_list.clear()
        for filepath in sorted(self.scanner.file_contents.keys()):
            item = QListWidgetItem(filepath)

            if filepath.endswith(".cs"):
                item.setText(f"📝 {filepath}")
            elif filepath.endswith(".prefab"):
                item.setText(f"🎲 {filepath}")
            elif filepath.endswith(".unity"):
                item.setText(f"🗺️ {filepath}")
            elif filepath.endswith(".asset"):
                item.setText(f"📦 {filepath}")
            else:
                item.setText(f"📄 {filepath}")

            self.files_list.addItem(item)

        total_size = sum(len(c) for c in self.scanner.file_contents.values()) / 1024
        self.project_status.setText(
            f"📊 {file_count} fichiers | {total_size:.1f} KB | Contexte prêt ✅"
        )

        if self.ai_connector.test_connection():
            self.status_bar.showMessage("✅ Connecté à LM Studio - Prêt !")
        else:
            QMessageBox.warning(
                self,
                "⚠️ Attention",
                "LM Studio n'est pas accessible.\n\nVérifiez que :\n"
                "- LM Studio est lancé\n"
                "- Le serveur local est actif sur http://localhost:1234\n"
                "- Un modèle est chargé"
            )

    def toggle_monitoring(self, enabled):
        if enabled:
            self.scanner.start_monitoring(
                callback=lambda filepath, action: self.file_changed_signal.emit(filepath, action)
            )
            self.btn_monitor.setText("⏹️ Arrêter Surveillance")
            self.status_bar.showMessage("👁️ Surveillance active...")
        else:
            self.scanner.stop_monitoring()
            self.btn_monitor.setText("👁️ Activer Surveillance")
            self.status_bar.showMessage("⏹️ Surveillance arrêtée")

    def on_file_changed(self, filepath: str, action: str):
        if action == "modified":
            self.project_status.setText(f"📝 {filepath} modifié - Contexte mis à jour ✅")
        elif action == "added":
            self.project_status.setText(f"➕ {filepath} ajouté au projet")
        elif action == "removed":
            self.project_status.setText(f"🗑️ {filepath} supprimé du projet")

    def on_unity_state_changed(self, state: dict):
        self.project_context.update_from_unity_state(state)

        if state.get("is_connected", False):
            self.unity_connection_label.setText("🟢 Unity : Connecté")
            self.unity_connection_label.setStyleSheet("color: #7CFC98;")
        else:
            self.unity_connection_label.setText("🔴 Unity : Déconnecté")
            self.unity_connection_label.setStyleSheet("color: #ff6b6b;")

        self.unity_project_label.setText(
            f"📦 Projet Unity connecté : {state.get('project_name', '-')}"
        )
        self.unity_scene_label.setText(
            f"🗺️ Scène active : {state.get('active_scene', '-')}"
        )
        self.unity_selection_label.setText(
            f"🎯 Sélection : {state.get('selected_object', '-')}"
        )
        self.unity_mode_label.setText(
            f"▶️ Mode : {state.get('play_mode', '-')}"
        )

    def send_question(self):
        question = self.question_input.toPlainText().strip()

        if not question:
            QMessageBox.warning(self, "⚠️ Attention", "Veuillez entrer une question.")
            return

        if not self.scanner.file_contents:
            QMessageBox.warning(
                self,
                "⚠️ Attention",
                "Aucun projet scanné.\n\nCliquez sur '🔍 Scanner le Projet' d'abord."
            )
            return

        self.conversation_manager.add_message("user", question)
        self.load_conversations_list()
        self.refresh_chat_display()

        self.question_input.clear()
        self.question_input.setReadOnly(True)
        self.btn_send.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)

        project_context = self.scanner.get_context_string(
            max_chars=self.config.get("max_context_tokens", 35000)
        )

        history = self.conversation_manager.get_model_messages(
            max_messages=self.config.get("max_history_messages_for_model", 4),
            exclude_last_user=True,
            max_chars_per_message=self.config.get("max_history_chars_per_message", 1500)
        )

        unity_context = (
            f"\n\nCONTEXTE UNITY TEMPS RÉEL :\n"
            f"• Projet connecté : {self.unity_project_label.text()}\n"
            f"• Scène active : {self.unity_scene_label.text()}\n"
            f"• Sélection : {self.unity_selection_label.text()}\n"
            f"• Mode : {self.unity_mode_label.text()}\n"
        )

        def ask_ai():
            try:
                answer = self.ai_connector.send_with_context(
                    question=question,
                    project_context=project_context + unity_context,
                    conversation_history=history
                )
                self.answer_received.emit(answer)
            except Exception as e:
                error_msg = f"❌ Erreur : {str(e)}\n\nVérifiez la connexion LM Studio."
                self.answer_received.emit(error_msg)

        thread = threading.Thread(target=ask_ai, daemon=True)
        thread.start()

    def on_answer_received(self, answer):
        self.conversation_manager.add_message("assistant", answer)
        self.refresh_chat_display()
        self.load_conversations_list()

        self.question_input.setReadOnly(False)
        self.btn_send.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.status_bar.showMessage("✅ Réponse reçue")

    def clear_input_only(self):
        self.question_input.clear()
        self.question_input.setFocus()

    def show_config_dialog(self):
        new_path = QFileDialog.getExistingDirectory(
            self,
            "Sélectionner le dossier Unity",
            self.config["unity_project_path"]
        )

        if new_path:
            self.config["unity_project_path"] = new_path
            self.project_context.set_project_path(new_path)

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)

            self.ai_connector = LMStudioConnector(
                self.config_path,
                project_context=self.project_context
            )
            self.scanner.stop_monitoring()
            self.scanner = UnityProjectScanner(
                self.config_path,
                project_context=self.project_context
            )

            self.project_path_label.setText(f"📂 Projet : {new_path}")
            self.files_list.clear()
            self.project_status.setText("📊 Nouveau projet sélectionné - Scan requis")

            self.btn_monitor.setChecked(False)
            self.btn_monitor.setText("👁️ Activer Surveillance")

            QMessageBox.information(
                self,
                "✅ Configuration",
                f"Projet mis à jour :\n{new_path}\n\nLe scanner a été rechargé."
            )

    def eventFilter(self, obj, event):
        if obj == self.question_input and event.type() == QEvent.Type.KeyPress:
            if (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.key() == Qt.Key.Key_Return
            ):
                self.send_question()
                return True

        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.scanner.stop_monitoring()
        self.bridge_server.stop()
        super().closeEvent(event)
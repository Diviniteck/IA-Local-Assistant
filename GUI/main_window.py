import os
import json
import threading

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QSplitter, QListWidget, QListWidgetItem,
    QStatusBar, QProgressBar, QMessageBox, QFileDialog, QFrame,
    QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QFont

from Core.ai_connector import LMStudioConnector
from Core.project_scanner import UnityProjectScanner
from Core.conversation_manager import ConversationManager
from Core.unity_bridge_server import UnityBridgeServer
from Core.project_context import ProjectContext
from Core.context_engine import ContextEngine
from Core.pages_manager import PagesManager


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

        self.context_engine = ContextEngine(
            project_context=self.project_context,
            scanner=self.scanner
        )

        self.conversation_manager = ConversationManager(self.config_path)
        self.pages_manager = PagesManager(self.config_path)

        self.bridge_server = UnityBridgeServer(
            host="127.0.0.1",
            port=8765,
            on_state_changed=lambda state: self.unity_state_signal.emit(state)
        )

        self.init_ui()
        self.setup_connections()
        self.load_conversations_list()
        self.ensure_startup_conversation()
        self.refresh_project_info_ui()
        self.refresh_right_panel()
        self.bridge_server.start()

        self.current_document_id = None
        self.current_page_id = None
        self.is_editing_page = False

    # ============================================================
    # UI HELPERS
    # ============================================================

    def _create_section_frame(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("sectionFrame")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)

        return frame, layout

    def _create_small_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(30)
        return btn

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1f1f1f;
            }
            QWidget {
                background-color: #1f1f1f;
                color: #e8e8e8;
                font-size: 13px;
            }
            QFrame#sectionFrame {
                background-color: #2a2a2a;
                border: 1px solid #3b3b3b;
                border-radius: 8px;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                padding-bottom: 4px;
            }
            QLabel#mutedLabel {
                color: #b8b8b8;
            }
            QListWidget, QTreeWidget, QTextEdit {
                background-color: #252525;
                color: #e6e6e6;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget::item, QTreeWidget::item {
                padding: 6px;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background-color: #3d4f63;
                color: #ffffff;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #5a3d1f;
                border: 1px solid #7a5527;
            }
            QPushButton#primaryButton {
                background-color: #3f7d4f;
                border: 1px solid #4e9a61;
                font-weight: bold;
            }
            QPushButton#primaryButton:hover {
                background-color: #4b9360;
            }
            QPushButton#dangerButton {
                background-color: #7d3f3f;
                border: 1px solid #a05252;
            }
            QPushButton#dangerButton:hover {
                background-color: #915050;
            }
            QProgressBar {
                background-color: #252525;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                text-align: center;
                color: #e6e6e6;
            }
            QStatusBar {
                background-color: #202020;
                color: #dcdcdc;
                border-top: 1px solid #333333;
            }
            QSplitter::handle {
                background-color: #2b2b2b;
                width: 2px;
            }
        """)

    # ============================================================
    # INIT UI
    # ============================================================

    def init_ui(self):
        self.setWindowTitle("DotTeck - B.O.B")
        self.setGeometry(80, 80, 1680, 940)
        self._apply_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==================== PANNEAU GAUCHE ====================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Projet
        project_frame, project_layout = self._create_section_frame("PROJET")
        self.project_name_label = QLabel("Projet : -")
        self.project_name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))

        self.project_path_label = QLabel("Chemin : -")
        self.project_path_label.setObjectName("mutedLabel")
        self.project_path_label.setWordWrap(True)

        self.project_status = QLabel("Statut : En attente...")
        self.project_status.setObjectName("mutedLabel")

        project_btn_row = QHBoxLayout()
        self.btn_scan = self._create_small_button("Scanner")
        self.btn_monitor = self._create_small_button("Surveillance")
        self.btn_monitor.setCheckable(True)
        self.btn_config = self._create_small_button("Projet...")
        project_btn_row.addWidget(self.btn_scan)
        project_btn_row.addWidget(self.btn_monitor)
        project_btn_row.addWidget(self.btn_config)

        project_layout.addWidget(self.project_name_label)
        project_layout.addWidget(self.project_path_label)
        project_layout.addWidget(self.project_status)
        project_layout.addLayout(project_btn_row)
        left_layout.addWidget(project_frame)

        # Unity Bridge
        unity_frame, unity_layout = self._create_section_frame("UNITY")
        self.unity_connection_label = QLabel("Unity : Déconnecté")
        self.unity_project_label = QLabel("Projet Unity connecté : -")
        self.unity_scene_label = QLabel("Scène active : -")
        self.unity_selection_label = QLabel("Sélection : -")
        self.unity_mode_label = QLabel("Mode : -")

        for lbl in [
            self.unity_project_label,
            self.unity_scene_label,
            self.unity_selection_label,
            self.unity_mode_label,
        ]:
            lbl.setWordWrap(True)
            lbl.setObjectName("mutedLabel")

        unity_layout.addWidget(self.unity_connection_label)
        unity_layout.addWidget(self.unity_project_label)
        unity_layout.addWidget(self.unity_scene_label)
        unity_layout.addWidget(self.unity_selection_label)
        unity_layout.addWidget(self.unity_mode_label)
        left_layout.addWidget(unity_frame)

        # Conversations
        conv_frame, conv_layout = self._create_section_frame("CONVERSATIONS")
        conv_btn_row = QHBoxLayout()
        self.btn_new_chat = self._create_small_button("Nouvelle conversation")
        conv_btn_row.addWidget(self.btn_new_chat)

        self.conversations_list = QListWidget()
        self.conversations_list.setFont(QFont("Consolas", 10))
        conv_layout.addLayout(conv_btn_row)
        conv_layout.addWidget(self.conversations_list)
        left_layout.addWidget(conv_frame, stretch=1)

        # Pages / Documents
        pages_frame, pages_layout = self._create_section_frame("PAGES / DOCUMENTS")
        pages_btn_row = QHBoxLayout()
        self.btn_new_page = self._create_small_button("+ Page")
        self.btn_new_doc = self._create_small_button("+ Document")
        pages_btn_row.addWidget(self.btn_new_page)
        pages_btn_row.addWidget(self.btn_new_doc)

        self.pages_tree = QTreeWidget()
        self.pages_tree.setHeaderHidden(True)
        self.pages_tree.setFont(QFont("Consolas", 10))

        pages_hint = QLabel("Prévu pour la documentation projet et le contexte épinglé.")
        pages_hint.setObjectName("mutedLabel")
        pages_hint.setWordWrap(True)

        pages_layout.addLayout(pages_btn_row)
        pages_layout.addWidget(self.pages_tree)
        pages_layout.addWidget(pages_hint)
        left_layout.addWidget(pages_frame, stretch=1)

        self.main_splitter.addWidget(left_panel)

        # ==================== PANNEAU CENTRE ====================
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        chat_header_frame, chat_header_layout = self._create_section_frame("B.O.B")
        self.chat_project_label = QLabel("Projet courant : -")
        self.chat_project_label.setObjectName("mutedLabel")
        self.chat_state_label = QLabel("Prêt à analyser le projet.")
        self.chat_state_label.setObjectName("mutedLabel")
        chat_header_layout.addWidget(self.chat_project_label)
        chat_header_layout.addWidget(self.chat_state_label)
        center_layout.addWidget(chat_header_frame)

        # MODE CHAT
        self.chat_frame, chat_layout = self._create_section_frame("CHAT")

        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setFont(QFont("Consolas", 10))
        self.response_area.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        chat_layout.addWidget(self.response_area)

        center_layout.addWidget(self.chat_frame, stretch=1)

        # MODE PAGE EDITOR
        self.page_frame, page_layout = self._create_section_frame("PAGE")

        self.page_title_label = QLabel("Aucune page sélectionnée")
        self.page_title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))

        self.page_editor = QTextEdit()
        self.page_editor.setFont(QFont("Consolas", 10))
        self.page_editor.setPlaceholderText("Écris ici ta documentation...")

        page_layout.addWidget(self.page_title_label)
        page_layout.addWidget(self.page_editor)

        self.page_frame.setVisible(False)

        center_layout.addWidget(self.page_frame, stretch=1)

        input_frame, input_layout = self._create_section_frame("MESSAGE")
        self.question_input = QTextEdit()
        self.question_input.setMaximumHeight(120)
        self.question_input.setFont(QFont("Consolas", 10))
        self.question_input.setPlaceholderText(
            "Pose une question sur ton projet..."
        )

        input_btn_col = QVBoxLayout()
        self.btn_send = QPushButton("Envoyer")
        self.btn_send.setObjectName("primaryButton")
        self.btn_clear_input = QPushButton("Vider")
        self.btn_clear_input.setObjectName("dangerButton")
        input_btn_col.addWidget(self.btn_send)
        input_btn_col.addWidget(self.btn_clear_input)
        input_btn_col.addStretch()

        input_row = QHBoxLayout()
        input_row.addWidget(self.question_input, stretch=1)
        input_row.addLayout(input_btn_col)

        self.progress_label = QLabel("B.O.B analyse le contexte...")
        self.progress_label.setObjectName("mutedLabel")
        self.progress_label.setVisible(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)

        input_layout.addLayout(input_row)
        input_layout.addWidget(self.progress_label)
        input_layout.addWidget(self.progress_bar)

        center_layout.addWidget(input_frame)

        self.main_splitter.addWidget(center_panel)

        # ==================== PANNEAU DROIT ====================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Contexte actuel
        context_frame, context_layout = self._create_section_frame("CONTEXTE ACTUEL")
        self.context_summary = QTextEdit()
        self.context_summary.setReadOnly(True)
        self.context_summary.setMinimumHeight(180)
        self.context_summary.setFont(QFont("Consolas", 10))
        context_layout.addWidget(self.context_summary)
        right_layout.addWidget(context_frame)

        # Sources utilisées
        sources_frame, sources_layout = self._create_section_frame("SOURCES UTILISÉES")
        self.sources_list = QListWidget()
        self.sources_list.setFont(QFont("Consolas", 10))
        sources_layout.addWidget(self.sources_list)
        right_layout.addWidget(sources_frame)

        # Changements récents
        changes_frame, changes_layout = self._create_section_frame("CHANGEMENTS RÉCENTS")
        self.recent_changes_list = QListWidget()
        self.recent_changes_list.setFont(QFont("Consolas", 10))
        changes_layout.addWidget(self.recent_changes_list)
        right_layout.addWidget(changes_frame)

        # Résumé scan
        scan_frame, scan_layout = self._create_section_frame("RÉSUMÉ DU SCAN")
        self.scan_summary_label = QLabel("Aucun scan effectué.")
        self.scan_summary_label.setObjectName("mutedLabel")
        self.scan_summary_label.setWordWrap(True)

        self.files_list = QListWidget()
        self.files_list.setFont(QFont("Consolas", 10))

        scan_layout.addWidget(self.scan_summary_label)
        scan_layout.addWidget(self.files_list)
        right_layout.addWidget(scan_frame, stretch=1)

        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setSizes([360, 760, 520])

        root_layout.addWidget(self.main_splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt. Bridge Unity actif sur le port 8765.")

        self.populate_pages_tree()

    # ============================================================
    # SIGNALS / EVENTS
    # ============================================================

    def setup_connections(self):
        self.btn_scan.clicked.connect(self.scan_project)
        self.btn_monitor.toggled.connect(self.toggle_monitoring)
        self.btn_send.clicked.connect(self.send_question)
        self.btn_clear_input.clicked.connect(self.clear_input_only)
        self.btn_config.clicked.connect(self.show_config_dialog)
        self.btn_new_chat.clicked.connect(self.create_new_conversation)

        self.btn_new_page.clicked.connect(self.on_new_page_clicked)
        self.btn_new_doc.clicked.connect(self.on_new_document_clicked)

        self.answer_received.connect(self.on_answer_received)
        self.file_changed_signal.connect(self.on_file_changed)
        self.unity_state_signal.connect(self.on_unity_state_changed)

        self.conversations_list.itemClicked.connect(self.on_conversation_selected)
        self.question_input.installEventFilter(self)

        self.pages_tree.itemClicked.connect(self.on_page_selected)
        self.page_editor.textChanged.connect(self.on_page_content_changed)
        self.pages_tree.itemChanged.connect(self.on_item_renamed)

    def on_page_selected(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if not data:
            return

        # Si document → ne rien faire
        if data["type"] == "document":
            return

        if data["type"] == "page":
            document_id = data["document_id"]
            page_id = data["page_id"]

            page = self.pages_manager.get_page(document_id, page_id)

            if not page:
                return

            # Mode édition activé
            self.is_editing_page = True
            self.current_document_id = document_id
            self.current_page_id = page_id

            # UI
            self.chat_frame.setVisible(False)
            self.page_frame.setVisible(True)

            self.page_title_label.setText(page["title"])
            self.page_editor.setPlainText(page.get("content", ""))  

    def on_page_content_changed(self):
        if not self.is_editing_page:
            return

        content = self.page_editor.toPlainText()

        self.pages_manager.update_page_content(
            self.current_document_id,
            self.current_page_id,
            content
        ) 

    def on_item_renamed(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if not data:
            return

        new_title = item.text(0).strip()

        if not new_title:
            return

        if data["type"] == "document":
            self.pages_manager.rename_document(
                data["document_id"],
                new_title
            )

        elif data["type"] == "page":
            self.pages_manager.rename_page(
                data["document_id"],
                data["page_id"],
                new_title
            )

            # Si la page renommée est actuellement ouverte dans l'éditeur,
            # on met aussi à jour le titre affiché au centre.
            if self.current_page_id == data["page_id"]:
                self.page_title_label.setText(new_title)

        self.populate_pages_tree()             

    # ============================================================
    # LEFT PANEL / PLACEHOLDERS
    # ============================================================

    def populate_pages_tree(self):
        self.pages_tree.clear()

        documents = self.pages_manager.list_documents()

        for document in documents:
            doc_item = QTreeWidgetItem([document["title"]])
            doc_item.setFlags(doc_item.flags() | Qt.ItemFlag.ItemIsEditable)
            doc_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "document",
                "document_id": document["id"]
            })

            for page in document.get("pages", []):
                page_item = QTreeWidgetItem([page["title"]])
                page_item.setFlags(page_item.flags() | Qt.ItemFlag.ItemIsEditable)
                page_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "page",
                    "document_id": document["id"],
                    "page_id": page["id"]
                })
                doc_item.addChild(page_item)

            self.pages_tree.addTopLevelItem(doc_item)

        self.pages_tree.expandAll()

    def on_new_page_clicked(self):
        item = self.pages_tree.currentItem()

        if not item:
            QMessageBox.warning(self, "Erreur", "Sélectionne un document.")
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)

        if not data:
            QMessageBox.warning(self, "Erreur", "Sélection invalide.")
            return

        if data["type"] == "document":
            document_id = data["document_id"]
        elif data["type"] == "page":
            document_id = data["document_id"]
        else:
            QMessageBox.warning(self, "Erreur", "Sélection invalide.")
            return

        self.pages_manager.add_page(document_id, "Nouvelle page")
        self.populate_pages_tree()

    def on_new_document_clicked(self):
        self.pages_manager.create_document("Nouveau document")
        self.populate_pages_tree()

    # ============================================================
    # REFRESH UI
    # ============================================================

    def refresh_project_info_ui(self):
        project_name = self.project_context.get_project_name() or "-"
        project_path = self.project_context.get_project_path() or "-"

        self.project_name_label.setText(f"Projet : {project_name}")
        self.project_path_label.setText(f"Chemin : {project_path}")
        self.chat_project_label.setText(f"Projet courant : {project_name}")

    def refresh_chat_display(self):
        messages = self.conversation_manager.get_current_messages()

        if not messages:
            self.response_area.setPlainText(
                "B.O.B est prêt.\n\nPose une question sur ton projet pour commencer."
            )
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

    def refresh_scan_summary_ui(self):
        summary = self.project_context.scan_summary or {}
        total_files = summary.get("total_files", 0)
        total_kb = summary.get("total_kb", 0.0)
        by_type = summary.get("by_type", {})

        self.scan_summary_label.setText(
            f"{total_files} fichiers détectés | {total_kb} KB\n"
            f"- Scripts C# : {by_type.get('scripts_cs', 0)}\n"
            f"- Scènes : {by_type.get('scenes', 0)}\n"
            f"- Prefabs : {by_type.get('prefabs', 0)}\n"
            f"- Assets texte / asmdef : {by_type.get('assets', 0)}"
        )

        self.files_list.clear()
        for filepath in summary.get("key_files", []):
            self.files_list.addItem(QListWidgetItem(filepath))

    def refresh_recent_changes_ui(self):
        self.recent_changes_list.clear()

        if not self.project_context.recent_changes:
            self.recent_changes_list.addItem("Aucun changement récent.")
            return

        for change in self.project_context.recent_changes[:10]:
            self.recent_changes_list.addItem(
                f"{change['action']} : {change['path']}"
            )

    def refresh_sources_ui(self, sources_used=None):
        self.sources_list.clear()

        if not sources_used:
            self.sources_list.addItem("Scan projet : en attente")
            self.sources_list.addItem("Unity runtime : en attente")
            self.sources_list.addItem("Changements récents : en attente")
            self.sources_list.addItem("Fichiers injectés : en attente")
            return

        mapping = [
            ("project_context", "Contexte projet"),
            ("scan_summary", "Résumé du scan"),
            ("unity_runtime", "Unity runtime"),
            ("recent_changes", "Changements récents"),
            ("file_excerpts", "Extraits de fichiers"),
        ]

        for key, label in mapping:
            enabled = sources_used.get(key, False)
            prefix = "✔" if enabled else "✖"
            self.sources_list.addItem(f"{prefix} {label}")

    def refresh_context_panel(self, context_package=None):
        lines = [
            f"Projet : {self.project_context.get_project_name()}",
            f"Type : {self.project_context.project_type}",
            f"Chemin : {self.project_context.get_project_path()}",
            "",
            f"Unity connecté : {'Oui' if self.project_context.unity_connected else 'Non'}",
            f"Scène active : {self.project_context.active_scene or '-'}",
            f"Objet sélectionné : {self.project_context.selected_object or '-'}",
            f"Mode : {self.project_context.play_mode or '-'}",
        ]

        if context_package:
            files_used = context_package.get("files_used", [])
            if files_used:
                lines.append("")
                lines.append("Fichiers utilisés :")
                for filepath in files_used:
                    lines.append(f"- {filepath}")

        self.context_summary.setPlainText("\n".join(lines))
        self.refresh_sources_ui(
            context_package.get("sources_used", {}) if context_package else None
        )

    def refresh_right_panel(self, context_package=None):
        self.refresh_project_info_ui()
        self.refresh_scan_summary_ui()
        self.refresh_recent_changes_ui()
        self.refresh_context_panel(context_package)

    # ============================================================
    # CONVERSATIONS
    # ============================================================

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
            item = QListWidgetItem(f"{title}\n{updated}")
            item.setData(Qt.ItemDataRole.UserRole, conv["id"])
            self.conversations_list.addItem(item)

    def create_new_conversation(self):
        self.conversation_manager.create_new_conversation()
        self.load_conversations_list()
        self.refresh_chat_display()
        self.status_bar.showMessage("Nouvelle conversation créée")

    def on_conversation_selected(self, item: QListWidgetItem):
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        self.conversation_manager.load_conversation(conversation_id)

        # RETOUR MODE CHAT
        self.is_editing_page = False
        self.chat_frame.setVisible(True)
        self.page_frame.setVisible(False)

        self.refresh_chat_display()
        self.status_bar.showMessage("Conversation chargée")

    # ============================================================
    # PROJECT / SCAN / WATCHER
    # ============================================================

    def scan_project(self):
        self.status_bar.showMessage("Scan en cours...")
        file_count = self.scanner.scan_all()

        total_size = sum(len(c) for c in self.scanner.file_contents.values()) / 1024
        self.project_status.setText(
            f"Statut : {file_count} fichiers | {total_size:.1f} KB | Contexte prêt"
        )

        self.refresh_right_panel()

        if self.ai_connector.test_connection():
            self.status_bar.showMessage("Connecté à LM Studio - Prêt")
            self.chat_state_label.setText("Projet scanné. B.O.B est prêt.")
        else:
            QMessageBox.warning(
                self,
                "Attention",
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
            self.btn_monitor.setText("Surveillance ON")
            self.status_bar.showMessage("Surveillance active")
        else:
            self.scanner.stop_monitoring()
            self.btn_monitor.setText("Surveillance")
            self.status_bar.showMessage("Surveillance arrêtée")

    def on_file_changed(self, filepath: str, action: str):
        if action == "modified":
            self.project_status.setText(f"Statut : {filepath} modifié")
        elif action == "added":
            self.project_status.setText(f"Statut : {filepath} ajouté")
        elif action == "removed":
            self.project_status.setText(f"Statut : {filepath} supprimé")

        self.refresh_right_panel()

    # ============================================================
    # UNITY BRIDGE
    # ============================================================

    def on_unity_state_changed(self, state: dict):
        self.project_context.update_from_unity_state(state)
        self.refresh_project_info_ui()

        if state.get("is_connected", False):
            self.unity_connection_label.setText("Unity : Connecté")
            self.unity_connection_label.setStyleSheet("color: #7CFC98; font-weight: bold;")
        else:
            self.unity_connection_label.setText("Unity : Déconnecté")
            self.unity_connection_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")

        self.unity_project_label.setText(
            f"Projet Unity connecté : {state.get('project_name', '-')}"
        )
        self.unity_scene_label.setText(
            f"Scène active : {state.get('active_scene', '-')}"
        )
        self.unity_selection_label.setText(
            f"Sélection : {state.get('selected_object', '-')}"
        )
        self.unity_mode_label.setText(
            f"Mode : {state.get('play_mode', '-')}"
        )

        self.refresh_right_panel()

    # ============================================================
    # CHAT / AI
    # ============================================================

    def send_question(self):
        question = self.question_input.toPlainText().strip()

        if not question:
            QMessageBox.warning(self, "Attention", "Veuillez entrer une question.")
            return

        if not self.scanner.file_contents:
            QMessageBox.warning(
                self,
                "Attention",
                "Aucun projet scanné.\n\nCliquez sur 'Scanner' d'abord."
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
        self.chat_state_label.setText("Analyse du contexte en cours...")

        context_package = self.context_engine.build_context_package(
            max_total_chars=self.config.get("max_context_tokens", 35000)
        )

        self.refresh_right_panel(context_package)

        project_context = context_package["combined_context"]

        history = self.conversation_manager.get_model_messages(
            max_messages=self.config.get("max_history_messages_for_model", 4),
            exclude_last_user=True,
            max_chars_per_message=self.config.get("max_history_chars_per_message", 1500)
        )

        files_used = context_package.get("files_used", [])
        if files_used:
            self.status_bar.showMessage(
                f"Contexte prêt | {len(files_used)} fichiers clés utilisés"
            )
        else:
            self.status_bar.showMessage("Contexte prêt")

        def ask_ai():
            try:
                answer = self.ai_connector.send_with_context(
                    question=question,
                    project_context=project_context,
                    conversation_history=history
                )
                self.answer_received.emit(answer)
            except Exception as e:
                error_msg = f"Erreur : {str(e)}\n\nVérifiez la connexion LM Studio."
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
        self.chat_state_label.setText("Réponse reçue. B.O.B est prêt.")

        self.status_bar.showMessage("Réponse reçue")

    def clear_input_only(self):
        self.question_input.clear()
        self.question_input.setFocus()

    # ============================================================
    # CONFIG
    # ============================================================

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
            self.context_engine = ContextEngine(
                project_context=self.project_context,
                scanner=self.scanner
            )

            self.files_list.clear()
            self.project_status.setText("Statut : nouveau projet sélectionné - scan requis")

            self.btn_monitor.setChecked(False)
            self.btn_monitor.setText("Surveillance")

            self.refresh_right_panel()

            QMessageBox.information(
                self,
                "Configuration",
                f"Projet mis à jour :\n{new_path}\n\nLe scanner a été rechargé."
            )

    # ============================================================
    # EVENTS
    # ============================================================

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
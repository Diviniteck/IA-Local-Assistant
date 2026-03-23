import os
import json
import time
from typing import Dict, List, Optional


class ProjectContext:
    """
    Source unique de vérité du projet courant.
    Priorité du nom projet :
    1. Bridge Unity si connecté
    2. Nom du dossier sélectionné
    3. Fallback config
    """

    def __init__(self, config_path: str = "config.json"):
        self.config_path = os.path.abspath(config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        initial_path = self.config.get("unity_project_path", "")
        self.project_path = os.path.abspath(initial_path) if initial_path else ""
        self.project_type = "unity"

        self.selected_project_name = self._extract_folder_name(self.project_path)
        self.fallback_project_name = self.config.get("project_name", "Projet Unity")

        self.unity_connected = False
        self.unity_project_name = ""
        self.unity_version = ""
        self.active_scene = ""
        self.selected_object = ""
        self.play_mode = ""

        self.scan_summary: Dict = {
            "total_files": 0,
            "total_kb": 0.0,
            "by_type": {},
            "key_files": [],
        }

        self.recent_changes: List[Dict] = []

    # ============================================================
    # INTERNAL
    # ============================================================

    def _extract_folder_name(self, path: str) -> str:
        if not path:
            return ""
        normalized = os.path.normpath(path)
        return os.path.basename(normalized)

    # ============================================================
    # PROJECT IDENTITY
    # ============================================================

    def set_project_path(self, new_path: str):
        self.project_path = os.path.abspath(new_path)
        self.selected_project_name = self._extract_folder_name(self.project_path)

    def get_project_path(self) -> str:
        return self.project_path

    def get_project_name(self) -> str:
        if self.unity_connected and self.unity_project_name.strip():
            return self.unity_project_name.strip()

        if self.selected_project_name.strip():
            return self.selected_project_name.strip()

        return self.fallback_project_name

    # ============================================================
    # UNITY STATE
    # ============================================================

    def update_from_unity_state(self, state: Dict):
        self.unity_connected = state.get("is_connected", False)
        self.unity_project_name = state.get("project_name", "") or ""
        self.unity_version = state.get("unity_version", "") or ""
        self.active_scene = state.get("active_scene", "") or ""
        self.selected_object = state.get("selected_object", "") or ""
        self.play_mode = state.get("play_mode", "") or ""

    def get_unity_state_dict(self) -> Dict:
        return {
            "is_connected": self.unity_connected,
            "project_name": self.unity_project_name,
            "unity_version": self.unity_version,
            "active_scene": self.active_scene,
            "selected_object": self.selected_object,
            "play_mode": self.play_mode,
        }

    # ============================================================
    # SCAN / FILE CHANGES
    # ============================================================

    def update_scan_summary(self, summary: Dict):
        self.scan_summary = summary or {}

    def add_recent_change(self, filepath: str, action: str, max_items: int = 30):
        self.recent_changes.insert(0, {
            "path": filepath,
            "action": action,
            "timestamp": time.time(),
        })
        self.recent_changes = self.recent_changes[:max_items]

    # ============================================================
    # PROMPT HELPERS
    # ============================================================

    def build_runtime_context_block(self) -> str:
        lines = [
            "CONTEXTE PROJET ACTUEL",
            f"- Nom du projet : {self.get_project_name()}",
            f"- Type : {self.project_type}",
            f"- Chemin : {self.get_project_path()}",
        ]

        if self.unity_connected:
            lines.extend([
                "- Unity : connecté",
                f"- Scène active : {self.active_scene or '-'}",
                f"- Objet sélectionné : {self.selected_object or '-'}",
                f"- Mode : {self.play_mode or '-'}",
            ])
        else:
            lines.append("- Unity : déconnecté")

        if self.recent_changes:
            lines.append("- Changements récents :")
            for change in self.recent_changes[:5]:
                lines.append(f"  • {change['action']} : {change['path']}")

        return "\n".join(lines)
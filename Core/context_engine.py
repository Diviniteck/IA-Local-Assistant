import os
from typing import Dict, List, Optional

from Core.project_context import ProjectContext
from Core.project_scanner import UnityProjectScanner


class ContextEngine:
    """
    Construit un contexte propre pour B.O.B à partir :
    - du ProjectContext
    - du scanner
    - de l'historique
    - des données Unity runtime
    """

    def __init__(self, project_context: ProjectContext, scanner: UnityProjectScanner):
        self.project_context = project_context
        self.scanner = scanner

    # ============================================================
    # OUTILS INTERNES
    # ============================================================

    def _truncate(self, text: str, max_len: int) -> str:
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n...[TRONQUÉ]..."

    def _safe_get_file(self, rel_path: str) -> str:
        return self.scanner.file_contents.get(rel_path, "")

    def _get_ranked_files(self) -> List[str]:
        return sorted(
            self.scanner.file_contents.keys(),
            key=lambda f: (-self.scanner.get_file_priority(f), f.lower())
        )

    def _split_ranked_files(self):
        ranked = self._get_ranked_files()

        scripts = [f for f in ranked if f.endswith(".cs")]
        scenes = [f for f in ranked if f.endswith(".unity")]
        prefabs = [f for f in ranked if f.endswith(".prefab")]
        assets = [f for f in ranked if f.endswith(".asset") or f.endswith(".asmdef")]

        priority_scripts = [f for f in scripts if not self.scanner.is_third_party_file(f)]
        third_party_scripts = [f for f in scripts if self.scanner.is_third_party_file(f)]

        priority_scenes = scenes
        priority_prefabs = [f for f in prefabs if not self.scanner.is_third_party_file(f)]
        important_assets = [f for f in assets if not self.scanner.is_third_party_file(f)]

        return {
            "scripts": scripts,
            "scenes": scenes,
            "prefabs": prefabs,
            "assets": assets,
            "priority_scripts": priority_scripts,
            "third_party_scripts": third_party_scripts,
            "priority_scenes": priority_scenes,
            "priority_prefabs": priority_prefabs,
            "important_assets": important_assets,
        }

    # ============================================================
    # BLOCS DE CONTEXTE
    # ============================================================

    def build_project_block(self) -> str:
        summary = self.project_context.scan_summary or {}

        total_files = summary.get("total_files", 0)
        total_kb = summary.get("total_kb", 0.0)
        by_type = summary.get("by_type", {})
        key_files = summary.get("key_files", [])

        lines = [
            "CONTEXTE PROJET ACTUEL",
            "============================================================",
            f"Nom du projet : {self.project_context.get_project_name()}",
            f"Type : {self.project_context.project_type}",
            f"Chemin : {self.project_context.get_project_path()}",
            "",
            "ÉTAT GLOBAL",
            f"- Unity connecté : {'Oui' if self.project_context.unity_connected else 'Non'}",
            f"- Fichiers détectés : {total_files}",
            f"- Taille scannée : {total_kb} KB",
            f"- Scripts C# : {by_type.get('scripts_cs', 0)}",
            f"- Scènes : {by_type.get('scenes', 0)}",
            f"- Prefabs : {by_type.get('prefabs', 0)}",
            f"- Assets texte / asmdef : {by_type.get('assets', 0)}",
        ]

        if key_files:
            lines.append("")
            lines.append("FICHIERS CLÉS DÉTECTÉS")
            for filepath in key_files[:8]:
                lines.append(f"- {filepath}")

        return "\n".join(lines)

    def build_unity_block(self) -> str:
        if not self.project_context.unity_connected:
            return "CONTEXTE UNITY\n============================================================\nUnity : déconnecté"

        lines = [
            "CONTEXTE UNITY",
            "============================================================",
            f"Projet Unity connecté : {self.project_context.unity_project_name or '-'}",
            f"Version Unity : {self.project_context.unity_version or '-'}",
            f"Scène active : {self.project_context.active_scene or '-'}",
            f"Objet sélectionné : {self.project_context.selected_object or '-'}",
            f"Mode : {self.project_context.play_mode or '-'}",
        ]
        return "\n".join(lines)

    def build_recent_changes_block(self, max_changes: int = 5) -> str:
        if not self.project_context.recent_changes:
            return ""

        lines = [
            "CHANGEMENTS RÉCENTS",
            "============================================================",
        ]

        for change in self.project_context.recent_changes[:max_changes]:
            lines.append(f"- {change['action']} : {change['path']}")

        return "\n".join(lines)

    def build_file_excerpt_block(
        self,
        max_scripts: int = 8,
        max_scenes: int = 3,
        max_prefabs: int = 4,
        max_assets: int = 4,
        script_chars: int = 2200,
        scene_chars: int = 1200,
        prefab_chars: int = 700,
        asset_chars: int = 600,
    ) -> str:
        buckets = self._split_ranked_files()
        parts: List[str] = []

        if buckets["priority_scenes"]:
            parts.append("SCÈNES PRINCIPALES")
            parts.append("------------------------------------------------------------")
            for filepath in buckets["priority_scenes"][:max_scenes]:
                content = self._safe_get_file(filepath)
                parts.append(f"\n[{filepath}]\n{self._truncate(content, scene_chars)}\n")

        if buckets["priority_scripts"]:
            parts.append("SCRIPTS PRINCIPAUX")
            parts.append("------------------------------------------------------------")
            for filepath in buckets["priority_scripts"][:max_scripts]:
                content = self._safe_get_file(filepath)
                parts.append(f"\n[{filepath}]\n{self._truncate(content, script_chars)}\n")

        if buckets["priority_prefabs"]:
            parts.append("PREFABS PRINCIPAUX")
            parts.append("------------------------------------------------------------")
            for filepath in buckets["priority_prefabs"][:max_prefabs]:
                content = self._safe_get_file(filepath)
                parts.append(f"\n[{filepath}]\n{self._truncate(content, prefab_chars)}\n")

        if buckets["important_assets"]:
            parts.append("ASSETS TEXTE IMPORTANTS")
            parts.append("------------------------------------------------------------")
            for filepath in buckets["important_assets"][:max_assets]:
                content = self._safe_get_file(filepath)
                parts.append(f"\n[{filepath}]\n{self._truncate(content, asset_chars)}\n")

        return "\n".join(parts).strip()

    def build_context_package(self, max_total_chars: int = 35000) -> Dict[str, object]:
        project_block = self.build_project_block()
        unity_block = self.build_unity_block()
        changes_block = self.build_recent_changes_block()
        file_excerpt_block = self.build_file_excerpt_block()

        blocks = [project_block, unity_block]
        if changes_block:
            blocks.append(changes_block)
        if file_excerpt_block:
            blocks.append(file_excerpt_block)

        combined = "\n\n".join(block for block in blocks if block).strip()
        combined = combined[:max_total_chars]

        sources_used = {
            "project_context": True,
            "scan_summary": True,
            "unity_runtime": self.project_context.unity_connected,
            "recent_changes": bool(self.project_context.recent_changes),
            "file_excerpts": bool(file_excerpt_block),
        }

        files_used = self.project_context.scan_summary.get("key_files", [])[:8]

        return {
            "combined_context": combined,
            "files_used": files_used,
            "sources_used": sources_used,
        }
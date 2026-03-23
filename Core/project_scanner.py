import os
import json
from typing import Dict, Optional, List, Tuple

from Core.project_context import ProjectContext
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class UnityFileHandler(FileSystemEventHandler):
    """Surveille les modifications de fichiers dans le projet"""

    def __init__(self, scanner: "UnityProjectScanner"):
        self.scanner = scanner

    def _is_unity_file(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        watch_extensions = self.scanner.config.get(
            "watch_extensions",
            [".cs", ".prefab", ".unity", ".asset", ".asmdef"]
        )
        return ext in watch_extensions

    def on_modified(self, event):
        if not event.is_directory and self._is_unity_file(event.src_path):
            print(f"📝 Fichier modifié : {event.src_path}")
            self.scanner.update_file(event.src_path)

    def on_created(self, event):
        if not event.is_directory and self._is_unity_file(event.src_path):
            print(f"➕ Fichier créé : {event.src_path}")
            self.scanner.add_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and self._is_unity_file(event.src_path):
            print(f"🗑️ Fichier supprimé : {event.src_path}")
            self.scanner.remove_file(event.src_path)


class UnityProjectScanner:
    """Lit et surveille le projet Unity"""

    def __init__(self, config_path="config.json", project_context: Optional[ProjectContext] = None):
        self.config_path = os.path.abspath(config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.project_context = project_context or ProjectContext(self.config_path)

        self.file_contents: Dict[str, str] = {}
        self.observer: Optional[Observer] = None
        self.callbacks = []

    @property
    def project_path(self) -> str:
        return self.project_context.get_project_path()

    @property
    def project_name(self) -> str:
        return self.project_context.get_project_name()

    # ============================================================
    # OUTILS INTERNES
    # ============================================================

    def _normalize_rel_path(self, rel_path: str) -> str:
        return rel_path.replace("\\", "/")

    def _starts_with_any(self, rel_path: str, prefixes: List[str]) -> bool:
        rel_path = self._normalize_rel_path(rel_path).lower()
        normalized_prefixes = [p.replace("\\", "/").lower().rstrip("/") for p in prefixes]
        return any(rel_path.startswith(prefix + "/") or rel_path == prefix for prefix in normalized_prefixes)

    def _contains_any_keyword(self, rel_path: str, keywords: List[str]) -> bool:
        rel_path_lower = self._normalize_rel_path(rel_path).lower()
        return any(keyword.lower() in rel_path_lower for keyword in keywords)

    def is_third_party_file(self, rel_path: str) -> bool:
        rel_path = self._normalize_rel_path(rel_path)
        third_party_folders = self.config.get("third_party_folders", [])
        third_party_keywords = self.config.get("third_party_keywords", [])
        return (
            self._starts_with_any(rel_path, third_party_folders)
            or self._contains_any_keyword(rel_path, third_party_keywords)
        )

    def is_priority_file(self, rel_path: str) -> bool:
        rel_path = self._normalize_rel_path(rel_path)
        priority_folders = self.config.get("project_priority_folders", [])
        return self._starts_with_any(rel_path, priority_folders)

    def get_file_priority(self, rel_path: str) -> int:
        """
        Score simple :
        100 = fichiers du projet prioritaire
        70 = scènes
        60 = prefabs
        20 = tiers
        40 = neutre
        """
        rel_path = self._normalize_rel_path(rel_path)

        if self.is_priority_file(rel_path):
            return 100
        if rel_path.endswith(".unity"):
            return 70
        if rel_path.endswith(".prefab"):
            return 60
        if self.is_third_party_file(rel_path):
            return 20
        return 40

    # ============================================================
    # SCAN
    # ============================================================

    def scan_all(self) -> int:
        """Lit tous les fichiers du projet Unity"""
        print(f"🔍 Scan de : {self.project_path}")
        total_files = 0
        self.file_contents.clear()

        watch_extensions = self.config.get(
            "watch_extensions",
            [".cs", ".prefab", ".unity", ".asset", ".asmdef"]
        )

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.config["ignore_folders"]]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in watch_extensions:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, self.project_path)
                    rel_path = self._normalize_rel_path(rel_path)

                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            self.file_contents[rel_path] = f.read()
                            total_files += 1
                    except Exception as e:
                        print(f"⚠️ Erreur lecture {file}: {e}")

        print(f"✅ Scan terminé : {total_files} fichiers")
        self.get_scan_summary()
        return total_files

    def update_file(self, filepath: str):
        rel_path = os.path.relpath(filepath, self.project_path)
        rel_path = self._normalize_rel_path(rel_path)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self.file_contents[rel_path] = f.read()

            self.project_context.add_recent_change(rel_path, "modified")

            for callback in self.callbacks:
                callback(rel_path, "modified")

        except Exception as e:
            print(f"⚠️ Erreur update {filepath}: {e}")

    def add_file(self, filepath: str):
        rel_path = os.path.relpath(filepath, self.project_path)
        rel_path = self._normalize_rel_path(rel_path)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self.file_contents[rel_path] = f.read()

            self.project_context.add_recent_change(rel_path, "added")

            for callback in self.callbacks:
                callback(rel_path, "added")

        except Exception as e:
            print(f"⚠️ Erreur ajout {filepath}: {e}")

    def remove_file(self, filepath: str):
        rel_path = os.path.relpath(filepath, self.project_path)
        rel_path = self._normalize_rel_path(rel_path)

        if rel_path in self.file_contents:
            del self.file_contents[rel_path]

        self.project_context.add_recent_change(rel_path, "removed")

        for callback in self.callbacks:
            callback(rel_path, "removed")

    # ============================================================
    # RÉSUMÉS / ACCÈS DONNÉES
    # ============================================================

    def _split_files(self) -> Tuple[List[str], List[str], List[str], List[str]]:
        all_files = list(self.file_contents.keys())

        cs_files = [f for f in all_files if f.endswith(".cs")]
        prefab_files = [f for f in all_files if f.endswith(".prefab")]
        unity_files = [f for f in all_files if f.endswith(".unity")]
        asset_files = [f for f in all_files if f.endswith(".asset") or f.endswith(".asmdef")]

        return cs_files, prefab_files, unity_files, asset_files

    def get_scan_summary(self) -> Dict:
        cs_files, prefab_files, unity_files, asset_files = self._split_files()
        total_size_kb = sum(len(c) for c in self.file_contents.values()) / 1024

        key_files = sorted(
            self.file_contents.keys(),
            key=lambda f: (-self.get_file_priority(f), f.lower())
        )[:10]

        summary = {
            "total_files": len(self.file_contents),
            "total_kb": round(total_size_kb, 1),
            "by_type": {
                "scripts_cs": len(cs_files),
                "prefabs": len(prefab_files),
                "scenes": len(unity_files),
                "assets": len(asset_files),
            },
            "key_files": key_files,
        }

        self.project_context.update_scan_summary(summary)
        return summary

    def get_ranked_files(self) -> List[str]:
        return sorted(
            self.file_contents.keys(),
            key=lambda f: (-self.get_file_priority(f), f.lower())
        )

    def get_file_content(self, rel_path: str) -> str:
        return self.file_contents.get(rel_path, "")

    def get_context_string(self, max_chars: int = 35000) -> str:
        """
        Compatibilité temporaire.
        Le vrai contexte doit maintenant être construit par ContextEngine.
        """
        summary = self.get_scan_summary()

        lines = [
            "CONTEXTE SCANNER (MODE COMPATIBILITÉ)",
            "============================================================",
            f"Nom du projet : {self.project_name}",
            f"Fichiers détectés : {summary.get('total_files', 0)}",
            f"Taille : {summary.get('total_kb', 0.0)} KB",
            "",
            "Fichiers clés :",
        ]

        for filepath in summary.get("key_files", [])[:8]:
            lines.append(f"- {filepath}")

        return "\n".join(lines)[:max_chars]

    # ============================================================
    # MONITORING
    # ============================================================

    def start_monitoring(self, callback=None):
        if callback and callback not in self.callbacks:
            self.callbacks.append(callback)

        if self.observer is not None:
            return

        event_handler = UnityFileHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.project_path, recursive=True)
        self.observer.start()
        print("👁️ Surveillance active...")

    def stop_monitoring(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            print("⏹️ Surveillance arrêtée")
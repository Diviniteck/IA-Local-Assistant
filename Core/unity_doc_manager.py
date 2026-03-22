import os
import json
import re
from typing import List, Dict, Any


class UnityDocManager:
    """Gère la documentation Unity locale versionnée."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = os.path.abspath(config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.app_root = os.path.dirname(self.config_path)
        self.docs_root = os.path.join(
            self.app_root,
            self.config.get("unity_docs_root", "Data/unity_docs")
        )
        self.active_version = self.config.get("unity_doc_version", "2022.3.62f2")

    def get_active_doc_folder(self) -> str:
        return os.path.join(self.docs_root, self.active_version)

    def get_metadata_path(self) -> str:
        return os.path.join(self.get_active_doc_folder(), "metadata.json")

    def get_index_path(self) -> str:
        return os.path.join(self.get_active_doc_folder(), "search_index.json")

    def get_raw_docs_folder(self) -> str:
        metadata = self.load_metadata()
        raw_rel = metadata.get("raw_docs_folder", "raw/Documentation/en")
        return os.path.join(self.get_active_doc_folder(), raw_rel)

    def has_active_docs(self) -> bool:
        return os.path.exists(self.get_metadata_path()) and os.path.exists(self.get_index_path())

    def load_metadata(self) -> Dict[str, Any]:
        path = self.get_metadata_path()
        if not os.path.exists(path):
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_index(self) -> List[Dict[str, Any]]:
        path = self.get_index_path()
        if not os.path.exists(path):
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        return data.get("entries", [])

    def _tokenize(self, text: str) -> List[str]:
        text = (text or "").lower()
        return re.findall(r"[a-zA-Z0-9_\.]+", text)

    def _extract_exact_symbols(self, text: str) -> List[str]:
        """
        Extrait les symboles/API exacts susceptibles d'être des noms Unity :
        - OnDrawGizmos
        - SerializedProperty
        - CharacterController.Move
        - EditorWindow
        """
        symbols = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b", text or "")

        filtered = []
        for s in symbols:
            if len(s) < 3:
                continue

            if any(c.isupper() for c in s) or "." in s:
                filtered.append(s)

        seen = set()
        result = []
        for s in filtered:
            low = s.lower()
            if low not in seen:
                seen.add(low)
                result.append(s)

        return result[:12]

    def _is_api_like_question(self, question: str, exact_symbols: List[str]) -> bool:
        q = (question or "").lower()

        api_markers = [
            "c'est quoi",
            "ca veut dire quoi",
            "que fait",
            "what is",
            "what does",
            "comment fonctionne",
            "callback",
            "event function",
            "api",
            "method",
            "class",
            "attribute",
            "property",
            "ondrawgizmos",
            "ondrawgizmosselected",
            "awake",
            "start",
            "update",
            "fixedupdate",
            "lateupdate",
            "onenable",
            "ondisable",
            "onvalidate",
            "monobehaviour",
            "scriptableobject",
            "editorwindow",
            "customeditor",
            "serializefield",
            "serializedproperty"
        ]

        if any(marker in q for marker in api_markers):
            return True

        if any("." in s or any(c.isupper() for c in s[1:]) for s in exact_symbols):
            return True

        return False

    def _score_entry(self, query_tokens: List[str], exact_symbols: List[str], entry: Dict[str, Any]) -> int:
        exact_boost = self.config.get("unity_doc_exact_match_boost", 80)
        title_boost = self.config.get("unity_doc_title_match_boost", 24)
        keyword_boost = self.config.get("unity_doc_keyword_match_boost", 12)
        category_boost = self.config.get("unity_doc_category_match_boost", 8)
        content_boost = self.config.get("unity_doc_content_match_boost", 2)

        score = 0

        title = entry.get("title", "")
        category = entry.get("category", "")
        keywords = entry.get("keywords", [])
        path = entry.get("path", "")
        content = entry.get("content", "")

        title_lower = title.lower()
        category_lower = category.lower()
        path_lower = path.lower()
        keywords_lower = [kw.lower() for kw in keywords]
        haystack = f"{title} {category} {' '.join(keywords)} {path} {content}".lower()

        # 1) énorme boost si symbole exact détecté
        for symbol in exact_symbols:
            symbol_lower = symbol.lower()

            if title_lower == symbol_lower:
                score += exact_boost + 60

            if symbol_lower in title_lower:
                score += exact_boost + 20

            if symbol_lower in path_lower:
                score += exact_boost

            if symbol_lower in keywords_lower:
                score += exact_boost - 20

            if symbol_lower in haystack:
                score += 10

        # 2) score token classique
        for token in query_tokens:
            if not token:
                continue

            if token == title_lower:
                score += title_boost + 10

            if token in title_lower:
                score += title_boost

            if token in category_lower:
                score += category_boost

            if token in keywords_lower:
                score += keyword_boost

            if token in haystack:
                score += content_boost

        # 3) boost Scripting API pour les questions API
        api_like = self._is_api_like_question(" ".join(query_tokens + exact_symbols), exact_symbols)
        if api_like and category == "Scripting API":
            score += 35

        # 4) bonus si le chemin ressemble à une page API directe
        if "/scriptreference/" in path_lower or "scriptreference" in path_lower:
            score += 20

        # 5) malus pour pages trop génériques
        generic_titles = {"unity", "introduction", "overview", "manual", "welcome"}
        if title_lower in generic_titles:
            score -= 20

        # 6) léger malus pour entrées trop pauvres
        if len(content.strip()) < 80:
            score -= 5

        return score

    def search(self, question: str, max_results: int = None) -> List[Dict[str, Any]]:
        entries = self.load_index()
        if not entries:
            return []

        query_tokens = self._tokenize(question)
        exact_symbols = self._extract_exact_symbols(question)

        if max_results is None:
            if self._is_api_like_question(question, exact_symbols):
                max_results = 3
            else:
                max_results = self.config.get("unity_doc_max_results", 6)

        ranked = []
        for entry in entries:
            score = self._score_entry(query_tokens, exact_symbols, entry)
            if score > 0:
                entry_copy = dict(entry)
                entry_copy["_score"] = score
                ranked.append(entry_copy)

        ranked.sort(key=lambda x: x["_score"], reverse=True)

        # dédoublonnage léger par titre
        results = []
        seen_titles = set()

        for entry in ranked:
            title_lower = entry.get("title", "").lower()
            if title_lower in seen_titles:
                continue

            seen_titles.add(title_lower)
            results.append(entry)

            if len(results) >= max_results:
                break

        return results

    def _smart_excerpt(self, content: str, question: str, max_chars: int) -> str:
        """
        Essaie de centrer l'extrait autour d'un token pertinent de la question.
        """
        content = content or ""
        if len(content) <= max_chars:
            return content

        query_tokens = self._tokenize(question)
        content_lower = content.lower()

        best_pos = -1
        for token in query_tokens:
            pos = content_lower.find(token.lower())
            if pos != -1:
                best_pos = pos
                break

        if best_pos == -1:
            return content[:max_chars] + "\n... [EXTRAIT TRONQUÉ] ..."

        half = max_chars // 2
        start = max(0, best_pos - half)
        end = min(len(content), start + max_chars)

        excerpt = content[start:end]

        if start > 0:
            excerpt = "... " + excerpt
        if end < len(content):
            excerpt = excerpt + " ..."

        return excerpt

    def _split_main_and_support(self, matches: List[Dict[str, Any]], query_mode: str) -> List[Dict[str, Any]]:
        """
        V3.5 :
        - unity_api_pure -> 1 principal + 2 support max
        - autres -> comportement plus souple
        """
        if not matches:
            return []

        if query_mode == "unity_api_pure":
            return matches[:3]

        if query_mode == "unity_api_plus_project":
            return matches[:4]

        return matches[:6]

    def build_context_for_question(self, question: str, query_mode: str = "project_or_general") -> str:
        """Construit un bloc de contexte doc ciblé pour la question."""
        if not self.has_active_docs():
            return ""

        metadata = self.load_metadata()
        matches = self.search(question)

        if not matches:
            return ""

        matches = self._split_main_and_support(matches, query_mode)

        max_excerpt_chars = self.config.get("unity_doc_max_excerpt_chars", 1400)

        if query_mode == "unity_api_pure":
            # Extrait principal plus large, supports plus petits
            main_excerpt_chars = min(max_excerpt_chars, 1200)
            support_excerpt_chars = min(max_excerpt_chars, 700)
        else:
            main_excerpt_chars = max_excerpt_chars
            support_excerpt_chars = min(max_excerpt_chars, 900)

        parts = []
        parts.append("📘 DOCUMENTATION UNITY LOCALE CIBLÉE")
        parts.append("============================================================")
        parts.append(f"Version active : {metadata.get('unity_version', self.active_version)}")
        parts.append(f"Source : {metadata.get('source', 'Documentation locale')}")
        parts.append(f"Sections indexées : {', '.join(metadata.get('indexed_sections', []))}")
        parts.append(f"Mode doc : {query_mode}")
        parts.append("Utilise en priorité ces extraits pour les détails Unity exacts.")
        parts.append("Ne pas extrapoler au-delà des extraits sans l'indiquer clairement.")
        parts.append("============================================================\n")

        if matches:
            first = matches[0]
            parts.append("[EXTRAIT PRINCIPAL]")
            parts.append(f"Titre : {first.get('title', 'Sans titre')}")
            parts.append(f"Catégorie : {first.get('category', 'general')}")
            parts.append(f"Fichier : {first.get('path', '-')}")
            if first.get("keywords"):
                parts.append(f"Mots-clés : {', '.join(first.get('keywords', []))}")
            parts.append(self._smart_excerpt(first.get("content", ""), question, main_excerpt_chars))
            parts.append("")

        if len(matches) > 1:
            for i, entry in enumerate(matches[1:], start=1):
                parts.append(f"[EXTRAIT SUPPORT {i}]")
                parts.append(f"Titre : {entry.get('title', 'Sans titre')}")
                parts.append(f"Catégorie : {entry.get('category', 'general')}")
                parts.append(f"Fichier : {entry.get('path', '-')}")
                if entry.get("keywords"):
                    parts.append(f"Mots-clés : {', '.join(entry.get('keywords', []))}")
                parts.append(self._smart_excerpt(entry.get("content", ""), question, support_excerpt_chars))
                parts.append("")

        return "\n".join(parts)
import os
import json
import re
from html.parser import HTMLParser
from datetime import datetime

from Core.unity_doc_manager import UnityDocManager


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_tags = {"script", "style", "noscript"}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def get_text(self):
        return " ".join(self.parts)


class UnityDocIndexer:
    def __init__(self, config_path="config.json"):
        self.doc_manager = UnityDocManager(config_path)
        self.doc_folder = self.doc_manager.get_active_doc_folder()
        self.metadata_path = self.doc_manager.get_metadata_path()
        self.index_path = self.doc_manager.get_index_path()

        metadata = self.doc_manager.load_metadata()
        raw_rel = metadata.get("raw_docs_folder", "raw/Documentation/en")
        self.raw_root = os.path.join(self.doc_folder, raw_rel)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = text.replace("Unity - Manual:", "")
        text = text.replace("Unity - Scripting API:", "")
        return text.strip()

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return "Sans titre"

        title = re.sub(r"<.*?>", "", match.group(1))
        return self._clean_text(title)

    def _extract_h1(self, html: str) -> str:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""

        h1 = re.sub(r"<.*?>", "", match.group(1))
        return self._clean_text(h1)

    def _extract_text(self, html: str) -> str:
        parser = HTMLTextExtractor()
        parser.feed(html)
        return self._clean_text(parser.get_text())

    def _make_keywords(self, title: str, rel_path: str) -> list[str]:
        filename = os.path.splitext(os.path.basename(rel_path))[0]
        tokens = re.findall(r"[A-Za-z0-9_\.]+", title + " " + filename)

        keywords = []
        seen = set()

        for token in tokens:
            token = token.strip()
            if len(token) < 3:
                continue

            token_lower = token.lower()
            if token_lower not in seen:
                seen.add(token_lower)
                keywords.append(token)

        return keywords[:20]

    def _categorize(self, rel_path: str) -> str:
        rel_path = rel_path.replace("\\", "/")

        if rel_path.startswith("ScriptReference/"):
            return "Scripting API"

        if rel_path.startswith("Manual/"):
            return "Manual"

        return "Other"

    def _should_index(self, rel_path: str) -> bool:
        rel_path = rel_path.replace("\\", "/")

        if not rel_path.endswith(".html"):
            return False

        return (
            rel_path.startswith("Manual/")
            or rel_path.startswith("ScriptReference/")
        )

    def build_index(self) -> int:
        if not os.path.exists(self.raw_root):
            raise FileNotFoundError(
                f"Dossier de doc brute introuvable : {self.raw_root}"
            )

        print(f"📂 Dossier de documentation brute : {self.raw_root}")

        entries = []
        scanned_html_files = 0
        indexed_files = 0

        for root, _, files in os.walk(self.raw_root):
            for filename in files:
                if not filename.endswith(".html"):
                    continue

                scanned_html_files += 1

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, self.raw_root).replace("\\", "/")

                if not self._should_index(rel_path):
                    continue

                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        html = f.read()

                    title = self._extract_title(html)
                    h1 = self._extract_h1(html)
                    text = self._extract_text(html)

                    if not text or len(text) < 120:
                        continue

                    final_title = h1 if h1 else title

                    entry = {
                        "title": final_title,
                        "category": self._categorize(rel_path),
                        "path": rel_path,
                        "keywords": self._make_keywords(final_title, rel_path),
                        "content": text[:6000]
                    }

                    entries.append(entry)
                    indexed_files += 1

                    if indexed_files % 500 == 0:
                        print(f"Indexation en cours... {indexed_files} pages indexées")

                except Exception as e:
                    print(f"⚠️ Erreur indexation {rel_path}: {e}")

        entries.sort(key=lambda e: (e["category"], e["title"].lower()))

        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        metadata = self.doc_manager.load_metadata()
        metadata["last_indexed_at"] = datetime.now().isoformat(timespec="seconds")
        metadata["indexed_entry_count"] = len(entries)

        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

        print(f"📄 Fichiers HTML scannés : {scanned_html_files}")
        print(f"✅ Pages indexées : {indexed_files}")

        return len(entries)


if __name__ == "__main__":
    indexer = UnityDocIndexer()
    count = indexer.build_index()
    print("=" * 60)
    print(f"✅ Indexation terminée : {count} entrées")
    print("=" * 60)
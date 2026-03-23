import os
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict


class PagesManager:
    """
    Gère les Documents et leurs Pages.

    Structure :
    - Un fichier JSON = un Document
    - Chaque Document contient une liste de Pages
    """

    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        self.app_root = os.path.dirname(self.config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.pages_dir = os.path.join(self.app_root, "Data/pages")
        os.makedirs(self.pages_dir, exist_ok=True)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _get_document_path(self, document_id: str) -> str:
        return os.path.join(self.pages_dir, f"{document_id}.json")

    def _save_document(self, document: Dict):
        document["updated_at"] = self._now()
        path = self._get_document_path(document["id"])

        with open(path, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=4)

    # ============================================================
    # DOCUMENTS
    # ============================================================

    def create_document(self, title: str = "Nouveau document") -> Dict:
        document_id = str(uuid.uuid4())
        now = self._now()

        document = {
            "id": document_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "pages": []
        }

        self._save_document(document)
        return document

    def list_documents(self) -> List[Dict]:
        documents = []

        for filename in os.listdir(self.pages_dir):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self.pages_dir, filename)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                documents.append(data)
            except Exception:
                continue

        documents.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return documents

    def load_document(self, document_id: str) -> Optional[Dict]:
        path = self._get_document_path(document_id)

        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete_document(self, document_id: str):
        path = self._get_document_path(document_id)
        if os.path.exists(path):
            os.remove(path)

    # ============================================================
    # PAGES
    # ============================================================

    def add_page(self, document_id: str, title: str = "Nouvelle page") -> Optional[Dict]:
        document = self.load_document(document_id)
        if not document:
            return None

        page = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": ""
        }

        document.setdefault("pages", []).append(page)
        self._save_document(document)
        return page

    def get_page(self, document_id: str, page_id: str) -> Optional[Dict]:
        document = self.load_document(document_id)
        if not document:
            return None

        for page in document.get("pages", []):
            if page.get("id") == page_id:
                return page

        return None

    def update_page_content(self, document_id: str, page_id: str, content: str) -> bool:
        document = self.load_document(document_id)
        if not document:
            return False

        for page in document.get("pages", []):
            if page.get("id") == page_id:
                page["content"] = content
                self._save_document(document)
                return True

        return False

    def rename_document(self, document_id: str, new_title: str) -> bool:
        document = self.load_document(document_id)
        if not document:
            return False

        document["title"] = new_title.strip() or "Nouveau document"
        self._save_document(document)
        return True

    def rename_page(self, document_id: str, page_id: str, new_title: str) -> bool:
        document = self.load_document(document_id)
        if not document:
            return False

        for page in document.get("pages", []):
            if page.get("id") == page_id:
                page["title"] = new_title.strip() or "Nouvelle page"
                self._save_document(document)
                return True

        return False

    def delete_page(self, document_id: str, page_id: str) -> bool:
        document = self.load_document(document_id)
        if not document:
            return False

        pages = document.get("pages", [])
        new_pages = [p for p in pages if p.get("id") != page_id]

        if len(new_pages) == len(pages):
            return False

        document["pages"] = new_pages
        self._save_document(document)
        return True
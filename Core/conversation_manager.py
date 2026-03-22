import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional


class ConversationManager:
    """Gère l'historique des conversations et leur sauvegarde sur disque."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = os.path.abspath(config_path)
        self.app_root = os.path.dirname(self.config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        conversations_dir = self.config.get("conversations_dir", "Data/conversations")
        self.conversations_dir = os.path.join(self.app_root, conversations_dir)
        os.makedirs(self.conversations_dir, exist_ok=True)

        self.current_conversation_id: Optional[str] = None
        self.current_conversation: Optional[Dict] = None

    def _get_conversation_path(self, conversation_id: str) -> str:
        return os.path.join(self.conversations_dir, f"{conversation_id}.json")

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def create_new_conversation(self, title: Optional[str] = None) -> Dict:
        conversation_id = str(uuid.uuid4())
        now = self._now_iso()

        if not title:
            title = f"Nouvelle conversation - {datetime.now().strftime('%d/%m/%Y %H:%M')}"

        self.current_conversation = {
            "id": conversation_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": []
        }
        self.current_conversation_id = conversation_id
        self.save_current_conversation()
        return self.current_conversation

    def load_conversation(self, conversation_id: str) -> Optional[Dict]:
        path = self._get_conversation_path(conversation_id)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            self.current_conversation = json.load(f)

        self.current_conversation_id = conversation_id
        return self.current_conversation

    def save_current_conversation(self):
        if not self.current_conversation or not self.current_conversation_id:
            return

        self.current_conversation["updated_at"] = self._now_iso()
        path = self._get_conversation_path(self.current_conversation_id)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.current_conversation, f, ensure_ascii=False, indent=4)

    def add_message(self, role: str, content: str):
        if not self.current_conversation:
            self.create_new_conversation()

        if not self.current_conversation["messages"] and role == "user":
            preview = content.strip().replace("\n", " ")
            if preview:
                self.current_conversation["title"] = preview[:60]

        self.current_conversation["messages"].append({
            "role": role,
            "content": content,
            "timestamp": self._now_iso()
        })

        self.save_current_conversation()

    def get_current_messages(self) -> List[Dict]:
        if not self.current_conversation:
            return []
        return self.current_conversation.get("messages", [])

    def get_model_messages(
        self,
        max_messages: int = 4,
        exclude_last_user: bool = False,
        max_chars_per_message: int = 1500
    ) -> List[Dict]:
        messages = self.get_current_messages()

        if exclude_last_user and messages:
            last = messages[-1]
            if last.get("role") == "user":
                messages = messages[:-1]

        filtered = []
        for msg in messages:
            if msg.get("role") not in ("user", "assistant"):
                continue

            content = msg.get("content", "")
            if len(content) > max_chars_per_message:
                content = content[:max_chars_per_message] + "\n... [message tronqué] ..."

            filtered.append({
                "role": msg["role"],
                "content": content
            })

        return filtered[-max_messages:]

    def list_conversations(self) -> List[Dict]:
        items = []

        for filename in os.listdir(self.conversations_dir):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self.conversations_dir, filename)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                items.append({
                    "id": data.get("id", filename[:-5]),
                    "title": data.get("title", "Conversation sans titre"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", "")
                })
            except Exception:
                continue

        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items
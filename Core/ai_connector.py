import os
import json
import re
import requests
from typing import Dict, List, Optional
from Core.project_context import ProjectContext

from Core.unity_doc_manager import UnityDocManager



class LMStudioConnector:
    def __init__(self, config_path="config.json", project_context: Optional[ProjectContext] = None):
        self.config_path = os.path.abspath(config_path)

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.project_context = project_context or ProjectContext(self.config_path)

        self.base_url = self.config["lm_studio_url"]
        self.model = self.config.get("model_name", "llama-3.1-8b-instruct.Q4_K_M")
        self.request_timeout = self.config.get("lm_request_timeout", 240)
        self.unity_doc_version = self.config.get("unity_doc_version", "2022.3.62f2")

        self.doc_manager = UnityDocManager(self.config_path)

    def _get_project_name(self) -> str:
        return self.project_context.get_project_name()    

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def send_message(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                temperature
                if temperature is not None
                else self.config.get("lm_temperature", 0.15)
            ),
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else self.config.get("lm_max_tokens", 4096)
            ),
            "stream": stream
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.request_timeout
        )

        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]

        return f"Erreur {response.status_code}: {response.text}"

    def _normalize_text(self, text: str) -> str:
        return (text or "").strip().lower()

    def _contains_any(self, text: str, markers: List[str]) -> bool:
        return any(marker in text for marker in markers)

    def _extract_symbols(self, question: str) -> List[str]:
        return re.findall(
            r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b",
            question or ""
        )

    def _looks_like_code_request(self, question: str) -> bool:
        q = self._normalize_text(question)

        code_markers = [
            "écris",
            "ecris",
            "génère",
            "genere",
            "donne moi le script",
            "donne le script",
            "fais le script",
            "crée le script",
            "cree le script",
            "code",
            "implémente",
            "implemente",
            "écris moi",
            "ecris moi",
            "script complet",
            "exemple de code",
            "snippet",
            "classe c#",
            "tool editor",
            "editorwindow",
            "custom editor",
            "propertydrawer"
        ]
        return self._contains_any(q, code_markers)

    def _looks_like_debug_request(self, question: str) -> bool:
        q = self._normalize_text(question)

        debug_markers = [
            "bug",
            "erreur",
            "error",
            "exception",
            "ça ne marche pas",
            "ca ne marche pas",
            "ça ne fonctionne pas",
            "ca ne fonctionne pas",
            "pourquoi",
            "corriger",
            "fix",
            "problème",
            "probleme",
            "warning",
            "nullreference",
            "compile",
            "compiler"
        ]
        return self._contains_any(q, debug_markers)

    def classify_query_mode(self, question: str) -> str:
        """
        Retour possible :
        - unity_api_pure
        - unity_api_plus_project
        - implementation_or_debug
        - project_or_general
        """
        q = self._normalize_text(question)

        api_markers = [
            "c'est quoi",
            "ca veut dire quoi",
            "que fait",
            "what is",
            "what does",
            "comment fonctionne",
            "how does",
            "callback",
            "event function",
            "monobehaviour",
            "scriptableobject",
            "editorwindow",
            "serializedproperty",
            "getcomponent",
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
            "rigidbody",
            "transform",
            "gameobject",
            "serializefield",
            "customeditor",
            "propertydrawer"
        ]

        project_markers = [
            "dans mon projet",
            "dans mon jeu",
            "dans mon outil",
            "chez moi",
            "mon script",
            "mon assistant",
            "mon code",
            "mon système",
            "race to the moon",
            "bloc escape",
            "unityai_assistant",
            "outil de tiles",
            "outil unity",
            "mon editor tool"
        ]

        exact_symbols = self._extract_symbols(question)

        has_technical_symbol = any(
            "." in symbol
            or any(c.isupper() for c in symbol[1:])
            or symbol.lower().startswith("on")
            for symbol in exact_symbols
        )

        has_api_markers = self._contains_any(q, api_markers) or has_technical_symbol
        has_project_context = self._contains_any(q, project_markers)
        wants_code = self._looks_like_code_request(question)
        is_debug = self._looks_like_debug_request(question)

        if (wants_code or is_debug) and (has_project_context or has_api_markers):
            return "implementation_or_debug"

        if has_api_markers and not has_project_context and not wants_code and not is_debug:
            return "unity_api_pure"

        if has_api_markers and has_project_context:
            return "unity_api_plus_project"

        if wants_code or is_debug:
            return "implementation_or_debug"

        return "project_or_general"

    def _build_system_prompt(self, query_mode: str) -> str:
        project_name = self._get_project_name()

        base_rules = f"""Tu es B.O.B (Bridge Of Builds), un assistant IA local intégré à DotTeck.
Tu aides l'utilisateur à comprendre, construire et corriger son projet actuel "{project_name}".

Règles générales :
1. Utilise le contexte fourni quand il est pertinent.
2. Donne des réponses compatibles avec Unity 2022.3.62f2 LTS si la question concerne Unity.
3. Si une documentation Unity locale ciblée est fournie, considère-la comme prioritaire pour les détails d'API Unity.
4. Ne présente jamais une déduction comme un fait certain.
5. Si une information projet manque, indique clairement la limite au lieu d'inventer.
6. Réponds en français sauf demande contraire.
7. Le contexte projet prime sur les anciens noms de projet ou suppositions.
8. Ne confonds jamais le cœur du projet avec des assets tiers importés.
9. Ne fournis du code que si l'utilisateur le demande explicitement ou si l'implémentation est clairement attendue."""

        if query_mode == "unity_api_pure":
            return base_rules + """

Mode actuel : QUESTION API UNITY PURE

Comportement attendu :
1. Réponds d'abord sur l'API Unity elle-même, sans dériver inutilement.
2. Reste sobre et précise ce qui est confirmé par les extraits.
3. Tu peux ajouter une courte précision pratique, mais sans inventer de contexte projet.
4. N'invente pas de noms de scripts, classes, variables, namespaces, outils, composants ou fichiers.
5. N'ajoute pas de code sauf si l'utilisateur le demande explicitement.
6. Si un détail n'est pas confirmé dans les extraits, signale-le clairement au lieu d'affirmer.

Format conseillé :
- Définition
- Précision utile
- Limite ou nuance importante

Le ton doit rester naturel, pas bureaucratique.
"""

        if query_mode == "unity_api_plus_project":
            return base_rules + """

Mode actuel : QUESTION UNITY + PROJET

Comportement attendu :
1. Commence par expliquer brièvement l'API Unity concernée.
2. Ensuite, relie-la au projet de façon prudente et utile.
3. N'invente pas de scripts, classes, variables, namespaces ou systèmes absents du contexte fourni.
4. Si tu proposes un exemple projet, présente-le explicitement comme une possibilité ou une structure recommandée, pas comme un élément déjà existant.
5. Ne fournis du code que si l'utilisateur le demande explicitement ou si la demande est clairement une demande d'implémentation.
6. Si l'utilisateur demande "comment utiliser", privilégie d'abord l'explication d'intégration avant de donner du code.
"""

        if query_mode == "implementation_or_debug":
            return base_rules + """

Mode actuel : IMPLÉMENTATION OU DEBUG

Comportement attendu :
1. Sois concret, pratique et orienté résolution.
2. Utilise la doc Unity comme ancrage technique pour sécuriser les comportements, signatures et patterns Unity.
3. Si du code aide réellement, tu peux en fournir.
4. Si le contexte projet est incomplet, formule des hypothèses prudentes au lieu d'inventer des faits.
5. Si plusieurs approches sont possibles, recommande la plus propre pour Unity 2022.3 LTS.
"""

        return base_rules + """

Mode actuel : QUESTION PROJET OU GÉNÉRALE

Comportement attendu :
1. Combine le contexte projet et la doc Unity si nécessaire.
2. Tu peux proposer des hypothèses de travail, mais distingue-les clairement des faits confirmés.
3. Si le contexte projet est incomplet, indique la limite au lieu d'inventer.
4. Cherche à être utile et concret, pas seulement prudent.
"""

    def _strip_box_tokens(self, text: str) -> str:
        text = text or ""
        text = text.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
        return text.strip()

    def _remove_project_noise_for_api_pure(self, response: str) -> str:
        if not response:
            return response

        lines = response.splitlines()
        leaned_lines = []

        current_project_name = self._get_project_name().lower().strip()

        forbidden_markers = [
            current_project_name,
            "race to the moon",
            "bloc escape",
            "octagonal",
            "unityai_assistant"
        ]

        forbidden_markers = [m for m in forbidden_markers if m]

        for line in lines:
            low = line.lower()
            if any(marker in low for marker in forbidden_markers):
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines).strip()
        return cleaned or response

    def send_with_context(
        self,
        question: str,
        project_context: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        query_mode = self.classify_query_mode(question)
        doc_context = self.doc_manager.build_context_for_question(question, query_mode=query_mode)
        system_prompt = self._build_system_prompt(query_mode)

        combined_context = project_context or ""

        if doc_context:
            combined_context += "\n\n" + doc_context

        max_context_chars = self.config.get("max_context_tokens", 35000)

        user_message = f"""MODE DE QUESTION :
{query_mode}

CONTEXTE DU PROJET UNITY :
============================================================
{combined_context[:max_context_chars]}
============================================================

QUESTION ACTUELLE :
{question}"""

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        if query_mode == "unity_api_pure":
            temperature = self.config.get("lm_api_temperature", 0.10)
            max_tokens = self.config.get("lm_api_max_tokens", 900)
        elif query_mode == "unity_api_plus_project":
            temperature = self.config.get("lm_guided_temperature", 0.14)
            max_tokens = self.config.get("lm_guided_max_tokens", 1600)
        elif query_mode == "implementation_or_debug":
            temperature = self.config.get("lm_impl_temperature", 0.18)
            max_tokens = self.config.get("lm_impl_max_tokens", 2600)
        else:
            temperature = self.config.get("lm_temperature", 0.15)
            max_tokens = self.config.get("lm_max_tokens", 4096)

        response = self.send_message(
            messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        response = self._strip_box_tokens(response)

        if query_mode == "unity_api_pure":
            response = self._remove_project_noise_for_api_pure(response)

        return response
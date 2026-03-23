import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class UnityBridgeState:
    """Stocke l'état courant reçu depuis Unity."""

    def __init__(self):
        self.is_connected = False
        self.last_seen = 0.0
        self.project_name = "Inconnu"
        self.unity_version = "Inconnue"
        self.active_scene = "Aucune"
        self.selected_object = "Aucun"
        self.play_mode = "EditMode"

    def update_from_payload(self, payload: dict):
        self.is_connected = True
        self.last_seen = time.time()
        self.project_name = payload.get("project_name", self.project_name)
        self.unity_version = payload.get("unity_version", self.unity_version)
        self.active_scene = payload.get("active_scene", self.active_scene)
        self.selected_object = payload.get("selected_object", self.selected_object)
        self.play_mode = payload.get("play_mode", self.play_mode)

    def check_timeout(self, timeout_seconds: float = 8.0):
        if self.is_connected and (time.time() - self.last_seen) > timeout_seconds:
            self.is_connected = False

    def to_dict(self):
        return {
            "is_connected": self.is_connected,
            "project_name": self.project_name,
            "unity_version": self.unity_version,
            "active_scene": self.active_scene,
            "selected_object": self.selected_object,
            "play_mode": self.play_mode,
            "last_seen": self.last_seen,
        }


class UnityBridgeServer:
    """Petit serveur HTTP local recevant les événements Unity."""

    def __init__(self, host="127.0.0.1", port=8765, on_state_changed=None):
        self.host = host
        self.port = port
        self.on_state_changed = on_state_changed
        self.state = UnityBridgeState()
        self.httpd = None
        self.server_thread = None
        self.monitor_thread = None
        self.running = False

    def start(self):
        if self.running:
            return

        parent = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _send_json(self, status_code: int, payload: dict):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path == "/health":
                    self._send_json(200, {"status": "ok"})
                else:
                    self._send_json(404, {"error": "not_found"})

            def do_POST(self):
                if self.path != "/unity-event":
                    self._send_json(404, {"error": "not_found"})
                    return

                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_length)
                    payload = json.loads(raw.decode("utf-8"))

                    parent.state.update_from_payload(payload)

                    if parent.on_state_changed:
                        parent.on_state_changed(parent.state.to_dict())

                    self._send_json(200, {"status": "received"})
                except Exception as e:
                    self._send_json(500, {"error": str(e)})

        self.httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self.running = True

        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

        self.monitor_thread = threading.Thread(target=self._monitor_connection, daemon=True)
        self.monitor_thread.start()

        print(f"🌉 Unity Bridge Server démarré sur http://{self.host}:{self.port}")

    def _monitor_connection(self):
        while self.running:
            previous = self.state.is_connected
            self.state.check_timeout()

            if previous != self.state.is_connected and self.on_state_changed:
                self.on_state_changed(self.state.to_dict())

            time.sleep(1.0)

    def stop(self):
        self.running = False

        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

        print("🌉 Unity Bridge Server arrêté")
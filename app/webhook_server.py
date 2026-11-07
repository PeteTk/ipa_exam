import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WebexClient

logger = logging.getLogger(__name__)
WEBEX_API_BASE = "https://webexapis.com/v1"

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        # 1. ตรวจสอบชนิด Event
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data", {})
        msg_id = data.get("id")
        if not msg_id:
            return None

        # 2. ป้องกัน Loop: ปฏิเสธถ้าผู้ส่งข้อความคือตัว Bot เอง
        if data.get("personId") == self.bot_person_id:
            return None

        # 3. ดึงเนื้อหาข้อความจาก Webex
        message = self.client.get_message(msg_id)
        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        mentioned_people = message.get("mentionedPeople", [])
        files = message.get("files", [])

        # 4. จัดการไฟล์แนบ
        if len(files) > 1:
            res = {"status": "error", "result": "multiple_attachments"}
            self.client.send_message(room_id, json.dumps(res))
            return res

        if len(files) == 0:
            try:
                res = self.processor(mentioned_people, None, self.bot_person_id)
            except Exception:
                logger.exception("Request processing failed")
                res = {"status": "error", "result": "backend_failed"}
            self.client.send_message(room_id, json.dumps(res))
            return res

        # กรณีมี 1 ไฟล์แนบ: ดาวน์โหลดลงไฟล์ชั่วคราวแล้วลบทิ้งหลังใช้งาน
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "request.yaml"
            file_bytes = self.client.download_file(files[0])
            file_path.write_bytes(file_bytes)

            try:
                res = self.processor(mentioned_people, file_path, self.bot_person_id)
            except Exception:
                logger.exception("Request processing failed")
                res = {"status": "error", "result": "backend_failed"}
            finally:
                if file_path.exists():
                    file_path.unlink()

            self.client.send_message(room_id, json.dumps(res))
            return res


def make_http_handler(submit_event):
    class HTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "ok", "result": "healthy"}).encode()
                )
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/webhook":
                content_length = self.headers.get("Content-Length")
                if not content_length or not content_length.isdigit():
                    self._send_error_400()
                    return

                length = int(content_length)
                if length < 1 or length > 1_000_000:
                    self._send_error_400()
                    return

                body = self.rfile.read(length)
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if not isinstance(payload, dict):
                        self._send_error_400()
                        return
                except Exception:
                    self._send_error_400()
                    return

                submit_event(payload)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "ok", "result": "accepted"}).encode()
                )
            else:
                self.send_response(404)
                self.end_headers()

        def _send_error_400(self):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"status": "error", "result": "invalid_event"}).encode()
            )

        def log_message(self, format, *args):
            pass

    return HTTPHandler


def build_event_handler():
    """Create a WebexEventHandler from WEBEX_BOT_TOKEN (raises on failure)."""
    raw_token = os.environ.get("WEBEX_BOT_TOKEN", "")
    token = raw_token.strip().strip('"').strip("'")
    if not token:
        raise PermissionError("WEBEX_BOT_TOKEN is missing")

    client = WebexClient(token=token)
    resp = client.session.get(
        f"{WEBEX_API_BASE}/people/me", headers=client.headers, timeout=10
    )
    resp.raise_for_status()
    me = resp.json()
    if "id" not in me:
        raise RuntimeError(f"Webex /people/me returned no id: {me}")
    logger.info("Bot ready: %s", me.get("displayName", me["id"]))
    return WebexEventHandler(client, me["id"])


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    # One worker => requests are processed sequentially (no overlapping
    # router changes) and handler_instance needs no locking.
    executor = ThreadPoolExecutor(max_workers=1)
    handler_instance = None

    def process_background_event(event):
        nonlocal handler_instance
        try:
            if handler_instance is None:
                handler_instance = build_event_handler()
            handler_instance.handle_event(event)
        except Exception:
            logger.exception("Failed to process webhook event")

    def submit_event(event):
        executor.submit(process_background_event, event)

    httpd = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    print(f"Starting Webhook Server on {host}:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        executor.shutdown(wait=False)


if __name__ == "__main__":
    main()
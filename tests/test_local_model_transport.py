import contextlib
from http.client import BadStatusLine, IncompleteRead, LineTooLong
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch

from engine.local_model import LocalModel, ModelUnavailable


class LocalModelTransportTests(unittest.TestCase):
    def test_protocol_errors_trip_circuit_during_startup_and_requests(self):
        for stage in ('startup', 'request'):
            for error in (BadStatusLine('broken'), LineTooLong('status line'),
                          IncompleteRead(b'partial', 20)):
                with self.subTest(stage=stage, error=type(error).__name__):
                    model = LocalModel()
                    self.addCleanup(model.close)
                    model.url = 'http://127.0.0.1:1'
                    with contextlib.ExitStack() as stack:
                        if stage == 'startup':
                            stack.enter_context(patch.object(model, 'start', side_effect=error))
                        else:
                            stack.enter_context(patch.object(model, 'start'))
                            stack.enter_context(patch.object(model.http, 'open', side_effect=error))
                        with self.assertRaises(ModelUnavailable):
                            model.ask('inspect', [], {})
                    self.assertIsNotNone(model.failure)
                    with patch.object(model.http, 'open') as request:
                        with self.assertRaises(ModelUnavailable):
                            model.ask('retry', [], {})
                        request.assert_not_called()

    def test_truncated_loopback_response_becomes_model_unavailable(self):
        class TruncatedResponse(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                self.wfile.write(b'20\r\npartial')
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), TruncatedResponse)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.shutdown)
        model = LocalModel()
        self.addCleanup(model.close)
        model.url = f'http://127.0.0.1:{server.server_port}'
        with patch.object(model, 'start'):
            with self.assertRaises(ModelUnavailable):
                model.ask('inspect', [], {})
        self.assertIn('IncompleteRead', model.failure)
        self.assertEqual(1, model.calls)
        self.assertIsNone(model.process)


if __name__ == '__main__':
    unittest.main()

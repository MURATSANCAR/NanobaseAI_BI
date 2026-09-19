#!/usr/bin/env python3
"""Loopback HTTP relay to the GPU through the existing Mac SOCKS VPN.

Each request uses a separate SOCKS connection, so a large image upload cannot
block unrelated model calls on a shared SSH forwarding channel. No cloud fallback.
"""
import argparse
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import struct
import threading
import time
import uuid


def exact(sock, count):
    data = b''
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise ConnectionError('SOCKS connection closed')
        data += part
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socks-port', type=int, default=11080)
    parser.add_argument('--gpu-host', default='172.23.85.10')
    parser.add_argument('--gpu-port', type=int, default=8001)
    parser.add_argument('--listen-port', type=int, default=18081)
    args = parser.parse_args()
    slots = threading.BoundedSemaphore(16)
    allowed = {'/health', '/gateway/status', '/v1/models', '/tokenize', '/v1/chat/completions'}
    hop = {'host', 'connection', 'transfer-encoding', 'keep-alive', 'upgrade',
           'proxy-authorization', 'proxy-authenticate', 'te', 'trailer'}

    def connect_gpu():
        sock = socket.create_connection(('127.0.0.1', args.socks_port), timeout=15)
        try:
            sock.sendall(b'\x05\x01\x00')
            if exact(sock, 2) != b'\x05\x00':
                raise ConnectionError('SOCKS authentication negotiation failed')
            host = args.gpu_host.encode('idna')
            if len(host) > 255:
                raise ValueError('GPU hostname too long')
            sock.sendall(b'\x05\x01\x00\x03' + bytes([len(host)]) + host + struct.pack('!H', args.gpu_port))
            version, status, _, kind = exact(sock, 4)
            if version != 5 or status:
                raise ConnectionError('SOCKS GPU connection rejected')
            size = 4 if kind == 1 else 16 if kind == 4 else exact(sock, 1)[0] if kind == 3 else None
            if size is None:
                raise ConnectionError('Invalid SOCKS response')
            exact(sock, size + 2)
            sock.settimeout(3600)
            return sock
        except Exception:
            sock.close()
            raise

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass  # Never write book content, authentication, or URLs to logs.

        def handle_request(self):
            request_id = uuid.uuid4().hex
            def event(stage, **details):
                print(json.dumps({'request_id': request_id, 'stage': stage, **details}), flush=True)
            if self.path not in allowed:
                self.send_error(404)
                return
            if not slots.acquire(blocking=False):
                self.send_error(503, 'GPU relay capacity reached')
                return
            connection = None
            started = False
            try:
                if self.headers.get('Transfer-Encoding'):
                    self.send_error(411, 'Content-Length required')
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 32 * 1024 * 1024:
                    self.send_error(413)
                    return
                self.connection.settimeout(120)
                event('receiving', bytes=size)
                body = self.rfile.read(size) if size else None
                if body is not None and len(body) != size:
                    raise ConnectionError('Incomplete request body')
                connection = http.client.HTTPConnection(args.gpu_host, args.gpu_port, timeout=3600)
                connection.sock = connect_gpu()
                event('forwarding', bytes=size)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in hop}
                # Pace uploads through userspace VPN TCP stacks instead of one
                # multi-megabyte sendall burst; keep source bytes unchanged.
                connection.putrequest(self.command, self.path)
                for key, value in headers.items():
                    connection.putheader(key, value)
                connection.endheaders()
                if body:
                    for offset in range(0, len(body), 16384):
                        connection.send(body[offset:offset + 16384])
                        time.sleep(0.001)
                event('awaiting_response')
                response = connection.getresponse()
                event('response', status=response.status)
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in hop:
                        self.send_header(key, value)
                self.send_header('Connection', 'close')
                self.end_headers()
                started = True
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (OSError, ValueError, http.client.HTTPException):
                if not started:
                    self.send_error(502, 'Private GPU route unavailable')
            finally:
                if connection:
                    connection.close()
                self.close_connection = True
                slots.release()

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(('127.0.0.1', args.listen_port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == '__main__':
    main()

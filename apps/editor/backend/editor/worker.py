"""Supervised worker process; analysis admission remains closed pending P0 qualification."""
import signal
import time
from editor.config import connection, RELEASE

running = True


def stop(*_):
    global running
    running = False


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            with connection() as db:
                db.execute('''INSERT INTO editor.worker_heartbeats(worker_id,release,mode)
                    VALUES ('foundation',%s,'awaiting_model_qualification')
                    ON CONFLICT(worker_id) DO UPDATE SET release=excluded.release,
                    seen_at=now(), mode=excluded.mode''', (RELEASE,))
        except Exception as exc:
            print('heartbeat_error:' + type(exc).__name__, flush=True)
        for _ in range(10):
            if not running:
                break
            time.sleep(1)


if __name__ == '__main__':
    main()

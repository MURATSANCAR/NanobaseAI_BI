"""Supervised worker process; analysis admission remains closed pending P0 qualification."""
import signal
import time
import threading
import uuid
import re
from editor.config import connection, RELEASE

running = True


def stop(*_):
    global running
    running = False


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    active = {}; owner=str(uuid.uuid4())
    def execute(job):
        try:
            from editor.analysis import run, answer_question
            if job.get('task')=='question':
                answer_question(job)
                return
            run(job)
        except Exception as exc:
            code=str(exc) if re.fullmatch('[A-Z_]{3,80}',str(exc)) else type(exc).__name__
            with connection() as db:
                db.execute("UPDATE editor.jobs SET status=%s,error_code=%s,finished_at=now() WHERE id=%s AND owner_id=%s AND fencing_token=%s AND status='RUNNING'",
                  ('CANCELLED' if code=='CANCELLED' else 'FAILED',code,job['id'],owner,job['fencing_token']))
            print('analysis_error:'+code,flush=True)
        finally:
            active.clear()
    while running:
        try:
            with connection() as db:
                db.execute('''INSERT INTO editor.worker_heartbeats(worker_id,release,mode)
                    VALUES ('foundation',%s,'book_analysis_worker')
                    ON CONFLICT(worker_id) DO UPDATE SET release=excluded.release,
                    seen_at=now(), mode=excluded.mode''', (RELEASE,))
                if active:
                    db.execute("UPDATE editor.jobs SET lease_until=now()+interval '90 seconds' WHERE id=%s AND owner_id=%s AND status='RUNNING'",(active['id'],owner))
                else:
                    db.execute("UPDATE editor.jobs SET status='CANCELLED',finished_at=now() WHERE status='RUNNING' AND cancellation_requested AND lease_until<now()")
                    job=db.execute("""SELECT * FROM editor.jobs WHERE
                      (status='QUEUED' OR (status='RUNNING' AND lease_until<now()))
                      AND attempt_no<3 AND NOT cancellation_requested ORDER BY created_at
                      FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
                    if job:
                        job=db.execute("""UPDATE editor.jobs SET status='RUNNING',owner_id=%s,
                          lease_until=now()+interval '90 seconds',attempt_no=attempt_no+1,
                          fencing_token=fencing_token+1 WHERE id=%s RETURNING *""",(owner,job['id'])).fetchone()
                        active.update(job)
            if active and not active.get('_started'):
                active['_started']=True
                threading.Thread(target=execute,args=(dict(active),),daemon=True).start()
        except Exception as exc:
            print('heartbeat_error:' + type(exc).__name__, flush=True)
        for _ in range(10):
            if not running:
                break
            time.sleep(1)


if __name__ == '__main__':
    main()

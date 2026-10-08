"""Background worker: makes Shorts on SHORTS_SCHEDULE and uploads scheduled videos. Run: python -m ytauto.worker"""
import logging
import time
from datetime import datetime, timezone

from croniter import croniter

from . import config, db, pipeline, reference

log = logging.getLogger("ytauto.worker")
STATE_KEY = "worker_state"


def next_run(expr=None, base=None):
    return croniter(expr or config.SHORTS_SCHEDULE, base or datetime.now(timezone.utc)).get_next(datetime)


def _state(**kw):
    state = db.get_json_setting(STATE_KEY, {}) or {}
    state.update(kw, heartbeat=db.utc_now())
    db.set_setting(STATE_KEY, state)


def run_job(job):
    k, p = job["kind"], job["payload"]
    if k == "run_next":
        return pipeline.run_continuous(manual=True)
    if k == "make":
        return f"made production {pipeline.generate(p.get('topic'), source='manual')}"
    if k == "rerender":
        pipeline.rerender(p["id"], p["story"])
        return f"re-rendered production {p['id']}"
    if k == "regenerate":
        return f"made production {pipeline.regenerate(p['id'], p.get('notes', ''))}"
    if k == "analyze":
        prof = reference.analyze(p["channel"], activate=True)
        return f"analyzed: {prof.get('niche', '')}"
    if k == "publish_now":
        db.cancel_schedule(p["id"])
        db.schedule_publish(p["id"], db.utc_now())
        return f"uploaded: {pipeline.publish_due()}"
    raise ValueError(f"unknown job {k}")


def run_jobs():
    while (job := db.claim_job()):
        log.info("Job %s: %s", job["id"], job["kind"])
        try:
            db.finish_job(job["id"], "done", run_job(job))
        except Exception as e:
            log.exception("Job %s failed", job["id"])
            db.finish_job(job["id"], "failed", e)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init()
    first = time.time() + config.SHORTS_FIRST_RUN_DELAY_S
    nxt = next_run()
    log.info("Worker started; continuous Shorts %s, next run %s", "on" if config.SHORTS_CONTINUOUS else "off", nxt)
    _state(next_run=nxt.isoformat(), started=db.utc_now())
    while True:
        try:
            pipeline.publish_due()
            run_jobs()
            now = datetime.now(timezone.utc)
            due = (first and time.time() >= first) or now >= nxt
            if config.SHORTS_CONTINUOUS and due:
                first = 0
                nxt = next_run(base=now)
                result = pipeline.run_continuous()
                log.info("Scheduler: %s", result)
                _state(last_result=result, last_run=db.utc_now(), next_run=nxt.isoformat())
            else:
                _state(next_run=nxt.isoformat())
        except Exception as e:
            log.exception("Worker tick failed")
            _state(last_result=f"error: {e}"[:300], last_run=db.utc_now())
        time.sleep(20)


if __name__ == "__main__":
    main()

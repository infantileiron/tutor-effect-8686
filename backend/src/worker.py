import time,traceback
from pathlib import Path
from sqlalchemy import select
from src.config.database import SessionLocal
from src.models.entities import Report
from src.services.reports import queue,compute_report
print('tutor effect worker started',flush=True)
while True:
    Path('/tmp/worker-heartbeat').touch()
    try:
        queue.brpop('tutor:reports',timeout=2)
        with SessionLocal() as db:
            task=db.scalar(select(Report).where(Report.status=='queued').order_by(Report.id).with_for_update(skip_locked=True))
            if not task: continue
            task.status='running';db.commit()
            try:
                task.result=compute_report(db,task)
                task.status='completed'
            except Exception as e:
                task.error=str(e);task.status='failed'
            db.commit()
            print(f'report={task.id} status={task.status}',flush=True)
    except Exception:
        traceback.print_exc();time.sleep(2)

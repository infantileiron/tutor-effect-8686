import os
from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
import redis
from src.models.entities import Report,Plan,Assignment,Student
from src.services.statistics import welch,roster_welch
queue=redis.Redis.from_url(os.environ['REDIS_URL'])
def list_reports(db): return db.scalars(select(Report).order_by(Report.id.desc())).all()
def create_report(db,plan_id,source=None):
    plan=db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,'辅导方案不存在')
    if source is None: source='roster' if plan.target_control+plan.target_intervention>0 else 'campus'
    running=db.scalars(select(Report).where(Report.status.in_(['queued','running']))).all()
    if len(running)>=10: raise HTTPException(429,'待执行任务已达10个，请稍后再试')
    item=Report(plan_id=plan_id,status='queued',source=source,created_at=datetime.now(timezone.utc).isoformat())
    db.add(item);db.commit();db.refresh(item)
    queue.lpush('tutor:reports',item.id)
    return item
def compute_report(db,task):
    """计算一份报告。roster 口径只读方案已锁定名单；campus 口径按教学点筛选。"""
    plan=db.get(Plan,task.plan_id)
    if task.source=='roster':
        rows=db.execute(select(Assignment,Student).join(Student,Student.id==Assignment.student_id).where(Assignment.plan_id==task.plan_id,Assignment.status=='locked').order_by(Student.code)).all()
        return roster_welch(plan,rows)
    return welch(db.scalars(select(Student).order_by(Student.code)).all(),plan)
def get_report(db,id):
    item=db.get(Report,id)
    if not item: raise HTTPException(404,'报告不存在')
    return item
def save_conclusion(db,id,data,user):
    item=get_report(db,id)
    if item.status!='completed': raise HTTPException(409,'计算完成后才能起草结论')
    if item.published and user.role!='admin': raise HTTPException(403,'已签核报告仅管理员可更改')
    if data.published and user.role!='admin': raise HTTPException(403,'仅管理员可签核发布')
    item.conclusion=data.conclusion;item.published=data.published
    db.commit();db.refresh(item)
    return item

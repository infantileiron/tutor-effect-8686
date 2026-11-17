"""联合招募：待分配 → 已锁定 的名额生命周期管理。

- 每人同期只占一个名额：部分唯一索引保证 pending/locked 一名额一学员；
- 并发安全：创建冲突整体重试，锁定行级串行，失败整体回滚；
- 幂等：同一 idempotency_key 重试返回原批次，不重复占位；重复锁定直接返回。
"""
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import Plan,Student,Assignment,RecruitBatch,Report
from src.services.allocation import joint_allocate,GROUPS

ACTIVE=('pending','locked')

def _now(): return datetime.now(timezone.utc).isoformat()

def _eligible(student,plan):
    return (plan.campus=='全部' or student.campus==plan.campus) and (not plan.exclude_absent or not student.absent)

def _load(db,plan_ids=None):
    plans=db.scalars(select(Plan).order_by(Plan.id)).all()
    if plan_ids is not None:
        known={p.id for p in plans}
        missing=[i for i in plan_ids if i not in known]
        if missing: raise HTTPException(404,f'方案不存在: {missing}')
        plans=[p for p in plans if p.id in set(plan_ids)]
    plans=[p for p in plans if p.target_control+p.target_intervention>0]
    active=db.scalars(select(Assignment).where(Assignment.status.in_(ACTIVE))).all()
    used={a.student_id for a in active}
    students=db.scalars(select(Student).order_by(Student.id)).all()
    free=[s for s in students if s.id not in used]
    withdrawn={(a.student_id,a.plan_id) for a in db.scalars(select(Assignment).where(Assignment.status=='withdrawn')).all()}
    return plans,active,students,free,withdrawn

def _eligible_ids(plan,free,withdrawn):
    """合格候选：教学点与缺考口径匹配、当前无有效名额、且未从本方案退出过。"""
    return {s.id for s in free if _eligible(s,plan) and (s.id,plan.id) not in withdrawn}

def _remaining(plans,active):
    rem={p.id:{g:getattr(p,f'target_{g}') for g in GROUPS} for p in plans}
    for a in active:
        if a.plan_id in rem and a.group in rem[a.plan_id]: rem[a.plan_id][a.group]-=1
    return rem

def _summarize(plans,rem,eligible,assignments,per_plan,min_ratio):
    taken_by={}
    for sid,pid,g in assignments: taken_by.setdefault(pid,set()).add(sid)
    all_assigned={sid for sid,_,_ in assignments}
    items=[];total=0
    for p in plans:
        caps={g:max(0,rem[p.id][g]) for g in GROUPS}
        got=per_plan.get(p.id,{'control':0,'intervention':0})
        target=caps['control']+caps['intervention']
        assigned=got['control']+got['intervention']
        total+=assigned
        reasons=[]
        if target==0:
            reasons.append({'code':'FULL','group':None,'message':'两组目标已招满，本轮无需分配'})
        elif assigned<target:
            pool=len(eligible[p.id])
            shortage=target-assigned
            if pool<target:
                reasons.append({'code':'INSUFFICIENT_POOL','group':None,'message':f'教学点合格候选不足：剩余目标 {target} 人，可分配候选仅 {pool} 人'})
            else:
                others=len({sid for sid in eligible[p.id] if sid in all_assigned and sid not in taken_by.get(p.id,set())})
                reasons.append({'code':'SHARED_CONTENTION','group':None,'message':f'共享候选被其他研究占用：{others} 名合格候选分配给其它方案；为保障各方案最低达成比例，本方案缺 {shortage} 人'})
            for g,label in (('control','对照组'),('intervention','干预组')):
                if got[g]<caps[g]: reasons.append({'code':'GROUP_SHORT','group':g,'message':f'{label}缺 {caps[g]-got[g]} 人（剩余目标 {caps[g]}，本轮分配 {got[g]}）'})
        items.append({'plan_id':p.id,'title':p.title,'target_control':caps['control'],'target_intervention':caps['intervention'],'assigned_control':got['control'],'assigned_intervention':got['intervention'],'ratio':round(assigned/target,4) if target else None,'reasons':reasons})
    return {'min_ratio':float(min_ratio),'total_assigned':total,'plans':items}

def create_recruitment(db,data):
    """生成待分配批次。同一 idempotency_key 重试返回原批次，不重复占位。"""
    for _ in range(4):
        existing=db.scalar(select(RecruitBatch).where(RecruitBatch.idempotency_key==data.idempotency_key))
        if existing: return existing
        try:
            plans,active,students,free,withdrawn=_load(db,data.plan_ids)
            if not plans: raise HTTPException(422,'没有设置目标人数的方案；请先在辅导分组中填写两组目标人数')
            rem=_remaining(plans,active)
            specs=[{'id':p.id,'caps':{g:max(0,rem[p.id][g]) for g in GROUPS}} for p in plans]
            eligible={p.id:_eligible_ids(p,free,withdrawn) for p in plans}
            assignments,per_plan,min_ratio=joint_allocate(specs,[s.id for s in free],eligible)
            batch=RecruitBatch(kind=data.kind,status='pending',idempotency_key=data.idempotency_key,summary=_summarize(plans,rem,eligible,assignments,per_plan,min_ratio),created_at=_now())
            db.add(batch);db.flush()
            now=_now()
            for sid,pid,g in assignments:
                db.add(Assignment(batch_id=batch.id,plan_id=pid,student_id=sid,group=g,status='pending',created_at=now,updated_at=now))
            db.commit();db.refresh(batch)
            return batch
        except IntegrityError:
            db.rollback()  # 并发占位冲突：整体回滚后用最新占用重试
    raise HTTPException(409,'招募请求与其他操作冲突，请重试')

def lock_batch(db,batch_id):
    """锁定批次：待分配 → 已锁定。并发下不超占；失败整体回滚保持待分配；重复锁定幂等。"""
    batch=db.scalar(select(RecruitBatch).where(RecruitBatch.id==batch_id).with_for_update())
    if not batch: raise HTTPException(404,'招募批次不存在')
    if batch.status=='locked': return batch
    plans={p.id:p for p in db.scalars(select(Plan)).all()}
    counts={}
    for a in db.scalars(select(Assignment).where(Assignment.status.in_(ACTIVE))).all():
        counts[(a.plan_id,a.group)]=counts.get((a.plan_id,a.group),0)+1
    for (pid,g),n in counts.items():
        target=getattr(plans[pid],f'target_{g}') if pid in plans else 0
        if n>target: raise HTTPException(409,f'方案 {plans[pid].title if pid in plans else pid} 目标人数已调低，现有名额 {n} 超过目标 {target}；请先退出多余名额或恢复目标')
    now=_now()
    for a in db.scalars(select(Assignment).where(Assignment.batch_id==batch.id,Assignment.status=='pending')).all():
        a.status='locked';a.updated_at=now
    batch.status='locked';batch.locked_at=now
    db.commit();db.refresh(batch)
    return batch

def withdraw(db,assignment_id):
    """退出：释放名额供补招；已受理报告的快照不受影响。幂等。"""
    a=db.scalar(select(Assignment).where(Assignment.id==assignment_id).with_for_update())
    if not a: raise HTTPException(404,'名额不存在')
    if a.status=='withdrawn': return a
    a.status='withdrawn';a.updated_at=_now()
    db.commit();db.refresh(a)
    return a

def _occupancy(plan,active):
    pa=[a for a in active if a.plan_id==plan.id]
    def count(status,group): return sum(1 for a in pa if a.status==status and a.group==group)
    return {'locked_control':count('locked','control'),'locked_intervention':count('locked','intervention'),'pending_control':count('pending','control'),'pending_intervention':count('pending','intervention')}

def overview(db):
    plans=db.scalars(select(Plan).order_by(Plan.id)).all()
    active=db.scalars(select(Assignment).where(Assignment.status.in_(ACTIVE))).all()
    students=db.scalars(select(Student)).all()
    used={a.student_id for a in active}
    free=[s for s in students if s.id not in used]
    withdrawn={(a.student_id,a.plan_id) for a in db.scalars(select(Assignment).where(Assignment.status=='withdrawn')).all()}
    latest=db.scalars(select(RecruitBatch).order_by(RecruitBatch.id.desc()).limit(1)).first()
    reasons={}
    if latest:
        for item in (latest.summary or {}).get('plans',[]):
            msgs=[r['message'] for r in item.get('reasons',[]) if r.get('code')!='FULL']
            if msgs: reasons[item['plan_id']]=msgs
    items=[]
    for p in plans:
        target=p.target_control+p.target_intervention
        occ=_occupancy(p,active)
        locked=occ['locked_control']+occ['locked_intervention']
        items.append({'plan_id':p.id,'title':p.title,'campus':p.campus,'target_control':p.target_control,'target_intervention':p.target_intervention,**occ,'ratio':round(locked/target,4) if target else None,'eligible_free':len(_eligible_ids(p,free,withdrawn)),'reasons':reasons.get(p.id,[])})
    return {'candidates_total':len(students),'candidates_free':len(free),'plans':items}

def roster(db,plan_id):
    plan=db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,'方案不存在')
    rows=db.execute(select(Assignment,Student).join(Student,Student.id==Assignment.student_id).where(Assignment.plan_id==plan_id).order_by(Assignment.id.desc())).all()
    items=[{'id':a.id,'batch_id':a.batch_id,'group':a.group,'status':a.status,'updated_at':a.updated_at,'student':{'id':s.id,'code':s.code,'name':s.name,'campus':s.campus,'score':s.score,'absent':s.absent}} for a,s in rows]
    active=db.scalars(select(Assignment).where(Assignment.status.in_(ACTIVE),Assignment.plan_id==plan_id)).all()
    reports=db.scalars(select(Report).where(Report.plan_id==plan_id).order_by(Report.id.desc())).all()
    basis=[{'id':r.id,'status':r.status,'source':r.source,'created_at':r.created_at,'published':r.published} for r in reports]
    return {'plan_id':plan_id,'occupancy':_occupancy(plan,active),'assignments':items,'reports':basis}

def list_batches(db):
    batches=db.scalars(select(RecruitBatch).order_by(RecruitBatch.id.desc())).all()
    result=[]
    for b in batches:
        counts={}
        for a in db.scalars(select(Assignment).where(Assignment.batch_id==b.id)).all():
            counts[a.status]=counts.get(a.status,0)+1
        result.append({'id':b.id,'kind':b.kind,'status':b.status,'idempotency_key':b.idempotency_key,'created_at':b.created_at,'locked_at':b.locked_at,'summary':b.summary,'counts':counts})
    return result

def batch_detail(db,batch_id):
    batch=db.get(RecruitBatch,batch_id)
    if not batch: raise HTTPException(404,'招募批次不存在')
    rows=db.execute(select(Assignment,Student,Plan).join(Student,Student.id==Assignment.student_id).join(Plan,Plan.id==Assignment.plan_id).where(Assignment.batch_id==batch_id).order_by(Assignment.id)).all()
    items=[{'id':a.id,'plan_id':a.plan_id,'plan_title':p.title,'group':a.group,'status':a.status,'student_code':s.code,'student_name':s.name,'campus':s.campus} for a,s,p in rows]
    return {'id':batch.id,'kind':batch.kind,'status':batch.status,'idempotency_key':batch.idempotency_key,'created_at':batch.created_at,'locked_at':batch.locked_at,'summary':batch.summary,'assignments':items}

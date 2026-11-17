"""检验口径：只读已锁定名单；退出/补招不改变已受理报告；成绩仍可修订。"""
import uuid
import pytest
from datetime import datetime,timezone
from sqlalchemy import select
from src.config.database import SessionLocal
from src.models.entities import Assignment,RecruitBatch,Report
from src.services import reports as report_service
from tests.conftest import add_student,add_plan

def now(): return datetime.now(timezone.utc).isoformat()

def recruit_and_lock(client,headers,kind='initial'):
    r=client.post('/recruitments',json={'kind':kind,'idempotency_key':uuid.uuid4().hex},headers=headers)
    assert r.status_code==201,r.text
    bid=r.json()['id']
    assert client.post(f'/recruitments/{bid}/lock',headers=headers).status_code==200
    return bid

def compute(plan_id,source='roster'):
    with SessionLocal() as session:
        item=report_service.create_report(session,plan_id,source)
        item.status='running'
        try:
            item.result=report_service.compute_report(session,item)
            item.status='completed'
        except Exception as e:
            item.error=str(e);item.status='failed'
        session.commit()
        item_id=item.id
    with SessionLocal() as session:
        return session.get(Report,item_id)

def test_roster_is_default_source_for_targeted_plan(client,admin_headers,db):
    p=add_plan(db,'有目标',tc=2,ti=2)
    q=add_plan(db,'无目标')
    r=client.post('/reports',json={'plan_id':p.id},headers=admin_headers)
    assert r.status_code==202 and r.json()['source']=='roster'
    r=client.post('/reports',json={'plan_id':q.id},headers=admin_headers)
    assert r.json()['source']=='campus'

def test_report_reads_only_locked_roster(client,admin_headers,db):
    students=[add_student(db,f'S{i+1:03}',score=70+i*3) for i in range(6)]
    p=add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    r=client.post('/recruitments',json={'kind':'initial','idempotency_key':uuid.uuid4().hex},headers=admin_headers)
    bid=r.json()['id']
    pending=compute(p.id)                       # 未锁定：待分配不计入样本
    assert pending.status=='failed' and '每组至少需要 2 个有效成绩' in pending.error
    client.post(f'/recruitments/{bid}/lock',headers=admin_headers)
    done=compute(p.id)
    assert done.status=='completed'
    assert done.result['source']=='roster'
    assert done.result['control_n']==2 and done.result['intervention_n']==2
    assert len(done.result['sample_snapshot'])==4  # 聚合锁定名单样本

def test_report_uses_assignment_group_not_student_group(client,admin_headers,db):
    s1=add_student(db,'G001',group='intervention',score=61.0)
    s2=add_student(db,'G002',group='intervention',score=63.0)
    s3=add_student(db,'G003',group='control',score=88.0)
    s4=add_student(db,'G004',group='control',score=92.0)
    p=add_plan(db,'方案G',tc=2,ti=2)
    with SessionLocal() as session:
        batch=RecruitBatch(kind='initial',status='locked',idempotency_key='manual-1',summary={},created_at=now(),locked_at=now())
        session.add(batch);session.flush()
        for sid,g in [(s1.id,'control'),(s2.id,'control'),(s3.id,'intervention'),(s4.id,'intervention')]:
            session.add(Assignment(batch_id=batch.id,plan_id=p.id,student_id=sid,group=g,status='locked',created_at=now(),updated_at=now()))
        session.commit()
    done=compute(p.id)
    assert done.status=='completed'
    groups={x['code']:x['group'] for x in done.result['sample_snapshot']}
    assert groups=={'G001':'control','G002':'control','G003':'intervention','G004':'intervention'}
    assert done.result['control_mean']==62.0       # 按名额分组聚合，而非学员原分组

def test_withdrawal_keeps_accepted_report_and_new_report_accepted(client,admin_headers,db):
    [add_student(db,f'S{i+1:03}',score=60+i*4) for i in range(8)]
    p=add_plan(db,'方案A',campus='全部',tc=3,ti=3)
    recruit_and_lock(client,admin_headers)
    accepted=compute(p.id)                      # 已受理报告
    assert accepted.status=='completed'
    snapshot_codes={x['code'] for x in accepted.result['sample_snapshot']}
    assert len(snapshot_codes)==6
    roster=client.get(f'/plans/{p.id}/roster',headers=admin_headers).json()
    victim=next(a for a in roster['assignments'] if a['status']=='locked' and a['group']=='control')
    client.post(f"/assignments/{victim['id']}/withdraw",headers=admin_headers)
    with SessionLocal() as session:                # 退出不改变已受理报告样本
        again=session.get(Report,accepted.id)
        assert {x['code'] for x in again.result['sample_snapshot']}==snapshot_codes
    followup=compute(p.id)                      # 退出后新检验仍受理，样本随之减少
    assert followup.status=='completed'
    new_codes={x['code'] for x in followup.result['sample_snapshot']}
    assert new_codes==snapshot_codes-{victim['student']['code']}

def test_supplementary_keeps_accepted_report(client,admin_headers,db):
    [add_student(db,f'S{i+1:03}',score=60+i*4) for i in range(8)]
    p=add_plan(db,'方案A',campus='全部',tc=3,ti=3)
    recruit_and_lock(client,admin_headers)
    accepted=compute(p.id)
    roster=client.get(f'/plans/{p.id}/roster',headers=admin_headers).json()
    victim=next(a for a in roster['assignments'] if a['status']=='locked' and a['group']=='control')
    client.post(f"/assignments/{victim['id']}/withdraw",headers=admin_headers)
    recruit_and_lock(client,admin_headers,kind='supplementary')   # 补招并锁定
    with SessionLocal() as session:
        again=session.get(Report,accepted.id)
        assert len(again.result['sample_snapshot'])==6            # 补招不改变已受理报告
        assert victim['student']['code'] in {x['code'] for x in again.result['sample_snapshot']}
    renewed=compute(p.id)
    assert renewed.status=='completed'
    assert len(renewed.result['sample_snapshot'])==6              # 新检验包含补招成员
    assert victim['student']['code'] not in {x['code'] for x in renewed.result['sample_snapshot']}

def test_score_revision_allowed_and_old_report_untouched(client,admin_headers,db):
    students=[add_student(db,f'S{i+1:03}',score=60+i*4) for i in range(6)]
    p=add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    recruit_and_lock(client,admin_headers)
    accepted=compute(p.id)
    old_mean=accepted.result['control_mean']
    roster=client.get(f'/plans/{p.id}/roster',headers=admin_headers).json()
    member=next(a for a in roster['assignments'] if a['status']=='locked')
    sid=member['student']['id']
    payload={'code':member['student']['code'],'name':member['student']['name'],'campus':member['student']['campus'],'group':'control','score':99.0,'absent':False}
    assert client.put(f'/students/{sid}',json=payload,headers=admin_headers).status_code==200  # 成绩仍可修订
    with SessionLocal() as session:
        assert session.get(Report,accepted.id).result['control_mean']==old_mean
    revised=compute(p.id)
    scores={x['code']:x['score'] for x in revised.result['sample_snapshot']}
    assert scores[member['student']['code']]==99.0                # 新检验采用修订后成绩

def test_campus_source_still_computes(client,admin_headers,db):
    for i in range(4): add_student(db,f'C{i+1:03}',group='control',score=70+i)
    for i in range(4): add_student(db,f'T{i+1:03}',group='intervention',score=80+i)
    p=add_plan(db,'传统方案')
    done=compute(p.id,source='campus')
    assert done.status=='completed' and done.result['source']=='campus'
    assert done.result['control_n']==4 and done.result['intervention_n']==4

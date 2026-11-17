"""招募 API：生命周期、幂等、并发不超占、失败恢复、退出与补招。"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from src.config.database import SessionLocal
from src.models.entities import Assignment,RecruitBatch
from tests.conftest import add_student,add_plan

def key(): return uuid.uuid4().hex

def recruit(client,headers,kind='initial',idem=None,plan_ids=None):
    payload={'kind':kind,'idempotency_key':idem or key()}
    if plan_ids: payload['plan_ids']=plan_ids
    return client.post('/recruitments',json=payload,headers=headers)

def active_map():
    with SessionLocal() as db:
        rows=db.scalars(select(Assignment).where(Assignment.status.in_(('pending','locked')))).all()
        return [(a.student_id,a.plan_id,a.group,a.status) for a in rows]

def test_create_lock_flow_and_shortfall_reasons(client,admin_headers,db):
    for i in range(6): add_student(db,f'S{i+1:03}',campus='城东',score=70+i)
    pa=add_plan(db,'方案A',campus='城东',tc=2,ti=2)
    pb=add_plan(db,'方案B',campus='全部',tc=2,ti=2)
    r=recruit(client,admin_headers)
    assert r.status_code==201,r.text
    batch=r.json()
    assert batch['status']=='pending'
    assert len(batch['assignments'])==6            # 容量 8、候选 6：各 3 人
    summary={p['plan_id']:p for p in batch['summary']['plans']}
    assert summary[pa.id]['assigned_control']+summary[pa.id]['assigned_intervention']==3
    assert summary[pb.id]['reasons']                # 缺额原因已列明
    assert '共享候选' in summary[pb.id]['reasons'][0]['message']
    ov=client.get('/recruitment/overview',headers=admin_headers).json()
    assert ov['candidates_free']==0
    r=client.post(f"/recruitments/{batch['id']}/lock",headers=admin_headers)
    assert r.status_code==200 and r.json()['status']=='locked'
    ov={p['plan_id']:p for p in client.get('/recruitment/overview',headers=admin_headers).json()['plans']}
    assert ov[pa.id]['locked_control']+ov[pa.id]['locked_intervention']==3
    roster=client.get(f'/plans/{pa.id}/roster',headers=admin_headers).json()
    assert len([a for a in roster['assignments'] if a['status']=='locked'])==3

def test_insufficient_pool_reason(client,admin_headers,db):
    for i in range(3): add_student(db,f'P{i+1:03}',campus='滨江')
    p=add_plan(db,'滨江方案',campus='滨江',tc=3,ti=3)
    batch=recruit(client,admin_headers).json()
    summary={x['plan_id']:x for x in batch['summary']['plans']}[p.id]
    assert summary['assigned_control']+summary['assigned_intervention']==3
    assert any(r['code']=='INSUFFICIENT_POOL' for r in summary['reasons'])

def test_idempotent_create_and_lock(client,admin_headers,db):
    for i in range(6): add_student(db,f'S{i+1:03}')
    add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    idem=key()
    r1=recruit(client,admin_headers,idem=idem)
    r2=recruit(client,admin_headers,idem=idem)     # 同次重试
    assert r1.json()['id']==r2.json()['id']
    with SessionLocal() as db2:
        assert len(db2.scalars(select(RecruitBatch)).all())==1
        assert len(db2.scalars(select(Assignment)).all())==4   # 不重复占位
    bid=r1.json()['id']
    for _ in range(2):
        r=client.post(f'/recruitments/{bid}/lock',headers=admin_headers)
        assert r.status_code==200 and r.json()['status']=='locked'
    with SessionLocal() as db2:
        assert len(db2.scalars(select(Assignment).where(Assignment.status=='locked')).all())==4

def test_concurrent_create_same_key(client,admin_headers,db):
    for i in range(8): add_student(db,f'S{i+1:03}')
    add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    idem=key()
    with ThreadPoolExecutor(8) as ex:
        results=list(ex.map(lambda _:recruit(client,admin_headers,idem=idem),range(8)))
    assert all(r.status_code==201 for r in results)
    assert len({r.json()['id'] for r in results})==1
    with SessionLocal() as db2:
        assert len(db2.scalars(select(RecruitBatch)).all())==1
        assert len(db2.scalars(select(Assignment)).all())==4

def test_concurrent_create_competing_keys_no_overbooking(client,admin_headers,db):
    for i in range(6): add_student(db,f'S{i+1:03}',campus='城东')
    add_plan(db,'方案A',campus='城东',tc=2,ti=2)
    add_plan(db,'方案B',campus='全部',tc=2,ti=2)
    with ThreadPoolExecutor(6) as ex:
        results=list(ex.map(lambda _:recruit(client,admin_headers),range(6)))
    assert all(r.status_code==201 for r in results)
    rows=active_map()
    students=[r[0] for r in rows]
    assert len(students)==len(set(students))       # 每人同期只占一个名额
    assert len(rows)==6                            # 不超占：总名额不超过候选数
    per_group={}
    for _,pid,g,_ in rows: per_group[(pid,g)]=per_group.get((pid,g),0)+1
    assert all(n<=2 for n in per_group.values())   # 每组不超目标

def test_concurrent_lock_same_batch(client,admin_headers,db):
    for i in range(6): add_student(db,f'S{i+1:03}')
    add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    bid=recruit(client,admin_headers).json()['id']
    with ThreadPoolExecutor(8) as ex:
        results=list(ex.map(lambda _:client.post(f'/recruitments/{bid}/lock',headers=admin_headers),range(8)))
    assert all(r.status_code==200 for r in results)
    with SessionLocal() as db2:
        locked=db2.scalars(select(Assignment).where(Assignment.status=='locked')).all()
        assert len(locked)==4                      # 并发锁定不超占、不重复

def test_lock_failure_restores_then_retry(client,admin_headers,db):
    for i in range(6): add_student(db,f'S{i+1:03}')
    p=add_plan(db,'方案A',campus='全部',tc=2,ti=2)
    bid=recruit(client,admin_headers).json()['id']
    shrink={'title':'方案A','campus':'全部','exclude_absent':True,'description':'','target_control':1,'target_intervention':1}
    assert client.put(f'/plans/{p.id}',json=shrink,headers=admin_headers).status_code==200
    r=client.post(f'/recruitments/{bid}/lock',headers=admin_headers)
    assert r.status_code==409                      # 目标调低后锁定失败
    with SessionLocal() as db2:                    # 失败后恢复：批次与名额保持待分配
        assert db2.get(RecruitBatch,bid).status=='pending'
        assert len(db2.scalars(select(Assignment).where(Assignment.status=='pending')).all())==4
    restore={**shrink,'target_control':2,'target_intervention':2}
    assert client.put(f'/plans/{p.id}',json=restore,headers=admin_headers).status_code==200
    assert client.post(f'/recruitments/{bid}/lock',headers=admin_headers).status_code==200

def test_withdraw_releases_slot_for_supplementary(client,admin_headers,db):
    students=[add_student(db,f'S{i+1:03}',campus='城东',score=70+i) for i in range(6)]
    p=add_plan(db,'方案A',campus='城东',tc=2,ti=2)
    bid=recruit(client,admin_headers).json()['id']
    client.post(f'/recruitments/{bid}/lock',headers=admin_headers)
    roster=client.get(f'/plans/{p.id}/roster',headers=admin_headers).json()
    victim=next(a for a in roster['assignments'] if a['status']=='locked')
    r=client.post(f"/assignments/{victim['id']}/withdraw",headers=admin_headers)
    assert r.json()['status']=='withdrawn'
    ov=client.get('/recruitment/overview',headers=admin_headers).json()
    assert ov['candidates_free']==3                # 释放 1 + 未分配 2
    r=recruit(client,admin_headers,kind='supplementary')
    assert r.status_code==201
    supplement=r.json()
    assert len(supplement['assignments'])==1       # 只补空缺
    newcomer=supplement['assignments'][0]
    assert newcomer['student_code']!=victim['student']['code']  # 退出者不被同方案补回
    client.post(f"/recruitments/{supplement['id']}/lock",headers=admin_headers)
    roster=client.get(f'/plans/{p.id}/roster',headers=admin_headers).json()
    assert len([a for a in roster['assignments'] if a['status']=='locked'])==4
    assert len([a for a in roster['assignments'] if a['status']=='withdrawn'])==1

def test_recruitment_requires_targets(client,admin_headers,db):
    add_student(db,'S001')
    add_plan(db,'无目标方案')
    r=recruit(client,admin_headers)
    assert r.status_code==422

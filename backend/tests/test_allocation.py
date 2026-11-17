"""联合分配算法：先最大化最低达成比例，再最大化总人数。"""
from fractions import Fraction
from src.services.allocation import joint_allocate

def spec(pid,c,i): return {'id':pid,'caps':{'control':c,'intervention':i}}
def total(per_plan,pid): return sum(per_plan[pid].values())

def test_shared_candidates_max_min_ratio_then_total():
    # 6 名共享候选；两方案容量各 4，先到先占会让后者全空
    cands=list(range(1,7))
    plans=[spec(1,2,2),spec(2,2,2)]
    eligible={1:set(cands),2:set(cands)}
    assignments,per_plan,r=joint_allocate(plans,cands,eligible)
    assert r==Fraction(3,4)                      # 最低达成比例最大化：各 3/4
    assert total(per_plan,1)==3 and total(per_plan,2)==3
    assert len(assignments)==6                   # 总人数最大化
    assert len({a[0] for a in assignments})==6   # 每人只占一个名额
    for pid in (1,2):
        assert per_plan[pid]['control']<=2 and per_plan[pid]['intervention']<=2

def test_total_maximized_under_ratio_floor():
    # 4 名共享候选；A 容量 2、B 容量 4：比例下限 1/2 下总人数应为 4
    cands=list(range(1,5))
    plans=[spec(1,1,1),spec(2,2,2)]
    eligible={1:set(cands),2:set(cands)}
    assignments,per_plan,r=joint_allocate(plans,cands,eligible)
    assert r==Fraction(1,2)
    assert len(assignments)==4
    assert total(per_plan,1)>=1 and total(per_plan,2)>=2

def test_disjoint_pools_both_full():
    plans=[spec(1,2,2),spec(2,1,1)]
    eligible={1:{1,2,3,4},2:{5,6}}
    assignments,per_plan,r=joint_allocate(plans,[1,2,3,4,5,6],eligible)
    assert r==Fraction(1)
    assert total(per_plan,1)==4 and total(per_plan,2)==2

def test_group_caps_and_single_slot():
    plans=[spec(1,1,1)]
    eligible={1:{1,2,3,4,5}}
    assignments,per_plan,r=joint_allocate(plans,[1,2,3,4,5],eligible)
    assert len(assignments)==2
    assert per_plan[1]=={'control':1,'intervention':1}

def test_insufficient_pool_ratio_zero_still_fills_others():
    # B 无合格候选（最低比例 0），A 仍应招满
    plans=[spec(1,1,1),spec(2,1,1)]
    eligible={1:{1,2,3},2:set()}
    assignments,per_plan,r=joint_allocate(plans,[1,2,3],eligible)
    assert r==Fraction(0)
    assert total(per_plan,1)==2 and total(per_plan,2)==0

def test_empty_inputs():
    assert joint_allocate([],[],{})==([],{},Fraction(0))
    assignments,per_plan,r=joint_allocate([spec(1,1,1)],[],{1:set()})
    assert assignments==[] and r==Fraction(0)

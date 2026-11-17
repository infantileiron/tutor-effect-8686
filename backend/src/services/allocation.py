"""多方案联合招募的公平分配。

目标按字典序：
1. 最大化各方案最低达成比例（本轮分配人数 / 剩余目标人数）；
2. 在此前提下最大化总分配人数。

约束：每名候选最多占一个名额；每组人数不超过该组剩余目标。
方法：最大流建模，比例用分数精确二分，下界可行性用超源超汇变换；
找到最优比例后固定各方案下界，继续在残余网络上增广以求总人数最大。
"""
from fractions import Fraction
from math import ceil

GROUPS=('control','intervention')

class _Dinic:
    def __init__(self):
        self.adj={}
    def add(self,u,v,c):
        self.adj.setdefault(v,[])
        self.adj.setdefault(u,[]).append([v,c,len(self.adj[v])])
        self.adj[v].append([u,0,len(self.adj[u])-1])
        return u,len(self.adj[u])-1
    def remove(self,u,i):
        v,_,rev=self.adj[u][i]
        self.adj[u][i][1]=0
        self.adj[v][rev][1]=0
    def max_flow(self,s,t,limit=None):
        flow=0
        while limit is None or flow<limit:
            level={s:0};queue=[s]
            for u in queue:
                for v,cap,_ in self.adj.get(u,[]):
                    if cap>0 and v not in level:
                        level[v]=level[u]+1;queue.append(v)
            if t not in level: break
            it={u:0 for u in level}
            def dfs(u,f):
                if u==t: return f
                edges=self.adj.get(u,[])
                while it[u]<len(edges):
                    i=it[u];v,cap,rev=edges[i]
                    if cap>0 and level.get(v)==level[u]+1:
                        d=dfs(v,min(f,cap))
                        if d>0:
                            edges[i][1]-=d
                            self.adj[v][rev][1]+=d
                            return d
                    it[u]+=1
                return 0
            while True:
                pushed=dfs(s,(limit-flow) if limit is not None else 1<<60)
                if pushed<=0: break
                flow+=pushed
        return flow

def _build(plans,candidates,eligible,lower=None):
    """构造网络。lower: {plan_id: 下界} 时启用超源超汇。"""
    S,T,SS,TT=0,1,2,3
    stu_node={sid:4+i for i,sid in enumerate(candidates)}
    base=4+len(candidates)
    grp_node={};plan_node={}
    for p in plans:
        for g in GROUPS:
            grp_node[(p['id'],g)]=base;base+=1
        plan_node[p['id']]=base;base+=1
    d=_Dinic();ephemeral=[]
    for sid,node in stu_node.items(): d.add(S,node,1)
    for p in plans:
        pid=p['id']
        for sid in eligible.get(pid,()):
            if sid not in stu_node: continue
            for g in GROUPS:
                d.add(stu_node[sid],grp_node[(pid,g)],1)
        for g in GROUPS:
            d.add(grp_node[(pid,g)],plan_node[pid],p['caps'][g])
        total=p['caps']['control']+p['caps']['intervention']
        lo=lower.get(pid,0) if lower else 0
        d.add(plan_node[pid],T,total-lo)
        if lo:
            ephemeral.append(d.add(SS,T,lo))
            ephemeral.append(d.add(plan_node[pid],TT,lo))
    if lower and any(lower.values()):
        ephemeral.append(d.add(T,S,1<<30))
    return d,S,T,SS,TT,stu_node,grp_node,plan_node,ephemeral

def _feasible(plans,candidates,eligible,lower):
    need=sum(lower.values())
    if need==0: return True
    d,_,_,SS,TT,*_=_build(plans,candidates,eligible,lower)
    return d.max_flow(SS,TT,limit=need)==need

def joint_allocate(plans,candidates,eligible):
    """联合分配。

    plans: [{'id':..,'caps':{'control':c,'intervention':i}}]，caps 为剩余目标人数；
    candidates: 可分配学员 id 列表（当前无任何有效名额）；
    eligible: {plan_id: {student_id,...}} 合格候选集合。

    返回 (assignments, per_plan, min_ratio)：
    assignments 为 (student_id, plan_id, group) 列表；
    per_plan 为 {plan_id: {'control':n,'intervention':n}}；
    min_ratio 为各方案最低达成比例（Fraction）。
    """
    plans=[p for p in plans if p['caps']['control']+p['caps']['intervention']>0]
    if not plans or not candidates:
        return [],{p['id']:{'control':0,'intervention':0} for p in plans},Fraction(0)
    totals={p['id']:p['caps']['control']+p['caps']['intervention'] for p in plans}
    ratios=sorted({Fraction(k,c) for c in totals.values() for k in range(c+1)})
    lo,hi=0,len(ratios)-1
    while lo<hi:
        mid=(lo+hi+1)//2
        r=ratios[mid]
        if _feasible(plans,candidates,eligible,{pid:ceil(r*c) for pid,c in totals.items()}): lo=mid
        else: hi=mid-1
    best=ratios[lo]
    lower={pid:ceil(best*c) for pid,c in totals.items()}
    d,S,T,SS,TT,stu_node,grp_node,plan_node,ephemeral=_build(plans,candidates,eligible,lower)
    if sum(lower.values()):
        d.max_flow(SS,TT,limit=sum(lower.values()))
        for u,i in ephemeral: d.remove(u,i)
    d.max_flow(S,T)
    assignments=[]
    per_plan={p['id']:{'control':0,'intervention':0} for p in plans}
    node_plan={node:pid for (pid,g),node in grp_node.items()}
    node_group={node:g for (pid,g),node in grp_node.items()}
    for sid,node in stu_node.items():
        for v,cap,_ in d.adj.get(node,[]):
            if cap==0 and v in node_plan:
                pid=node_plan[v];g=node_group[v]
                assignments.append((sid,pid,g))
                per_plan[pid][g]+=1
    return assignments,per_plan,best

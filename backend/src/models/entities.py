from sqlalchemy import String,Float,Boolean,Integer,ForeignKey,JSON,Text,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True)
    role:Mapped[str]=mapped_column(String(20))
    password_hash:Mapped[str]=mapped_column(String(200))
class Student(Base):
    __tablename__='students'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    name:Mapped[str]=mapped_column(String(80))
    campus:Mapped[str]=mapped_column(String(50))
    group:Mapped[str]=mapped_column(String(20))
    score:Mapped[float|None]=mapped_column(Float,nullable=True)
    absent:Mapped[bool]=mapped_column(Boolean,default=False)
class Plan(Base):
    __tablename__='plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    campus:Mapped[str]=mapped_column(String(50),default='全部')
    exclude_absent:Mapped[bool]=mapped_column(Boolean,default=True)
    description:Mapped[str]=mapped_column(Text,default='')
    target_control:Mapped[int]=mapped_column(Integer,default=0)
    target_intervention:Mapped[int]=mapped_column(Integer,default=0)
class Report(Base):
    __tablename__='reports'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('plans.id'))
    status:Mapped[str]=mapped_column(String(20),default='queued')
    source:Mapped[str]=mapped_column(String(20),default='campus')
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    conclusion:Mapped[str]=mapped_column(Text,default='')
    published:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[str]=mapped_column(String(40))
class Audit(Base):
    __tablename__='audit_logs'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(120))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[str]=mapped_column(String(40))
class RecruitBatch(Base):
    __tablename__='recruit_batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    kind:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(20),default='pending')
    idempotency_key:Mapped[str]=mapped_column(String(80),unique=True)
    summary:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[str]=mapped_column(String(40))
    locked_at:Mapped[str]=mapped_column(String(40),default='')
class Assignment(Base):
    __tablename__='assignments'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('recruit_batches.id'))
    plan_id:Mapped[int]=mapped_column(ForeignKey('plans.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('students.id'))
    group:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(20),default='pending')
    created_at:Mapped[str]=mapped_column(String(40))
    updated_at:Mapped[str]=mapped_column(String(40))
    __table_args__=(Index('uq_assignment_active_student','student_id',unique=True,sqlite_where=text("status IN ('pending','locked')"),postgresql_where=text("status IN ('pending','locked')")),)

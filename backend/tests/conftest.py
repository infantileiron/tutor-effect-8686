import os,sys,tempfile,pathlib
_tmp=tempfile.mkdtemp(prefix='tutor-test-')
os.environ['DATABASE_URL']=f"sqlite:///{_tmp}/test.db"
os.environ['REDIS_URL']='redis://127.0.0.1:6390/0'
os.environ['JWT_SECRET']='test-secret'
os.environ['SEED_DEMO']='false'
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from src.config.database import Base,engine,SessionLocal
from src.models.entities import User,Student,Plan
from src.utils.security import hash_password,token_for
from sqlalchemy import select

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield

@pytest.fixture(autouse=True)
def fake_queue(monkeypatch):
    import types
    from src.services import reports
    stub=types.SimpleNamespace(lpush=lambda *a,**k:None,brpop=lambda *a,**k:None,ping=lambda:True)
    monkeypatch.setattr(reports,'queue',stub)
    return stub

@pytest.fixture
def db():
    with SessionLocal() as session: yield session

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.main import app
    with TestClient(app) as c: yield c

@pytest.fixture
def admin_headers(client):
    with SessionLocal() as session:
        session.add(User(email='admin@test.local',role='admin',password_hash=hash_password('Test123!')))
        session.commit()
        user=session.scalar(select(User).where(User.email=='admin@test.local'))
        token=token_for(user)
    return {'Authorization':f'Bearer {token}'}

def add_student(db,code,campus='城东',group='control',score=80.0,absent=False):
    s=Student(code=code,name='学员'+code,campus=campus,group=group,score=score,absent=absent)
    db.add(s);db.commit();db.refresh(s)
    return s

def add_plan(db,title,campus='全部',tc=0,ti=0,exclude_absent=True):
    p=Plan(title=title,campus=campus,exclude_absent=exclude_absent,description='',target_control=tc,target_intervention=ti)
    db.add(p);db.commit();db.refresh(p)
    return p

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
url=os.environ['DATABASE_URL']
connect_args={'check_same_thread':False,'timeout':15} if url.startswith('sqlite') else {}
engine=create_engine(url,pool_pre_ping=True,connect_args=connect_args)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
def get_db():
    with SessionLocal() as db: yield db

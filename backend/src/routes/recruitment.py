from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import RecruitmentInput
from src.services import recruitment
router=APIRouter()
@router.get('/recruitment/overview')
def overview(db=Depends(get_db),user=Depends(current_user)): return recruitment.overview(db)
@router.post('/recruitments',status_code=201)
def create(data:RecruitmentInput,db=Depends(get_db),user=Depends(editor)): return recruitment.batch_detail(db,recruitment.create_recruitment(db,data).id)
@router.get('/recruitments')
def batches(db=Depends(get_db),user=Depends(current_user)): return recruitment.list_batches(db)
@router.get('/recruitments/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)): return recruitment.batch_detail(db,id)
@router.post('/recruitments/{id}/lock')
def lock(id:int,db=Depends(get_db),user=Depends(editor)): return recruitment.batch_detail(db,recruitment.lock_batch(db,id).id)
@router.post('/assignments/{id}/withdraw')
def withdraw_assignment(id:int,db=Depends(get_db),user=Depends(editor)): return {'id':id,'status':recruitment.withdraw(db,id).status}
@router.get('/plans/{id}/roster')
def plan_roster(id:int,db=Depends(get_db),user=Depends(current_user)): return recruitment.roster(db,id)

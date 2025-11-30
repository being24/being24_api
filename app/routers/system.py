from fastapi import APIRouter
from ..internal.ayame_update import ayame_update

router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
)


@router.get("/update_database")
async def update_database(password: str):
    if ayame_update.get_update_password() == password:
        return await ayame_update.update_database()
    else:
        return False


"""
@router.get("/convert_database")
async def convert_database():
    await ayame_update.convert_database_type()
"""
"""
@router.get("/fix_test")
async def fix_test():
    return await ayame_fix.test()
"""

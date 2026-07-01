from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Package
from schemas import PackageCreate, PackageOut, PackageDetailOut

router = APIRouter(prefix="/api/packages", tags=["Package Registry"])

@router.get("", response_model=list[PackageOut])
async def list_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).order_by(Package.name))
    return result.scalars().all()

@router.post("", response_model=PackageOut, status_code=201)
async def publish_package(data: PackageCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Package).where(Package.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Package '{data.name}' already exists")
    pkg = Package(
        name=data.name,
        version=data.version,
        description=data.description,
        author=data.author,
        source_content=data.source_content,
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return pkg

@router.get("/{name}", response_model=PackageOut)
async def get_package(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.name == name))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, f"Package '{name}' not found")
    return pkg

@router.get("/{name}/download", response_model=PackageDetailOut)
async def download_package(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.name == name))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, f"Package '{name}' not found")
    return pkg

@router.delete("/{name}", status_code=204)
async def delete_package(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.name == name))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, f"Package '{name}' not found")
    await db.delete(pkg)
    await db.commit()

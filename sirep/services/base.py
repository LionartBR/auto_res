from contextlib import contextmanager
from typing import Iterable, Dict, Any
from sqlalchemy.orm import Session
from sirep.infra.db import SessionLocal
from sirep.infra.repositories import PlanRepository, EventRepository, JobRunRepository
from sirep.domain.enums import Step

@contextmanager
def unit_of_work():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

class ServiceResult(Dict[str, Any]): ...
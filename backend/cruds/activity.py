from datetime import date, datetime, timedelta
from typing import Optional

from backend import models
from backend.schemas import activities as schemas
from sqlalchemy.orm import Session


def get_activity_in_schema(type: str):
    if type == "work":
        return schemas.Work
    elif type == "meeting":
        return schemas.Meeting
    elif type == "shopping":
        return schemas.Shopping
    elif type == "studying":
        return schemas.Studying
    elif type == "sport":
        return schemas.Sport
    elif type == "other":
        return schemas.OtherActivity
    else:
        return None


def get_activity_out_schema(type: str):
    if type == "work":
        return schemas.WorkOut
    elif type == "meeting":
        return schemas.MeetingOut
    elif type == "shopping":
        return schemas.ShoppingOut
    elif type == "studying":
        return schemas.StudyingOut
    elif type == "sport":
        return schemas.SportOut
    elif type == "other":
        return schemas.OtherActivityOut
    else:
        return None


def get_activity_model(type: str):
    if type == "work":
        return models.Work
    elif type == "meeting":
        return models.Meeting
    elif type == "shopping":
        return models.Shopping
    elif type == "studying":
        return models.Studying
    elif type == "sport":
        return models.Sport
    elif type == "other":
        return models.OtherActivity
    else:
        return None


def is_periodic(activity) -> bool:
    return not (activity.period is None)


def update_periodic_activity(activity) -> None:
    while (
        activity.processing_date < date.today()
        and activity.processing_date <= activity.end_time.date()
    ):
        activity.processing_date += activity.period


def get_full_activity(db: Session, activity) -> list:
    type = activity.activity_type

    in_schema = get_activity_in_schema(type)
    out_schema = get_activity_out_schema(type)
    model = get_activity_model(type)

    activity_ext = db.query(model).filter(model.activity_id == activity.id).first()

    sch_base = schemas.ActivityOut(**activity.__dict__)
    sch_ext = in_schema(**activity_ext.__dict__)

    return out_schema(**sch_base.dict(), **sch_ext.dict())


def is_periodic_activity_in_interval(
    activity,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    if start_time is None and end_time is None:
        return True

    time_window = (activity.end_time - activity.start_time) % timedelta(days=1)

    time = activity.start_time
    while time < activity.end_time:
        _start_time = time
        _end_time = _start_time + time_window

        if start_time and end_time:
            if _start_time >= end_time:
                return False

            if _end_time > start_time:
                return True
        elif start_time:
            if _end_time > start_time:
                return True
        elif end_time:
            return _start_time < end_time

        time += activity.period

    return False


def get(
    db: Session, user_id: int, activity_id: int, full: bool = False
) -> Optional[schemas.ActivityOut]:
    activity = (
        db.query(models.Activity)
        .filter(models.Activity.user_id == user_id)
        .filter(models.Activity.id == activity_id)
        .one_or_none()
    )

    if full:
        activity = get_full_activity(db, activity)

    return activity


def list(
    db: Session,
    user_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    completed: Optional[bool] = None,
) -> list:
    queries = [models.Activity.user_id == user_id]

    if start_time:
        queries.append(models.Activity.end_time > start_time)
    if end_time:
        queries.append(models.Activity.start_time < end_time)
    if not (completed is None):
        if completed:
            queries.append(models.Activity.completed == "выполнено")
        else:
            queries.append(models.Activity.completed == "не выполнено")

    activities = db.query(models.Activity).filter(*queries).all()

    for activity in activities:
        if is_periodic(activity):
            update_periodic_activity(activity)
    db.commit()

    activities = filter(
        lambda a: not is_periodic(a)
        or is_periodic_activity_in_interval(a, start_time, end_time),
        activities,
    )

    out_activities = [get_full_activity(db, activity) for activity in activities]

    return out_activities


def create(db: Session, activity: schemas.FullActivityIn, user_id: int) -> None:
    row_activity = schemas.ActivityIn(**activity.dict())

    activity_base = models.Activity(**row_activity.dict(), user_id=user_id)

    schema = get_activity_in_schema(row_activity.activity_type)
    model = get_activity_model(row_activity.activity_type)

    if schema is None or model is None:
        raise ValueError("Unsupported action type")

    activity_ext = model(**schema(**activity.dict()).dict(), activity=activity_base)

    db.add(activity_base)
    db.add(activity_ext)
    db.commit()


def update(
    db: Session, activity: schemas.FullActivityUpdate, activity_id: int, user_id: int
) -> None:
    activity_base_update = schemas.ActivityUpdate(**activity.dict()).dict(
        exclude_none=True
    )

    if activity_base_update:
        db.query(models.Activity).filter(models.Activity.user_id == user_id).filter(
            models.Activity.id == activity_id
        ).update(activity_base_update)

    activity_type = (
        db.query(models.Activity.activity_type)
        .filter(models.Activity.user_id == user_id)
        .filter(models.Activity.id == activity_id)
        .first()
        .activity_type
    )

    schema = get_activity_in_schema(activity_type)
    model = get_activity_model(activity_type)

    if schema is None or model is None:
        raise ValueError("Unsupported action type")

    activity_ext_update = schema(**activity.dict()).dict(exclude_none=True)

    if activity_ext_update:
        db.query(model).filter(model.activity_id == activity_id).update(
            activity_ext_update
        )

    db.commit()


def delete(db: Session, activity_id: int, user_id: int) -> None:
    db.query(models.Activity).filter(models.Activity.user_id == user_id).filter(
        models.Activity.id == activity_id
    ).delete()
    db.commit()

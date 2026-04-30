import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.services.matrix import get_planning_matrix
from app.services.roster_matrix import get_roster_matrix


def _doctor_label(doctor) -> str:
    return f"{doctor.first_name} {doctor.last_name}".strip()


def export_matrix_csv(db: Session, planning_period_id: int, *, shift_group_id: int | None = None) -> str:
    matrix = get_planning_matrix(db, planning_period_id, shift_group_id=shift_group_id)
    cells = {(cell.cell_date, cell.doctor_id): cell for cell in matrix.cells}
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", *[_doctor_label(doctor) for doctor in matrix.doctors]])
    for day in matrix.days:
        row = [day.date.isoformat()]
        for doctor in matrix.doctors:
            cell = cells.get((day.date, doctor.id))
            if cell is None:
                row.append("")
                continue
            value = cell.status
            if cell.comment:
                value = f"{value} - {cell.comment}"
            row.append(value)
        writer.writerow(row)
    return buffer.getvalue()


def export_roster_matrix_csv(db: Session, planning_period_id: int, *, shift_group_id: int | None = None) -> str:
    matrix = get_roster_matrix(db, planning_period_id, shift_group_id=shift_group_id)
    slots_by_day = {}
    for slot in matrix.slots:
        slots_by_day.setdefault(slot.slot_date, []).append(slot)
    assignments = {assignment.roster_slot_id: assignment for assignment in matrix.assignments}
    doctors = {doctor.id: doctor for doctor in matrix.doctors}

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "slot", "start", "end", "doctor", "template_code", "variant", "category"])
    for day in matrix.days:
        for slot in slots_by_day.get(day.date, []):
            assignment = assignments.get(slot.id) if slot else None
            doctor = doctors.get(assignment.doctor_id) if assignment else None
            writer.writerow(
                [
                    day.date.isoformat(),
                    slot.label or "",
                    slot.starts_at.isoformat() if slot.starts_at else "",
                    slot.ends_at.isoformat() if slot.ends_at else "",
                    _doctor_label(doctor) if doctor else "",
                    slot.template_code or "",
                    slot.variant_label or "",
                    slot.category or "",
                ]
            )
    return buffer.getvalue()

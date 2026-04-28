import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.services.matrix import get_planning_matrix
from app.services.planning import list_roster_assignments
from app.services.roster_matrix import get_roster_matrix


def export_matrix_csv(db: Session, planning_period_id: int) -> str:
    matrix = get_planning_matrix(db, planning_period_id)
    cells = {(cell.cell_date, cell.doctor_id): cell for cell in matrix.cells}
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", *[doctor.name for doctor in matrix.doctors]])
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


def export_roster_csv(db: Session, planning_period_id: int) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "doctor", "doctor_email", "shift_code", "shift_de", "shift_en", "note"])
    for assignment in list_roster_assignments(db, planning_period_id=planning_period_id):
        writer.writerow(
            [
                assignment.assignment_date.isoformat(),
                assignment.doctor.name,
                assignment.doctor.email,
                assignment.shift_type.code,
                assignment.shift_type.name_de,
                assignment.shift_type.name_en,
                assignment.note or "",
            ]
        )
    return buffer.getvalue()


def export_roster_matrix_csv(db: Session, planning_period_id: int) -> str:
    matrix = get_roster_matrix(db, planning_period_id)
    slots = {(slot.slot_date, slot.shift_type_id, slot.position): slot for slot in matrix.slots}
    assignments = {assignment.roster_slot_id: assignment for assignment in matrix.assignments}
    doctors = {doctor.id: doctor for doctor in matrix.doctors}

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", *[shift_type.name_de for shift_type in matrix.shift_types]])
    for day in matrix.days:
        row = [day.date.isoformat()]
        for shift_type in matrix.shift_types:
            slot = slots.get((day.date, shift_type.id, 1))
            assignment = assignments.get(slot.id) if slot else None
            doctor = doctors.get(assignment.doctor_id) if assignment else None
            value = doctor.name if doctor else ""
            row.append(value)
        writer.writerow(row)
    return buffer.getvalue()

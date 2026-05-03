import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.services.matrix import get_planning_matrix
from app.services.roster_matrix import get_roster_matrix


def _team_member_label(member) -> str:
    return f"{member.first_name} {member.last_name}".strip()


def export_matrix_csv(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> str:
    matrix = get_planning_matrix(db, planning_period_id, organization_id=organization_id, shift_group_id=shift_group_id)
    cells = {(cell.cell_date, cell.team_member_id): cell for cell in matrix.cells}
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", *[_team_member_label(m) for m in matrix.team_members]])
    for day in matrix.days:
        row = [day.date.isoformat()]
        for m in matrix.team_members:
            cell = cells.get((day.date, m.id))
            if cell is None:
                row.append("")
                continue
            value = cell.status
            if cell.comment:
                value = f"{value} - {cell.comment}"
            row.append(value)
        writer.writerow(row)
    return buffer.getvalue()


def export_roster_matrix_csv(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> str:
    matrix = get_roster_matrix(db, planning_period_id, organization_id=organization_id, shift_group_id=shift_group_id)
    slots_by_day = {}
    for slot in matrix.slots:
        slots_by_day.setdefault(slot.slot_date, []).append(slot)
    assignments = {assignment.roster_slot_id: assignment for assignment in matrix.assignments}
    members = {m.id: m for m in matrix.team_members}

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "slot", "start", "end", "team_member", "template_code", "variant", "category"])
    for day in matrix.days:
        for slot in slots_by_day.get(day.date, []):
            assignment = assignments.get(slot.id) if slot else None
            member = members.get(assignment.team_member_id) if assignment else None
            writer.writerow(
                [
                    day.date.isoformat(),
                    slot.label or "",
                    slot.starts_at.isoformat() if slot.starts_at else "",
                    slot.ends_at.isoformat() if slot.ends_at else "",
                    _team_member_label(member) if member else "",
                    slot.template_code or "",
                    slot.variant_label or "",
                    slot.category or "",
                ]
            )
    return buffer.getvalue()

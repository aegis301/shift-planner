from sqlalchemy.orm import Session

from app.schemas import (
    TeamMemberPropertyDefinitionRead,
    TeamMemberPropertyMatrixMember,
    TeamMemberPropertyMatrixRead,
    TeamMemberPropertyMatrixValue,
)
from app.services.team_member_property_definitions import list_team_member_property_definitions
from app.services.team_member_property_values import property_value_maps_for_members
from app.services.team_members import list_team_members


def get_team_member_property_matrix(
    db: Session,
    *,
    organization_id: int,
    active_members_only: bool = True,
    active_definitions_only: bool = True,
) -> TeamMemberPropertyMatrixRead:
    definitions = sorted(
        list_team_member_property_definitions(
            db,
            organization_id=organization_id,
            active_only=active_definitions_only,
        ),
        key=lambda definition: (definition.display_order, definition.name.casefold(), definition.id),
    )
    members = list_team_members(
        db,
        organization_id=organization_id,
        active_only=active_members_only,
    )
    member_ids = {member.id for member in members}
    value_maps = property_value_maps_for_members(
        db,
        organization_id=organization_id,
        team_member_ids=member_ids,
    )
    definition_ids = {definition.id for definition in definitions}
    values = [
        TeamMemberPropertyMatrixValue(
            team_member_id=team_member_id,
            property_definition_id=definition_id,
            value=value,
        )
        for team_member_id, member_values in value_maps.items()
        for definition_id, value in member_values.items()
        if definition_id in definition_ids
    ]
    values.sort(key=lambda value: (value.team_member_id, value.property_definition_id))
    return TeamMemberPropertyMatrixRead(
        definitions=[
            TeamMemberPropertyDefinitionRead.model_validate(definition)
            for definition in definitions
        ],
        members=[
            TeamMemberPropertyMatrixMember(
                id=member.id,
                first_name=member.first_name,
                last_name=member.last_name,
                nickname=member.nickname,
                is_active=member.is_active,
            )
            for member in members
        ],
        values=values,
    )

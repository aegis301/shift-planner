export type RosterColumnSlot = {
  id: number;
  slot_date: string;
  shift_template_id?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
  position: number;
  template_code?: string | null;
  template_name?: string | null;
  category?: string | null;
};

export type RosterColumnTemplate = {
  id: number;
  code: string;
  name: string;
  category: string;
  display_order: number;
};

export type RosterGridColumn = {
  key: string;
  templateId: number | null;
  position: number;
  code: string;
  name: string;
  category: string;
};

export function rosterGridColumns(slots: RosterColumnSlot[], templates: RosterColumnTemplate[]): RosterGridColumn[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const maxPosition = new Map<number, number>();
  for (const slot of slots) {
    const templateId = slot.shift_template_id ?? -1;
    maxPosition.set(templateId, Math.max(maxPosition.get(templateId) ?? 0, slot.position));
  }
  const orderedIds = [...templates]
    .filter((template) => maxPosition.has(template.id))
    .sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name) || left.code.localeCompare(right.code))
    .map((template) => template.id);
  for (const templateId of [...maxPosition.keys()].sort((left, right) => left - right)) {
    if (!orderedIds.includes(templateId)) {
      orderedIds.push(templateId);
    }
  }
  const columns: RosterGridColumn[] = [];
  for (const templateId of orderedIds) {
    const count = maxPosition.get(templateId) ?? 0;
    const template = templateId === -1 ? null : templatesById.get(templateId);
    const sample = slots.find((slot) => (slot.shift_template_id ?? -1) === templateId);
    const code = template?.code ?? sample?.template_code ?? "?";
    const name = template?.name ?? sample?.template_name ?? code;
    const category = template?.category ?? sample?.category ?? "other";
    for (let position = 1; position <= count; position += 1) {
      columns.push({
        key: `${templateId}:${position}`,
        templateId: templateId === -1 ? null : templateId,
        position,
        code,
        name,
        category
      });
    }
  }
  return columns;
}

export function slotForColumn(slots: RosterColumnSlot[], date: string, column: RosterGridColumn): RosterColumnSlot | null {
  return (
    slots.find(
      (slot) => slot.slot_date === date && (slot.shift_template_id ?? null) === column.templateId && slot.position === column.position
    ) ?? null
  );
}

export function columnHeader(column: RosterGridColumn): string {
  return `${column.code} #${column.position}`;
}

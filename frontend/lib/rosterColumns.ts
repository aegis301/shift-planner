export type RosterColumnSlot = {
  id: number;
  slot_date: string;
  shift_template_id?: number | null;
  shift_variant_id?: number | null;
  variant_label?: string | null;
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
  variantId: number | null;
  position: number;
  code: string;
  name: string;
  variantLabel: string;
  category: string;
  displayOrder: number;
};

export function rosterGridColumns(slots: RosterColumnSlot[], templates: RosterColumnTemplate[]): RosterGridColumn[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const columns = new Map<string, RosterGridColumn>();
  for (const slot of slots) {
    const templateId = slot.shift_template_id ?? null;
    const variantId = slot.shift_variant_id ?? null;
    const key = `${templateId ?? -1}:${variantId ?? 0}:${slot.position}`;
    if (columns.has(key)) {
      continue;
    }
    const template = templateId == null ? undefined : templatesById.get(templateId);
    columns.set(key, {
      key,
      templateId,
      variantId,
      position: slot.position,
      code: template?.code ?? slot.template_code ?? "?",
      name: template?.name ?? slot.template_name ?? slot.template_code ?? "?",
      variantLabel: slot.variant_label?.trim() ?? "",
      category: template?.category ?? slot.category ?? "other",
      displayOrder: template?.display_order ?? 0
    });
  }
  return [...columns.values()].sort((left, right) => {
    return (
      left.displayOrder - right.displayOrder ||
      left.name.localeCompare(right.name) ||
      left.code.localeCompare(right.code) ||
      left.variantLabel.localeCompare(right.variantLabel) ||
      left.position - right.position ||
      (left.variantId ?? 0) - (right.variantId ?? 0)
    );
  });
}

export function slotForColumn(slots: RosterColumnSlot[], date: string, column: RosterGridColumn): RosterColumnSlot | null {
  return (
    slots.find(
      (slot) =>
        slot.slot_date === date &&
        (slot.shift_template_id ?? null) === column.templateId &&
        (slot.shift_variant_id ?? null) === column.variantId &&
        slot.position === column.position
    ) ?? null
  );
}

export function columnHeader(column: RosterGridColumn): string {
  const label = column.variantLabel ? `${column.code} ${column.variantLabel}` : column.code;
  return `${label} #${column.position}`;
}

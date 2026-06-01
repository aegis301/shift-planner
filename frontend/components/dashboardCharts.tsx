"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import type {
  MonthCategorySeries,
  MonthTemplateSeries,
  ShiftCategoryCount,
  ShiftTemplateCount,
} from "@/lib/dashboard";
import { formatMonthShort, shiftTemplateChartLabel } from "@/lib/dashboard";

const CHART_COLORS = ["#0f766e", "#e85d4c", "#6366f1", "#ca8a04", "#64748b"];

export function categoryLabel(locale: Locale, category: string): string {
  const map: Record<string, TranslationKey> = {
    bereitschaftsdienst: "onCallDutyCategory",
    rufdienst: "standbyDutyCategory",
    spaetdienst: "lateDutyCategory",
    other: "other",
  };
  const key = map[category];
  return key ? t(locale, key) : category;
}

type SimpleDatum = { name: string; value: number };

export function DashboardDonutChart({
  data,
  height = 220,
}: {
  data: SimpleDatum[];
  height?: number;
}) {
  if (data.length === 0) {
    return null;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} paddingAngle={2}>
          {data.map((_, index) => (
            <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function DashboardHorizontalBarChart({
  data,
  height = 260,
  yAxisWidth = 120,
}: {
  data: SimpleDatum[];
  height?: number;
  yAxisWidth?: number;
}) {
  if (data.length === 0) {
    return null;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="value" fill="#0f172a" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DashboardCategoryBarChart({
  locale,
  categories,
  height = 220,
}: {
  locale: Locale;
  categories: ShiftCategoryCount[];
  height?: number;
}) {
  if (categories.length === 0) {
    return <p className="text-sm text-slate-500">{t(locale, "noData")}</p>;
  }
  const data = categories.map((row) => ({
    name: categoryLabel(locale, row.category),
    value: row.count,
  }));
  return <DashboardHorizontalBarChart data={data} height={height} />;
}

export function DashboardStackedMonthChart({
  locale,
  series,
  height = 280,
}: {
  locale: Locale;
  series: MonthCategorySeries[];
  height?: number;
}) {
  const hasAnyShifts = series.some((month) => month.categories.some((row) => row.count > 0));
  if (!hasAnyShifts) {
    return null;
  }
  const categoryKeys = new Set<string>();
  for (const month of series) {
    for (const row of month.categories) {
      categoryKeys.add(row.category);
    }
  }
  const keys = [...categoryKeys];
  const data = series.map((month) => {
    const row: Record<string, string | number> = {
      label: formatMonthShort(locale, month.year, month.month),
    };
    for (const key of keys) {
      row[categoryLabel(locale, key)] = month.categories.find((c) => c.category === key)?.count ?? 0;
    }
    return row;
  });
  const labels = keys.map((key) => categoryLabel(locale, key));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Legend />
        {labels.map((label, index) => (
          <Bar key={label} dataKey={label} stackId="shifts" fill={CHART_COLORS[index % CHART_COLORS.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DashboardTemplateBarChart({
  locale,
  templates,
  height = 220,
}: {
  locale: Locale;
  templates: ShiftTemplateCount[];
  height?: number;
}) {
  if (templates.length === 0) {
    return <p className="text-sm text-slate-500">{t(locale, "noData")}</p>;
  }
  const data = templates.map((row) => ({
    name: shiftTemplateChartLabel(locale, row),
    value: row.count,
  }));
  return <DashboardHorizontalBarChart data={data} height={height} yAxisWidth={200} />;
}

export function DashboardStackedMonthTemplateChart({
  locale,
  series,
  height = 280,
}: {
  locale: Locale;
  series: MonthTemplateSeries[];
  height?: number;
}) {
  const hasAnyShifts = series.some((month) => month.templates.some((row) => row.count > 0));
  if (!hasAnyShifts) {
    return null;
  }
  const templateMeta = new Map<number, ShiftTemplateCount>();
  for (const month of series) {
    for (const row of month.templates) {
      templateMeta.set(row.shift_template_id, row);
    }
  }
  const keys = [...templateMeta.keys()].sort((left, right) =>
    shiftTemplateChartLabel(locale, templateMeta.get(left)!).localeCompare(
      shiftTemplateChartLabel(locale, templateMeta.get(right)!),
      locale === "de" ? "de" : "en"
    )
  );
  const data = series.map((month) => {
    const row: Record<string, string | number> = {
      label: formatMonthShort(locale, month.year, month.month),
    };
    for (const templateId of keys) {
      row[String(templateId)] = month.templates.find((t) => t.shift_template_id === templateId)?.count ?? 0;
    }
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Legend />
        {keys.map((templateId, index) => (
          <Bar
            key={templateId}
            dataKey={String(templateId)}
            name={shiftTemplateChartLabel(locale, templateMeta.get(templateId)!)}
            stackId="shifts"
            fill={CHART_COLORS[index % CHART_COLORS.length]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DashboardMonthLineChart({
  data,
  height = 220,
}: {
  data: { label: string; value: number }[];
  height?: number;
}) {
  if (data.length === 0) {
    return null;
  }
  const chartData = data.map((row) => ({ name: row.label, value: row.value }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Bar dataKey="value" fill="#0f766e" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Smartphone } from "lucide-react";
import { Card } from "@/components/Card";
import { apiFetch } from "@/lib/api";
import type { components } from "@/lib/api/schema";
import { t } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";

type DeviceSession = components["schemas"]["DeviceSessionRead"];

function platformLabel(locale: "de" | "en", platform: DeviceSession["platform"]): string {
  if (platform === "ios") return t(locale, "devicePlatformIos");
  if (platform === "android") return t(locale, "devicePlatformAndroid");
  if (platform === "web") return t(locale, "devicePlatformWeb");
  return t(locale, "devicePlatformOther");
}

function formatWhen(locale: "de" | "en", value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale === "de" ? "de-DE" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

export function SignedInDevicesCard({ locale }: { locale: "de" | "en" }) {
  const queryClient = useQueryClient();
  const devices = useQuery({
    queryKey: queryKeys.deviceSessions(),
    queryFn: () => apiFetch<DeviceSession[]>("/api/v1/auth/me/devices")
  });
  const revoke = useMutation({
    mutationFn: (id: number) => apiFetch<void>(`/api/v1/auth/me/devices/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.deviceSessions() });
    }
  });

  return (
    <Card>
      <div className="flex items-start gap-4">
        <Smartphone className="shrink-0 text-emerald-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold text-ink">{t(locale, "devicesTitle")}</h2>
          <p className="mt-2 text-sm text-slate-600">{t(locale, "devicesIntro")}</p>
          {devices.isError ? <p className="mt-4 text-sm text-red-600">{t(locale, "devicesError")}</p> : null}
          {devices.data && devices.data.length === 0 ? (
            <p className="mt-4 text-sm text-slate-600">{t(locale, "devicesEmpty")}</p>
          ) : null}
          {devices.data && devices.data.length > 0 ? (
            <ul className="mt-4 divide-y divide-slate-200">
              {devices.data.map((device) => (
                <li key={device.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">
                      {device.name}
                      <span className="ml-2 text-sm font-normal text-slate-600">
                        {platformLabel(locale, device.platform)}
                      </span>
                      {device.current ? (
                        <span className="ml-2 text-sm font-normal text-emerald-800">{t(locale, "devicesCurrent")}</span>
                      ) : null}
                    </p>
                    <p className="text-sm text-slate-600">
                      {t(locale, "devicesLastUsed", { when: formatWhen(locale, device.last_used_at) })}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="h-11 rounded-lg border border-slate-300 px-4 text-sm font-semibold text-ink hover:bg-slate-50 disabled:opacity-50"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate(device.id)}
                  >
                    {t(locale, "devicesRevoke")}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

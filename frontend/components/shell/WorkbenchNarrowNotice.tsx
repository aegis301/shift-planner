"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "@/components/LocaleProvider";
import { t, type Locale } from "@/lib/i18n";
import { isUserSession } from "@/lib/membershipRouting";

const STORAGE_KEY = "shift-planner-workbench-narrow-dismissed";

export function WorkbenchNarrowNotice({ locale }: { locale: Locale }) {
  const { me } = useSession();
  const [narrow, setNarrow] = useState(false);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const apply = () => setNarrow(query.matches);
    apply();
    query.addEventListener("change", apply);
    setDismissed(window.sessionStorage.getItem(STORAGE_KEY) === "1");
    return () => query.removeEventListener("change", apply);
  }, []);

  if (!narrow || dismissed) {
    return null;
  }
  const memberLink = me && isUserSession(me) && me.capabilities.team_member_portal;
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p>{t(locale, "workbenchNarrowNotice")}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {memberLink ? (
          <Link href="/my" className="inline-flex h-11 items-center rounded-lg bg-ink px-3 font-semibold text-white">
            {t(locale, "workbenchNarrowMemberLink")}
          </Link>
        ) : null}
        <button
          type="button"
          className="inline-flex h-11 items-center rounded-lg border border-amber-300 bg-white px-3 font-semibold"
          onClick={() => {
            window.sessionStorage.setItem(STORAGE_KEY, "1");
            setDismissed(true);
          }}
        >
          {t(locale, "workbenchNarrowContinue")}
        </button>
      </div>
    </div>
  );
}

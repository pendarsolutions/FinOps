import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { InventoryView } from "../api/types";
import { useI18n } from "../lib/i18n";
import { ConfirmedInventory } from "../components/Guard";
import { Button, Card, ErrorBox } from "../components/ui";
import { Icon } from "../components/Icon";

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ReportsInner({ inv }: { inv: InventoryView }) {
  const { t } = useI18n();
  const m = useMutation({
    mutationFn: async (lang: "fa" | "en") => {
      const blob = await api.report(inv.id, lang);
      saveBlob(blob, `finops-agent-${inv.id.slice(0, 8)}-${lang}.html`);
    },
  });
  return (
    <Card title={t("reportTitle")}>
      <p>{t("reportBody")}</p>
      <div className="row gap wrap">
        <Button variant="primary" busy={m.isPending && m.variables === "fa"} onClick={() => m.mutate("fa")}>
          <Icon name="download" /> {t("downloadFa")}
        </Button>
        <Button busy={m.isPending && m.variables === "en"} onClick={() => m.mutate("en")}>
          <Icon name="download" /> {t("downloadEn")}
        </Button>
      </div>
      <ErrorBox error={m.error} />
    </Card>
  );
}

export function ReportsPage() {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1>{t("navReports")}</h1>
      <ConfirmedInventory>{(inv) => <ReportsInner inv={inv} />}</ConfirmedInventory>
    </div>
  );
}

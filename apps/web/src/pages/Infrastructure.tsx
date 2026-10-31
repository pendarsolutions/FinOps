import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { InventoryView } from "../api/types";
import { useI18n } from "../lib/i18n";
import { useInventory, useInventoryMutation } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Builder } from "../components/Builder";
import { ReviewTable } from "../components/ReviewTable";
import { Badge, Button, Card, ErrorBox, Field, Loading, StatusChip, Tabs } from "../components/ui";
import { EmptyWorkspace } from "./Overview";

type Tab = "review" | "builder" | "chat" | "invoice";

function ChatEntry({ onCreated }: { onCreated: (v: InventoryView) => void }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [name, setName] = useState("Chat draft");
  const m = useInventoryMutation(() => api.fromChat(text, name), onCreated);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate(undefined);
  };
  return (
    <Card title={t("tabChat")}>
      <form className="stack" onSubmit={submit}>
        <Field label={t("chatPrompt")} htmlFor="chat-text" hint={t("chatNote")}>
          <textarea id="chat-text" rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("chatPlaceholder")} minLength={3} maxLength={8000} required />
        </Field>
        <Field label={t("inventoryName")} htmlFor="chat-name">
          <input id="chat-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <ErrorBox error={m.error} />
        <Button type="submit" variant="primary" busy={m.isPending} disabled={text.trim().length < 3}>
          {t("extract")}
        </Button>
      </form>
    </Card>
  );
}

function InvoiceEntry({ onCreated }: { onCreated: (v: InventoryView) => void }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("Invoice draft");
  const m = useInventoryMutation(() => api.fromInvoice(file!, name), onCreated);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) m.mutate(undefined);
  };
  return (
    <Card title={t("tabInvoice")}>
      <form className="stack" onSubmit={submit}>
        <Field label={t("invoiceFile")} htmlFor="inv-file" hint={t("invoiceNote")}>
          <input id="inv-file" type="file" accept=".pdf,.csv,application/pdf,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </Field>
        <Field label={t("inventoryName")} htmlFor="inv-name">
          <input id="inv-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <ErrorBox error={m.error} />
        <Button type="submit" variant="primary" busy={m.isPending} disabled={!file}>
          {t("upload")}
        </Button>
      </form>
    </Card>
  );
}

export function InfrastructurePage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const { activeId, setActiveId, inventoriesLoading } = useSession();
  const inv = useInventory(activeId);
  const tab = ((params.get("tab") as Tab) || (activeId ? "review" : "builder")) as Tab;
  const setTab = (k: Tab) => setParams({ tab: k }, { replace: true });
  const created = (v: InventoryView) => {
    setActiveId(v.id);
    setTab("review");
  };

  return (
    <div className="stack">
      <h1>{t("navInfrastructure")}</h1>
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { key: "review", label: t("tabReview") },
          { key: "builder", label: t("tabBuilder") },
          { key: "chat", label: t("tabChat") },
          { key: "invoice", label: t("tabInvoice") },
        ]}
      />
      {tab === "builder" && <Builder onCreated={created} />}
      {tab === "chat" && <ChatEntry onCreated={created} />}
      {tab === "invoice" && <InvoiceEntry onCreated={created} />}
      {tab === "review" &&
        (inventoriesLoading || inv.isLoading ? (
          <Loading />
        ) : !activeId ? (
          <EmptyWorkspace />
        ) : inv.error ? (
          <ErrorBox error={inv.error} onRetry={() => inv.refetch()} />
        ) : inv.data ? (
          <Card
            title={
              <>
                {inv.data.name}{" "}
                <StatusChip
                  tone={inv.data.status === "confirmed" ? "good" : "warn"}
                  label={inv.data.status === "confirmed" ? t("invStatusConfirmed") : t("invStatusDraft")}
                />{" "}
                <Badge>
                  {inv.data.source_type === "builder"
                    ? t("tabBuilder")
                    : inv.data.source_type === "chat"
                      ? t("tabChat")
                      : inv.data.source_type === "invoice"
                        ? t("tabInvoice")
                        : inv.data.source_type}
                </Badge>
              </>
            }
          >
            <ReviewTable inv={inv.data} />
          </Card>
        ) : null)}
    </div>
  );
}

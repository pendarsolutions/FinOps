import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AdvisorAnswer } from "../api/types";
import { useI18n } from "../lib/i18n";
import { useInventory } from "../lib/hooks";
import { Badge, Button, Drawer, ErrorBox } from "./ui";

interface Turn {
  q: string;
  a: AdvisorAnswer;
}

export function Advisor({ open, onClose, inventoryId }: { open: boolean; onClose: () => void; inventoryId: string }) {
  const { t, lang } = useI18n();
  const inv = useInventory(open ? inventoryId : null);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const m = useMutation({
    mutationFn: (question: string) => api.advisor(inventoryId, question, lang),
    onSuccess: (a, question) => {
      setTurns((ts) => [...ts, { q: question, a }]);
      setQ("");
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length >= 2) m.mutate(q.trim());
  };
  const notConfirmed = inv.data && inv.data.status !== "confirmed";

  return (
    <Drawer open={open} onClose={onClose} title={t("advisorTitle")}>
      <p className="muted">{t("advisorHint")}</p>
      {notConfirmed ? <div className="alert alert-warn">{t("needsConfirmedInv")}</div> : null}
      <div className="advisor-log" aria-live="polite">
        {turns.map((tn, i) => (
          <div key={i} className="turn">
            <div className="q">{tn.q}</div>
            <div className="a">
              <div className="pre">{tn.a.answer}</div>
              <div className="row gap wrap">
                {tn.a.guard.ok ? (
                  <Badge tone="good">✓ {t("guardOk")}</Badge>
                ) : (
                  <Badge tone="bad">
                    {t("guardFail")}: {(tn.a.guard.unsupported_numbers ?? []).join(", ")}
                  </Badge>
                )}
                <Badge>{tn.a.path}</Badge>
              </div>
              {tn.a.evidence_ids.length > 0 && (
                <div>
                  <small className="muted">{t("evidenceIds")}:</small>
                  <div className="chips" dir="ltr">
                    {tn.a.evidence_ids.map((id) => (
                      <code key={id} className="chip" title={id}>
                        {id.slice(0, 8)}
                      </code>
                    ))}
                  </div>
                </div>
              )}
              {tn.a.tool_calls.length > 0 && (
                <small className="muted" dir="ltr">
                  {t("toolCalls")}: {tn.a.tool_calls.map((c) => c.tool + (c.error ? " ⚠" : "")).join(", ")}
                </small>
              )}
            </div>
          </div>
        ))}
      </div>
      <ErrorBox error={m.error} />
      <form onSubmit={submit} className="stack">
        <label htmlFor="advisor-q" className="sr-only">
          {t("ask")}
        </label>
        <textarea id="advisor-q" rows={3} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("askPlaceholder")} maxLength={4000} />
        <Button type="submit" variant="primary" busy={m.isPending} disabled={q.trim().length < 2}>
          {t("ask")}
        </Button>
      </form>
    </Drawer>
  );
}

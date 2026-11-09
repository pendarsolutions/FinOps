import sprite from "@pendar/icons.svg";
import { ICONS, type IconName } from "@pendar/icons";

export type { IconName };

/** A Pendar icon from the generated sprite, in the colour of the text around it; arrows mirror in English. */
export function Icon({ name, label, className }: { name: IconName; label?: string; className?: string }) {
  return (
    <svg
      className={["icon", className ?? ""].filter(Boolean).join(" ")}
      data-mirror={ICONS[name] || undefined}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <use href={`${sprite}#${name}`} />
    </svg>
  );
}

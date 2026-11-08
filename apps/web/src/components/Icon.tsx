import sprite from "../pendar/icons.svg";
import { ICONS, type IconName } from "../pendar/icons";

export type { IconName };

/**
 * A Pendar icon from the generated sprite. It takes the colour of the text around it, and icons that point somewhere
 * (arrows, chevrons, external link…) mirror in left-to-right text. Without a label it is decorative.
 */
export function Icon({ name, label, small, className }: { name: IconName; label?: string; small?: boolean; className?: string }) {
  const cls = ["icon", small ? "icon-sm" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <svg
      className={cls}
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

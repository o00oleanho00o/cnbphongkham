type IconProps = { name: string; filled?: boolean };

export function Icon({ name, filled }: IconProps) {
  return (
    <span className="icon" data-filled={filled || undefined} aria-hidden="true">
      {name}
    </span>
  );
}

type IconButtonProps = {
  icon: string;
  label: string;
  onClick: () => void;
  pressed?: boolean;
  disabled?: boolean;
};

export function IconButton({ icon, label, onClick, pressed, disabled }: IconButtonProps) {
  return (
    <button
      type="button"
      className="icon-btn"
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon name={icon} filled={pressed} />
    </button>
  );
}

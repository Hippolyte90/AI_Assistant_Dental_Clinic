import type { ReactNode } from "react";

function Icon({ size = 18, children }: { size?: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

type P = { size?: number };

export const MicIcon = ({ size }: P) => (
  <Icon size={size}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Icon>
);
export const StopIcon = ({ size }: P) => (
  <Icon size={size}>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </Icon>
);
export const CheckIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
);
export const DownloadIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M12 4v11m-4.5-4.5L12 15l4.5-4.5M5 20h14" />
  </Icon>
);
export const TrashIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M4 7h16M9 7V4h6v3m3 0-.8 13H6.8L6 7m4 4v5m4-5v5" />
  </Icon>
);
export const PlusIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);
export const ClockIcon = ({ size }: P) => (
  <Icon size={size}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);
export const AlertIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M12 4 2.8 20h18.4L12 4Zm0 6v4.5m0 2.8v.1" />
  </Icon>
);
export const SpeakerIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Zm12 -.5a4 4 0 0 1 0 6" />
  </Icon>
);
export const RefreshIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3L20 9.3M20 4v5.3h-5.3" />
  </Icon>
);
export const ChevronIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="m7 10 5 5 5-5" />
  </Icon>
);
export const DocumentIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M7 3h7l4 4v14H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v4h4M9.5 12.5h6m-6 4h6" />
  </Icon>
);
export const ListIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
  </Icon>
);

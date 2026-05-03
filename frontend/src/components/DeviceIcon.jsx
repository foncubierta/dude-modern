import {
  Router, Server, Monitor, Smartphone, Camera,
  Wifi, HelpCircle, Printer, Tv
} from "lucide-react";

const ICONS = {
  router: Router,
  switch: Wifi,
  server: Server,
  pc: Monitor,
  phone: Smartphone,
  camera: Camera,
  printer: Printer,
  tv: Tv,
  unknown: HelpCircle,
};

export function DeviceIcon({ type = "unknown", size = 20, color }) {
  const Icon = ICONS[type] || ICONS.unknown;
  return <Icon size={size} color={color} />;
}

export const ICON_TYPES = Object.keys(ICONS);

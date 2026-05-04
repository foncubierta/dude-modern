import {
  Router, Server, Monitor, Smartphone, Cctv,
  Wifi, HelpCircle, Printer, Tv, Radio,
  Plug, AirVent, Sun, Cpu, PhoneCall, Speaker,
} from "lucide-react";

const ICONS = {
  router:  Router,
  ap:      Radio,
  switch:  Wifi,
  server:  Server,
  pc:      Monitor,
  phone:   Smartphone,
  camera:  Cctv,
  printer: Printer,
  tv:      Tv,
  plug:    Plug,
  hvac:    AirVent,
  solar:   Sun,
  iot:     Cpu,
  voip:    PhoneCall,
  speaker: Speaker,
  unknown: HelpCircle,
};

export function DeviceIcon({ type = "unknown", size = 20, color }) {
  const Icon = ICONS[type] || ICONS.unknown;
  return <Icon size={size} color={color} />;
}

export const ICON_TYPES = Object.keys(ICONS);

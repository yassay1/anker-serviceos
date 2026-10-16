import { BatteryCharging, Cable, Headphones, Package, PlugZap, Speaker, Usb, Wind, type LucideProps } from 'lucide-react'

/** A model label only chooses an illustration; it never asserts a device fact. */
export function DeviceIcon({ model, ...props }: LucideProps & { model?: string | null }) {
  const name = model ?? ''
  const Icon = /耳机|soundcore.*(?:buds|liberty|space|life)|headphone|earbud/i.test(name) ? Headphones
    : /音箱|speaker|boom|motion/i.test(name) ? Speaker
      : /净化|purifier|风扇/i.test(name) ? Wind
        : /线材|数据线|cable/i.test(name) ? Cable
          : /扩展坞|hub|dock/i.test(name) ? Usb
            : /充电宝|移动电源|power.?bank|737|prime.*(?:12000|20000|27650)/i.test(name) ? BatteryCharging
              : /充电器|charger|nano|gan/i.test(name) ? PlugZap : Package
  return <Icon aria-hidden="true" {...props} />
}

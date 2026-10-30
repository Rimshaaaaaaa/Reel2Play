import type { ReactNode } from "react";
import "./PhoneFrame.css";

interface PhoneFrameProps {
  /** Painted on the signboard at the top, like a shop's own board. */
  sign: string;
  children: ReactNode;
}

export function PhoneFrame({ sign, children }: PhoneFrameProps) {
  return (
    <figure className="phone" aria-label="Phone preview">
      <div className="phone-sign" dir="auto">
        {sign}
      </div>
      <div className="phone-screen">{children}</div>
    </figure>
  );
}

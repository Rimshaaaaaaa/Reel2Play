import type { BriefValues } from "./api";

export const EMPTY_BRIEF: BriefValues = {
  shopName: "",
  whatsappNumber: "",
  shopUrl: "",
  price: "",
  offer: "",
  language: "auto",
  rightsConfirmed: false,
  occasion: "none",
};

/** The one thing the browser checks before sending; the API checks the rest. */
export function briefProblem(fields: BriefValues): string | null {
  return !fields.whatsappNumber && !fields.shopUrl
    ? "Add a WhatsApp number or a shop link for orders."
    : null;
}

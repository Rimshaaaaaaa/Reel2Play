/** Small display helpers shared by the studio and the gallery. */

export const STATUS_LABEL: Record<string, string> = {
  queued: "Waiting",
  analyzing: "Director reading",
  cutting_out: "Cutting out",
  building: "Building",
  testing: "Testing",
  fixing: "Fixing",
  publishing: "Publishing",
  published: "Live",
  needs_person: "Needs a person",
  blocked: "Not allowed",
  failed: "Stopped",
  ready: "Ready for you",
  replaced: "Replaced",
};

export const TEMPLATE_NAME: Record<string, string> = {
  catch: "Catch",
  runner: "Runner",
  puzzle: "Puzzle",
  memory: "Memory match",
  scratch: "Scratch card",
  spots: "Tap to reveal",
  stack: "Stack",
  quiz: "Quiz",
  colours: "Colour picker",
};

export const percent = (value: number | null) =>
  value === null ? "–" : `${Math.round(value * 100)}%`;

export const rupees = (value: number) =>
  `Rs ${value.toLocaleString("en-PK", { maximumFractionDigits: value < 10 ? 2 : 0 })}`;

/** Who did a step, in the shop's words. */
export const ACTOR_LABEL: Record<string, string> = {
  system: "Reel2Play",
  director: "Director",
  cutout: "Cut-out",
  builder: "Builder",
  tester: "Tester",
  critic: "Critic",
  reporter: "Report",
  safety: "Safety",
  publisher: "Publisher",
};

/** Occasions a game can be themed for (features 10 and 22). */
export const OCCASION_LABEL: Record<string, string> = {
  ramzan: "Ramzan",
  eid: "Eid",
  independence_day: "14 August",
  wedding_season: "Wedding season",
  winter_sale: "Winter sale",
};

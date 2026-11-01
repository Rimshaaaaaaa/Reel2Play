# Evaluation video permission record

Use this record for each real shop video before adding it to `videos.json`.
Do not put a shop owner's personal phone number, private contact details, or a copy of
this signed record in public reports, the gallery, Git, or a distributable ZIP.

## Permission checklist

- [ ] The shop owns the video or has permission to grant its use.
- [ ] The shop explicitly agrees that Reel2Play may process the video for the hackathon
      evaluation and create a playable game and promotional preview from it.
- [ ] The shop confirms the product, price, offer, logo, and other claims it wants shown.
- [ ] The shop confirms that the original audio/music may be removed. Reel2Play mutes the
      source audio and uses only its own permitted sound effects.
- [ ] Bystanders' faces are blurred before any public output. If face checking is unavailable,
      use the safe fallback and do not publish an unchecked original frame.
- [ ] The shop understands that a passed game may be shown in the public evaluation gallery
      only after a separate publication approval.
- [ ] The shop has approved the final game, preview, offer, and call to action before publication.

## Permission record (keep privately)

- Shop/business name:
- Business category: clothing / bakery_food / shoes / cosmetics / phone_accessories / home_decor
- Name and role of person granting permission:
- Date permission granted (with timezone):
- Video filename or private reference:
- Allowed use: hackathon processing / public gallery / gameplay Reel (check each separately)
- Restrictions or expiry date:
- Confirmation method and private evidence location:

## Manifest entry

In `videos.json`, put only the minimum operational record required by the runner:

- `consent`: a short non-sensitive note identifying who agreed and when.
- `synthetic`: `false` for real shop footage, `true` only for generated/demo footage.
- `file`: a relative path to a locally stored video under the project directory.

Keep the videos themselves in `eval/videos/`. That directory is ignored by Git and must not
be included in shared ZIPs. Never label synthetic footage as real or include synthetic results
in claims about real-shop performance.

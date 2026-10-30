"""What the Reel2Play chat says. Before the game's language is known, English then Urdu.

Urdu full stops are written as \\u06d4 so the source stays plain to linters.
"""

from __future__ import annotations

STOP = "\u06d4"

HELP = (
    "Send me one product video (MP4, up to 16 MB) or a product photo, and I will turn it into "
    "a 20-second game ad that ends on your offer. Write your price and offer in the caption, "
    "like: Rs 2,499, 20% off this week.\n\n"
    f"اپنی پراڈکٹ کی ایک ویڈیو یا تصویر بھیجیں، ہم اسے 20 سیکنڈ کی گیم بنا دیں گے{STOP} "
    f"کیپشن میں قیمت اور آفر لکھیں{STOP}"
)

CONSENT = (
    "Is this video yours to use for ads? We remove its sound, and the game shows only the "
    "price and offer you give.\n\n"
    f"کیا یہ ویڈیو آپ کی اپنی ہے؟ ہم اس کی آواز ہٹا دیتے ہیں{STOP}"
)
YES = ("rights_yes", "Yes, it's mine")
NO = ("rights_no", "No")

STARTED = (
    "Got it. Your game is being made and tested on small and large phones. The link will "
    "come here in a few minutes.\n\n"
    f"شکریہ! آپ کی گیم بن رہی ہے، لنک چند منٹ میں یہیں آئے گا{STOP}"
)
DECLINED = (
    "No problem. We only make games from videos you own. Send another one any time.\n\n"
    f"کوئی بات نہیں{STOP} ہم صرف آپ کی اپنی ویڈیو سے گیم بناتے ہیں{STOP}"
)
NOTHING_PENDING = "Send the video first, then confirm it is yours."
VOICE_ADDED = (
    "Got your voice note; we will listen to it for the offer. Is the video yours to use?\n\n"
    f"آپ کا وائس نوٹ مل گیا{STOP} کیا یہ ویڈیو آپ کی اپنی ہے؟"
)
VOICE_FIRST = (
    "Send the video first, then a voice note about the offer, like: Eid sale, 20% off, for "
    "young girls."
)
BUSY = "Your last game is still being made. The link will come here soon."
REJECTED = "We could not use that file: {reason}"

DONE = {
    "en": (
        "Your game is ready: {link}\n\nShare the link in chats and on your Status. "
        "Your gameplay Reel is next, ready to post."
    ),
    "ur": (
        f"آپ کی گیم تیار ہے: {{link}}\n\nیہ لنک چیٹس اور اسٹیٹس پر شیئر کریں{STOP} "
        f"گیم پلے ریل اگلے میسج میں ہے{STOP}"
    ),
}
NEEDS_PERSON = {
    "en": (
        "We tested your game and could not get every check to pass, so we are not sending a "
        "broken game. Our team will look at it and reply here."
    ),
    "ur": (
        f"ہم نے آپ کی گیم ٹیسٹ کی، کچھ چیزیں ٹھیک نہیں ہوئیں{STOP} "
        f"ہماری ٹیم دیکھ کر یہیں جواب دے گی{STOP}"
    ),
}
FAILED = {
    "en": "We could not make a game from this video: {reason}. Please try another video.",
    "ur": f"اس ویڈیو سے گیم نہیں بن سکی: {{reason}}{STOP} کوئی اور ویڈیو بھیجیں{STOP}",
}
BLOCKED = {
    "en": "We cannot make game ads for this kind of product.",
    "ur": f"ہم اس قسم کی پراڈکٹ کے لیے گیم نہیں بناتے{STOP}",
}
EASIER = {
    "en": (
        "Players are finding your game hard, so we made an easier version and tested it. "
        "Try it and choose whether it replaces the live game: {link}"
    ),
    "ur": (
        f"کھلاڑیوں کو آپ کی گیم مشکل لگ رہی ہے، اس لیے ہم نے آسان ورژن بنا کر ٹیسٹ کیا ہے{STOP} "
        f"اسے آزمائیں اور فیصلہ کریں: {{link}}"
    ),
}

# --- Feature 43: a player asks for a shop's offers ----------------------------------------
LEAD_CONSENT = (
    "Do you agree that {shop} may send you offers on WhatsApp? Reel2Play keeps your number "
    "only for this, and you can stop any time by sending STOP.\n\n"
    f"کیا آپ راضی ہیں کہ {{shop}} آپ کو واٹس ایپ پر آفرز بھیجے؟ بند کرنے کے لیے STOP بھیجیں{STOP}"
)
LEAD_YES = ("lead_yes", "Yes, send offers")
LEAD_NO = ("lead_no", "No, thanks")
LEAD_DONE = (
    "Done: {shop} may send you offers here. Send STOP any time to stop.\n\n"
    f"ہو گیا{STOP} بند کرنے کے لیے کسی بھی وقت STOP بھیجیں{STOP}"
)
LEAD_DECLINED = "No problem. Nothing was saved."
LEAD_UNKNOWN = "That code is not taking sign-ups. Check the code on the game's end card."
LEAD_STOPPED = (
    "Stopped: no shop will send you offers through Reel2Play, and your sign-ups are deleted.\n\n"
    f"بند کر دیا گیا{STOP} آپ کی معلومات حذف کر دی گئی ہیں{STOP}"
)

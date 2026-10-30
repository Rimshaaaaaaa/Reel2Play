# Handoff: Rimsha ke liye

Yeh file batati hai ke ZIP milne ke baad kya karna hai. Commands English mein hain; unhein
waise hi terminal mein chalayein.

## 1. Team listing (sab se pehle)

Hackathon ke rules kehte hain ke jis jis ne project par kaam kiya, woh sab submission page par
list hon.

- Jo shakhs yeh code bana kar ZIP de raha hai, usay apni submission par teammate list karein.
- Pehle Discord ke **#questions** channel mein poochh lein ke kya ek banda do entries par ho
  sakta hai (agar woh kisi aur entry mein bhi hai). Jawab ka screenshot rakh lein.
- Ahsaan ya koi aur code likhe to usay bhi list karein (team mein zyada se zyada 4 log).

## 2. Repo banana aur ZIP push karna

1. GitHub par ek **naya public repo** banayein, naam `reel2play`. README, .gitignore ya
   license **na** add karein (bilkul khaali repo).
2. ZIP ko unzip karein aur us folder mein jayein:

```bash
unzip reel2play.zip
cd reel2play
git init -b main
git add -A
git commit -m "Foundation, director and cut-out"
git remote add origin https://github.com/<aap-ka-username>/reel2play.git
git push -u origin main
```

3. **Har nayi ZIP aane par** (har group ke baad nayi ZIP aayegi), purani files hata kar nayi
   daalein aur commit karein, taake repo ki history mein event ke dino ka kaam nazar aaye:

```bash
cd reel2play
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
unzip -o ../reel2play.zip -d ..
git add -A
git commit -m "<group ka naam, jaise: Director and cut-out>"
git push
```

ZIP mein kabhi `.env` ya koi key nahi hoti. Apni `.env` file kabhi commit na karein
(`.gitignore` usay pehle se rokta hai).

## 3. Accounts aur keys (isi tarteeb se)

Koi key chat mein ya repo mein nahi jaati. Har value sirf in jagahon par jaati hai:
**local `.env`** (aap ki machine), **GitHub → Settings → Secrets and variables → Actions**,
ya **Render / Modal ki settings**.

| # | Account | Value(s) | Kahan daalni hai | Kya chalu hota hai |
| --- | --- | --- | --- | --- |
| 1 | **Baseten** (hackathon credit form) | `BASETEN_API_KEY` | `.env`, GitHub secret, Render | Spark Open: director, critic, captions (4, 5, 8, 9, 14, 16, 20, 27, 29, 30, 34) |
| 2 | **Fireworks** (sign-up, phir credit form) | `FIREWORKS_API_KEY` | `.env`, GitHub secret, Render | Failover (64) |
| 3 | **Modal** (sign-up, phir credit form) | (a) `modal token new` (aap ki machine par); (b) dashboard → Settings → **API Tokens** se ek token → `MODAL_TOKEN_ID` aur `MODAL_TOKEN_SECRET`; (c) dashboard → Settings → **Proxy Auth Tokens** se ek token → `MODAL_PROXY_TOKEN` = `<id>.<secret>` | `.env`, GitHub secret, Render | SAM 3.1 cut-out (6), Glimmer tester (25), play-test Sandboxes (57). Deploy ka tareeqa `workers/modal/README.md` mein. Deploy ke baad `SAM_URL`, `GLIMMER_BASE_URL` (aakhir mein `/v1`) aur `GLIMMER_API_KEY` (wohi proxy token) `.env`, GitHub secrets aur Render mein |
| 4 | **Hugging Face** | token; SAM 3.1 aur Glimmer ke pages par terms accept karein agar maange | Modal secret `huggingface` (`HF_TOKEN`): `uv run modal secret create huggingface HF_TOKEN=...` | Model weights download |
| 5 | **Neon** (region Singapore) | Connection string → `DATABASE_URL` (shuru `postgresql+psycopg://` se, aakhir mein `?sslmode=require`) | Render | Production database |
| 6 | **Supabase** (region Singapore) | Project URL → `SUPABASE_URL`, service_role key → `SUPABASE_SERVICE_KEY`; do buckets: `reel2play-private` (private) aur `reel2play-public` (public) | Render | Videos, sprites, games, Reels ki storage |
| 7 | **Render** | Blueprint `render.yaml` se deploy | Render dashboard | API + web site |
| 8 | **cron-job.org** | Har 5 minute `POST https://<api>/internal/cron`, header `X-Cron-Secret: <CRON_SECRET>` | cron-job.org | Free Render service jaagti rehti hai, queue chalti hai |
| 9 | **Meta for Developers** (WhatsApp product, free test number) | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` (neeche "WhatsApp setup" dekhein); offers ke sign-up ke liye `WHATSAPP_BUSINESS_NUMBER` (API Setup wala number, sirf digits, country code ke saath) | `.env`, Render | WhatsApp intake (2), offers on WhatsApp (43) |
| 10 | **Meta for Developers** (wohi app, "Facebook Login for Business" product) | `META_APP_ID`, `META_APP_SECRET` (aur agar configuration banayein to `META_LOGIN_CONFIG_ID`); neeche "Instagram/Facebook import setup" | `.env`, Render | Instagram/Facebook se post import (3) |
| 11 | **X account** | — | — | Most Viral post |
| 12 | **Khud banayein** (koi account nahi) | `ADMIN_KEY`: koi bhi lambi random string | `.env`, Render | Designers ke templates ka review (49) |

### WhatsApp setup (feature 2)

1. developers.facebook.com → **My Apps → Create App** → "Business" type → app mein
   **WhatsApp** product add karein. Meta khud ek free **test number** deta hai.
2. **WhatsApp → API Setup** page par:
   - "Phone number ID" → `WHATSAPP_PHONE_NUMBER_ID`
   - access token → `WHATSAPP_TOKEN`. Yahan wala temporary token 24 ghante chalta hai;
     demo ke liye Business Settings → **System users** se permanent token banayein
     (permission: `whatsapp_business_messaging`).
   - "To" mein apna (aur demo wale phones ke) number add karke verify karein; test number
     sirf in numbers ko message bhej sakta hai.
3. **App settings → Basic** → "App secret" → `WHATSAPP_APP_SECRET` (har webhook isi se sign
   hota hai; galat secret par API 401 deti hai).
4. `WHATSAPP_VERIFY_TOKEN` khud banayein (neeche wali command se ek lambi random string).
5. **WhatsApp → Configuration → Webhook**: Callback URL `https://<API ka Render URL>/webhooks/whatsapp`,
   Verify token wohi string, phir **Verify and save**. Phir "Webhook fields" mein
   **messages** subscribe karein.
6. Test: apne phone se test number par product ki video bhejein, caption mein price likhein
   (jaise `Rs 2,499, 20% off`). Bot poochega "Is this video yours?" → **Yes, it's mine** →
   kuch minute baad game ka link aur gameplay Reel isi chat mein aayenge.

Owner ka number sirf chat aur shop ke record mein rehta hai (jawab bhejne ke liye); logs,
links aur audit trail mein kabhi nahi jata.

### Instagram/Facebook import setup (feature 3)

1. developers.facebook.com → wohi app (jo WhatsApp ke liye banaya) → **Add product** →
   **Facebook Login for Business**.
2. **App settings → Basic**: "App ID" → `META_APP_ID`, "App secret" → `META_APP_SECRET`
   (dono Render aur `.env` mein; chat mein kabhi na bhejein).
3. **Facebook Login → Settings → Valid OAuth Redirect URIs** mein yeh address add karein:
   `https://<API ka Render URL>/api/import/meta/callback`
4. Agar Facebook "configuration" maange to **Configurations → Create** karein, permissions:
   `pages_show_list`, `pages_read_engagement`, `instagram_basic`; us ka ID
   `META_LOGIN_CONFIG_ID` mein daalein. (Na maange to yeh khali chhor dein.)
5. App abhi **Development mode** mein hai: sirf app ke admins/testers sign in kar sakte hain,
   demo ke liye yehi kaafi hai. Apna Facebook account (jo shop ka Page chalata hai) app ka
   admin hona chahiye, aur Instagram professional account us Page se linked ho.
6. Test: web par **Import a post** → **Continue with Facebook** → apna Page chunein → videos
   ki list aayegi → ek chunein, price/offer likhein, "yeh video meri hai" tick karein →
   **Make my game**. Jis Reel mein Instagram ki library wali music ho us ki file Instagram
   nahi deta; woh "Upload it instead" dikhayega.

Sign-in sirf server ki memory mein 30 minute rehta hai; token kabhi database, logs ya link
mein nahi jata.

`CRON_SECRET` aur `SECRET_KEY` aap khud bana sakti hain:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### AI assistant se order (MCP, feature 52)

Deploy ke baad koi bhi MCP wala AI assistant (masalan Claude Desktop ya Claude.ai ke
"Connectors" mein "Add custom connector") is address se jur sakta hai:
`https://<aap ki API ka address>/mcp`. Koi key nahi chahiye. Assistant se kahein: "Is video
se meri shop ki game bana do: <video ka public https link>, WhatsApp 923001234567, Rs 2,499,
20% off" aur bata dein ke video aap ki apni hai. Woh `make_playable_ad` chalaye ga, phir
`get_playable_ad` se link laye ga. Pehli dafa jawab mein `shop_key` aata hai: isay sambhal
lein, agli games usi shop mein jayengi.

## 4. Local chalana, live evaluation, deploy

**Zaroori cheezein:** Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22,
PostgreSQL 16, ffmpeg.

```bash
cp .env.example .env        # bina keys ke sab kuch mock model par chalta hai
make setup
createdb reel2play
make db
make api                    # terminal 1: http://localhost:8000
make web                    # terminal 2: http://localhost:5173
make check                  # lint, types, saare tests, web build
make e2e                    # Playwright (pehli dafa: cd web && npx playwright install chromium)
```

**Live models check (keys ke baad):** `.env` mein `AI_MODE=live` aur keys daalein, phir:

```bash
cd api && uv run reel2play model-check
```

Har role ke saamne `ok` aur endpoint ka naam aana chahiye.

**GitHub par live evaluation:** keys ko repository secrets mein daalein
(`BASETEN_API_KEY`, `FIREWORKS_API_KEY`, `GLIMMER_BASE_URL`, `GLIMMER_API_KEY`,
`SAM_URL`, `MODAL_PROXY_TOKEN`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`), phir
**Actions → Live model evaluation → Run workflow**. Yeh sirf haath se chalta hai.

**Deploy:** Render → New → Blueprint → apna repo chunein → `render.yaml` load hoga. Jo values
`sync: false` hain, woh Render maangega (upar wali table se). Web site ke liye
`VITE_API_BASE_URL` = API ka Render URL. Phir cron-job.org wala job banayein.

## 5. Kya bana hai, kya baqi hai

Poori list `FEATURES.md` mein hai. Abhi tak (spec ki saari 65 features, Build, Stretch aur Later):

- **done:** 1 (upload), 7 (video se product ki chalti hui sprite), 12 (teen templates), 13
  (chhe naye templates: memory match, scratch card, tap to reveal, stack, quiz, colour
  picker), 18 (square aur landscape game aur Reels), 23 (accessibility: sirf tap se khelna,
  awaaz ki captions, kam motion), 31 (na sabit hone wale daawe aur price na hona), 36 (counter
  ke liye A4 poster QR code ke saath), 37 (website par game lagane ka code), 40 (har jeetne
  wale ka apna coupon code, studio mein "used" mark), 42 (score se dost ko chaillenge, baghair
  naam/number ke), 47 (agency workspace: kai brands, roles), 49 (templates ki gallery aur
  designers ke templates), 17 (end card), 21 (sound effects), 26 (13
  quality gates), 28 (phone aur tablet), 32 (game page + short link), 33 (gameplay Reel), 35
  (Meta playable + lead-in video), 38 (WhatsApp end card), 39 (plays aur order taps, baghair
  personal data), 41 (compare page), 45 (studio), 48 (cost), 50 (agents ki pipeline), 51 (why
  panel), 54 (rights), 56 (prompt-injection guard), 58 (blocked products, cash prize nahi),
  59 ("Built with Muse Spark Open"), 60 (try it), 63 (mock), 65 (live progress).
- **needs-key:** 4, 5, 8, 9 (director), 14, 15, 16, 20 (game design aur alfaaz:
  `BASETEN_API_KEY`), 6 (SAM 3.1: `SAM_URL` + `MODAL_PROXY_TOKEN`; in ke baghair simple
  cut-out chalta hai aur "lower quality" likha aata hai), 25 (Glimmer tester:
  `GLIMMER_BASE_URL` + `GLIMMER_API_KEY`), 27, 29, 30 (critic, fix aur report:
  `BASETEN_API_KEY`), 34 (captions: `BASETEN_API_KEY`), 57 (Modal Sandbox: `MODAL_TOKEN_ID`
  + `MODAL_TOKEN_SECRET`), 2 (WhatsApp: upar wali 4 values), 64 (failover), 3
  (Instagram/Facebook import: `META_APP_ID` + `META_APP_SECRET`), 10 (voice note brief:
  `BASETEN_API_KEY`), 11 (aik video ya catalog se kai products: `BASETEN_API_KEY`), 19 (A/B:
  teen versions, `BASETEN_API_KEY`), 22 (Eid/Ramzan/14 August waghaira themes,
  `BASETEN_API_KEY`), 44 (game mushkil lage to aasan version, owner ki marzi se:
  `BASETEN_API_KEY`), 46 (batch: kai products ek saath, har aik ki apni game:
  `BASETEN_API_KEY`), 52 (MCP: koi bhi AI assistant game order kar sake: `BASETEN_API_KEY`),
  53 (har shop ki yaad: pichli games mein kya chala: `BASETEN_API_KEY`), 55 (doosre logon ke
  chehre blur: `SAM_URL` + `MODAL_PROXY_TOKEN`; in ke baghair game video ka koi frame nahi
  dikhati, sirf product ka cut-out), 24 (experimental game: director nayi mechanic likhta
  hai, code check karta hai: `BASETEN_API_KEY`), 43 (WhatsApp par offers ka sign-up, ijazat
  ke saath: WhatsApp keys + `WHATSAPP_BUSINESS_NUMBER`). Yeh sab mock par tested hain.
- **partial:** 61 (gallery: page tayyar, evaluation ke baad bharegi), 62 (evaluation harness
  tayyar aur tested; 30 asli videos aur live run baqi).

**Production mein Modal Sandbox zaroori hai:** Render par `MODAL_TOKEN_ID` aur
`MODAL_TOKEN_SECRET` na hon to game test nahi hoga aur ad "failed" ho jayega, saaf wajah ke
saath. Yeh jaan boojh kar hai: production mein game sirf baghair internet wale Sandbox mein
khelta hai. Local aur CI mein wohi harness aap ki machine ke Chromium mein chalta hai.

**Sound effects:** spec mein "free sound-effects set" ka task tha. Ab iski zaroorat nahi:
saari awaazein game khud code se banata hai (koi file nahi, kisi ka license nahi).

**Asli phone par yeh check karein:**

- Upload page par "Record a voice note" dabayein, mic ki ijazat dein, bolein (jaise "Eid
  sale, 20% off, young girls ke liye"), Stop karein: player aaye aur sun sakein. Game banne
  ke baad "What the director found" mein Offer ke saath "(said in your voice note)" aur
  "Occasion: Eid" aana chahiye (yeh live model ke saath; mock par fixed jawab aata hai).
- Do ya zyada photos chunein: "These are different products" ka option aaye.
- Naye templates: Try it page se ya apni video se game banayein; har template 15 se 30
  second mein khatam ho aur end card par offer aaye.
- Upload form par "Occasion" mein Eid chunein: game ke upar Eid ki lights aur chaand aayen,
  aur intro/end card par "Eid Mubarak" (Urdu game mein "عید مبارک").
- Game khelte waqt awaaz band rakhein: har catch par neeche chhota sa "Caught!" likha aaye;
  upar "CC" dabane se yeh band ho jaye.
- Published game ke card mein "Other shapes": square aur landscape game khol kar dekhein
  (laptop par), aur dono Reels download ho kar chalen.
- "Test three versions" → "Make two more versions" (usi browser se jis ne game banaya):
  chand minute mein B aur C live hon, teeno alag game hon, aur "Share this one link" wala
  link har dafa koi ek version khole.
- Offer mein "Best in Pakistan" likh kar game banayein: report mein "Worth checking" ke
  neeche iska zikr aaye. Price khali chhorein to bhi wahan yaad dilaye.
- Published game ke card mein "Counter poster": "Download poster (PDF)" se A4 PDF aaye;
  print karein (ya screen par kholein) aur phone ke camera se QR scan karein: game khule.
- "Put it on your website": Tall/Wide chun kar "Copy code" karein, kisi bhi website builder
  ke HTML/Embed block mein paste karein: game wahan chale. Kuch plays ke baad studio mein
  "from the counter poster" aur "from your website" ginti aaye.
- Game jeetein (published link par, kisi aur phone se): end card par "Your code:
  R2P-XXXX-XXXX" jaisa naya code aaye, aur WhatsApp button ke message mein bhi wohi code ho.
  Studio → "Win codes" mein code likhein → "Use code": "marked as used". Dobara likhein:
  "already used".
- Upload page par "Upload a batch" → 2 se 12 photos/videos chunein, har aik ka naam aur
  price likhein (ya khali chhorein) → "Make N games": agle page par har product ka card
  aaye, aur ek ek kar ke "Live" ho kar "Open game" aaye. Games alag alag qism ki hon.
- Studio mein "What works for your shop": jab kuch games par plays aa jayen to har game ki
  qism ki line aaye (kitne log end tak pohanche, kitno ne order dabaya), sab se achhi upar.
- Faces (sirf SAM 3.1 lagne ke baad): aisi video upload karein jis mein peeche koi aur
  shakhs ho; puzzle game ki tasveer mein us ka chehra dhundla ho. SAM ke baghair puzzle mein
  video ki tasveer ki jagah product ka cut-out saada rang par aaye.
- Upload form par "Experimental" tick karein: game nayi qism ka ho (mock par "bubble pop":
  product walay bulbulay tap karein). "How your game was made" mein "code checked its script"
  aaye, aur game baqi games ki tarah test ho kar live ho.
- Published game jeet kar "Challenge a friend" dabayein: WhatsApp khule, message mein score
  aur link ho. Woh link kholne par intro card par "A friend scored ..." likha aaye.
- Studio → "Offers on WhatsApp" (WhatsApp keys aur `WHATSAPP_BUSINESS_NUMBER` ke baad) On
  karein: game ke end card par "Get this shop's offers on WhatsApp" aaye. Kisi aur phone se
  dabayein → "JOIN ..." bhejein → "Yes" dabayein: studio mein ginti 1 ho, "Download the list"
  se CSV aaye. Us phone se STOP bhejein: list se hat jaye.
- Footer → "Agency workspace": workspace banayein, brand add karein, "Make an invite link"
  se kisi aur browser mein join karein (Editor), wahan "Make a game" se us brand ki game
  banayein.
- Footer → "Game templates": har template ka "Play the demo" phone frame mein chale.
- Easier version: yeh tab aata hai jab 30 plays ke baad aadhe se kam log end tak pohanchein
  ya jeetne wale 40% se kam hon. Test ke liye kisi game ko kai dafa shuru kar ke chhor dein
  (ya haar jayein). Game ke page par "Players find this game hard" card aaye, chand minute
  mein "Play the easier version" aur "Use the easier version". Use karne ke baad wohi purana
  link aasan game khole (poster aur website wala code bhi).

- Phone ke browser se upload page kholein, gallery se Reel chunein: preview baghair awaaz ke
  chale.
- Rights wala checkbox lagaye baghair "Make my game" button band rahe.
- Upload ke baad "Working on your game" mein har agent ki line aaye, phir "What the director
  found" mein product, rang, price aur offer, aur phone frame mein product ka cut-out.
- Urdu option (اردو) theek nazar aaye.
- Phone frame mein game khule: "Tap to play" dabayein aur khel kar dekhein (catch mein bag
  ungli se khiskayein). Aakhir mein offer, price aur "Order on WhatsApp" button aaye; button
  WhatsApp kholay aur message mein product aur code likha ho.
- Urdu game (language: اردو) mein text right-to-left aur saaf parhne ke qabil ho.
- Game banne ke baad 1 se 2 minute mein "Tested and ready" wala report card aaye: har check
  ke saath tick, aur "See what the tester saw" par end card ki tasveer khule. Urdu game ho to
  report bhi Urdu mein right-to-left aaye.
- Phir "Your game is live" card: "Copy link" se link copy ho, "Open game" se game ka page
  khule aur wahan khel kar end card par WhatsApp button kaam kare. Gameplay Reel chale (10–15
  second, awaaz ke baghair) aur download ho. Captions ke tabs (WhatsApp Status, Instagram,
  Facebook) badlein aur "Copy caption" try karein.
- Game ka link WhatsApp par kisi ko bhejein: link ke saath end card ki chhoti tasveer
  (preview) aani chahiye. (Render ke free plan par pehli dafa 30–50 second lag sakte hain;
  cron-job.org wala job API ko jagaye rakhta hai.)
- WhatsApp setup ke baad: test number par video bhejein → "Yes, it's mine" → link aur Reel
  wapas aayein.

**Group 6 ke naye pages (phone aur laptop dono par dekhein):**

- **Try it** (`/try`): sample chunein → "Make this game" → agle page par har agent ki line
  usi waqt aaye (live). Har sample par "Synthetic sample" likha ho. "A product we never
  advertise" wala sample game banaye baghair ruk jaye aur wajah bataye.
- **Studio** (`/studio`): upload karne wale browser mein aap ki games, plays, order taps aur
  cost (Rs) dikhein. "Forget this browser" ke baad studio khaali ho jaye.
- Har game ke page par neeche **"Why the agents decided this"** kholein: "Audit trail
  intact" aur director ki wajah nazar aaye.
- **Gallery** (`/gallery`) abhi khaali hai; evaluation (Group 7) ke baad bharegi. Kisi game
  ko gallery mein daalne ke liye: `cd api && uv run reel2play gallery add <ad id>`.
- **Compare** (`/compare`): do ads bina naam ke; ek chunein → "Thank you".

**Asli shops ki videos (try-it aur evaluation ke liye):** sirf us shop ki ijazat ke baad.
File `samples/` folder mein rakhein aur `samples/manifest.json` mein ek entry banayein:
`"synthetic": false` aur `"source"` mein likhein kis ne ijazat di (jaise "Ali Shoes, Lahore,
agreed on 30 Oct"). Synthetic samples par hamesha "Synthetic sample" likha rehta hai.

**Evaluation (Group 7), 30 videos ke saath:**

1. `eval/videos.example.json` ko `eval/videos.json` naam se copy karein.
2. Har video `eval/videos/` folder mein rakhein (yeh folder kabhi commit ya ZIP nahi hota),
   aur `videos.json` mein uski entry ke saare `<...>` bharein: shop ka naam, price (bilkul
   waise jaise shop likhti hai), WhatsApp number, aur `consent` (kis ne, kab ijazat di).
3. Keys `.env` mein hon (`AI_MODE=live`), phir:

```bash
cd api
uv run reel2play eval run ../eval/videos.json --gallery
```

4. Report `eval/results/<date>-live/report.md` mein banegi; yeh folder commit karein.
   Log `/compare` par vote karein aur games khelein, phir numbers update karne ke liye:
   `uv run reel2play eval report ../eval/results/<folder>/results.json`

Bina keys ke check karna ho to: `make eval` (3 synthetic videos, mock model).

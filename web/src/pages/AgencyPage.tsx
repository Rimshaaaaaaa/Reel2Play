import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  addBrand,
  ApiError,
  brandStudio,
  changeRole,
  chooseBrand,
  getAgency,
  inviteMember,
  joinAgency,
  rememberAgency,
  removeMember,
  startAgency,
  storedAgency,
  type AgencyOut,
  type AgencyRole,
  type ShopOut,
} from "../api";
import { STATUS_LABEL } from "../format";
import "./AgencyPage.css";

const ROLE_WORDS: Record<AgencyRole, string> = {
  owner: "Owner",
  editor: "Editor",
  viewer: "Viewer",
};
const RANK: Record<AgencyRole, number> = { viewer: 0, editor: 1, owner: 2 };
const message = (error: unknown) =>
  error instanceof ApiError ? error.message : "That did not go through. Try again.";

function Welcome({ onKey }: { onKey: (key: string, name: string) => void }) {
  const [params] = useSearchParams();
  const [agencyName, setAgencyName] = useState("");
  const [yourName, setYourName] = useState("");
  const [code, setCode] = useState(params.get("invite") ?? "");
  const [joinName, setJoinName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  async function start(event: FormEvent) {
    event.preventDefault();
    try {
      const made = await startAgency(agencyName, yourName);
      onKey(made.key, made.agency.name);
    } catch (error) {
      setProblem(message(error));
    }
  }

  async function join(event: FormEvent) {
    event.preventDefault();
    try {
      const joined = await joinAgency(code, joinName);
      onKey(joined.key, joined.agency.name);
    } catch (error) {
      setProblem(message(error));
    }
  }

  return (
    <div className="agency">
      <header className="agency-head">
        <h1>Agency workspace</h1>
        <p className="agency-lede">
          For agencies with several brands: everyone on the team sees every brand's games and
          numbers; editors add brands and make games for them; the owner invites people.
        </p>
      </header>
      <div className="agency-doors">
        <form className="card agency-door" onSubmit={(e) => void start(e)}>
          <h2>Start a workspace</h2>
          <label className="field">
            <span>Agency name</span>
            <input required maxLength={120} value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
          </label>
          <label className="field">
            <span>Your name, as the team will see it</span>
            <input required maxLength={80} value={yourName} onChange={(e) => setYourName(e.target.value)} />
          </label>
          <button type="submit" className="btn" disabled={!agencyName.trim() || !yourName.trim()}>
            Start the workspace
          </button>
        </form>
        <form className="card agency-door" onSubmit={(e) => void join(e)}>
          <h2>Join with an invite</h2>
          <label className="field">
            <span>Invite code</span>
            <input required maxLength={40} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <label className="field">
            <span>Your name</span>
            <input required maxLength={80} value={joinName} onChange={(e) => setJoinName(e.target.value)} />
          </label>
          <button type="submit" className="btn btn-quiet" disabled={!code.trim() || !joinName.trim()}>
            Join the workspace
          </button>
        </form>
      </div>
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

function BrandGames({ agencyKey, shopId }: { agencyKey: string; shopId: string }) {
  const [studio, setStudio] = useState<ShopOut | null>(null);
  useEffect(() => {
    brandStudio(agencyKey, shopId).then(setStudio).catch(() => setStudio(null));
  }, [agencyKey, shopId]);
  if (!studio) return <p className="agency-muted">Loading the games…</p>;
  if (studio.ads.length === 0) return <p className="agency-muted">No games yet.</p>;
  return (
    <ul className="brand-games">
      {studio.ads.map((ad) => (
        <li key={ad.id}>
          <Link to={`/ads/${ad.id}`}>{ad.product ?? "Game"}</Link>
          <span className="status-chip" data-status={ad.status}>
            {STATUS_LABEL[ad.status] ?? ad.status}
          </span>
          <span className="agency-muted">{ad.stats.plays} plays</span>
        </li>
      ))}
    </ul>
  );
}

/** Feature 47: an agency's brands, its people and their roles. */
export function AgencyPage() {
  const navigate = useNavigate();
  const [stored, setStored] = useState(storedAgency);
  const [agency, setAgency] = useState<AgencyOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [brandName, setBrandName] = useState("");
  const [brandPhone, setBrandPhone] = useState("");
  const [inviteRole, setInviteRole] = useState<AgencyRole>("editor");
  const [invite, setInvite] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!stored) return;
    getAgency(stored.key)
      .then(setAgency)
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          rememberAgency(null);
          setStored(null);
        } else setProblem("The workspace could not be loaded. Refresh to try again.");
      });
  }, [stored]);
  useEffect(load, [load]);

  if (!stored) {
    return (
      <Welcome
        onKey={(key, name) => {
          rememberAgency({ key, name });
          setStored({ key, name });
        }}
      />
    );
  }
  if (problem && !agency) return <p className="form-error" role="alert">{problem}</p>;
  if (!agency) return <p role="status">Loading the workspace…</p>;

  const key = stored.key;
  const role = agency.you.role;
  const run = async (action: () => Promise<AgencyOut | void>) => {
    setProblem(null);
    try {
      const next = await action();
      if (next) setAgency(next);
    } catch (error) {
      setProblem(message(error));
    }
  };

  return (
    <div className="agency">
      <header className="agency-head agency-bar">
        <h1>{agency.name}</h1>
        <span className="role-chip" data-role={role}>
          {agency.you.name}, {ROLE_WORDS[role].toLowerCase()}
        </span>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            rememberAgency(null);
            chooseBrand(null);
            setStored(null);
            setAgency(null);
          }}
        >
          Forget this browser
        </button>
      </header>

      <section aria-labelledby="brands-title" className="agency-section">
        <h2 id="brands-title">Brands</h2>
        {agency.brands.length === 0 ? <p className="agency-muted">No brands yet.</p> : null}
        <ul className="brand-grid">
          {agency.brands.map((brand) => (
            <li key={brand.id} className="card brand-card">
              <h3 dir="auto">{brand.name}</h3>
              <dl className="brand-numbers">
                <div>
                  <dt>Games</dt>
                  <dd>{brand.games}</dd>
                </div>
                <div>
                  <dt>Live</dt>
                  <dd>{brand.live}</dd>
                </div>
                <div>
                  <dt>Plays</dt>
                  <dd>{brand.plays}</dd>
                </div>
                <div>
                  <dt>Order taps</dt>
                  <dd>{brand.cta_taps}</dd>
                </div>
              </dl>
              <div className="brand-actions">
                {RANK[role] >= RANK.editor ? (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      chooseBrand({ shopId: brand.id, name: brand.name, agencyKey: key });
                      navigate("/");
                    }}
                  >
                    Make a game
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn-quiet"
                  aria-expanded={open === brand.id}
                  onClick={() => setOpen(open === brand.id ? null : brand.id)}
                >
                  {open === brand.id ? "Hide games" : "See games"}
                </button>
              </div>
              {open === brand.id ? <BrandGames agencyKey={key} shopId={brand.id} /> : null}
            </li>
          ))}
        </ul>
        {RANK[role] >= RANK.editor ? (
          <form
            className="card brand-add"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                const next = await addBrand(key, {
                  name: brandName,
                  ...(brandPhone ? { whatsapp_number: brandPhone } : {}),
                });
                setBrandName("");
                setBrandPhone("");
                return next;
              });
            }}
          >
            <h3>Add a brand</h3>
            <div className="field-row">
              <label className="field">
                <span>Brand name</span>
                <input required maxLength={120} value={brandName} onChange={(e) => setBrandName(e.target.value)} />
              </label>
              <label className="field">
                <span>Its WhatsApp number for orders</span>
                <input inputMode="tel" placeholder="923001234567" value={brandPhone}
                  onChange={(e) => setBrandPhone(e.target.value)} />
              </label>
            </div>
            <button type="submit" className="btn btn-quiet" disabled={!brandName.trim()}>
              Add brand
            </button>
          </form>
        ) : null}
      </section>

      <section aria-labelledby="team-title" className="agency-section">
        <h2 id="team-title">Team</h2>
        <ul className="team">
          {agency.members.map((member) => (
            <li key={member.id} className="team-row">
              <span className="team-name" dir="auto">
                {member.name}
                {member.you ? " (you)" : ""}
              </span>
              {role === "owner" && !member.you ? (
                <>
                  <select
                    aria-label={`Role of ${member.name}`}
                    value={member.role}
                    onChange={(e) => void run(() => changeRole(key, member.id, e.target.value as AgencyRole))}
                  >
                    {(Object.keys(ROLE_WORDS) as AgencyRole[]).map((r) => (
                      <option key={r} value={r}>
                        {ROLE_WORDS[r]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="team-remove"
                    onClick={() => void run(() => removeMember(key, member.id))}
                  >
                    Remove
                  </button>
                </>
              ) : (
                <span className="role-chip" data-role={member.role}>
                  {ROLE_WORDS[member.role]}
                </span>
              )}
            </li>
          ))}
        </ul>
        {role === "owner" ? (
          <div className="card invite">
            <h3>Invite someone</h3>
            <div className="invite-row">
              <select aria-label="Role for the invite" value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as AgencyRole)}>
                {(Object.keys(ROLE_WORDS) as AgencyRole[]).map((r) => (
                  <option key={r} value={r}>
                    {ROLE_WORDS[r]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-quiet"
                onClick={() =>
                  void run(async () => {
                    const made = await inviteMember(key, inviteRole);
                    setInvite(`${window.location.origin}/agency?invite=${encodeURIComponent(made.code)}`);
                  })
                }
              >
                Make an invite link
              </button>
            </div>
            {invite ? (
              <p className="invite-link">
                Send this link to them; it works once, for seven days: <code>{invite}</code>
              </p>
            ) : null}
          </div>
        ) : null}
      </section>
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  MAX_BATCH,
  uploadBatch,
  type BatchProduct,
  type BriefValues,
} from "../api";
import { EMPTY_BRIEF, briefProblem } from "../brief";
import { BriefFields } from "../components/BriefFields";
import "./BatchPage.css";

const ACCEPT = "video/mp4,video/quicktime,video/webm,image/jpeg,image/png,image/webp";

function Thumb({ file }: { file: File }) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return file.type.startsWith("video/") ? (
    <video className="tray-thumb" src={url} muted playsInline preload="metadata" aria-hidden="true" />
  ) : (
    <img className="tray-thumb" src={url} alt="" />
  );
}

/**
 * Feature 46: a catalog of products, one file each, becomes a set of tested games that share
 * the shop's details. Each product may have its own name, price and offer.
 */
export function BatchPage() {
  const navigate = useNavigate();
  const [fields, setFields] = useState<BriefValues>(EMPTY_BRIEF);
  const [products, setProducts] = useState<BatchProduct[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof BriefValues>(key: K, value: BriefValues[K]) =>
    setFields((current) => ({ ...current, [key]: value }));

  function add(files: File[]) {
    setProducts((current) =>
      [...current, ...files.map((file) => ({ file, name: "", price: "", offer: "" }))].slice(
        0,
        MAX_BATCH,
      ),
    );
    if (products.length + files.length > MAX_BATCH) {
      setError(`A batch has up to ${MAX_BATCH} products; the rest were left out.`);
    }
  }

  function change(index: number, key: "name" | "price" | "offer", value: string) {
    setProducts((current) => current.map((p, i) => (i === index ? { ...p, [key]: value } : p)));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem =
      briefProblem(fields) ?? (products.length < 2 ? "Add at least two products." : null);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const batch = await uploadBatch(fields, products);
      navigate(`/batches/${batch.id}`);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Upload failed. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="batch">
      <header className="batch-head">
        <h1>Games for several products</h1>
        <p className="batch-lede">
          One file per product, a short video or a photo. Each becomes its own tested game with
          your shop's details; name and price each one, or let the director read them.
        </p>
        <p className="batch-alt">
          Only one product? <Link to="/">Upload a single Reel</Link>.
        </p>
      </header>

      <form className="brief-form card batch-form" onSubmit={submit} noValidate>
        <BriefFields fields={fields} set={set} pricePerProduct>
          <div className="field">
            <span id="products-label">Products</span>
            <label className="tray-add">
              <input
                type="file"
                accept={ACCEPT}
                multiple
                aria-labelledby="products-label"
                onChange={(e) => {
                  add(Array.from(e.target.files ?? []));
                  e.target.value = "";
                }}
              />
              <span className="tray-add-face">
                {products.length ? "Add more products" : "Choose videos or photos"}
              </span>
              <small>
                {products.length} of {MAX_BATCH} products
              </small>
            </label>
            {products.length ? (
              <ol className="trays">
                {products.map((product, index) => (
                  <li key={`${product.file.name}-${index}`} className="tray">
                    <span className="tray-number" aria-hidden="true">
                      {index + 1}
                    </span>
                    <Thumb file={product.file} />
                    <div className="tray-fields">
                      <label>
                        <span>Name</span>
                        <input
                          maxLength={60}
                          placeholder="Read from the file"
                          value={product.name}
                          aria-label={`Product ${index + 1} name`}
                          onChange={(e) => change(index, "name", e.target.value)}
                        />
                      </label>
                      <label>
                        <span>Price</span>
                        <input
                          maxLength={40}
                          placeholder="Rs 2,499"
                          value={product.price}
                          aria-label={`Product ${index + 1} price`}
                          onChange={(e) => change(index, "price", e.target.value)}
                        />
                      </label>
                      <label className="tray-offer">
                        <span>Own offer</span>
                        <input
                          maxLength={200}
                          placeholder="Same as above"
                          value={product.offer}
                          aria-label={`Product ${index + 1} offer`}
                          onChange={(e) => change(index, "offer", e.target.value)}
                        />
                      </label>
                    </div>
                    <button
                      type="button"
                      className="tray-remove"
                      aria-label={`Remove product ${index + 1}`}
                      onClick={() => setProducts((current) => current.filter((_, i) => i !== index))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        </BriefFields>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          className="btn"
          disabled={busy || !fields.rightsConfirmed || products.length < 2}
        >
          {busy ? "Sending…" : products.length >= 2 ? `Make ${products.length} games` : "Make the games"}
        </button>
      </form>
    </div>
  );
}

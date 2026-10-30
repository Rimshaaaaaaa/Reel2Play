import { Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AdPage } from "./pages/AdPage";
import { AgencyPage } from "./pages/AgencyPage";
import { BatchPage } from "./pages/BatchPage";
import { BatchStatusPage } from "./pages/BatchStatusPage";
import { ComparePage } from "./pages/ComparePage";
import { GalleryPage } from "./pages/GalleryPage";
import { ImportPage } from "./pages/ImportPage";
import { StudioPage } from "./pages/StudioPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { TryPage } from "./pages/TryPage";
import { UploadPage } from "./pages/UploadPage";

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/ads/:adId" element={<AdPage />} />
        <Route path="/import" element={<ImportPage />} />
        <Route path="/batch" element={<BatchPage />} />
        <Route path="/batches/:batchId" element={<BatchStatusPage />} />
        <Route path="/try" element={<TryPage />} />
        <Route path="/studio" element={<StudioPage />} />
        <Route path="/agency" element={<AgencyPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}

function NotFound() {
  return (
    <section>
      <h1>Page not found</h1>
      <p>
        This link does not lead anywhere. <Link to="/">Make a game from your Reel</Link>.
      </p>
    </section>
  );
}

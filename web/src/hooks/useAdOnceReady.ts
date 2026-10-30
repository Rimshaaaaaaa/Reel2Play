import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getVideo, type VideoOut } from "../api";

const POLL_MS = 1500;

/**
 * After an upload or a try-it pick: wait while the video is prepared, then open its ad page.
 * Returns the video once it is known to have failed, so the page can say why.
 */
export function useAdOnceReady(video: VideoOut | null): VideoOut | null {
  const navigate = useNavigate();
  const [failed, setFailed] = useState<VideoOut | null>(null);
  useEffect(() => {
    if (!video) return;
    let cancelled = false;
    let timer: number | undefined;
    const check = async () => {
      try {
        const latest = await getVideo(video.id);
        if (cancelled) return;
        if (latest.status === "failed") return setFailed(latest);
        if (latest.ad_id) return navigate(`/ads/${latest.ad_id}`);
      } catch {
        // A dropped request is retried below.
      }
      if (!cancelled) timer = window.setTimeout(check, POLL_MS);
    };
    timer = window.setTimeout(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [video, navigate]);
  return failed;
}

import { Innertube, UniversalCache, YTNodes, YT } from 'npm:youtubei.js';
import { readFileSync } from 'node:fs';

/**
 * Parses cookies from a Netscape cookie file.
 * @param {string} filePath Path to the cookie file.
 * @returns {string | null}
 */
function parseCookies(filePath) {
  try {
    const text = readFileSync(filePath, 'utf8');
    const cookies = text.split('
')
      .filter(line => line.trim() && !line.startsWith('#'))
      .map(line => {
        const parts = line.split('	');
        if (parts.length < 7) return null;
        return { name: parts[5], value: parts[6].trim() };
      })
      .filter(cookie => cookie !== null);

    // Standard Innertube authentication sometimes requires SAPISID.
    // If SAPISID is missing but __Secure-3PAPISID is present, we use it as SAPISID.
    const hasSapisid = cookies.some(c => c.name === 'SAPISID');
    const secure3papisid = cookies.find(c => c.name === '__Secure-3PAPISID');
    if (!hasSapisid && secure3papisid) {
      cookies.push({ name: 'SAPISID', value: secure3papisid.value });
    }

    return cookies.map(c => `${c.name}=${c.value}`).join('; ');
  } catch (error) {
    return null;
  }
}

(async () => {
  try {
    const args = Deno.args;
    const cookiesPath = args[0];
    const continuationToken = args[1];
    
    if (!cookiesPath) {
        console.error(JSON.stringify({ error: "Cookies path is required" }));
        Deno.exit(1);
    }

    const cookieString = parseCookies(cookiesPath);
    if (!cookieString) {
        console.error(JSON.stringify({ error: "Failed to parse cookies" }));
        Deno.exit(1);
    }

    const yt = await Innertube.create({
      cookie: cookieString,
      cache: new UniversalCache(false)
    });

    if (!yt.session.logged_in) {
        console.error(JSON.stringify({ error: "Not logged in with provided cookies" }));
        Deno.exit(1);
    }

    let feed;
    
    if (continuationToken) {
        // Use the continuation token to fetch the next page
        const response = await yt.actions.execute('/browse', { continuation: continuationToken });
        feed = new YT.History(yt.actions, response);
    } else {
        // Fetch the first page of history
        feed = await yt.getHistory();
    }

    const processedVideos = [];
    
    // feed.videos contains all video-like nodes found in the response via memoization.
    // This includes Video, CompactVideo, GridVideo, ReelItem, etc.
    if (feed.videos && feed.videos.length > 0) {
        feed.videos.forEach(v => {
            try {
                // Filter out Shorts (ReelItem or ShortsLockupView)
                if (v.is(YTNodes.ReelItem, YTNodes.ShortsLockupView)) return;

                // Extra check for nodes that might be videos but are marked as shorts in metadata
                const isShort = v.style === 'SHORTS' || v.overlay_metadata?.includes?.('Shorts');
                if (isShort) return;

                const id = v.video_id || v.id;
                const title = v.title?.toString();
                const author = v.author?.name || v.author?.toString() || 'Unknown';
                
                if (id && title) {
                    // Determine if live. Video and CompactVideo have is_live getter.
                    let is_live = false;
                    if (v.is(YTNodes.Video, YTNodes.CompactVideo)) {
                        is_live = v.is_live;
                    } else if (v.is(YTNodes.GridVideo)) {
                        const time_status = v.thumbnail_overlays?.firstOfType?.(YTNodes.ThumbnailOverlayTimeStatus);
                        is_live = time_status?.style === 'LIVE';
                    } else {
                        // Fallback check for other video-like nodes
                        is_live = !!v.is_live;
                    }

                    processedVideos.push({
                        title: title,
                        url: `https://www.youtube.com/watch?v=${id}`,
                        author: author,
                        is_live: is_live
                    });
                }
            } catch (err) {
                // Skip items that fail to process
            }
        });
    }

    // Extract continuation token for the next page
    const continuation = feed.memo.getType(YTNodes.ContinuationItem)?.[0];
    const nextToken = continuation?.endpoint.payload.token || null;

    console.log(JSON.stringify({
      videos: processedVideos,
      continuation: nextToken
    }));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    Deno.exit(1);
  }
})();

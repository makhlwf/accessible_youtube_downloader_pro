import { Innertube, UniversalCache } from 'npm:youtubei.js';
import { readFileSync } from 'node:fs';

function parseCookies(filePath) {
  try {
    const text = readFileSync(filePath, 'utf8');
    const cookies = text.split('\n')
      .filter(line => line.trim() && !line.startsWith('#'))
      .map(line => {
        const parts = line.split('\t');
        if (parts.length < 7) return null;
        return { name: parts[5], value: parts[6].trim() };
      })
      .filter(cookie => cookie !== null);

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
        Deno.exit(1);
    }

    const cookieString = parseCookies(cookiesPath);
    if (!cookieString) {
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

    const processedVideos = [];
    let nextToken = null;

    let feed;
    if (continuationToken) {
        feed = await yt.browse(continuationToken);
    } else {
        feed = await yt.getHistory();
    }

    if (feed) {
        let items = [];
        if (feed.videos) {
            items = feed.videos;
        } else if (feed.contents && feed.contents.contents) {
             feed.contents.contents.forEach(item => {
                  if (item.type === 'Video' || item.type === 'CompactVideo' || item.type === 'GridVideo' || item.type === 'HistoryVideo') {
                      items.push(item);
                  } else if (item.type === 'RichItem' && item.content) {
                      items.push(item.content);
                  }
             });
        }

        items.forEach(v => {
            try {
                if (!v) return;
                const type = v.type || v.constructor?.name || '';
                const isShort = type === 'ShortsLockupView' ||
                                type === 'ReelItem' ||
                                type.includes('Short') ||
                                (v.overlay_metadata && JSON.stringify(v.overlay_metadata).includes('Shorts')) ||
                                (v.accessibility_text && v.accessibility_text.includes('Shorts'));

                if (isShort) return;

                const id = v.videoId || v.id;
                const title = v.title?.toString() || v.headline?.toString();
                const author = v.author?.name || v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || 'Unknown';
                
                if (id && title) {
                    processedVideos.push({
                        title: title,
                        url: `https://www.youtube.com/watch?v=${id}`,
                        author: author,
                        is_live: v.is_live || false
                    });
                }
            } catch (err) {
                // skip
            }
        });

        nextToken = feed.continuation || null;
    }

    // Fallback to manual extraction from raw data if still empty
    if (processedVideos.length === 0 && feed && feed.page) {
        const extract = (obj) => {
            if (!obj || typeof obj !== 'object') return;

            const v = obj.videoRenderer || obj.compactVideoRenderer || obj.gridVideoRenderer || obj.historyVideoRenderer;
            if (v) {
                const isShort =
                  v.navigationEndpoint?.reelWatchEndpoint ||
                  v.navigationEndpoint?.commandMetadata?.webCommandMetadata?.url?.includes('/shorts/') ||
                  v.thumbnailOverlays?.some(o => o.thumbnailOverlayTimeStatusRenderer?.style === 'SHORTS');

                if (!isShort) {
                    const id = v.videoId;
                    const title = v.title?.runs?.[0]?.text || v.title?.simpleText || v.headline?.simpleText;
                    const author = v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || v.author?.name || 'Unknown';

                    if (id && title) {
                        processedVideos.push({
                            title: title.toString(),
                            url: `https://www.youtube.com/watch?v=${id}`,
                            author: author.toString(),
                            is_live: !!(v.badges?.some(b => b.metadataBadgeRenderer?.style === 'BADGE_STYLE_TYPE_LIVE_NOW') || v.thumbnailOverlays?.some(o => o.thumbnailOverlayTimeStatusRenderer?.style === 'LIVE'))
                        });
                    }
                }
            }

            if (obj.continuationItemRenderer && !nextToken) {
                nextToken = obj.continuationItemRenderer.continuationEndpoint?.continuationCommand?.token;
            }

            for (const k in obj) {
                if (k !== 'trackingParams' && processedVideos.length < 30) {
                    extract(obj[k]);
                }
            }
        };
        extract(feed.page);
    }

    console.log(JSON.stringify({
      videos: processedVideos,
      continuation: nextToken || null
    }));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    Deno.exit(1);
  }
})();

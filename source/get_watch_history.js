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

    const extract = (obj) => {
        if (!obj || typeof obj !== 'object') return;
        
        // Video renderers
        if (obj.videoRenderer || obj.compactVideoRenderer || obj.gridVideoRenderer) {
            const v = obj.videoRenderer || obj.compactVideoRenderer || obj.gridVideoRenderer;
            
            // Filter Shorts
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
                        is_live: v.badges?.some(b => b.metadataBadgeRenderer?.style === 'BADGE_STYLE_TYPE_LIVE_NOW') || v.thumbnailOverlays?.some(o => o.thumbnailOverlayTimeStatusRenderer?.style === 'LIVE')
                    });
                }
            }
        } 
        
        // Continuation tokens
        if (obj.continuationItemRenderer) {
            const token = obj.continuationItemRenderer.continuationEndpoint?.continuationCommand?.token;
            if (token) nextToken = token;
        }

        // Recursive search
        for (const k in obj) {
            if (k !== 'trackingParams' && processedVideos.length < 30) {
                extract(obj[k]);
            }
        }
    };

    if (continuationToken) {
        const response = await yt.actions.execute('/browse', { continuation: continuationToken });
        extract(response.data);
    } else {
        const response = await yt.actions.execute('/browse', { browseId: 'FEhistory' });
        extract(response.data);
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
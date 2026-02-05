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
    
    let yt;
    if (cookiesPath) {
      const cookieString = parseCookies(cookiesPath);
      yt = await Innertube.create({
        cookie: cookieString || '',
        cache: new UniversalCache(false)
      });
    } else {
      yt = await Innertube.create({
        cache: new UniversalCache(false)
      });
    }

    const results = [];
    let nextToken = null;

    const extract = (obj) => {
        if (!obj || typeof obj !== 'object') return;
        if (obj.videoRenderer) {
            const v = obj.videoRenderer;
            const id = v.videoId;
            const title = v.title?.runs?.[0]?.text || v.title?.simpleText || v.title?.toString();
            // Basic filter for regular videos: must have duration-like overlay or length text
            const hasDuration = v.lengthText || v.thumbnailOverlays?.some(o => o.thumbnailOverlayTimeStatusRenderer);
            if (id && title && hasDuration) {
                results.push({
                    title: title,
                    author: v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || 'Unknown',
                    id: id,
                    url: `https://www.youtube.com/watch?v=${id}`
                });
            }
        } else if (obj.continuationItemRenderer) {
            const token = obj.continuationItemRenderer.continuationEndpoint?.continuationCommand?.token;
            if (token) nextToken = token;
        } else {
            for (const k in obj) {
                if (k !== 'trackingParams') extract(obj[k]);
            }
        }
    };

    if (continuationToken) {
        const response = await yt.actions.execute('/browse', { continuation: continuationToken });
        extract(response.data);
    } else {
      let feed = await yt.getHomeFeed();
      let pages = 0;
      const MAX_PAGES = 20;

      while (pages < MAX_PAGES) {
          let items = [];
          
          if (feed.contents && feed.contents.contents) {
              feed.contents.contents.forEach(item => {
                  if (item.type === 'RichItem' && item.content) {
                      items.push(item.content);
                  } else if (item.type === 'RichSection' && item.content?.contents) {
                      items.push(...item.content.contents);
                  } else if (item.type === 'Video' || item.type === 'LockupView') { 
                      items.push(item);
                  }
              });
          }
          
          // Fallback to built-in getter if manual extraction is empty
          if (items.length === 0 && feed.videos) {
              items = feed.videos;
          }

          if (items && items.length > 0) {
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

                      let id, title, author, views;

                      if (type === 'LockupView' || v.metadata) {
                          id = v.content_id || v.videoId || v.id;
                          title = v.metadata?.title?.text || v.metadata?.title?.runs?.[0]?.text || v.title?.toString();
                          try {
                              author = v.metadata?.metadata?.metadata_rows?.[0]?.metadata_parts?.[0]?.text?.text || 
                                       v.metadata?.metadata?.metadata_rows?.[0]?.metadata_parts?.[0]?.text?.runs?.[0]?.text ||
                                       v.author?.name || 'Unknown';
                              
                              const metadataRows = v.metadata?.metadata?.metadata_rows || [];
                              for (const row of metadataRows) {
                                  const parts = row.metadata_parts || [];
                                  for (const part of parts) {
                                      const text = part.text?.text || part.text?.toString() || '';
                                      if (text.includes('views') || text.includes('مشاهدة')) {
                                          views = text;
                                          break;
                                      }
                                  }
                                  if (views) break;
                              }
                          } catch (e) {
                              author = author || 'Unknown';
                          }
                      } else {
                          id = v.videoId || v.id;
                          title = v.title?.runs?.[0]?.text || v.title?.toString() || v.headline?.toString();
                          author = v.author?.name || v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || 'Unknown';
                          views = v.view_count?.toString() || v.short_view_count?.toString();
                      }

                      if (id && title) {
                          let displayAuthor = author;
                          if (views) displayAuthor += ` (${views})`;
                          results.push({
                              title: title,
                              author: displayAuthor,
                              id: id,
                              url: `https://www.youtube.com/watch?v=${id}`
                          });
                      }
                  } catch (err) {
                      // Skip failed items
                  }
              });
          }
          
          if (!feed.has_continuation) {
              nextToken = feed.continuation;
              break;
          }
          try {
            feed = await feed.getContinuation();
            nextToken = feed.continuation;
          } catch (e) {
            break;
          }
          pages++;
      }
      
      // Fallback to subscriptions if still empty
      if (results.length === 0) {
          const subs = await yt.getSubscriptionsFeed();
          if (subs.videos) {
              subs.videos.forEach(v => {
                  if (v.id && v.title) {
                      const views = v.view_count?.toString() || v.short_view_count?.toString();
                      let displayAuthor = v.author?.name || 'Unknown';
                      if (views) displayAuthor += ` (${views})`;
                      results.push({
                          title: v.title.toString(),
                          author: displayAuthor,
                          id: v.id,
                          url: `https://www.youtube.com/watch?v=${v.id}`
                      });
                  }
              });
          }
          nextToken = subs.continuation;
      }
    }

    const unique = [];
    const seen = new Set();
    results.forEach(v => {
        if (!seen.has(v.id)) {
            unique.push(v);
            seen.add(v.id);
        }
    });

    console.log(JSON.stringify({
        videos: unique,
        continuation: nextToken || null
    }));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    Deno.exit(1);
  }
})();

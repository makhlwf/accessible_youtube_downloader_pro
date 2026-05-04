import { Innertube, UniversalCache, YTNodes, YT } from 'npm:youtubei.js@17.0.1';
import { readFileSync } from 'node:fs';
import { TextLineStream } from "https://deno.land/std@0.224.0/streams/text_line_stream.ts";

/**
 * Parses cookies from a Netscape cookie file.
 * @param {string} filePath Path to the cookie file.
 * @returns {string | null}
 */
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

let yt = null;
let currentCookiesPath = null;

async function getYT(cookiesPath) {
    if (yt && currentCookiesPath === cookiesPath) {
        return yt;
    }
    
    let cookieString = null;
    if (cookiesPath) {
        cookieString = parseCookies(cookiesPath);
    }
    
    yt = await Innertube.create({
        cookie: cookieString || '',
        cache: new UniversalCache(false)
    });
    currentCookiesPath = cookiesPath;
    return yt;
}

async function handleGetHomeFeed(params) {
    const yt = await getYT(params.cookiesPath);
    const results = [];
    let nextToken = null;

    const extract = (obj) => {
        if (!obj || typeof obj !== 'object') return;
        if (obj.videoRenderer) {
            const v = obj.videoRenderer;
            const id = v.videoId;
            const title = v.title?.runs?.[0]?.text || v.title?.simpleText || v.title?.toString();
            const hasDuration = v.lengthText || v.thumbnailOverlays?.some(o => o.thumbnailOverlayTimeStatusRenderer);
            if (id && title && hasDuration) {
                const date = v.publishedTimeText?.runs?.[0]?.text || v.publishedTimeText?.simpleText || v.publishedTimeText?.toString() || '';
                let displayAuthor = v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || 'Unknown';
                if (date) displayAuthor += ` - ${date}`;
                results.push({
                    title: title,
                    author: displayAuthor,
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

    if (params.continuationToken) {
        const response = await yt.actions.execute('/browse', { continuation: params.continuationToken });
        extract(response.data);
    } else {
        let feed = await yt.getHomeFeed();
        let pages = 0;
        const MAX_PAGES = 5;

        while (pages < MAX_PAGES) {
            let items = [];
            
            if (feed.contents && feed.contents.contents) {
                feed.contents.contents.forEach(item => {
                    if (item.type === 'RichItem' && item.content) {
                        items.push(item.content);
                    } else if (item.type === 'RichSection' && item.content) {
                        if (item.content.contents) {
                            items.push(...item.content.contents.map(i => i.content || i));
                        } else {
                            items.push(item.content);
                        }
                    } else if (item.type === 'Video' || item.type === 'LockupView' || item.type === 'CompactVideo' || item.type === 'GridVideo') { 
                        items.push(item);
                    }
                });
            }
            
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

                        let id, title, author, views, date;

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
                                        } else if (text.includes('ago') || text.includes('قبل') || text.includes('hours') || text.includes('days') || text.includes('weeks') || text.includes('months') || text.includes('years')) {
                                            date = text;
                                        }
                                    }
                                }
                            } catch (e) {
                                author = author || 'Unknown';
                            }
                        } else if (type === 'Video' || type === 'CompactVideo' || type === 'GridVideo') {
                            id = v.id || v.videoId;
                            title = v.title?.toString();
                            author = v.author?.name || v.short_byline?.toString() || 'Unknown';
                            views = v.view_count?.toString() || v.short_view_count?.toString();
                            date = v.published_time?.toString() || v.publishedTimeText?.toString();
                        } else {
                            id = v.videoId || v.id;
                            title = v.title?.runs?.[0]?.text || v.title?.toString() || v.headline?.toString();
                            author = v.author?.name || v.shortBylineText?.runs?.[0]?.text || v.longBylineText?.runs?.[0]?.text || 'Unknown';
                            views = v.view_count?.toString() || v.short_view_count?.toString();
                            date = v.published_time?.toString() || v.publishedTimeText?.toString();
                        }

                        if (id && title) {
                            let displayAuthor = author;
                            if (views) displayAuthor += ` (${views})`;
                            if (date) displayAuthor += ` - ${date}`;
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

    return {
        videos: unique,
        continuation: nextToken || null
    };
}

async function handleGetWatchHistory(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = await getYT(params.cookiesPath);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in with provided cookies");
    }

    let feed;
    if (params.continuationToken) {
        const response = await yt.actions.execute('/browse', { continuation: params.continuationToken });
        feed = new YT.History(yt.actions, response);
    } else {
        feed = await yt.getHistory();
    }

    const processedVideos = [];
    if (feed.videos && feed.videos.length > 0) {
        feed.videos.forEach(v => {
            try {
                if (v.is(YTNodes.ReelItem, YTNodes.ShortsLockupView)) return;
                const isShort = v.style === 'SHORTS' || v.overlay_metadata?.includes?.('Shorts');
                if (isShort) return;

                const id = v.video_id || v.id;
                const title = v.title?.toString();
                const author = v.author?.name || v.author?.toString() || 'Unknown';
                
                if (id && title) {
                    let is_live = false;
                    if (v.is(YTNodes.Video, YTNodes.CompactVideo)) {
                        is_live = v.is_live;
                    } else if (v.is(YTNodes.GridVideo)) {
                        const time_status = v.thumbnail_overlays?.firstOfType?.(YTNodes.ThumbnailOverlayTimeStatus);
                        is_live = time_status?.style === 'LIVE';
                    } else {
                        is_live = !!v.is_live;
                    }

                    processedVideos.push({
                        title: title,
                        url: `https://www.youtube.com/watch?v=${id}`,
                        author: author,
                        is_live: is_live,
                        id: id
                    });
                }
            } catch (err) {
                // Skip items
            }
        });
    }

    const continuation = feed.memo.getType(YTNodes.ContinuationItem)?.[0];
    const nextToken = continuation?.endpoint.payload.token || null;

    return {
        videos: processedVideos,
        continuation: nextToken
    };
}

async function handleLikeInteraction(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = await getYT(params.cookiesPath);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in");
    }
    const { videoId, action } = params;
    try {
        if (action === 'like') {
            await yt.interact.like(videoId);
        } else if (action === 'dislike') {
            await yt.interact.dislike(videoId);
        } else if (action === 'remove_like') {
            await yt.interact.removeLike(videoId);
        }
        return { success: true };
    } catch (error) {
        throw new Error(`Interaction failed: ${error.message}`);
    }
}

async function main() {
    const lines = Deno.stdin.readable
        .pipeThrough(new TextDecoderStream())
        .pipeThrough(new TextLineStream());

    for await (const line of lines) {
        if (!line.trim()) continue;
        let request;
        try {
            request = JSON.parse(line);
        } catch (e) {
            console.error(JSON.stringify({ error: "Invalid JSON input" }));
            continue;
        }

        const { id, command, params } = request;
        try {
            let result;
            if (command === 'get_home_feed') {
                result = await handleGetHomeFeed(params);
            } else if (command === 'get_watch_history') {
                result = await handleGetWatchHistory(params);
            } else if (command === 'like_video') {
                result = await handleLikeInteraction(params);
            } else {
                throw new Error(`Unknown command: ${command}`);
            }
            console.log(JSON.stringify({ id, result }));
        } catch (error) {
            console.log(JSON.stringify({ id, error: error.message }));
        }
    }
}

main().catch(err => {
    console.error(JSON.stringify({ error: err.message }));
    Deno.exit(1);
});

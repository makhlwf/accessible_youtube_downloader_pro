import { Innertube, UniversalCache, YTNodes, YT } from 'youtubei.js';

/**
 * Reads text content from a file across different JS runtimes (txiki.js, Deno, Node).
 * @param {string} filePath
 * @returns {Promise<string>}
 */
async function readTextFile(filePath) {
  if (typeof tjs !== 'undefined' && tjs.readFile) {
    const data = await tjs.readFile(filePath);
    return new TextDecoder().decode(data);
  }
  if (typeof Deno !== 'undefined' && Deno.readTextFileSync) {
    return Deno.readTextFileSync(filePath);
  }
  try {
    const fs = await import('node:fs');
    return fs.readFileSync(filePath, 'utf8');
  } catch (e) {
    return '';
  }
}

/**
 * Parses cookies from a Netscape cookie file.
 * @param {string} filePath Path to the cookie file.
 * @returns {Promise<string | null>}
 */
async function parseCookies(filePath) {
  try {
    const text = await readTextFile(filePath);
    const cookieMap = new Map();
    const lines = text.split('\n').filter(line => line.trim() && !line.startsWith('#'));

    // Process lines so that youtube.com lines are sorted last, giving them precedence
    lines.sort((a, b) => {
      const aIsYt = a.includes('youtube.com') ? 1 : 0;
      const bIsYt = b.includes('youtube.com') ? 1 : 0;
      return aIsYt - bIsYt;
    });

    for (const line of lines) {
      const parts = line.split('\t');
      if (parts.length < 7) continue;
      const name = parts[5].trim();
      const value = parts[6].trim();
      if (name) {
        cookieMap.set(name, value);
      }
    }

    if (!cookieMap.has('SAPISID') && cookieMap.has('__Secure-3PAPISID')) {
      cookieMap.set('SAPISID', cookieMap.get('__Secure-3PAPISID'));
    }

    const cookiePairs = [];
    for (const [name, value] of cookieMap.entries()) {
      cookiePairs.push(`${name}=${value}`);
    }
    return cookiePairs.join('; ');
  } catch (error) {
    return null;
  }
}

let yt = null;
let currentCookiesPath = null;
let currentClientLocation = null;
let tokenCounter = 0;
const commentsPages = new Map();
const replyThreads = new Map();

function makeToken(prefix) {
    tokenCounter += 1;
    return `${prefix}-${tokenCounter}`;
}

function textValue(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    if (Array.isArray(value)) return value.map(textValue).join('');

    if (value.simpleText) return textValue(value.simpleText);
    if (value.text) return textValue(value.text);
    if (value.runs) return value.runs.map(run => textValue(run.text || run)).join('');

    if (typeof value.toString === 'function' && value.toString !== Object.prototype.toString) {
        const text = value.toString();
        if (text && text !== '[object Object]') return text;
    }

    return '';
}

function parseCount(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;

    const text = textValue(value).trim();
    if (!text) return null;

    const match = text.match(/([\d.,]+)\s*([kmb])?/i);
    if (!match) return null;

    const numberText = match[1].replace(/,/g, '');
    const number = Number.parseFloat(numberText);
    if (!Number.isFinite(number)) return null;

    const suffix = (match[2] || '').toLowerCase();
    const multiplier =
        suffix === 'k' ? 1000 : suffix === 'm' ? 1000000 : suffix === 'b' ? 1000000000 : 1;
    return Math.round(number * multiplier);
}

function extractLikeInfo(info) {
    info = info || {};
    const basicInfo = info.basic_info || {};
    const buttons = info.primary_info?.menu?.top_level_buttons || [];
    const buttonItems = Array.isArray(buttons) || typeof buttons?.[Symbol.iterator] === 'function'
        ? Array.from(buttons)
        : [];
    const segmentedButton = buttonItems.find(button =>
        button?.type === 'SegmentedLikeDislikeButtonView' ||
        (button?.like_button && button?.dislike_button)
    );

    let likes = parseCount(basicInfo.like_count);
    if (likes === null) likes = parseCount(info.likes);
    if (likes === null) likes = parseCount(info.like_count);
    if (likes === null) likes = parseCount(segmentedButton?.like_count);
    if (likes === null) likes = parseCount(segmentedButton?.short_like_count);

    const likeStatus =
        basicInfo.like_status ||
        segmentedButton?.like_button?.like_status_entity?.like_status ||
        info.actions?.like_button?.status ||
        null;
    const isLiked =
        basicInfo.is_liked === true || info.is_liked === true || likeStatus === 'LIKE';
    const isDisliked =
        basicInfo.is_disliked === true || info.is_disliked === true || likeStatus === 'DISLIKE';
    const rating = isLiked ? 'like' : isDisliked ? 'dislike' : null;

    return {
        likes,
        is_liked: isLiked,
        is_disliked: isDisliked,
        rating
    };
}

function chapterTimeMs(chapter) {
    const millisecondKeys = [
        'time_ms',
        'time_range_start_millis',
        'timeRangeStartMillis',
        'start_millis',
        'startMillis',
        'start_time_ms'
    ];
    for (const key of millisecondKeys) {
        const milliseconds = Number(chapter?.[key]);
        if (Number.isFinite(milliseconds)) return Math.max(0, Math.floor(milliseconds));
    }

    for (const key of ['start_time', 'startTime']) {
        const seconds = Number(chapter?.[key]);
        if (Number.isFinite(seconds)) return Math.max(0, Math.floor(seconds * 1000));
    }

    return null;
}

function normalizeChapter(chapter) {
    const timeMs = chapterTimeMs(chapter);
    if (timeMs === null) return null;

    const title = textValue(chapter?.title || chapter?.name).trim() || 'Untitled chapter';
    return { title, time_ms: timeMs };
}

function extractChapters(info) {
    info = info || {};
    const candidates = [
        info.basic_info?.chapters,
        info.chapters,
        info.player_overlays?.decorated_player_bar?.player_bar?.markers_map
    ];
    const chapters = [];

    for (const candidate of candidates) {
        if (!candidate) continue;

        const items =
            Array.isArray(candidate) || typeof candidate?.[Symbol.iterator] === 'function'
                ? Array.from(candidate)
                : [];
        if (items.length > 0 && !items[0]?.value) {
            chapters.push(...items);
            continue;
        }

        for (const marker of items) {
            if (marker?.value?.chapters) {
                chapters.push(...marker.value.chapters);
            }
        }
    }

    const normalized = chapters
        .map(normalizeChapter)
        .filter(chapter => chapter !== null)
        .sort((a, b) => a.time_ms - b.time_ms);

    const seen = new Set();
    return normalized.filter(chapter => {
        const key = `${chapter.time_ms}:${chapter.title}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function normalizeComment(comment, thread = null) {
    const replyCount = parseCount(comment?.reply_count) || 0;
    const hasReplies = !!thread?.has_replies || replyCount > 0;
    let replyToken = null;

    if (thread && hasReplies) {
        replyToken = makeToken('replies');
        replyThreads.set(replyToken, thread);
    }

    return {
        id: comment?.comment_id || '',
        parent_id: comment?.parent || comment?.parent_id || '',
        author: textValue(comment?.author?.name) || 'Unknown',
        content: textValue(comment?.content),
        published_time: textValue(comment?.published_time),
        likes: parseCount(comment?.like_count) || 0,
        replies: replyCount,
        has_replies: hasReplies,
        reply_token: replyToken,
        is_liked: !!comment?.is_liked || comment?.vote === 'LIKE',
        is_disliked: !!comment?.is_disliked || comment?.vote === 'DISLIKE'
    };
}

function normalizeCommentThreads(threads) {
    return Array.from(threads || [])
        .map(thread => thread?.comment ? normalizeComment(thread.comment, thread) : null)
        .filter(comment => comment !== null);
}

function normalizeReplyComments(comments) {
    return Array.from(comments || [])
        .map(comment => normalizeComment(comment))
        .filter(comment => comment !== null);
}

function commentsPageResponse(page) {
    let continuation = null;
    if (page?.has_continuation) {
        continuation = makeToken('comments');
        commentsPages.set(continuation, page);
    }

    return {
        comments: normalizeCommentThreads(page?.contents || []),
        continuation,
        is_disabled: !!page?.is_disabled || !!page?.header?.comments_disabled
    };
}

function repliesResponse(thread) {
    let continuation = null;
    if (thread?.replies && thread.has_continuation) {
        continuation = makeToken('replies-more');
        replyThreads.set(continuation, thread);
    }

    return {
        comments: normalizeReplyComments(thread?.replies || []),
        continuation
    };
}

async function getYT(cookiesPath, location) {
    const targetLocation = location || null;
    if (yt && currentCookiesPath === cookiesPath && currentClientLocation === targetLocation) {
        return yt;
    }
    
    let cookieString = null;
    if (cookiesPath) {
        cookieString = await parseCookies(cookiesPath);
    }
    
    const options = {
        cookie: cookieString || '',
        cache: new UniversalCache(false)
    };
    if (location) {
        options.location = location;
    }
    
    yt = await Innertube.create(options);
    currentCookiesPath = cookiesPath;
    currentClientLocation = targetLocation;
    return yt;
}

async function handleGetHomeFeed(params) {
    const yt = await getYT(params.cookiesPath, params.location);
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
        } else if (obj.radioRenderer || obj.compactRadioRenderer) {
            // Mix / auto-generated radio playlist (RD...) surfaced in the feed.
            const r = obj.radioRenderer || obj.compactRadioRenderer;
            const pid = r.playlistId;
            const title = r.title?.runs?.[0]?.text || r.title?.simpleText || r.title?.toString();
            if (pid && title && String(pid).startsWith('RD')) {
                const seed = r.navigationEndpoint?.watchEndpoint?.videoId
                    || r.videos?.[0]?.childVideoRenderer?.videoId || '';
                const author = r.shortBylineText?.runs?.[0]?.text
                    || r.longBylineText?.runs?.[0]?.text
                    || (r.videoCountText?.runs || []).map(x => x.text).join('')
                    || 'YouTube';
                results.push({
                    type: 'mix',
                    title: title,
                    author: author,
                    id: seed,
                    playlistId: pid,
                    url: seed
                        ? `https://www.youtube.com/watch?v=${seed}&list=${pid}`
                        : `https://www.youtube.com/playlist?list=${pid}`
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

                        // Mix / auto-generated radio playlist (RD...) lockup.
                        // Detect by the RD-prefixed content/playlist id itself
                        // rather than by the exact `type` string: youtubei.js
                        // labels these variously (LockupView, LockupViewModel,
                        // Radio, ...), and a missed match here lets the generic
                        // fallback below emit `watch?v=RD...` (the playlist id in
                        // the video slot), which yt-dlp then fails to resolve.
                        const lockupContentId = (v.content_id || v.contentId || '').toString();
                        const lockupPlaylistId = (v.playlist_id || v.playlistId || '').toString();
                        const mixPid = lockupContentId.startsWith('RD')
                            ? lockupContentId
                            : (lockupPlaylistId.startsWith('RD') ? lockupPlaylistId : '');
                        if (mixPid || type === 'Radio' || type === 'CompactRadio') {
                            const pid = mixPid || lockupPlaylistId || lockupContentId;
                            if (pid && pid.startsWith('RD')) {
                                const mixTitle = v.metadata?.title?.text
                                    || v.metadata?.title?.runs?.[0]?.text
                                    || v.title?.toString() || 'Mix';
                                const mixAuthor = v.metadata?.metadata?.metadata_rows?.[0]?.metadata_parts?.[0]?.text?.text
                                    || v.author?.name || 'YouTube';
                                // Classic RD<videoId> mixes embed the seed video
                                // id; expose it so playback can seed /next with it.
                                const seed = /^RD[\w-]{11}$/.test(pid) ? pid.slice(2) : '';
                                results.push({
                                    type: 'mix',
                                    title: mixTitle,
                                    author: mixAuthor,
                                    id: seed,
                                    playlistId: pid,
                                    url: seed
                                        ? `https://www.youtube.com/watch?v=${seed}&list=${pid}`
                                        : `https://www.youtube.com/playlist?list=${pid}`
                                });
                            }
                            return;
                        }

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

                        // Only emit a playable video when `id` is a real 11-char
                        // YouTube video id. This rejects playlist/mix ids (RD..,
                        // PL.., etc.) that some lockups expose as `content_id`,
                        // so a playlist id never becomes a bogus `watch?v=` URL.
                        if (id && title && /^[\w-]{11}$/.test(String(id))) {
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
        const key = v.type === 'mix' ? `mix:${v.playlistId}` : v.id;
        if (!seen.has(key)) {
            unique.push(v);
            seen.add(key);
        }
    });

    return {
        videos: unique,
        continuation: nextToken || null
    };
}

function historyContinuationToken(feed) {
    const types = [YTNodes.ContinuationItem];
    if (YTNodes.ContinuationItemView) {
        types.push(YTNodes.ContinuationItemView);
    }
    const continuations = feed.memo.getType(...types) || [];
    const continuation = continuations.find(item =>
        item?.endpoint?.payload?.token || item?.endpoint?.payload?.continuation
    );
    return continuation?.endpoint?.payload?.token ||
        continuation?.endpoint?.payload?.continuation ||
        null;
}

function historyMetadataText(video, rowIndex = 0, partIndex = 0) {
    return textValue(
        video?.metadata?.metadata?.metadata_rows?.[rowIndex]
            ?.metadata_parts?.[partIndex]?.text
    );
}

function historyVideoId(video) {
    return video.video_id ||
        video.id ||
        video.content_id ||
        video.endpoint?.payload?.videoId ||
        video.renderer_context?.command_context?.on_tap?.payload?.videoId ||
        '';
}

function historyVideoTitle(video) {
    return textValue(video.title) ||
        textValue(video.metadata?.title) ||
        textValue(video.accessibility_label) ||
        '';
}

function historyVideoAuthor(video) {
    return video.author?.name ||
        textValue(video.author) ||
        textValue(video.short_byline_text) ||
        textValue(video.long_byline_text) ||
        historyMetadataText(video, 0, 0) ||
        'Unknown';
}

function isHistoryShort(video) {
    const contentType = String(video.content_type || '').toUpperCase();
    const style = String(video.style || '').toUpperCase();
    const overlay = textValue(video.overlay_metadata).toUpperCase();
    const shortTypes = [YTNodes.ReelItem];
    if (YTNodes.ShortsLockupView) {
        shortTypes.push(YTNodes.ShortsLockupView);
    }
    return contentType === 'SHORT' ||
        style.includes('SHORT') ||
        overlay.includes('SHORTS') ||
        (typeof video.is === 'function' && video.is(...shortTypes));
}

function isHistoryLive(video) {
    if (video.is_live !== undefined) {
        return !!video.is_live;
    }
    const timeStatus = video.thumbnail_overlays?.firstOfType?.(
        YTNodes.ThumbnailOverlayTimeStatus
    );
    return timeStatus?.style === 'LIVE';
}

async function handleGetWatchHistory(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = await getYT(params.cookiesPath, params.location);
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
                if (isHistoryShort(v)) return;

                const id = historyVideoId(v);
                const title = historyVideoTitle(v);
                const author = historyVideoAuthor(v);
                
                if (id && title) {
                    processedVideos.push({
                        title: title,
                        url: `https://www.youtube.com/watch?v=${id}`,
                        author: author,
                        is_live: isHistoryLive(v),
                        id: id
                    });
                }
            } catch (err) {
                // Skip items
            }
        });
    }

    const nextToken = historyContinuationToken(feed);

    return {
        videos: processedVideos,
        continuation: nextToken
    };
}

async function handleLikeInteraction(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in");
    }
    const { videoId, action } = params;
    let endpoint;
    if (action === 'like') {
        endpoint = 'like/like';
    } else if (action === 'dislike') {
        endpoint = 'like/dislike';
    } else if (action === 'remove_like') {
        endpoint = 'like/removelike';
    } else {
        throw new Error(`Unknown interaction action: ${action}`);
    }

    try {
        const response = await yt.actions.execute(endpoint, {
            target: { videoId }
        });
        if (response && response.success === false) {
            const errorMsg = response.data?.error?.message || response.data?.message || `HTTP ${response.status_code || 'error'}`;
            throw new Error(errorMsg);
        }
        return { success: true };
    } catch (error) {
        throw new Error(`Interaction failed: ${error.message}`);
    }
}

async function handleGetVideoLikes(params) {
    const yt = await getYT(params.cookiesPath, params.location);
    const { videoId } = params;
    try {
        const info = await yt.getInfo(videoId);
        const basic_info = info.basic_info || {};
        const likeInfo = extractLikeInfo(info);

        return {
            ...likeInfo,
            title: textValue(basic_info.title || info.title) || "Unknown",
        };
    } catch (error) {
        console.error(JSON.stringify({ debug: "handleGetVideoLikes error", error: error.message, stack: error.stack }));
        throw new Error(`Failed to fetch video info: ${error.message}`);
    }
}

async function handleGetVideoChapters(params) {
    const yt = await getYT(params.cookiesPath, params.location);
    const { videoId } = params;
    try {
        const info = await yt.getInfo(videoId);
        return { chapters: extractChapters(info) };
    } catch (error) {
        console.error(JSON.stringify({ debug: "handleGetVideoChapters error", error: error.message }));
        throw new Error(`Failed to fetch chapters: ${error.message}`);
    }
}

async function handleGetVideoComments(params) {
    const yt = await getYT(params.cookiesPath, params.location);
    const { videoId, sortBy = 'TOP_COMMENTS', continuationToken } = params;
    try {
        if (continuationToken) {
            const page = commentsPages.get(continuationToken);
            if (!page) {
                throw new Error("Comments continuation expired");
            }
            commentsPages.delete(continuationToken);
            const nextPage = await page.getContinuation();
            return commentsPageResponse(nextPage);
        }

        const page = await yt.getComments(videoId, sortBy);
        return commentsPageResponse(page);
    } catch (error) {
        console.error(JSON.stringify({
            debug: "handleGetVideoComments error",
            error: error.message
        }));
        throw new Error(`Failed to fetch comments: ${error.message}`);
    }
}

async function handleGetCommentReplies(params) {
    const { replyToken, continuationToken } = params;
    const token = continuationToken || replyToken;
    try {
        const thread = replyThreads.get(token);
        if (!thread) {
            throw new Error("Replies token expired");
        }
        replyThreads.delete(token);

        if (continuationToken) {
            await thread.getContinuation();
        } else {
            await thread.getReplies();
        }

        return repliesResponse(thread);
    } catch (error) {
        console.error(JSON.stringify({
            debug: "handleGetCommentReplies error",
            error: error.message
        }));
        throw new Error(`Failed to fetch replies: ${error.message}`);
    }
}

async function handlePostVideoComment(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in");
    }

    const { videoId } = params;
    const text = textValue(params.text).trim();
    if (!videoId) {
        throw new Error("Video ID is required");
    }
    if (!text) {
        throw new Error("Comment text is required");
    }

    try {
        const response = await yt.interact.comment(videoId, text);
        return {
            success: response?.success === true,
            status_code: response?.status_code || null
        };
    } catch (error) {
        console.error(JSON.stringify({
            debug: "handlePostVideoComment error",
            error: error.message
        }));
        throw new Error(`Failed to post comment: ${error.message}`);
    }
}

async function handleLikeComment(params) {
    if (!params.ytClient && !params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = params.ytClient || await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in");
    }
    const { commentId, action } = params;
    if (!commentId) {
        throw new Error("Comment ID is required");
    }
    let endpointAction;
    if (action === 'like') {
        endpointAction = 'LIKE';
    } else if (action === 'dislike') {
        endpointAction = 'DISLIKE';
    } else if (action === 'remove_like') {
        endpointAction = 'INDIFFERENT';
    } else {
        throw new Error(`Unknown interaction action: ${action}`);
    }

    try {
        const response = await yt.actions.execute('comment/perform_comment_action', {
            action: endpointAction,
            commentId: commentId
        });
        if (response && response.success === false) {
            const errorMsg = response.data?.error?.message || response.data?.message || `HTTP ${response.status_code || 'error'}`;
            throw new Error(errorMsg);
        }
        return { success: true };
    } catch (error) {
        console.error(JSON.stringify({
            debug: "handleLikeComment error",
            error: error.message
        }));
        throw new Error(`Comment interaction failed: ${error.message}`);
    }
}

async function handleReplyComment(params) {
    if (!params.ytClient && !params.cookiesPath) {
        throw new Error("Cookies path is required");
    }
    const yt = params.ytClient || await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in");
    }
    const { commentId } = params;
    const text = textValue(params.text).trim();
    if (!commentId) {
        throw new Error("Comment ID is required");
    }
    if (!text) {
        throw new Error("Comment text is required");
    }

    try {
        const response = await yt.actions.execute('comment/create_comment_reply', {
            commentId: commentId,
            commentText: text
        });
        if (response && response.success === false) {
            const errorMsg = response.data?.error?.message || response.data?.message || `HTTP ${response.status_code || 'error'}`;
            throw new Error(errorMsg);
        }
        return {
            success: response?.success !== false,
            status_code: response?.status_code || null
        };
    } catch (error) {
        console.error(JSON.stringify({
            debug: "handleReplyComment error",
            error: error.message
        }));
        throw new Error(`Failed to reply to comment: ${error.message}`);
    }
}

async function handleGetPlaylist(params) {
    const yt = await getYT(params.cookiesPath, params.location);
    const { playlistId } = params;
    try {
        const playlist = await yt.getPlaylist(playlistId);
        const videos = playlist.videos.map(v => ({
            title: v.title.text,
            id: v.id,
            url: `https://www.youtube.com/watch?v=${v.id}`,
            author: v.author?.name || 'Unknown'
        }));
        return { videos };
    } catch (error) {
        throw new Error(`Failed to fetch playlist: ${error.message}`);
    }
}

async function handleGetShortsFeed(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required for Shorts");
    }
    const yt = await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in with provided cookies");
    }

    let seedId = params.seedVideoId || null;
    if (!seedId) {
        try {
            const home = await yt.getHomeFeed();
            const items = home.contents?.contents || home.videos || [];
            for (const item of items) {
                const str = JSON.stringify(item);
                if (str.includes('Shorts') || str.includes('reelWatchEndpoint') || str.includes('/shorts/')) {
                    const match = str.match(/\/shorts\/([a-zA-Z0-9_-]{11})/) || str.match(/"videoId":"([a-zA-Z0-9_-]{11})"/);
                    if (match) {
                        seedId = match[1];
                        break;
                    }
                }
            }
        } catch (e) {
            // Ignore feed parsing errors
        }
    }

    if (!seedId) {
        try {
            const searchRes = await yt.search('#shorts');
            const firstVideo = searchRes.videos?.[0] || searchRes.results?.[0];
            seedId = firstVideo?.video_id || firstVideo?.id || firstVideo?.videoId || null;
        } catch (e) {
            // Ignore search errors
        }
    }

    if (!seedId) {
        seedId = 'dQw4w9WgXcQ';
    }

    try {
        const info = await yt.getShortsVideoInfo(seedId);
        const shorts = [];
        const seen = new Set();

        const currentId = info.basic_info?.id || seedId;
        const currentTitle = textValue(info.basic_info?.title) || 'Short Video';
        const currentAuthor = textValue(info.basic_info?.author) || 'Unknown';

        if (currentId) {
            shorts.push({
                id: currentId,
                title: currentTitle,
                author: currentAuthor,
                url: `https://www.youtube.com/shorts/${currentId}`
            });
            seen.add(currentId);
        }

        if (info.watch_next_feed) {
            for (const item of info.watch_next_feed) {
                const vid = item.payload?.videoId || item.metadata?.url?.replace('/shorts/', '');
                if (vid && !seen.has(vid)) {
                    seen.add(vid);
                    const title = textValue(item.payload?.title || item.title) || `Short (${vid})`;
                    const author = textValue(item.payload?.author || item.author) || 'Unknown';
                    shorts.push({
                        id: vid,
                        title: title,
                        author: author,
                        url: `https://www.youtube.com/shorts/${vid}`
                    });
                }
            }
        }

        return { shorts };
    } catch (error) {
        console.error(JSON.stringify({ debug: "handleGetShortsFeed error", error: error.message }));
        throw new Error(`Failed to fetch Shorts feed: ${error.message}`);
    }
}

function subscriptionsPublishedTime(video) {
    if (video.is_upcoming) return '';
    const clean = (value) => {
        const text = textValue(value).trim();
        // A malformed slot must not announce a view count, duration, live badge,
        // or future premiere as a publication time. Preserve actual localized
        // publication text verbatim; never derive timestamps from relative ages.
        if (/^[\p{N}\s.,:]+[KMB]?$/iu.test(text) ||
            /(?:\bviews?\b|\bwatching\b|\bsubscribers?\b|\bAufrufe?\b|مشاهد|مشترك)/iu.test(text) ||
            /^(?:live|4K|8K|HD|SD|members only|بث مباشر)$/iu.test(text) ||
            /^(?:premieres?|scheduled for|starts in)\b/iu.test(text) ||
            /^(?:سيبدأ العرض|سيتم العرض|سيُعرض|العرض الأول بعد|يبدأ العرض الأول)/u.test(text)) return '';
        return text;
    };
    for (const value of [video.published, video.published_time, video.publishedTimeText]) {
        const text = clean(value);
        if (text) return text;
    }
    if (video.type !== 'LockupView') return '';
    const rows = video.metadata?.metadata?.metadata_rows || [];
    let publication;
    // FEsubscriptions' list layout places author, views, publication in ONE row.
    // Card layouts place the author in row 0 and views/publication in row 1.
    // Accept only these known shapes, not an arbitrary last metadata string.
    if (rows.length === 1 && rows[0].metadata_parts?.length === 3) {
        publication = rows[0].metadata_parts[2];
    } else if (rows.length === 2 && rows[0].metadata_parts?.length === 1 &&
               rows[1].metadata_parts?.length === 2) {
        publication = rows[1].metadata_parts[1];
    }
    const text = publication?.text;
    // Channel links are not publication text even if a malformed layout moves one.
    if (text?.endpoint || text?.runs?.some(run => run.endpoint)) return '';
    return clean(text);
}

/**
 * Read only the main subscriptions timeline, in renderer order. In youtubei.js 18.x,
 * Feed.videos uses Memo.getType(), which groups by type (Video before LockupView)
 * and loses chronology on mixed pages. Never sort localized publication text.
 */
function subscriptionsPageResponse(page) {
    const videos = [];
    const seen = new Set();
    let continuation = null;
    let hasBody = false;
    const containers = new Set([
        'RichGrid', 'RichItem', 'RichSection', 'Shelf',
        'SectionList', 'ItemSection', 'Grid', 'HorizontalList', 'VerticalList',
        'ExpandedShelfContents', 'AppendContinuationItemsAction',
        'reloadContinuationItemsCommand', 'sectionListContinuation',
        'itemSectionContinuation', 'gridContinuation'
    ]);

    const visit = (node) => {
        if (!node || typeof node !== 'object') return;
        if (Array.isArray(node)) {
            node.forEach(visit);
            return;
        }
        // Parser.SuperParsedResult wraps the initial body and some continuations.
        if (node.is_array && typeof node.array === 'function') {
            visit(node.array());
            return;
        }
        if (node.is_node && typeof node.item === 'function') {
            visit(node.item());
            return;
        }
        if (node.type === 'TwoColumnBrowseResults' || node.type === 'SingleColumnBrowseResults') {
            const tabs = node.tabs || [];
            visit(tabs.find(tab => tab.selected) || tabs[0]);
            return;
        }
        if (node.type === 'Tab') {
            visit(node.content);
            return;
        }
        if (node.type === 'ContinuationItem' || node.type === 'ContinuationItemView') {
            const token = node.endpoint?.payload?.token || node.endpoint?.payload?.continuation;
            if (typeof token === 'string' && token) continuation = token;
            return;
        }
        if (node.type === 'Message') {
            // YouTube can return an explicit empty-feed message without a grid.
            // Do not return its arbitrary upstream text across the RPC boundary.
            hasBody = true;
            return;
        }
        // RichShelf modules (e.g. Most relevant) are ranked recommendations,
        // not timeline entries. Exclude the entire module before it can claim
        // a video's ID or replace the main continuation with its own token.
        // Do not match its localized title or sort relative publication labels.
        if (node.type === 'RichShelf') return;
        if (containers.has(node.type)) {
            hasBody = true;
            // Do not descend into Shorts shelves, menus, headers, sidebars or
            // community posts with embedded videos/independent continuations.
            if (String(node.icon_type || '').includes('SHORTS')) return;
            visit(node.contents || node.content || node.items);
            if (typeof node.continuation === 'string' && node.continuation) {
                continuation = node.continuation;
            }
            return;
        }
        const isLockup = node.type === 'LockupView';
        if (!isLockup && !['Video', 'GridVideo', 'CompactVideo'].includes(node.type)) return;
        if (isLockup && !['VIDEO', 'MOVIE'].includes(node.content_type)) return;
        try {
            if (isHistoryShort(node) || node.endpoint?.metadata?.url?.startsWith('/shorts/')) return;
            const id = historyVideoId(node);
            const title = historyVideoTitle(node);
            if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{11}$/.test(id) || !title || seen.has(id)) return;
            const metadataRows = node.metadata?.metadata?.metadata_rows || [];
            const metadataText = metadataRows.flatMap(row =>
                (row.metadata_parts || []).map(part => textValue(part.text)).filter(Boolean)
            );
            const published = subscriptionsPublishedTime(node);
            const author = textValue(node.author?.name) ||
                textValue(node.short_byline_text || node.long_byline_text || node.byline_text) ||
                (isLockup ? historyMetadataText(node, 0, 0) : '');
            seen.add(id);
            videos.push({
                id,
                title,
                author,
                url: `https://www.youtube.com/watch?v=${id}`,
                published_time: published,
                is_live: isHistoryLive(node),
                metadata_text: metadataText
            });
        } catch {
            // A malformed entry must not discard otherwise usable page entries.
        }
    };

    visit(page?.contents);
    visit(page?.continuation_contents);
    visit(page?.on_response_received_actions);
    visit(page?.on_response_received_commands);
    visit(page?.on_response_received_endpoints);
    if (!hasBody) throw new Error('Invalid subscriptions response');
    return { videos, continuation };
}

async function handleGetSubscriptionsFeed(params, client = null) {
    // The optional client is an offline-test seam, not a JSON-RPC parameter.
    // Every failure crossing the RPC boundary is generic: upstream exceptions
    // can contain request headers, cookie values or private response bodies.
    try {
        if (typeof params?.cookiesPath !== 'string' || !params.cookiesPath.trim()) {
            throw new Error('Cookies required');
        }
        const token = params.continuationToken;
        if (token != null && (typeof token !== 'string' || !token.trim())) {
            throw new Error('Invalid continuation');
        }
        const yt = client || await getYT(params.cookiesPath, params.location);
        if (yt.session?.logged_in !== true) throw new Error('Authentication required');
        let page;
        if (token) {
            page = await yt.actions.execute('/browse', { continuation: token, parse: true });
        } else {
            // getSubscriptionsFeed targets FEsubscriptions (not FEwhat_to_watch).
            // Its main timeline is the ordering authority; embedded ranked
            // shelves are excluded by subscriptionsPageResponse.
            const feed = await yt.getSubscriptionsFeed();
            page = feed.page;
        }
        return subscriptionsPageResponse(page);
    } catch {
        throw new Error('Unable to fetch subscriptions feed');
    }
}

async function handleGetSubscribedChannels(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required for subscriptions");
    }
    const yt = await getYT(params.cookiesPath, params.location);
    if (!yt.session.logged_in) {
        throw new Error("Not logged in with provided cookies");
    }

    const channels = [];
    const seen = new Set();

    const push = (id, name, subscribers) => {
        if (!id || !name) return;
        if (seen.has(id)) return;
        seen.add(id);
        const url = String(id).startsWith('@')
            ? `https://www.youtube.com/${id}`
            : `https://www.youtube.com/channel/${id}`;
        channels.push({ id, name, subscribers: subscribers || '', url });
    };

    const extractFromFeed = (feed) => {
        if (!feed) return;
        // Classic responses carry GridChannel renderers.
        const gridChannels = feed.memo?.getType ? feed.memo.getType(YTNodes.GridChannel) : [];
        for (const c of gridChannels) {
            push(c.id || c.author?.id, textValue(c.author?.name), textValue(c.subscribers));
        }

        // Direct channel renderers if present
        if (YTNodes.Channel) {
            const direct = feed.memo?.getType ? feed.memo.getType(YTNodes.Channel) : [];
            for (const c of direct) {
                push(c.id || c.author?.id, textValue(c.author?.name || c.title), textValue(c.subscribers || c.subscriber_count));
            }
        }

        // Newer responses use lockup view models for channel entries.
        const lockups = feed.memo?.getType ? feed.memo.getType(YTNodes.LockupView) : [];
        for (const l of lockups) {
            const id = l.contentId;
            const meta = l.metadata?.lockupMetadataViewModel;
            const name = textValue(meta?.title);
            let subscribers = '';
            const rows = meta?.metadata?.contentMetadataViewModel?.metadataRows || [];
            for (const row of rows) {
                for (const part of (row.metadataParts || [])) {
                    const t = textValue(part?.text);
                    if (t && /subscribers|subscribes|مشترك/i.test(t)) {
                        subscribers = t;
                    }
                }
            }
            push(id, name, subscribers);
        }
    };

    let feed = null;
    if (typeof yt.getChannelsFeed === 'function') {
        try {
            feed = await yt.getChannelsFeed();
            extractFromFeed(feed);
        } catch {
            // fallback
        }
    }

    if (channels.length === 0) {
        try {
            feed = await yt.getSubscriptionsFeed();
            extractFromFeed(feed);
        } catch {
            // ignore
        }
    }

    return { channels };
}

async function handleGetMix(params) {
    if (!params.cookiesPath) {
        throw new Error("Cookies path is required for Mixes");
    }
    const yt = await getYT(params.cookiesPath, params.location);

    const playlistId = params.playlistId;
    if (!playlistId) {
        throw new Error("playlistId is required for Mix");
    }

    // Determine the seed video the mix is anchored to. The caller may provide
    // one (the last played track, when growing the queue, or the &list= URL's
    // videoId). It is OPTIONAL: the watch-next /next endpoint accepts a mix
    // playlistId on its own and seeds the panel from the mix's first item.
    // NOTE: mixes are NOT viewable via getPlaylist ("This playlist type is
    // unviewable"), so we must never seed through it.
    let seedId = params.videoId || null;
    // For classic "RD<videoId>" radio mixes the seed video id is encoded in the
    // playlist id itself; recover it as a hint when the caller gave none.
    if (!seedId && /^RD[\w-]{11}$/.test(playlistId)) {
        seedId = playlistId.slice(2);
    }

    // The mix queue lives in the watch-next response's playlist panel. Mixes
    // are infinite: re-requesting with the last played video as the seed
    // returns the next window (mirrors how the Shorts feed is extended).
    const nextPayload = {
        playlistId: playlistId,
        racyCheckOk: true,
        contentCheckOk: true
    };
    if (seedId) nextPayload.videoId = seedId;
    const response = await yt.actions.execute('/next', nextPayload);

    const data = response.data || {};
    const panel = data?.contents?.twoColumnWatchNextResults?.playlist?.playlist || null;

    const videos = [];
    const seen = new Set();
    const mixTitle = textValue(panel?.title) || 'Mix';

    const pushItem = (renderer) => {
        if (!renderer) return;
        const id = renderer.videoId;
        if (!id || seen.has(id)) return;
        const title = textValue(renderer.title) || `Video (${id})`;
        const author = textValue(renderer.longBylineText || renderer.shortBylineText) || 'Unknown';
        seen.add(id);
        videos.push({
            id,
            title,
            author,
            url: `https://www.youtube.com/watch?v=${id}`
        });
    };

    let continuation = null;
    if (panel && Array.isArray(panel.contents)) {
        for (const entry of panel.contents) {
            if (entry.playlistPanelVideoRenderer) {
                pushItem(entry.playlistPanelVideoRenderer);
            } else if (entry.continuationItemRenderer) {
                continuation = entry.continuationItemRenderer?.continuationEndpoint?.continuationCommand?.token || continuation;
            }
        }
        const cont = panel.continuations?.[0]?.nextContinuationData?.continuation
            || panel.continuations?.[0]?.reloadContinuationData?.continuation;
        if (cont) continuation = cont;
    }

    // Fallback: some mixes surface via the generic watch-next feed rather than
    // a playlist panel. Seed from that so the queue is never empty. Requires a
    // seed video; skipped when the mix was opened from the playlistId alone.
    if (videos.length === 0 && seedId) {
        try {
            const info = await yt.getInfo(seedId);
            const feed = info.watch_next_feed || [];
            for (const item of feed) {
                const vid = item.payload?.videoId || item.video_id || item.id;
                if (vid && !seen.has(vid)) {
                    seen.add(vid);
                    const title = textValue(item.payload?.title || item.title) || `Video (${vid})`;
                    const author = textValue(item.payload?.author || item.author) || 'Unknown';
                    videos.push({
                        id: vid,
                        title,
                        author,
                        url: `https://www.youtube.com/watch?v=${vid}`
                    });
                }
            }
        } catch (e) {
            // ignore - empty result handled by caller
        }
    }

    return { videos, playlistId, mixTitle, continuation: continuation || null };
}

async function handleUpdateWatchHistory(params) {
    if (!params.cookiesPath || !params.videoId) {
        throw new Error("videoId and cookiesPath are required for watch history");
    }
    const yt = await getYT(params.cookiesPath, params.location);
    const info = await yt.getInfo(params.videoId);
    await info.addToWatchHistory();
    const watchedSeconds = parseFloat(params.watchedSeconds || '0');
    if (watchedSeconds > 0) {
        await info.updateWatchTime(watchedSeconds);
    }
    return { success: true };
}

async function* getStdinLines() {
    if (typeof tjs !== 'undefined' && tjs.stdin) {
        const reader = tjs.stdin.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split('\n');
            buf = parts.pop();
            for (const p of parts) yield p;
        }
        if (buf.trim()) yield buf;
    } else if (typeof Deno !== 'undefined' && Deno.stdin) {
        const reader = Deno.stdin.readable.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split('\n');
            buf = parts.pop();
            for (const p of parts) yield p;
        }
        if (buf.trim()) yield buf;
    }
}

async function main() {
    for await (const line of getStdinLines()) {
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
            } else if (command === 'update_watch_history') {
                result = await handleUpdateWatchHistory(params);
            } else if (command === 'like_video') {
                result = await handleLikeInteraction(params);
            } else if (command === 'get_video_likes') {
                result = await handleGetVideoLikes(params);
            } else if (command === 'get_video_chapters') {
                result = await handleGetVideoChapters(params);
            } else if (command === 'get_video_comments') {
                result = await handleGetVideoComments(params);
            } else if (command === 'get_comment_replies') {
                result = await handleGetCommentReplies(params);
            } else if (command === 'post_video_comment') {
                result = await handlePostVideoComment(params);
            } else if (command === 'like_comment') {
                result = await handleLikeComment(params);
            } else if (command === 'reply_to_comment') {
                result = await handleReplyComment(params);
            } else if (command === 'get_playlist') {
                result = await handleGetPlaylist(params);
            } else if (command === 'get_shorts_feed') {
                result = await handleGetShortsFeed(params);
            } else if (command === 'get_subscriptions_feed') {
                result = await handleGetSubscriptionsFeed(params);
            } else if (command === 'get_subscribed_channels') {
                result = await handleGetSubscribedChannels(params);
            } else if (command === 'get_mix') {
                result = await handleGetMix(params);
            } else {
                throw new Error(`Unknown command: ${command}`);
            }
            console.log(JSON.stringify({ id, result }));
        } catch (error) {
            console.log(JSON.stringify({ id, error: error.message }));
        }
    }
}

export {
    commentsPageResponse,
    extractChapters,
    extractLikeInfo,
    handleGetShortsFeed,
    handleGetSubscribedChannels,
    handleGetSubscriptionsFeed,
    handleLikeComment,
    handleLikeInteraction,
    handleReplyComment,
    handleUpdateWatchHistory,
    normalizeChapter,
    normalizeComment,
    normalizeCommentThreads,
    normalizeReplyComments,
    parseCount
};

const SERVICE_VERSION = "1.0.0";

const exitService = (code = 0) => {
    if (typeof Deno !== 'undefined' && Deno.exit) {
        Deno.exit(code);
    } else if (typeof tjs !== 'undefined' && tjs.exit) {
        tjs.exit(code);
    } else if (typeof process !== 'undefined' && process.exit) {
        process.exit(code);
    }
};

const isMainExecution = (typeof Deno !== 'undefined' && import.meta.main) || (typeof tjs !== 'undefined');
if (isMainExecution) {
    const rawArgs = typeof Deno !== 'undefined' ? (Deno.args || []) : (typeof tjs !== 'undefined' ? (tjs.args || []) : (typeof process !== 'undefined' ? process.argv.slice(2) : []));
    if (rawArgs.some(arg => arg === '--version' || arg === '-v')) {
        console.log(`youtube_service ${SERVICE_VERSION}`);
        exitService(0);
    } else if (rawArgs.some(arg => arg === '--help' || arg === '-h')) {
        console.log(`HexPlayer YouTube Service v${SERVICE_VERSION}\nUsage: youtube_service [options]\n\nOptions:\n  -v, --version  Show version\n  -h, --help     Show help`);
        exitService(0);
    } else {
        main().catch(err => {
            console.error(JSON.stringify({ error: err.message }));
            exitService(1);
        });
    }
}



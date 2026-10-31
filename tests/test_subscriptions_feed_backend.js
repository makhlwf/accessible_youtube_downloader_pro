import { Innertube, Parser } from 'youtubei.js';
import { handleGetSubscriptionsFeed } from '../src/service.js';

// Same offline Deno.test/fake-client pattern as src/service_test.js. The Python
// suite also runs these fixtures via Node against the installed build dependency.
function assertEquals(actual, expected) {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
        throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

const cookieParams = { cookiesPath: 'offline-cookies.txt', location: 'LY' };
const ids = ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc', 'ddddddddddd'];

function legacy(id, published = 'قبل يومين', kind = 'videoRenderer') {
    return { [kind]: {
        videoId: id,
        title: { simpleText: `Video ${id}` },
        ownerText: { simpleText: 'Legacy author' },
        shortBylineText: { simpleText: 'Legacy author' },
        longBylineText: { simpleText: 'Legacy author' },
        publishedTimeText: { simpleText: published },
        thumbnail: { thumbnails: [] },
        thumbnailOverlays: [],
        navigationEndpoint: { watchEndpoint: { videoId: id } }
    } };
}

function lockup(id, published = 'vor 3 Stunden', contentType = 'VIDEO') {
    return { lockupViewModel: {
        contentId: id,
        contentType: `LOCKUP_CONTENT_TYPE_${contentType}`,
        rendererContext: { commandContext: {
            onTap: { innertubeCommand: { watchEndpoint: { videoId: id } } }
        } },
        metadata: { lockupMetadataViewModel: {
            title: { content: `Lockup ${id}` },
            metadata: { contentMetadataViewModel: {
                metadataRows: [
                    { metadataParts: [{ text: { content: 'Modern author' } }] },
                    { metadataParts: [
                        { text: { content: '1.234 Aufrufe' } },
                        { text: { content: published } }
                    ] }
                ]
            } }
        } }
    } };
}

function more(token, modern = false) {
    const command = { continuationCommand: {
        token, request: 'CONTINUATION_REQUEST_TYPE_BROWSE'
    } };
    return modern
        ? { continuationItemViewModel: { continuationCommand: command } }
        : { continuationItemRenderer: { continuationEndpoint: command } };
}

function initial(items) {
    return { contents: { twoColumnBrowseResultsRenderer: { tabs: [
        { tabRenderer: { selected: false, content: {
            richGridRenderer: { contents: [legacy('ignored0000'), more('wrong-tab')] }
        } } },
        { tabRenderer: { selected: true, content: { richGridRenderer: {
            header: more('header-token'),
            contents: items.map(item => item.richSectionRenderer ? item : ({ richItemRenderer: { content: item } }))
        } } } }
    ], secondaryContents: { sectionListRenderer: {
        contents: [{ itemSectionRenderer: { contents: [legacy('sidebar0000'), more('sidebar')] } }]
    } } } } };
}

function continuation(items, field = 'onResponseReceivedActions', reload = false) {
    return { [field]: [{ [reload ? 'reloadContinuationItemsCommand' : 'appendContinuationItemsAction']: {
        targetId: 'browse-feed', continuationItems: items
    } }] };
}

function clientFor(pages) {
    const calls = [];
    // Exercise the actual library's FEsubscriptions method and parser, not a
    // hand-rolled feed.videos mock (which would hide renderer grouping bugs).
    const client = new Innertube({ logged_in: true, actions: {
        execute: async (endpoint, payload) => {
            calls.push({ endpoint, payload });
            const raw = pages.shift();
            if (!raw) throw new Error('No fixture page');
            return Parser.parseResponse(raw);
        }
    } });
    return { client, calls };
}

Deno.test('subscriptions preserve mixed renderer chronology, publication text and body token', async () => {
    const { client, calls } = clientFor([initial([
        lockup(ids[0]),
        legacy(ids[1]),
        lockup(ids[0], 'duplicate'),
        lockup('PLnot-a-video', '', 'PLAYLIST'),
        lockup(ids[2], '', 'SHORT'),
        lockup('invalid-id'),
        legacy(ids[2], '2 days ago', 'gridVideoRenderer'),
        legacy(ids[3], '1 day ago', 'compactVideoRenderer'),
        more('page-2')
    ])]);
    const result = await handleGetSubscriptionsFeed(cookieParams, client);
    assertEquals(result.videos.map(video => video.id), ids);
    assertEquals(result.videos.map(video => video.published_time), [
        'vor 3 Stunden', 'قبل يومين', '2 days ago', '1 day ago'
    ]);
    assertEquals(result.videos[0].author, 'Modern author');
    assertEquals(result.videos[1].author, 'Legacy author');
    assertEquals(result.videos[0].url, `https://www.youtube.com/watch?v=${ids[0]}`);
    assertEquals(result.videos[0].metadata_text, ['Modern author', '1.234 Aufrufe', 'vor 3 Stunden']);
    assertEquals(result.continuation, 'page-2');
    assertEquals(calls.length, 1);
    assertEquals(calls[0].endpoint, 'browse');
    assertEquals(calls[0].payload.browseId, 'FEsubscriptions');
    assertEquals(calls[0].payload.parse, true);
});

Deno.test('subscriptions continuation fetches exactly the supplied token, without restarting feed', async () => {
    for (const field of ['onResponseReceivedActions', 'onResponseReceivedCommands', 'onResponseReceivedEndpoints']) {
        const { client, calls } = clientFor([
            continuation([lockup(ids[0]), legacy(ids[1]), more('last-page', true)], field),
            continuation([legacy(ids[2])], field, true)
        ]);
        const first = await handleGetSubscriptionsFeed({ ...cookieParams, continuationToken: 'opaque+/=' }, client);
        assertEquals(first.videos.map(video => video.id), ids.slice(0, 2));
        assertEquals(first.continuation, 'last-page');
        const last = await handleGetSubscriptionsFeed({ ...cookieParams, continuationToken: first.continuation }, client);
        assertEquals(last.videos.map(video => video.id), [ids[2]]);
        assertEquals(last.continuation, null);
        assertEquals(calls, [
            { endpoint: '/browse', payload: { continuation: 'opaque+/=', parse: true } },
            { endpoint: '/browse', payload: { continuation: 'last-page', parse: true } }
        ]);
    }
});

Deno.test('subscriptions preserve continuation on empty video pages and exclude nested posts', async () => {
    const { client } = clientFor([initial([
        lockup(ids[0], '', 'SHORT'),
        more('next-video-page')
    ])]);
    assertEquals(await handleGetSubscriptionsFeed(cookieParams, client), {
        videos: [], continuation: 'next-video-page'
    });
    const fake = { session: { logged_in: true }, getSubscriptionsFeed: async () => ({ page: {
        contents: { type: 'SectionList', contents: [
            { type: 'BackstagePost', content: { type: 'Video', id: ids[0], title: 'Embedded video' } },
            { type: 'ReelShelf', contents: [{ type: 'Video', id: ids[1], title: 'Short' }] }
        ] }
    } }) };
    assertEquals(await handleGetSubscriptionsFeed(cookieParams, fake), { videos: [], continuation: null });
});

Deno.test('subscriptions require cookies and logged_in and redact every failure', async () => {
    let called = false;
    const getSubscriptionsFeed = async () => { called = true; throw new Error('SAPISID=secret'); };
    for (const [params, client] of [
        [{}, { session: { logged_in: true }, getSubscriptionsFeed }],
        [cookieParams, { session: { logged_in: false }, getSubscriptionsFeed }],
        [{ ...cookieParams, continuationToken: {} }, { session: { logged_in: true }, getSubscriptionsFeed }]
    ]) {
        try {
            await handleGetSubscriptionsFeed(params, client);
            throw new Error('Expected authentication/validation failure');
        } catch (error) {
            assertEquals(error.message, 'Unable to fetch subscriptions feed');
        }
    }
    assertEquals(called, false);
    for (const getSubscriptionsFeed of [
        async () => { throw new Error('SAPISID=secret'); },
        async () => ({ page: {} }),
        async () => null
    ]) {
        try {
            await handleGetSubscriptionsFeed(cookieParams, { session: { logged_in: true }, getSubscriptionsFeed });
            throw new Error('Expected sanitized failure');
        } catch (error) {
            assertEquals(error.message, 'Unable to fetch subscriptions feed');
        }
    }
});

Deno.test('subscriptions support legacy continuation containers without losing order', async () => {
    for (const kind of ['itemSectionContinuation', 'sectionListContinuation', 'gridContinuation']) {
        const contentsKey = kind === 'gridContinuation' ? 'items' : 'contents';
        const { client, calls } = clientFor([{ continuationContents: { [kind]: {
            [contentsKey]: [lockup(ids[0]), legacy(ids[1])],
            continuations: [{ nextContinuationData: { continuation: 'next-legacy-page' } }]
        } } }]);
        const result = await handleGetSubscriptionsFeed({ ...cookieParams, continuationToken: 'legacy-page' }, client);
        assertEquals(result.videos.map(video => video.id), ids.slice(0, 2));
        assertEquals(result.continuation, 'next-legacy-page');
        assertEquals(calls.length, 1);
    }
});

Deno.test('subscriptions accept explicit empty messages and do not invent publication times', async () => {
    const { client } = clientFor([{ contents: {
        messageRenderer: { text: { simpleText: 'No subscriptions yet' } }
    } }]);
    assertEquals(await handleGetSubscriptionsFeed(cookieParams, client), { videos: [], continuation: null });
    const undated = lockup(ids[0], '');
    const modernMetadata = undated.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel;
    modernMetadata.metadataRows.pop();
    const short = legacy(ids[1]);
    short.videoRenderer.navigationEndpoint.commandMetadata = { webCommandMetadata: { url: `/shorts/${ids[1]}` } };
    const { client: undatedClient } = clientFor([initial([undated, short])]);
    const result = await handleGetSubscriptionsFeed(cookieParams, undatedClient);
    assertEquals(result.videos.length, 1);
    assertEquals(result.videos[0].published_time, '');
    assertEquals(Object.hasOwn(result.videos[0], 'timestamp'), false);
});

Deno.test('subscriptions retain publication time in the single-row list layout', async () => {
    // Live FEsubscriptions list layout: author, views and publication are parts
    // of ONE metadata row, not an author row followed by a views/date row.
    const item = lockup(ids[0], '3 hours ago');
    const metadata = item.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel;
    metadata.metadataRows = [{ metadataParts: metadata.metadataRows.flatMap(row => row.metadataParts) }];
    const { client } = clientFor([initial([item])]);
    const result = await handleGetSubscriptionsFeed(cookieParams, client);
    assertEquals(result.videos[0].published_time, '3 hours ago');
    assertEquals(result.videos[0].author, 'Modern author');
});

Deno.test('subscriptions preserve localized publication qualifiers in both supported layouts', async () => {
    for (const published of ['قبل ٣ ساعات', 'تم بثه قبل ساعة واحدة', 'Premiered 2 days ago', 'Streamed 1 hour ago', 'vor 3 Stunden']) {
        for (const inline of [false, true]) {
            const item = lockup(ids[0], `  ${published}  `);
            const metadata = item.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel;
            if (inline) metadata.metadataRows = [{ metadataParts: metadata.metadataRows.flatMap(row => row.metadataParts) }];
            const { client } = clientFor([initial([item])]);
            const result = await handleGetSubscriptionsFeed(cookieParams, client);
            assertEquals(result.videos[0].published_time, published);
        }
    }
});

Deno.test('subscriptions do not announce counts, durations, blank or unknown layouts as publication times', async () => {
    for (const published of ['   ', '1.2K views', '١٢٣ مشاهدة', '1.234 Aufrufe', '12:30', '4K', 'LIVE', 'Premieres in 2 hours']) {
        const item = lockup(ids[0], published);
        const { client } = clientFor([initial([item])]);
        const result = await handleGetSubscriptionsFeed(cookieParams, client);
        assertEquals(result.videos.length, 1);
        assertEquals(result.videos[0].published_time, '');
    }
    for (const texts of [['Author', '1.2K views'], ['Author', '1.2K views', 'extra badge', '3 hours ago']]) {
        const item = lockup(ids[0]);
        item.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel.metadataRows = [
            { metadataParts: texts.map(content => ({ text: { content } })) }
        ];
        const { client } = clientFor([initial([item])]);
        assertEquals((await handleGetSubscriptionsFeed(cookieParams, client)).videos[0].published_time, '');
    }
    const { client } = clientFor([initial([legacy(ids[0], '   ')])]);
    assertEquals((await handleGetSubscriptionsFeed(cookieParams, client)).videos[0].published_time, '');
});

Deno.test('subscriptions recover single-row publication time on continuation without reordering', async () => {
    const item = lockup(ids[0], '2 hours ago');
    const metadata = item.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel;
    metadata.metadataRows = [{ metadataParts: metadata.metadataRows.flatMap(row => row.metadataParts) }];
    const { client } = clientFor([continuation([item, legacy(ids[1], '3 hours ago'), more('more-dates')])]);
    const result = await handleGetSubscriptionsFeed({ ...cookieParams, continuationToken: 'date-page' }, client);
    assertEquals(result.videos.map(video => [video.id, video.published_time]), [[ids[0], '2 hours ago'], [ids[1], '3 hours ago']]);
    assertEquals(result.continuation, 'more-dates');
});

Deno.test('subscriptions do not label upcoming premiere schedules as publication times', async () => {
    for (const published of ['Premieres tomorrow', 'Premiere Oct 31, 2100', 'سيبدأ العرض الأول غدًا', 'العرض الأول بعد ساعتين']) {
        for (const inline of [false, true]) {
            const item = lockup(ids[0], published);
            const metadata = item.lockupViewModel.metadata.lockupMetadataViewModel.metadata.contentMetadataViewModel;
            if (inline) metadata.metadataRows = [{ metadataParts: metadata.metadataRows.flatMap(row => row.metadataParts) }];
            const { client } = clientFor([initial([item])]);
            const result = await handleGetSubscriptionsFeed(cookieParams, client);
            assertEquals(result.videos[0].published_time, '');
            assertEquals(result.videos[0].id, ids[0]);
        }
    }
    // Prefer the parser's explicit upcoming state over guessing localized text.
    const upcoming = legacy(ids[0], '31. Oktober 2100');
    upcoming.videoRenderer.upcomingEventData = { startTime: '4128624000' };
    const { client } = clientFor([initial([upcoming])]);
    assertEquals((await handleGetSubscriptionsFeed(cookieParams, client)).videos[0].published_time, '');
});

function rankedShelf(title, items) {
    return { richSectionRenderer: { content: { richShelfRenderer: {
        title: { simpleText: title },
        contents: items.map(item => ({ richItemRenderer: { content: item } }))
    } } } };
}

Deno.test('subscriptions exclude ranked shelves before deduplication to preserve timeline order', async () => {
    for (const title of ['Most relevant', 'الأكثر صلة', 'Relevanteste', 'Unrecognized localized shelf']) {
        const { client, calls } = clientFor([
            initial([
                lockup(ids[0], '6h ago'),
                rankedShelf(title, [legacy(ids[2], '13h ago'), legacy(ids[3], '4d ago'), more('shelf-page')]),
                legacy(ids[1], '7h ago'),
                lockup(ids[2], '13h ago'),
                more('timeline-page')
            ]),
            continuation([
                legacy(ids[3], '4d ago'),
                more('next-timeline-page'),
                rankedShelf(title, [lockup(ids[0], '6h ago'), more('wrong-shelf-page')])
            ])
        ]);
        const first = await handleGetSubscriptionsFeed(cookieParams, client);
        assertEquals(first.videos.map(video => [video.id, video.published_time]), [
            [ids[0], '6h ago'], [ids[1], '7h ago'], [ids[2], '13h ago']
        ]);
        assertEquals(first.continuation, 'timeline-page');
        const second = await handleGetSubscriptionsFeed({ ...cookieParams, continuationToken: first.continuation }, client);
        assertEquals(second.videos.map(video => video.id), [ids[3]]);
        assertEquals(second.continuation, 'next-timeline-page');
        assertEquals(calls.length, 2);
        assertEquals(calls[1].payload.continuation, 'timeline-page');
    }
});

Deno.test('subscriptions keep only main continuation on recommendation-only pages', async () => {
    const { client } = clientFor([initial([
        more('next-main-page'),
        rankedShelf('Most relevant', [legacy(ids[0]), more('ranked-page')])
    ])]);
    assertEquals(await handleGetSubscriptionsFeed(cookieParams, client), {
        videos: [], continuation: 'next-main-page'
    });
});

Deno.test('subscriptions keep replay publication order rather than sorting streamed age labels', async () => {
    // A replay may be published later than its stream ended. FEsubscriptions'
    // main position is authoritative; its displayed stream age is not a sort key.
    const { client } = clientFor([initial([
        legacy(ids[0], '8h ago'),
        lockup(ids[1], 'Streamed 12h ago'),
        legacy(ids[2], '9h ago'),
        lockup(ids[3], '')
    ])]);
    const result = await handleGetSubscriptionsFeed(cookieParams, client);
    assertEquals(result.videos.map(video => video.id), ids);
    assertEquals(result.videos.map(video => video.published_time), ['8h ago', 'Streamed 12h ago', '9h ago', '']);
});

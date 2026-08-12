import {
    commentsPageResponse,
    extractChapters,
    extractLikeInfo,
    handleGetShortsFeed,
    handleLikeComment,
    handleReplyComment,
    normalizeComment,
    normalizeReplyComments,
    parseCount
} from './service.js';

function assertEquals(actual, expected) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) {
        throw new Error(`Expected ${expectedJson}, got ${actualJson}`);
    }
}

Deno.test('parseCount handles exact and compact counts', () => {
    assertEquals(parseCount('1,234 likes'), 1234);
    assertEquals(parseCount('1.2K'), 1200);
    assertEquals(parseCount(Number.NaN), null);
});

Deno.test('extractLikeInfo reads segmented dislike state', () => {
    const info = {
        basic_info: {},
        primary_info: {
            menu: {
                top_level_buttons: [
                    {
                        type: 'SegmentedLikeDislikeButtonView',
                        short_like_count: '1.2K',
                        like_button: {
                            like_status_entity: {
                                like_status: 'DISLIKE'
                            }
                        },
                        dislike_button: {}
                    }
                ]
            }
        }
    };

    assertEquals(extractLikeInfo(info), {
        likes: 1200,
        is_liked: false,
        is_disliked: true,
        rating: 'dislike'
    });
});

Deno.test('extractChapters normalizes marker chapters', () => {
    const info = {
        player_overlays: {
            decorated_player_bar: {
                player_bar: {
                    markers_map: [
                        {
                            marker_key: 'MARKERS_KEY_CHAPTERS',
                            value: {
                                chapters: [
                                    {
                                        title: { toString: () => 'Intro' },
                                        time_range_start_millis: '0'
                                    },
                                    {
                                        title: { runs: [{ text: 'Part two' }] },
                                        startMillis: '60000'
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
    };

    assertEquals(extractChapters(info), [
        { title: 'Intro', time_ms: 0 },
        { title: 'Part two', time_ms: 60000 }
    ]);
});

Deno.test('normalizeComment includes author, metadata, is_liked, is_disliked, and reply token', () => {
    const comment = normalizeComment(
        {
            comment_id: 'comment-1',
            author: { name: 'User One' },
            content: { toString: () => 'Nice video' },
            published_time: '2 days ago',
            like_count: '7',
            reply_count: '3',
            is_liked: true
        },
        { has_replies: true }
    );

    if (!comment.reply_token) {
        throw new Error('Expected reply token for comment with replies');
    }
    delete comment.reply_token;

    assertEquals(comment, {
        id: 'comment-1',
        parent_id: '',
        author: 'User One',
        content: 'Nice video',
        published_time: '2 days ago',
        likes: 7,
        replies: 3,
        has_replies: true,
        is_liked: true,
        is_disliked: false
    });

    const dislikedComment = normalizeComment({
        comment_id: 'comment-disliked',
        vote: 'DISLIKE'
    });
    assertEquals(dislikedComment.is_liked, false);
    assertEquals(dislikedComment.is_disliked, true);
});

Deno.test('commentsPageResponse normalizes comment threads and includes is_disabled', () => {
    const page = {
        has_continuation: false,
        is_disabled: false,
        contents: [
            {
                has_replies: false,
                comment: {
                    comment_id: 'comment-2',
                    author: { name: 'User Two' },
                    content: { toString: () => 'Thanks' },
                    published_time: '1 hour ago',
                    like_count: '0',
                    reply_count: '0'
                }
            }
        ]
    };

    assertEquals(commentsPageResponse(page), {
        comments: [
            {
                id: 'comment-2',
                parent_id: '',
                author: 'User Two',
                content: 'Thanks',
                published_time: '1 hour ago',
                likes: 0,
                replies: 0,
                has_replies: false,
                reply_token: null,
                is_liked: false,
                is_disliked: false
            }
        ],
        continuation: null,
        is_disabled: false
    });

    const disabledPage = {
        header: { comments_disabled: true },
        contents: []
    };
    assertEquals(commentsPageResponse(disabledPage).is_disabled, true);
});

Deno.test('normalizeReplyComments normalizes reply comments without reply tokens', () => {
    assertEquals(
        normalizeReplyComments([
            {
                comment_id: 'reply-1',
                author: { name: 'Reply User' },
                content: { toString: () => 'A reply' },
                published_time: 'now',
                like_count: '2',
                reply_count: '0',
                vote: 'LIKE'
            }
        ]),
        [
            {
                id: 'reply-1',
                parent_id: '',
                author: 'Reply User',
                content: 'A reply',
                published_time: 'now',
                likes: 2,
                replies: 0,
                has_replies: false,
                reply_token: null,
                is_liked: true,
                is_disliked: false
            }
        ]
    );
});

Deno.test('handleLikeInteraction routes actions to correct Innertube endpoints', async () => {
    const executed = [];
    const fakeYt = {
        session: { logged_in: true },
        actions: {
            execute: async (endpoint, payload) => {
                executed.push({ endpoint, payload });
                return { success: true, status_code: 200, data: {} };
            }
        }
    };

    const actionsMap = {
        like: 'like/like',
        dislike: 'like/dislike',
        remove_like: 'like/removelike'
    };

    for (const [action, expectedEndpoint] of Object.entries(actionsMap)) {
        const endpoint = action === 'like' ? 'like/like' : action === 'dislike' ? 'like/dislike' : 'like/removelike';
        const res = await fakeYt.actions.execute(endpoint, { target: { videoId: 'VIDEO_123' } });
        assertEquals(res.success, true);
    }

    assertEquals(executed, [
        { endpoint: 'like/like', payload: { target: { videoId: 'VIDEO_123' } } },
        { endpoint: 'like/dislike', payload: { target: { videoId: 'VIDEO_123' } } },
        { endpoint: 'like/removelike', payload: { target: { videoId: 'VIDEO_123' } } }
    ]);
});

Deno.test('handleLikeComment calls perform_comment_action with correct endpoint action', async () => {
    const executed = [];
    const fakeYt = {
        session: { logged_in: true },
        actions: {
            execute: async (endpoint, payload) => {
                executed.push({ endpoint, payload });
                return { success: true, status_code: 200, data: {} };
            }
        }
    };

    const actionsMap = {
        like: 'LIKE',
        dislike: 'DISLIKE',
        remove_like: 'INDIFFERENT'
    };

    for (const [action] of Object.entries(actionsMap)) {
        const res = await handleLikeComment({
            ytClient: fakeYt,
            commentId: 'COMMENT_456',
            action: action
        });
        assertEquals(res.success, true);
    }

    assertEquals(executed, [
        { endpoint: 'comment/perform_comment_action', payload: { action: 'LIKE', commentId: 'COMMENT_456' } },
        { endpoint: 'comment/perform_comment_action', payload: { action: 'DISLIKE', commentId: 'COMMENT_456' } },
        { endpoint: 'comment/perform_comment_action', payload: { action: 'INDIFFERENT', commentId: 'COMMENT_456' } }
    ]);
});

Deno.test('handleReplyComment calls create_comment_reply with commentId and trimmed commentText', async () => {
    const executed = [];
    const fakeYt = {
        session: { logged_in: true },
        actions: {
            execute: async (endpoint, payload) => {
                executed.push({ endpoint, payload });
                return { success: true, status_code: 200, data: {} };
            }
        }
    };

    const res = await handleReplyComment({
        ytClient: fakeYt,
        commentId: 'COMMENT_789',
        text: 'Nice reply!'
    });
    assertEquals(res.success, true);

    assertEquals(executed, [
        { endpoint: 'comment/create_comment_reply', payload: { commentId: 'COMMENT_789', commentText: 'Nice reply!' } }
    ]);
});

Deno.test('handleGetShortsFeed throws error if cookies path is missing', async () => {
    let threw = false;
    try {
        await handleGetShortsFeed({});
    } catch (e) {
        threw = true;
        assertEquals(e.message, 'Cookies path is required for Shorts');
    }
    assertEquals(threw, true);
});



import {
    commentsPageResponse,
    extractChapters,
    extractLikeInfo,
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

Deno.test('normalizeComment includes author, metadata, and reply token', () => {
    const comment = normalizeComment(
        {
            comment_id: 'comment-1',
            author: { name: 'User One' },
            content: { toString: () => 'Nice video' },
            published_time: '2 days ago',
            like_count: '7',
            reply_count: '3'
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
        has_replies: true
    });
});

Deno.test('commentsPageResponse normalizes comment threads', () => {
    const page = {
        has_continuation: false,
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
                reply_token: null
            }
        ],
        continuation: null
    });
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
                reply_count: '0'
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
                reply_token: null
            }
        ]
    );
});

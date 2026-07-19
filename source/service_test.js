import { extractChapters, extractLikeInfo, parseCount } from './service.js';

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

// QuickJS / txiki.js polyfills for YouTube.js compatibility

if (typeof globalThis.Intl === 'undefined') {
    globalThis.Intl = {
        DateTimeFormat: () => ({
            resolvedOptions: () => ({ timeZone: 'UTC' })
        })
    };
}

const _nativeFetch = globalThis.fetch;
if (_nativeFetch) {
    globalThis.fetch = function(input, init) {
        if (input instanceof URL || (input && typeof input.href === 'string')) {
            input = input.toString();
        }
        return _nativeFetch(input, init);
    };
}
